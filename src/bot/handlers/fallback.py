from aiogram import F, Router
from aiogram.types import Message

from .. import texts

router = Router(name="fallback")


@router.message(F.text)
async def unknown_text(message: Message) -> None:
    await message.answer(texts.FALLBACK)


@router.message()
async def unknown_media(message: Message) -> None:
    await message.answer(texts.FALLBACK_MEDIA)
