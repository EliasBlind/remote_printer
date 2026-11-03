import asyncio
import logging
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.exceptions import TelegramAPIError
from aiogram.types import BotCommand, BotCommandScopeChat

from src.bot.handlers import setup_routers
from src.bot.worker import PrintWorker
from src.services.config import Config
from src.services.db import DB
from src.services.printing import Printer
from src.services.scanning import Scanner

BASE_DIR = Path(__file__).resolve().parent

COMMANDS = [
    BotCommand(command="start", description="Главное меню"),
    BotCommand(command="scan", description="Сканировать документ"),
    BotCommand(command="jobs", description="Мои задания"),
    BotCommand(command="status", description="Статус принтера"),
    BotCommand(command="formats", description="Какие файлы можно печатать"),
    BotCommand(command="help", description="Помощь"),
    BotCommand(command="cancel", description="Отменить действие"),
]

ROOT_COMMANDS = [
    *COMMANDS,
    BotCommand(command="users", description="Пользователи и доступ"),
    BotCommand(command="diag", description="Диагностика принтера и сканера"),
]


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )

    cfg = Config(BASE_DIR / "config.toml")
    db = DB(cfg)
    await db.connect()

    bot = Bot(cfg.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    printer = Printer(cfg)
    scanner = Scanner(cfg)
    worker = PrintWorker(bot, db, printer, cfg)

    dp = Dispatcher(
        storage=MemoryStorage(),
        cfg=cfg, db=db, printer=printer, scanner=scanner, worker=worker,
    )
    dp.include_router(setup_routers())

    await bot.set_my_commands(COMMANDS)
    try:
        await bot.set_my_commands(ROOT_COMMANDS, scope=BotCommandScopeChat(chat_id=cfg.root_id))
    except TelegramAPIError:
        pass
    await worker.restore()
    worker_task = asyncio.create_task(worker.run())

    try:
        await dp.start_polling(bot)
    finally:
        worker_task.cancel()
        await db.close()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
