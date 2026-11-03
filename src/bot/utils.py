import re
from pathlib import Path

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message


def callback_message(callback: CallbackQuery) -> Message | None:
    msg = callback.message
    return msg if isinstance(msg, Message) else None


async def edit_message(msg: Message, text: str, kb: InlineKeyboardMarkup | None = None) -> None:
    try:
        if msg.photo or msg.document:
            await msg.edit_caption(caption=text, reply_markup=kb)
        else:
            await msg.edit_text(text, reply_markup=kb)
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            raise


def safe_filename(name: str, max_len: int = 80) -> str:
    p = Path(Path(name).name)
    stem = re.sub(r"[^\w\-]+", "_", p.stem).strip("_") or "file"
    return stem[:max_len] + p.suffix.lower()
