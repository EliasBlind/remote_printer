from collections.abc import Mapping, Sequence

from aiogram.filters.callback_data import CallbackData
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from ..services.db import Row
from . import texts

SELECTED = "✓ "


class PrintCb(CallbackData, prefix="pr"):
    action: str
    job_id: int


class ReprintCb(CallbackData, prefix="rp"):
    job_id: int


class ScanCb(CallbackData, prefix="sc"):
    action: str
    value: str = ""


class AccessCb(CallbackData, prefix="ac"):
    action: str
    user_id: int


class UsersCb(CallbackData, prefix="us"):
    user_id: int


def _btn(text: str, cb: CallbackData) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=cb.pack())


def _markup(rows: list[list[InlineKeyboardButton]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=rows)


def main_menu(is_root: bool) -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text=texts.BTN_PRINT), KeyboardButton(text=texts.BTN_SCAN)],
        [KeyboardButton(text=texts.BTN_JOBS), KeyboardButton(text=texts.BTN_STATUS)],
    ]
    if is_root:
        rows.append([KeyboardButton(text=texts.BTN_USERS), KeyboardButton(text=texts.BTN_HELP)])
    else:
        rows.append([KeyboardButton(text=texts.BTN_HELP)])
    return ReplyKeyboardMarkup(
        keyboard=rows,
        resize_keyboard=True,
        input_field_placeholder="Пришлите файл для печати",
    )


def print_kb(job: Row, duplex_supported: bool) -> InlineKeyboardMarkup | None:
    jid = job["id"]
    status = job["status"]

    def cb(action: str) -> PrintCb:
        return PrintCb(action=action, job_id=jid)

    if status == "queued":
        return _markup([[_btn("Отменить", cb("cancel"))]])
    if status == "error":
        return _markup([[_btn("Повторить", cb("retry"))]])
    if status != "draft":
        return None

    rows = [
        [
            _btn("−", cb("dec")),
            _btn(texts.copies_label(job["copies"]), cb("noop")),
            _btn("+", cb("inc")),
        ],
    ]
    if job["pages"]:
        rows.append([_btn("Изменить страницы", cb("pages")), _btn("Все страницы", cb("pages_all"))])
    else:
        rows.append([_btn("Выбрать страницы", cb("pages"))])
    if duplex_supported:
        state = "вкл" if job["duplex"] else "выкл"
        rows.append([_btn(f"С двух сторон: {state}", cb("duplex"))])
    rows.append([_btn("Отмена", cb("cancel")), _btn("Печатать", cb("go"))])
    return _markup(rows)


def reprint_kb(job_id: int) -> InlineKeyboardMarkup:
    return _markup([[_btn("Распечатать копию", ReprintCb(job_id=job_id))]])


def scan_settings_kb(
    mode: str, dpi: int, modes: Mapping[str, tuple[str, str]], dpis: tuple[int, ...]
) -> InlineKeyboardMarkup:
    mode_row = [
        _btn((SELECTED if key == mode else "") + label, ScanCb(action="mode", value=key))
        for key, (_, label) in modes.items()
    ]
    dpi_row = [
        _btn((SELECTED if d == dpi else "") + f"{d} dpi", ScanCb(action="dpi", value=str(d)))
        for d in dpis
    ]
    return _markup([
        mode_row,
        dpi_row,
        [_btn("Отмена", ScanCb(action="cancel")), _btn("Сканировать", ScanCb(action="scan"))],
    ])


def scan_session_kb() -> InlineKeyboardMarkup:
    return _markup([
        [_btn("Ещё страница", ScanCb(action="scan"))],
        [_btn("Готово: PDF", ScanCb(action="pdf")), _btn("Готово: JPG", ScanCb(action="jpg"))],
        [_btn("Отмена", ScanCb(action="cancel"))],
    ])


def scan_retry_kb() -> InlineKeyboardMarkup:
    return _markup([[_btn("Отмена", ScanCb(action="cancel")), _btn("Повторить", ScanCb(action="scan"))]])


def access_request_kb(user_id: int) -> InlineKeyboardMarkup:
    return _markup([[
        _btn("Пустить", AccessCb(action="allow", user_id=user_id)),
        _btn("Отклонить", AccessCb(action="deny", user_id=user_id)),
    ]])


def users_kb(users: Sequence[Row], root_id: int) -> InlineKeyboardMarkup | None:
    rows = [
        [_btn(
            f"{'Закрыть' if u['is_allowed'] else 'Открыть'}: {texts.trim(texts.user_label(u), 40)}",
            UsersCb(user_id=u["id"]),
        )]
        for u in users
        if u["id"] != root_id
    ]
    return _markup(rows) if rows else None
