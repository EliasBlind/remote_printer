from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove

from ...services.config import Config
from ...services.db import DB
from .. import texts, views
from ..filters import IsRoot
from ..keyboards import AccessCb, UsersCb, main_menu
from ..utils import callback_message, edit_message

router = Router(name="admin")
router.message.filter(IsRoot())
router.callback_query.filter(IsRoot())


async def _notify(bot: Bot, user_id: int, allowed: bool) -> None:
    try:
        if allowed:
            await bot.send_message(user_id, texts.ACCESS_GRANTED, reply_markup=main_menu(False))
        else:
            await bot.send_message(user_id, texts.ACCESS_DENIED, reply_markup=ReplyKeyboardRemove())
    except TelegramAPIError:
        pass


@router.callback_query(AccessCb.filter())
async def on_access_request(callback: CallbackQuery, callback_data: AccessCb, db: DB, bot: Bot) -> None:
    allow = callback_data.action == "allow"
    await db.set_allowed(callback_data.user_id, allow)

    msg = callback_message(callback)
    if msg is not None:
        verdict = texts.VERDICT_ALLOWED if allow else texts.VERDICT_DENIED
        await edit_message(msg, f"{msg.html_text}\n\n{verdict}")
    await callback.answer(texts.TOAST_DONE)
    await _notify(bot, callback_data.user_id, allow)


@router.message(F.text == texts.BTN_USERS)
@router.message(Command("users"))
async def users_list(message: Message, db: DB, cfg: Config) -> None:
    text, kb = views.users(await db.all_users(), cfg.root_id)
    await message.answer(text, reply_markup=kb)


@router.callback_query(UsersCb.filter())
async def toggle_user(callback: CallbackQuery, callback_data: UsersCb, db: DB, cfg: Config, bot: Bot) -> None:
    user = await db.get_user(callback_data.user_id)
    if user is None or user["id"] == cfg.root_id:
        await callback.answer()
        return

    allowed = not user["is_allowed"]
    await db.set_allowed(user["id"], allowed)

    msg = callback_message(callback)
    if msg is not None:
        text, kb = views.users(await db.all_users(), cfg.root_id)
        await edit_message(msg, text, kb)
    await callback.answer(texts.TOAST_ALLOWED if allowed else texts.TOAST_REVOKED)
    await _notify(bot, user["id"], allowed)


@router.message(Command("allow", "deny"))
async def allow_deny(message: Message, command: CommandObject, db: DB, bot: Bot) -> None:
    arg = (command.args or "").strip()
    if not arg.isdigit():
        await message.answer(texts.allow_usage(command.command))
        return
    allowed = command.command == "allow"
    await db.set_allowed(int(arg), allowed)
    await message.answer(texts.allow_result(allowed, arg))
    await _notify(bot, int(arg), allowed)
