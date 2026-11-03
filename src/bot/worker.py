import asyncio
import logging
from pathlib import Path

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from ..services.config import Config
from ..services.db import DB
from ..services.printing import Printer
from ..services.shell import DeviceError
from . import texts, views

log = logging.getLogger(__name__)


class PrintWorker:

    def __init__(self, bot: Bot, db: DB, printer: Printer, cfg: Config) -> None:
        self.bot = bot
        self.db = db
        self.printer = printer
        self.cfg = cfg
        self.queue: asyncio.Queue[int] = asyncio.Queue()

    @property
    def pending(self) -> int:
        return self.queue.qsize()

    async def put(self, job_id: int) -> None:
        await self.queue.put(job_id)

    async def restore(self) -> None:
        for job in await self.db.jobs_with_status(["processing"]):
            await self.db.set_status(job["id"], "error", "Бот был перезапущен во время печати")
            await self.refresh(job["id"])
        for job in await self.db.jobs_with_status(["queued"]):
            await self.put(job["id"])

    async def run(self) -> None:
        while True:
            job_id = await self.queue.get()
            try:
                await self._process(job_id)
            except Exception:
                log.exception("Ошибка при обработке задания %s", job_id)
            finally:
                self.queue.task_done()

    async def _process(self, job_id: int) -> None:
        job = await self.db.get_job(job_id)
        if job is None or job["status"] != "queued":
            return

        await self.db.set_status(job_id, "processing")
        await self.refresh(job_id)

        try:
            await self.printer.print_file(
                Path(job["file_path"]),
                copies=job["copies"],
                duplex=bool(job["duplex"]),
                pages=job["pages"],
            )
        except DeviceError as e:
            await self.db.set_status(job_id, "error", str(e))
        except Exception:
            log.exception("Сбой печати задания %s", job_id)
            await self.db.set_status(job_id, "error", "Внутренняя ошибка, подробности в логах бота")
        else:
            await self.db.set_status(job_id, "done")

        await self.refresh(job_id)
        await self._notify(job_id)

    async def refresh(self, job_id: int) -> None:
        job = await self.db.get_job(job_id)
        if job is None or job["message_id"] is None:
            return
        text, kb = views.print_card(job, self.cfg)
        try:
            await self.bot.edit_message_text(
                text=text, chat_id=job["user_id"], message_id=job["message_id"], reply_markup=kb
            )
        except TelegramAPIError as e:
            if "message is not modified" not in str(e):
                log.warning("Не удалось обновить карточку задания %s: %s", job_id, e)

    async def _notify(self, job_id: int) -> None:
        job = await self.db.get_job(job_id)
        if job is None:
            return
        try:
            await self.bot.send_message(job["user_id"], texts.job_finished(job))
        except TelegramAPIError as e:
            log.warning("Не удалось уведомить о задании %s: %s", job_id, e)
