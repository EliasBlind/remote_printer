import asyncio
from collections.abc import Iterable
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from PIL import Image

from .config import Config
from .shell import DeviceError, run

PREVIEW_SIZE = (1600, 1600)


class Scanner:
    def __init__(self, cfg: Config) -> None:
        self.device = cfg.scanner_device
        self.out_dir = cfg.scans
        self._lock = asyncio.Lock()

    @property
    def busy(self) -> bool:
        return self._lock.locked()

    async def scan_page(self, mode: str, dpi: int) -> Path:
        args = ["scanimage", "--format=png", f"--mode={mode}", f"--resolution={dpi}"]
        if self.device:
            args += ["--device-name", self.device]

        async with self._lock:
            data = await run(*args, timeout=240)
        if not data:
            raise DeviceError("Сканер вернул пустой результат")

        dst = self.out_dir / f"{uuid4().hex}.jpg"
        await asyncio.to_thread(self._save_jpeg, data, dst, dpi)
        return dst

    @staticmethod
    def _save_jpeg(png: bytes, dst: Path, dpi: int) -> None:
        with Image.open(BytesIO(png)) as img:
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")
            img.save(dst, "JPEG", quality=90, dpi=(dpi, dpi))

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
