from collections.abc import Mapping, Sequence
from typing import Any

from aiogram.types import InlineKeyboardMarkup

from ..services.config import Config
from ..services.db import Row
from . import keyboards, texts

SCAN_MODES: dict[str, tuple[str, str]] = {
    "gray": ("Gray", "Ч/Б"),
    "color": ("Color", "Цветной"),
}
DEFAULT_SCAN_MODE = "gray"
SCAN_DPIS = (150, 300)

View = tuple[str, InlineKeyboardMarkup | None]


def print_card(job: Row, cfg: Config) -> View:
    return texts.print_card(job, cfg.duplex), keyboards.print_kb(job, cfg.duplex)


def scan_settings(data: Mapping[str, Any]) -> View:
    mode = data["mode"] if data["mode"] in SCAN_MODES else DEFAULT_SCAN_MODE
    dpi = data["dpi"]
    return (
        texts.scan_settings(SCAN_MODES[mode][1], dpi),
        keyboards.scan_settings_kb(mode, dpi, SCAN_MODES, SCAN_DPIS),
    )


def users(rows: Sequence[Row], root_id: int) -> View:
    return texts.users_list(rows, root_id), keyboards.users_kb(rows, root_id)
