import os
import tomllib
from pathlib import Path

from dotenv import load_dotenv


class Config:
    def __init__(self, path: str | Path) -> None:
        path = Path(path).resolve()
        base = path.parent

        load_dotenv(base / ".env")
        self.bot_token: str = os.environ["BOT_TOKEN"]
        self.root_id: int = int(os.environ["ROOT_TG_ID"])
        self.ai_api_key: str | None = os.getenv("AI_API_KEY")

        with open(path, "rb") as f:
            raw = tomllib.load(f)

        paths = raw["paths"]
        self.converted = base / paths["converted"]
        self.scans = base / paths["scans"]
        self.upload = base / paths["upload"]

        files = raw["files"]
        self.data_base = base / files["data_base"]
        self.data_schema = base / files["data_schema"]

        printer = raw["printer"]
        self.printer_name: str = printer["name"]
        self.max_copies: int = int(printer.get("max_copies", 20))
        self.duplex: bool = bool(printer.get("duplex", False))
        self.print_timeout: int = int(printer.get("timeout", 300))

        scanner = raw.get("scanner", {})
        self.scanner_device: str | None = scanner.get("device") or None
        self.scan_width_mm: float = float(scanner.get("width_mm", 210))
        self.scan_height_mm: float = float(scanner.get("height_mm", 297))

        for folder in (self.converted, self.scans, self.upload, self.data_base.parent):
            folder.mkdir(parents=True, exist_ok=True)
