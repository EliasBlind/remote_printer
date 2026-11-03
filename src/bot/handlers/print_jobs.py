import logging
import mimetypes
from pathlib import Path

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Document, Message, PhotoSize, User

from ...services.config import Config
from ...services.db import DB
from ...services.printing import Printer, valid_pages
from .. import texts, views
from ..keyboards import PrintCb, ReprintCb
from ..states import PrintStates
from ..utils import callback_message, edit_message, safe_filename
from ..worker import PrintWorker

log = logging.getLogger(__name__)
router = Router(name="print")

MAX_DOWNLOAD = 20 * 1024 * 1024

EXTRA_MIME = {
    "image/heic": ".heic",
    "image/heif": ".heif",
    "image/avif": ".avif",
    "image/vnd.djvu": ".djvu",
    "application/epub+zip": ".epub",
    "application/x-fictionbook+xml": ".fb2",
    "text/markdown": ".md",
}


def with_extension(name: str, mime: str | None) -> str:
    if Path(name).suffix or not mime:
        return name
    ext = EXTRA_MIME.get(mime) or mimetypes.guess_extension(mime) or ""
    return name + ext


async def _accept_file(
    message: Message, user: User, bot: Bot, db: DB, cfg: Config,
    file: Document | PhotoSize, original_name: str, size: int | None,
) -> None:
    if size and size > MAX_DOWNLOAD:
        await message.reply(texts.TOO_BIG)
        return
    if not Printer.is_supported(original_name):
        await message.reply(texts.UNSUPPORTED)
        return

    job_id = await db.create_job(user.id, "print", original_name)
    card = await message.reply(texts.DOWNLOADING)
    dst = cfg.upload / f"{job_id}_{safe_filename(original_name)}"

    try:
        await bot.download(file, destination=dst)
    except Exception:
        log.exception("Не удалось скачать файл для задания %s", job_id)
        await db.set_status(job_id, "error", "Не удалось скачать файл")
        await card.edit_text(texts.DOWNLOAD_FAILED)
        return

    await db.update_job(job_id, file_path=str(dst), message_id=card.message_id)
    job = await db.get_job(job_id)
    assert job is not None
    text, kb = views.print_card(job, cfg)
    await card.edit_text(text, reply_markup=kb)


@router.message(F.document)
async def on_document(message: Message, event_from_user: User, bot: Bot, db: DB, cfg: Config) -> None:
    doc = message.document
    assert doc is not None
    await _accept_file(
        message, event_from_user, bot, db, cfg,
        doc, with_extension(doc.file_name or "document", doc.mime_type), doc.file_size,
    )


@router.message(F.photo)
async def on_photo(message: Message, event_from_user: User, bot: Bot, db: DB, cfg: Config) -> None:
    assert message.photo
    photo = message.photo[-1]
    await _accept_file(
        message, event_from_user, bot, db, cfg,
        photo, f"photo_{message.message_id}.jpg", photo.file_size,
    )


@router.callback_query(PrintCb.filter())
async def on_print_action(
    callback: CallbackQuery, callback_data: PrintCb, event_from_user: User,
    state: FSMContext, db: DB, cfg: Config, worker: PrintWorker,
) -> None:
    job = await db.get_job(callback_data.job_id)
    if job is None or job["user_id"] != event_from_user.id:
        await callback.answer(texts.JOB_NOT_FOUND, show_alert=True)
        return

    action, status, jid = callback_data.action, job["status"], job["id"]
    toast: str | None = None

    if action == "noop":
        await callback.answer()
        return

    if action in {"inc", "dec", "duplex", "pages", "pages_all", "go"} and status != "draft":
        await callback.answer(texts.JOB_LOCKED, show_alert=True)
        return

    if action == "inc":
        if job["copies"] >= cfg.max_copies:
            await callback.answer(texts.max_copies(cfg.max_copies))
            return
        await db.update_job(jid, copies=job["copies"] + 1)
    elif action == "dec":
        if job["copies"] <= 1:
            await callback.answer()
            return
        await db.update_job(jid, copies=job["copies"] - 1)
    elif action == "duplex":
        await db.update_job(jid, duplex=int(not job["duplex"]))
    elif action == "pages_all":
        await db.update_job(jid, pages=None)
    elif action == "pages":
        await state.set_state(PrintStates.pages)
        await state.update_data(job_id=jid)
        await callback.answer()
        msg = callback_message(callback)
        if msg is not None:
            await msg.answer(texts.ASK_PAGES)
        return
    elif action == "go":
        if not job["file_path"]:
            await callback.answer(texts.FILE_GONE, show_alert=True)
            return
        await db.set_status(jid, "queued")
        await worker.put(jid)
        toast = texts.TOAST_QUEUED
    elif action == "cancel":
        if status not in {"draft", "queued"}:
            await callback.answer(texts.CANNOT_CANCEL, show_alert=True)
            return
        await db.set_status(jid, "cancelled")
        toast = texts.TOAST_CANCELLED
    elif action == "retry":
        if status != "error" or not job["file_path"] or not Path(job["file_path"]).exists():
            await callback.answer(texts.FILE_GONE, show_alert=True)
            return
        await db.set_status(jid, "queued")
        await worker.put(jid)
        toast = texts.TOAST_RETRY

    msg = callback_message(callback)
    job = await db.get_job(jid)
    if msg is not None and job is not None:
        text, kb = views.print_card(job, cfg)
        await edit_message(msg, text, kb)
    await callback.answer(toast)


@router.message(PrintStates.pages, F.text)
async def on_pages_input(message: Message, state: FSMContext, bot: Bot, db: DB, cfg: Config) -> None:
    pages = (message.text or "").replace(" ", "")
    if not valid_pages(pages):
        await message.answer(texts.BAD_PAGES)
        return

    data = await state.get_data()
    await state.clear()
    job = await db.get_job(data.get("job_id", 0))
    if job is None or job["status"] != "draft":
        await message.answer(texts.JOB_LOCKED)
        return

    await db.update_job(job["id"], pages=pages)
    job = await db.get_job(job["id"])
    assert job is not None
    text, kb = views.print_card(job, cfg)
    await bot.edit_message_text(
        text=text, chat_id=message.chat.id, message_id=job["message_id"], reply_markup=kb
    )
    await message.answer(texts.pages_set(pages))


@router.callback_query(ReprintCb.filter())
async def on_reprint(
    callback: CallbackQuery, callback_data: ReprintCb, event_from_user: User, db: DB, cfg: Config
) -> None:
    src = await db.get_job(callback_data.job_id)
    if (
        src is None
        or src["user_id"] != event_from_user.id
        or not src["file_path"]
        or not Path(src["file_path"]).exists()
    ):
        await callback.answer(texts.FILE_GONE, show_alert=True)
        return

    msg = callback_message(callback)
    if msg is None:
        await callback.answer()
        return

    job_id = await db.create_job(event_from_user.id, "print", src["original_name"], file_path=src["file_path"])
    job = await db.get_job(job_id)
    assert job is not None
    text, kb = views.print_card(job, cfg)
    card = await msg.answer(text, reply_markup=kb)
    await db.update_job(job_id, message_id=card.message_id)
    await callback.answer()
