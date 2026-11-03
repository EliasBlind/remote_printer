from aiogram.filters import Filter
from aiogram.types import TelegramObject, User

from ..services.config import Config


class IsRoot(Filter):
    async def __call__(
        self, event: TelegramObject, cfg: Config, event_from_user: User | None = None
    ) -> bool:
        return event_from_user is not None and event_from_user.id == cfg.root_id
