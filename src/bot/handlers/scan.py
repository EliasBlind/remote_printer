import asyncio
import logging
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, InputMediaDocument, Message, User

from ...services.config import Config
from ...services.db import DB
from ...services.scanning import Scanner
from ...services.shell import DeviceError
from .. import keyboards, texts, views
from ..keyboards import ScanCb
from ..states import ScanStates
from ..utils import callback_message, edit_message

log = logging.getLogger(__name__)
router = Router(name="scan")


@router.message(Command("scan"))
@router.message(F.text == texts.BTN_SCAN)
async def scan_menu(message: Message, state: FSMContext, scanner: Scanner) -> None:
    old = await state.get_data()
    Scanner.cleanup(old.get("pages", []))

    if scanner.busy:
        await message.answer(texts.SCAN_BUSY)
        return

    data = {"mode": views.DEFAULT_SCAN_MODE, "dpi": 300, "pages": []}
    await state.set_state(ScanStates.session)
    await state.set_data(data)
    text, kb = views.scan_settings(data)
    await message.answer(text, reply_markup=kb)


@router.callback_query(ScanStates.session, ScanCb.filter(F.action.in_({"mode", "dpi"})))
async def scan_settings(callback: CallbackQuery, callback_data: ScanCb, state: FSMContext) -> None:
    if callback_data.action == "mode" and callback_data.value in views.SCAN_MODES:
        data = await state.update_data(mode=callback_data.value)
    elif callback_data.action == "dpi" and callback_data.value.isdigit() and int(callback_data.value) in views.SCAN_DPIS:
        data = await state.update_data(dpi=int(callback_data.value))
    else:
        await callback.answer()
        return

    msg = callback_message(callback)
    if msg is not None:
        text, kb = views.scan_settings(data)
        await edit_message(msg, text, kb)
    await callback.answer()


@router.callback_query(ScanStates.session, ScanCb.filter(F.action == "scan"))
async def do_scan(callback: CallbackQuery, state: FSMContext, scanner: Scanner) -> None:
    msg = callback_message(callback)
    if msg is None:
        await callback.answer()
        return
    if scanner.busy:
        await callback.answer(texts.SCAN_BUSY, show_alert=True)
        return
    await callback.answer()

    data = await state.get_data()
    n = len(data["pages"]) + 1

    if msg.photo:
        await msg.edit_reply_markup(reply_markup=None)
        status = await msg.answer(texts.scanning(n))
    else:
        await edit_message(msg, texts.scanning(n))
        status = msg

    try:
        mode = data["mode"] if data["mode"] in views.SCAN_MODES else views.DEFAULT_SCAN_MODE
        page = await scanner.scan_page(views.SCAN_MODES[mode][0], data["dpi"])
        preview = await scanner.make_preview(page)
    except DeviceError as e:
        await edit_message(status, texts.scan_error(str(e)), keyboards.scan_retry_kb())
        return
    except Exception as e:
        log.exception("Сбой сканирования")
        await edit_message(status, texts.scan_error(f"{type(e).__name__}: {e}"), keyboards.scan_retry_kb())
        return

    pages = [*data["pages"], str(page)]
    await state.update_data(pages=pages)
    caption = texts.scan_page_done(len(pages))
    try:
        await status.answer_photo(FSInputFile(preview), caption=caption, reply_markup=keyboards.scan_session_kb())
    except TelegramAPIError:
        log.exception("Не удалось отправить превью, отправляю файлом")
        await status.answer_document(FSInputFile(page), caption=caption, reply_markup=keyboards.scan_session_kb())
    try:
        await status.delete()
    except TelegramAPIError:
        pass


@router.callback_query(ScanStates.session, ScanCb.filter(F.action.in_({"pdf", "jpg"})))
async def scan_finish(
    callback: CallbackQuery, callback_data: ScanCb, event_from_user: User,
    state: FSMContext, db: DB, cfg: Config,
) -> None:
    msg = callback_message(callback)
    data = await state.get_data()
    pages = [Path(p) for p in data.get("pages", [])]
    if msg is None or not pages:
        await callback.answer(texts.SCAN_NO_PAGES, show_alert=True)
        return

    await callback.answer(texts.SCAN_ASSEMBLING)
    await msg.edit_reply_markup(reply_markup=None)
    await state.clear()
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M")

    try:
        if callback_data.action == "pdf":
            await _send_pdf(msg, pages, data["dpi"], stamp, event_from_user.id, db, cfg)
        else:
            await _send_jpgs(msg, pages, stamp)
            await db.create_job(event_from_user.id, "scan", f"{len(pages)} × JPG", status="done")
            await msg.answer(texts.scan_ready(len(pages)))
    except Exception as e:
        log.exception("Не удалось отправить скан")
        await msg.answer(texts.scan_send_failed(str(e)))
    finally:
        Scanner.cleanup(pages)


async def _send_pdf(
    msg: Message, pages: list[Path], dpi: int, stamp: str, user_id: int, db: DB, cfg: Config
) -> None:
    name = f"scan_{stamp}.pdf"
    dst = cfg.scans / f"{uuid4().hex}.pdf"
    await asyncio.to_thread(Scanner.pages_to_pdf, pages, dst, dpi)
    job_id = await db.create_job(user_id, "scan", name, file_path=str(dst), status="done")
    await msg.answer_document(
        FSInputFile(dst, filename=name),
        caption=texts.scan_ready(len(pages)),
        reply_markup=keyboards.reprint_kb(job_id),
    )


async def _send_jpgs(msg: Message, pages: list[Path], stamp: str) -> None:
    files = [
        FSInputFile(p, filename=f"scan_{stamp}_{n}.jpg" if len(pages) > 1 else f"scan_{stamp}.jpg")
        for n, p in enumerate(pages, 1)
    ]
    for i in range(0, len(files), 10):
        chunk = files[i : i + 10]
        if len(chunk) == 1:
            await msg.answer_document(chunk[0])
        else:
            await msg.answer_media_group([InputMediaDocument(media=f) for f in chunk])


@router.callback_query(ScanStates.session, ScanCb.filter(F.action == "cancel"))
async def scan_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    Scanner.cleanup(data.get("pages", []))
    await state.clear()
    msg = callback_message(callback)
    if msg is not None:
        await edit_message(msg, texts.SCAN_CANCELLED)
    await callback.answer()


@router.callback_query(ScanCb.filter())
async def scan_expired(callback: CallbackQuery) -> None:
    await callback.answer(texts.SCAN_EXPIRED, show_alert=True)
