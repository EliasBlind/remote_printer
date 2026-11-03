from collections.abc import Sequence
from datetime import datetime, timezone
from html import escape

from aiogram.types import User

from ..services.db import Row
from ..services.printing import FORMAT_GROUPS, SCALE_STRETCH, format_label, is_image

BTN_PRINT = "Печать"
BTN_SCAN = "Сканировать"
BTN_JOBS = "Мои задания"
BTN_STATUS = "Статус принтера"
BTN_HELP = "Помощь"
BTN_USERS = "Пользователи"


def plural(n: int, one: str, few: str, many: str) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


def trim(s: str, n: int) -> str:
    return s if len(s) <= n else s[: n - 1] + "…"


def fmt_time(ts: str | None) -> str:
    if not ts:
        return ""
    dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    return dt.astimezone().strftime("%d.%m %H:%M")


def _formats() -> str:
    return "\n".join(
        f"<b>{g.title}:</b> {', '.join(sorted(e.lstrip('.') for e in g.exts))}"
        for g in FORMAT_GROUPS
    )


FORMATS = "<b>Поддерживаемые форматы</b>\n\n" + _formats()
FORMATS_SHORT = "PDF, Word, Excel, PowerPoint, фото (включая HEIC), EPUB, FB2, DjVu, текст и код"


def welcome(name: str) -> str:
    return (
        f"<b>Привет, {escape(name)}!</b>\n\n"
        "Это бот домашнего принтера.\n\n"
        "<b>Печать</b> — пришлите файл или фото\n"
        "<b>Сканирование</b> — документ придёт в чат в PDF\n"
        "<b>Задания</b> — история печати и сканов\n\n"
        "<i>Отправьте файл, чтобы начать.</i>"
    )


HELP = (
    "<b>Печать</b>\n"
    "Отправьте файл или фото. В карточке задания выберите число копий и страницы, "
    "затем нажмите «Печатать».\n"
    "<blockquote>Фото лучше отправлять файлом, без сжатия, — так печать будет чётче. "
    "Размер файла — до 20 МБ.</blockquote>\n"
    f"<b>Форматы:</b> {FORMATS_SHORT}. Полный список — /formats\n\n"
    "<b>Сканирование</b>\n"
    "Положите лист на стекло лицевой стороной вниз и нажмите «Сканировать». "
    "Несколько страниц можно собрать в один PDF — готовый файл придёт в чат, "
    "откуда его можно сохранить на телефон или распечатать копию.\n\n"
    "<b>Команды</b>\n"
    "/scan — сканировать\n"
    "/jobs — мои задания\n"
    "/status — статус принтера\n"
    "/formats — форматы файлов\n"
    "/cancel — отменить действие"
)

PRINT_HINT = (
    "<b>Пришлите файл или фото</b>\n\n"
    "После загрузки появится карточка с настройками печати.\n\n"
    f"<i>Форматы:</i> {FORMATS_SHORT}. Полный список — /formats"
)

NO_ACCESS = "<b>Нет доступа к принтеру</b>\n\nНажмите /start, чтобы отправить запрос владельцу."
NO_ACCESS_SHORT = "Нет доступа"
ACCESS_REQUESTED = (
    "<b>Это бот домашнего принтера</b>\n\n"
    "Запрос на доступ отправлен владельцу. Я напишу, как только он ответит."
)
ACCESS_PENDING = "Запрос уже отправлен — дождитесь ответа владельца."
ACCESS_GRANTED = "<b>Доступ открыт</b>\n\nПришлите файл, чтобы напечатать его."
ACCESS_DENIED = "<b>Доступ закрыт</b>\n\nВладелец принтера отклонил запрос."
VERDICT_ALLOWED = "<b>Доступ выдан</b>"
VERDICT_DENIED = "<b>Запрос отклонён</b>"
TOAST_DONE = "Готово"
TOAST_ALLOWED = "Доступ выдан"
TOAST_REVOKED = "Доступ закрыт"


def access_request(user: User) -> str:
    username = f"@{escape(user.username)}" if user.username else "<i>нет</i>"
    return (
        "<b>Запрос доступа</b>\n\n"
        f"<b>Имя:</b> {escape(user.full_name)}\n"
        f"<b>Username:</b> {username}\n"
        f"<b>ID:</b> <code>{user.id}</code>"
    )


def user_label(u: Row) -> str:
    name = u["full_name"] or "Без имени"
    if u["username"]:
        name += f" (@{u['username']})"
    return name


def users_list(users: Sequence[Row], root_id: int) -> str:
    others = [u for u in users if u["id"] != root_id]
    if not others:
        return "<b>Пользователи</b>\n\nПока никто, кроме вас, не писал боту."
    lines = ["<b>Пользователи</b>"]
    for u in others:
        access = "есть доступ" if u["is_allowed"] else "нет доступа"
        lines.append(f"\n{escape(user_label(u))} · <code>{u['id']}</code>\n<i>{access}</i>")
    lines.append("\n<i>Нажмите кнопку, чтобы открыть или закрыть доступ.</i>")
    return "\n".join(lines)


def allow_usage(command: str) -> str:
    return f"Использование: <code>/{command} telegram_id</code>"


def allow_result(allowed: bool, user_id: str) -> str:
    return f"<b>{TOAST_ALLOWED if allowed else TOAST_REVOKED}:</b> <code>{user_id}</code>"


STATUS_TEXT = {
    "draft": "настройте параметры и нажмите «Печатать»",
    "queued": "в очереди",
    "processing": "печатается…",
    "done": "напечатано — заберите листы из принтера",
    "error": "ошибка печати",
    "cancelled": "отменено",
}
STATUS_SHORT = {
    "draft": "черновик",
    "queued": "в очереди",
    "processing": "печатается",
    "done": "готово",
    "error": "ошибка",
    "cancelled": "отменено",
}
KIND_TEXT = {"print": "печать", "scan": "скан"}
SCALE_TEXT = {
    "fit": "по размеру листа, с сохранением пропорций",
    "stretch": "на весь лист по вертикали и горизонтали",
}

TOO_BIG = (
    "<b>Файл больше 20 МБ</b>\n\n"
    "Telegram не даёт ботам скачивать такие файлы. Сожмите его или разделите на части."
)
UNSUPPORTED = "<b>Этот формат не поддерживается</b>\n\n" + _formats()
DOWNLOADING = "<i>Загружаю файл…</i>"
DOWNLOAD_FAILED = "<b>Не удалось скачать файл</b>\n\nПопробуйте отправить его ещё раз."
ASK_PAGES = (
    "<b>Какие страницы печатать?</b>\n\n"
    "Напишите номера, например <code>1-3</code> или <code>1,4,6-8</code>.\n"
    "<i>/cancel — отмена</i>"
)
BAD_PAGES = "Не удалось разобрать номера страниц. Пример: <code>1-3,5</code>\n<i>/cancel — отмена</i>"
JOB_NOT_FOUND = "Задание не найдено"
JOB_LOCKED = "Задание уже отправлено на печать"
FILE_GONE = "Файл больше недоступен"
CANNOT_CANCEL = "Уже нельзя отменить"
TOAST_QUEUED = "Отправлено в очередь"
TOAST_CANCELLED = "Отменено"
TOAST_RETRY = "Отправлено повторно"


def max_copies(n: int) -> str:
    return f"Максимум {n} {plural(n, 'копия', 'копии', 'копий')}"


def pages_set(pages: str) -> str:
    return f"<b>Страницы:</b> {escape(pages)}\n<i>Карточка задания обновлена.</i>"


def copies_label(n: int) -> str:
    return f"{n} {plural(n, 'копия', 'копии', 'копий')}"


def print_card(job: Row, duplex_supported: bool) -> str:
    name = job["original_name"] or "файл"
    lines = [
        f"<b>Печать · задание #{job['id']}</b>",
        f"<code>{escape(trim(name, 60))}</code> · <i>{format_label(name)}</i>",
        "",
        f"<b>Копий:</b> {job['copies']}",
        f"<b>Страницы:</b> {escape(job['pages']) if job['pages'] else 'все'}",
    ]
    if is_image(name):
        lines.append(f"<b>Масштаб:</b> {SCALE_TEXT.get(job['scale'], job['scale'])}")
        if job["scale"] == SCALE_STRETCH:
            lines.append("<i>Пропорции изображения могут исказиться.</i>")
    if duplex_supported:
        lines.append(f"<b>С двух сторон:</b> {'да' if job['duplex'] else 'нет'}")
    lines += ["", f"<b>Статус:</b> {STATUS_TEXT.get(job['status'], job['status'])}"]
    if job["status"] == "error" and job["error"]:
        lines.append(f"<blockquote>{escape(trim(job['error'], 300))}</blockquote>")
    return "\n".join(lines)


def job_finished(job: Row) -> str:
    name = escape(trim(job["original_name"] or "файл", 40))
    result = "напечатано" if job["status"] == "done" else "не напечатано"
    return f"<b>Задание #{job['id']} {result}</b>\n<code>{name}</code>"


def jobs_list(jobs: Sequence[Row]) -> str:
    if not jobs:
        return "<b>Заданий пока нет</b>\n\nПришлите файл — он появится здесь."
    lines = ["<b>Последние задания</b>"]
    for j in jobs:
        name = escape(trim(j["original_name"] or "—", 32))
        lines.append(
            f"\n<b>#{j['id']}</b> {KIND_TEXT.get(j['kind'], j['kind'])} · <code>{name}</code>\n"
            f"<i>{fmt_time(j['created_at'])} · {STATUS_SHORT.get(j['status'], j['status'])}</i>"
        )
    return "\n".join(lines)


def printer_status(ready: bool, desc: str, cups_queue: int, bot_queue: int) -> str:
    text = (
        "<b>Принтер</b>\n\n"
        f"<b>Состояние:</b> {escape(desc)}\n"
        f"<b>Ожидают в боте:</b> {bot_queue}\n"
        f"<b>В очереди принтера:</b> {cups_queue}"
    )
    if not ready:
        text += "\n\n<i>Печать сейчас недоступна.</i>"
    return text


SCAN_BUSY = "Сканер сейчас занят. Попробуйте через минуту."
SCAN_EXPIRED = "Сессия сканирования устарела. Начните заново: /scan"
SCAN_CANCELLED = "<i>Сканирование отменено.</i>"
SCAN_NO_PAGES = "Нет отсканированных страниц"
SCAN_ASSEMBLING = "Собираю файл…"


def scan_settings(mode_label: str, dpi: int) -> str:
    return (
        "<b>Сканирование</b>\n\n"
        "Положите документ на стекло <b>лицевой стороной вниз</b> и закройте крышку.\n\n"
        f"<b>Режим:</b> {mode_label}\n"
        f"<b>Качество:</b> {dpi} dpi"
    )


def scanning(n: int) -> str:
    return f"<b>Сканирую страницу {n}…</b>\n\n<i>Не поднимайте крышку, это займёт до минуты.</i>"


def scan_page_done(n: int) -> str:
    return (
        f"<b>Страница {n} готова</b>\n\n"
        "Положите следующий лист и нажмите «Ещё страница» или завершите сканирование."
    )


def scan_error(err: str) -> str:
    return f"<b>Не удалось отсканировать</b>\n<blockquote>{escape(trim(err, 300))}</blockquote>"


def scan_send_failed(err: str) -> str:
    return f"<b>Не удалось отправить скан</b>\n<blockquote>{escape(trim(err, 300))}</blockquote>"


def scan_ready(n: int) -> str:
    return (
        f"<b>Готово:</b> {n} {plural(n, 'страница', 'страницы', 'страниц')}\n\n"
        "<i>Нажмите на файл, чтобы сохранить его на телефон.</i>"
    )


CANCELLED = "Действие отменено."
FALLBACK = "Пришлите файл или фото для печати либо выберите действие в меню."
FALLBACK_MEDIA = "Такие сообщения я не печатаю. Пришлите документ или фото."
