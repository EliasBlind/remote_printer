import asyncio
import struct
import zlib
from collections.abc import Iterable
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from PIL import Image, ImageFile, UnidentifiedImageError

from .config import Config
from .shell import DeviceError, run

PREVIEW_SIZE = (1600, 1600)
MIN_RECEIVED_SHARE = 0.1
PNG_CHANNELS = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}


def png_received_rows(png: bytes) -> tuple[int, int] | None:
    if png[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    pos, idat = 8, bytearray()
    width = height = depth = color = interlace = 0
    while pos + 8 <= len(png):
        length, kind = struct.unpack(">I4s", png[pos : pos + 8])
        body = png[pos + 8 : pos + 8 + length]
        if kind == b"IHDR":
            width, height, depth, color, _, _, interlace = struct.unpack(">IIBBBBB", body)
        elif kind == b"IDAT":
            idat += body
        elif kind == b"IEND":
            break
        pos += 12 + length
    if not width or interlace or color not in PNG_CHANNELS:
        return None
    stride = 1 + (width * PNG_CHANNELS[color] * depth + 7) // 8
    try:
        raw = zlib.decompressobj().decompress(bytes(idat))
    except zlib.error:
        return None
    return height, min(height, len(raw) // stride)


class Scanner:
    def __init__(self, cfg: Config) -> None:
        self.device = cfg.scanner_device
        self.width_mm = cfg.scan_width_mm
        self.height_mm = cfg.scan_height_mm
        self.out_dir = cfg.scans
        self._lock = asyncio.Lock()

    @property
    def busy(self) -> bool:
        return self._lock.locked()

    async def scan_page(self, mode: str, dpi: int) -> Path:
        args = ["scanimage", "--format=png", f"--mode={mode}", f"--resolution={dpi}"]
        if self.device:
            args += ["--device-name", self.device]
        if self.width_mm > 0 and self.height_mm > 0:
            args += ["-l", "0", "-t", "0", "-x", f"{self.width_mm:g}", "-y", f"{self.height_mm:g}"]

        async with self._lock:
            data = await run(*args, timeout=240)
        if not data:
            raise DeviceError("Сканер вернул пустой результат")

        name = uuid4().hex
        raw = self.out_dir / f"{name}.png"
        dst = self.out_dir / f"{name}.jpg"
        try:
            raw.write_bytes(data)
        except OSError as e:
            raise DeviceError(f"Не удалось сохранить скан в {self.out_dir}: {e.strerror}") from e

        try:
            await asyncio.to_thread(self._save_jpeg, data, dst, dpi)
        except (UnidentifiedImageError, OSError) as e:
            raise DeviceError(
                f"Сканер вернул данные, которые не читаются как изображение ({len(data)} байт). "
                f"Они сохранены в {raw}"
            ) from e
        raw.unlink(missing_ok=True)
        return dst

    async def devices(self) -> str:
        out = await run("scanimage", "-L", timeout=60)
        return out.decode(errors="replace").strip()

    @staticmethod
    def _save_jpeg(png: bytes, dst: Path, dpi: int) -> None:
        img = Scanner._decode(png)
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        img.save(dst, "JPEG", quality=90, dpi=(dpi, dpi))

    @staticmethod
    def _decode(png: bytes) -> Image.Image:
        try:
            with Image.open(BytesIO(png)) as img:
                img.load()
                return img.copy()
        except OSError as e:
            if "truncated" not in str(e):
                raise
        rows = png_received_rows(png)
        if rows is None:
            raise UnidentifiedImageError("Неизвестный формат данных от сканера")
        declared, received = rows
        if received < declared * MIN_RECEIVED_SHARE:
            raise UnidentifiedImageError(f"Получено только {received} строк из {declared}")
        previous = ImageFile.LOAD_TRUNCATED_IMAGES
        ImageFile.LOAD_TRUNCATED_IMAGES = True
        try:
            with Image.open(BytesIO(png)) as img:
                img.load()
                return img.crop((0, 0, img.width, received))
        finally:
            ImageFile.LOAD_TRUNCATED_IMAGES = previous

    @staticmethod
    def preview_path(page: Path) -> Path:
        return page.with_name(f"{page.stem}_preview.jpg")

    async def make_preview(self, page: Path) -> Path:
        dst = self.preview_path(page)

        def _make() -> None:
            with Image.open(page) as img:
                img.thumbnail(PREVIEW_SIZE)
                img.save(dst, "JPEG", quality=80)

        await asyncio.to_thread(_make)
        return dst

    @staticmethod
    def pages_to_pdf(pages: list[Path], dst: Path, dpi: int) -> None:
        images = [Image.open(p) for p in pages]
        try:
            first, *rest = images
            first.save(dst, "PDF", save_all=True, append_images=rest, resolution=dpi)
        finally:
            for img in images:
                img.close()

    @classmethod
    def cleanup(cls, pages: Iterable[str | Path]) -> None:
        for p in pages:
            page = Path(p)
            page.unlink(missing_ok=True)
            cls.preview_path(page).unlink(missing_ok=True)
