from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject, User

from ..services.config import Config
from ..services.db import DB
from . import texts


class AccessMiddleware(BaseMiddleware):

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user: User | None = data.get("event_from_user")
        cfg: Config = data["cfg"]
        db: DB = data["db"]

        if user is not None:
            if user.id == cfg.root_id:
                await db.ensure_user(user.id, user.username, user.full_name)
                return await handler(event, data)
            if await db.is_allowed(user.id):
                return await handler(event, data)

        if isinstance(event, Message):
            await event.answer(texts.NO_ACCESS)
        elif isinstance(event, CallbackQuery):
            await event.answer(texts.NO_ACCESS_SHORT, show_alert=True)
        return None
