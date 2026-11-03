import asyncio
import re
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageOps, ImageSequence, UnidentifiedImageError

from .config import Config
from .shell import DeviceError, run

try:
    from pillow_heif import register_heif_opener

    register_heif_opener()
except ImportError:
    pass


PDF_EXT = {".pdf"}

IMAGE_EXT = {
    ".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif",
    ".tif", ".tiff", ".heic", ".heif", ".avif",
}
MULTIPAGE_IMAGE_EXT = {".tif", ".tiff"}

OFFICE_DOC_EXT = {
    ".doc", ".docx", ".docm", ".dot", ".dotx", ".odt", ".ott", ".fodt",
    ".rtf", ".wpd", ".wps", ".pages", ".sxw", ".htm", ".html", ".xhtml",
}
OFFICE_SHEET_EXT = {
    ".xls", ".xlsx", ".xlsm", ".xlsb", ".xlt", ".xltx", ".ods", ".fods", ".numbers",
}
OFFICE_SLIDES_EXT = {
    ".ppt", ".pptx", ".pptm", ".pps", ".ppsx", ".pot", ".potx", ".odp", ".fodp", ".key",
}
OFFICE_DRAW_EXT = {".svg", ".odg", ".vsd", ".vsdx", ".pub", ".cdr"}
OFFICE_EXT = OFFICE_DOC_EXT | OFFICE_SHEET_EXT | OFFICE_SLIDES_EXT | OFFICE_DRAW_EXT

CSV_EXT = {".csv", ".tsv"}

TEXT_EXT = {
    ".txt", ".md", ".log", ".ini", ".cfg", ".conf", ".toml", ".yaml", ".yml",
    ".json", ".xml", ".sql", ".css", ".sh",
    ".py", ".js", ".ts", ".c", ".h", ".cpp", ".hpp", ".cs", ".java", ".kt", ".go", ".rs", ".php", ".rb",
}

MUPDF_EXT = {".epub", ".fb2", ".cbz", ".xps", ".oxps"}
DJVU_EXT = {".djvu", ".djv"}
PS_EXT = {".ps", ".eps"}

SUPPORTED_EXT = (
    PDF_EXT | IMAGE_EXT | OFFICE_EXT | CSV_EXT | TEXT_EXT | MUPDF_EXT | DJVU_EXT | PS_EXT
)


@dataclass(frozen=True)
class FormatGroup:
    title: str
    label: str
    exts: frozenset[str]


FORMAT_GROUPS = (
    FormatGroup("Документы", "документ", frozenset(PDF_EXT | OFFICE_DOC_EXT)),
    FormatGroup("Таблицы", "таблица", frozenset(OFFICE_SHEET_EXT | CSV_EXT)),
    FormatGroup("Презентации", "презентация", frozenset(OFFICE_SLIDES_EXT)),
    FormatGroup("Изображения", "изображение", frozenset(IMAGE_EXT)),
    FormatGroup("Графика", "графика", frozenset(OFFICE_DRAW_EXT | PS_EXT)),
    FormatGroup("Книги", "книга", frozenset(MUPDF_EXT | DJVU_EXT)),
    FormatGroup("Текст и код", "текст", frozenset(TEXT_EXT)),
)


def format_label(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    for group in FORMAT_GROUPS:
        if ext in group.exts:
            return group.label
    return "файл"


PAGES_RE = re.compile(r"^\d+(-\d+)?(,\d+(-\d+)?)*$")


def valid_pages(pages: str) -> bool:
    if not PAGES_RE.match(pages):
        return False
    for part in pages.split(","):
        a, _, b = part.partition("-")
        if int(a) < 1 or (b and int(b) < int(a)):
            return False
    return True


A4_300DPI = (2480, 3508)
A4_POINTS = (595, 842)
MARGIN = 118
MAX_IMAGE_PAGES = 50


def _fit_a4(frame: Image.Image) -> Image.Image:
    img = ImageOps.exif_transpose(frame)
    if img.mode in ("RGBA", "LA", "P"):
        bg = Image.new("RGB", img.size, "white")
        bg.paste(img.convert("RGBA"), mask=img.convert("RGBA").getchannel("A"))
        img = bg
    img = img.convert("L")

    page_w, page_h = A4_300DPI
    if img.width > img.height:
        page_w, page_h = page_h, page_w

    img.thumbnail((page_w - 2 * MARGIN, page_h - 2 * MARGIN))
    page = Image.new(img.mode, (page_w, page_h), "white")
    page.paste(img, ((page_w - img.width) // 2, (page_h - img.height) // 2))
    return page


def _read_text(src: Path) -> str:
    raw = src.read_bytes()
    for enc in ("utf-8-sig", "cp1251"):
        with suppress(UnicodeDecodeError):
            return raw.decode(enc)
    return raw.decode("utf-8", errors="replace")


class Printer:
    def __init__(self, cfg: Config) -> None:
        self.name = cfg.printer_name
        self.converted = cfg.converted
        self.duplex_supported = cfg.duplex
        self.timeout = cfg.print_timeout

    @staticmethod
    def is_supported(filename: str) -> bool:
        return Path(filename).suffix.lower() in SUPPORTED_EXT


    async def status(self) -> tuple[bool, str]:
        try:
            out = (await run("lpstat", "-p", self.name)).decode(errors="replace")
        except DeviceError:
            return False, "не найден в системе печати (CUPS)"
        if "disabled" in out:
            return False, "выключен или не подключён"
        if "now printing" in out:
            return True, "печатает"
        if "idle" in out:
            return True, "готов к печати"
        return True, out.strip()

    async def queue_size(self) -> int:
        try:
            out = (await run("lpstat", "-o", self.name)).decode(errors="replace")
        except DeviceError:
            return 0
        return sum(1 for line in out.splitlines() if line.strip())


    async def to_pdf(self, src: Path) -> Path:
        ext = src.suffix.lower()
        if ext in PDF_EXT:
            return src

        dst = self.converted / f"{src.stem}.pdf"
        dst.unlink(missing_ok=True)

        if ext in IMAGE_EXT:
            await asyncio.to_thread(self._image_to_pdf, src, dst)
        elif ext in OFFICE_EXT:
            await self._soffice(src)
        elif ext in TEXT_EXT:
            await self._text_to_pdf(src)
        elif ext in CSV_EXT:
            await self._csv_to_pdf(src)
        elif ext in MUPDF_EXT:
            w, h = A4_POINTS
            await run(
                "mutool", "convert", "-W", str(w), "-H", str(h), "-S", "11",
                "-o", str(dst), str(src),
                timeout=300,
            )
        elif ext in DJVU_EXT:
            await run("ddjvu", "-format=pdf", str(src), str(dst), timeout=300)
        elif ext in PS_EXT:
            args = ["ps2pdf"]
            if ext == ".eps":
                args.append("-dEPSCrop")
            await run(*args, str(src), str(dst), timeout=180)
        else:
            raise DeviceError(f"Формат {ext or 'без расширения'} не поддерживается")

        if not dst.exists() or dst.stat().st_size == 0:
            raise DeviceError("Не удалось сконвертировать файл в PDF")
        return dst

    async def _soffice(self, src: Path, infilter: str | None = None) -> None:
        args = [
            "soffice",
            "-env:UserInstallation=file:///tmp/lo_remote_printer",
            "--headless",
        ]
        if infilter:
            args.append(f"--infilter={infilter}")
        args += ["--convert-to", "pdf", "--outdir", str(self.converted), str(src)]
        await run(*args, timeout=180)

    async def _text_to_pdf(self, src: Path) -> None:
        tmp = self.converted / f"{src.stem}.txt"
        tmp.write_text(_read_text(src), encoding="utf-8")
        try:
            await self._soffice(tmp, infilter="Text (encoded):UTF8")
        finally:
            tmp.unlink(missing_ok=True)

    async def _csv_to_pdf(self, src: Path) -> None:
        text = _read_text(src)
        if src.suffix.lower() == ".tsv":
            sep = "\t"
        else:
            first = text.split("\n", 1)[0]
            sep = ";" if first.count(";") > first.count(",") else ","

        tmp = self.converted / f"{src.stem}.csv"
        tmp.write_text(text, encoding="utf-8")
        try:
            await self._soffice(tmp, infilter=f"CSV:{ord(sep)},34,76")
        finally:
            tmp.unlink(missing_ok=True)

    @staticmethod
    def _image_to_pdf(src: Path, dst: Path) -> None:
        try:
            opened = Image.open(src)
        except (UnidentifiedImageError, OSError) as e:
            raise DeviceError("Не удалось открыть изображение: файл повреждён или формат не поддерживается") from e

        with opened:
            if src.suffix.lower() in MULTIPAGE_IMAGE_EXT:
                pages = [
                    _fit_a4(frame)
                    for i, frame in enumerate(ImageSequence.Iterator(opened))
                    if i < MAX_IMAGE_PAGES
                ]
            else:
                pages = [_fit_a4(opened)]

        first, *rest = pages
        first.save(dst, "PDF", save_all=True, append_images=rest, resolution=300)


    async def print_pdf(
        self, pdf: Path, copies: int = 1, duplex: bool = False, pages: str | None = None
    ) -> str:
        args = ["lp", "-d", self.name, "-n", str(copies)]
        if duplex and self.duplex_supported:
            args += ["-o", "sides=two-sided-long-edge"]
        if pages:
            if not valid_pages(pages):
                raise DeviceError("Страницы указываются так: 1-3,5")
            args += ["-o", f"page-ranges={pages}"]
        args.append(str(pdf))

        out = (await run(*args)).decode(errors="replace")
        m = re.search(r"request id is (\S+)", out)
        if not m:
            raise DeviceError(f"Не удалось получить id задания: {out.strip()}")
        return m.group(1)

    async def is_done(self, cups_job_id: str) -> bool:
        out = (await run("lpstat", "-W", "not-completed", "-o", self.name)).decode(errors="replace")
        pending = {line.split()[0] for line in out.splitlines() if line.strip()}
        return cups_job_id not in pending

    async def wait_done(self, cups_job_id: str, poll: float = 3) -> None:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.timeout
        while not await self.is_done(cups_job_id):
            if loop.time() > deadline:
                raise DeviceError(
                    "Принтер не взял задание. Проверьте, что он включён и в нём есть бумага."
                )
            await asyncio.sleep(poll)

    async def cancel(self, cups_job_id: str) -> None:
        await run("cancel", cups_job_id)

    async def print_file(
        self, src: Path, copies: int = 1, duplex: bool = False, pages: str | None = None
    ) -> None:
        if not src.exists():
            raise DeviceError("Файл для печати не найден на сервере")
        ready, desc = await self.status()
        if not ready:
            raise DeviceError(f"Принтер {desc}")

        pdf = await self.to_pdf(src)
        job = await self.print_pdf(pdf, copies=copies, duplex=duplex, pages=pages)
        try:
            await self.wait_done(job)
        except DeviceError:
            with suppress(DeviceError):
                await self.cancel(job)
            raise
