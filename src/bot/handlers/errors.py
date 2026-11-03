import logging

from aiogram import Bot, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.types import ErrorEvent

from .. import texts

log = logging.getLogger(__name__)
router = Router(name="errors")


@router.errors()
async def on_error(event: ErrorEvent, bot: Bot) -> None:
    log.exception("Необработанная ошибка", exc_info=event.exception)
    update = event.update
    chat_id: int | None = None
    if update.message is not None:
        chat_id = update.message.chat.id
    elif update.callback_query is not None:
        chat_id = update.callback_query.from_user.id
        try:
            await update.callback_query.answer()
        except TelegramAPIError:
            pass
    if chat_id is None:
        return
    try:
        await bot.send_message(chat_id, texts.internal_error(event.exception))
    except TelegramAPIError:
        pass
