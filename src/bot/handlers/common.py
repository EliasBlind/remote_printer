from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, User

from ...services.db import DB
from ...services.printing import Printer
from ...services.scanning import Scanner
from .. import texts
from ..worker import PrintWorker

router = Router(name="common")


@router.message(Command("help"))
@router.message(F.text == texts.BTN_HELP)
async def cmd_help(message: Message) -> None:
    await message.answer(texts.HELP)


@router.message(Command("formats"))
async def cmd_formats(message: Message) -> None:
    await message.answer(texts.FORMATS)


@router.message(F.text == texts.BTN_PRINT)
async def print_hint(message: Message) -> None:
    await message.answer(texts.PRINT_HINT)


@router.message(Command("status"))
@router.message(F.text == texts.BTN_STATUS)
async def cmd_status(message: Message, printer: Printer, worker: PrintWorker) -> None:
    ready, desc = await printer.status()
    cups_queue = await printer.queue_size()
    await message.answer(texts.printer_status(ready, desc, cups_queue, worker.pending))


@router.message(Command("jobs"))
@router.message(F.text == texts.BTN_JOBS)
async def cmd_jobs(message: Message, event_from_user: User, db: DB) -> None:
    jobs = await db.user_jobs(event_from_user.id, limit=10)
    await message.answer(texts.jobs_list(jobs))


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    Scanner.cleanup(data.get("pages", []))
    await state.clear()
    await message.answer(texts.CANCELLED)
