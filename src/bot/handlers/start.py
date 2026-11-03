from aiogram import Bot, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, ReplyKeyboardRemove, User

from ...services.config import Config
from ...services.db import DB
from .. import texts
from ..keyboards import access_request_kb, main_menu

router = Router(name="start")


@router.message(CommandStart())
async def cmd_start(
    message: Message, event_from_user: User, state: FSMContext, db: DB, cfg: Config, bot: Bot
) -> None:
    await state.clear()
    user = event_from_user
    is_new = await db.add_user(user.id, user.username, user.full_name)
    is_root = user.id == cfg.root_id

    if is_root or await db.is_allowed(user.id):
        await message.answer(texts.welcome(user.first_name), reply_markup=main_menu(is_root))
        return

    if not is_new:
        await message.answer(texts.ACCESS_PENDING, reply_markup=ReplyKeyboardRemove())
        return

    await message.answer(texts.ACCESS_REQUESTED, reply_markup=ReplyKeyboardRemove())
    try:
        await bot.send_message(
            cfg.root_id, texts.access_request(user), reply_markup=access_request_kb(user.id)
        )
    except TelegramAPIError:
        pass
