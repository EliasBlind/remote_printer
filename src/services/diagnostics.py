import getpass
import grp
import os
import pwd
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from PIL import Image

from .config import Config
from .printing import Printer
from .scanning import Scanner
from .shell import DeviceError

TOOLS = ("lp", "lpstat", "scanimage", "soffice", "mutool", "ddjvu", "ps2pdf")


@dataclass
class Check:
    title: str
    ok: bool
    detail: str


def _owner(path: Path) -> str:
    try:
        return pwd.getpwuid(path.stat().st_uid).pw_name
    except (KeyError, OSError):
        return "?"


def _writable(path: Path) -> Check:
    if not path.exists():
        return Check(str(path), False, "папка не существует")
    probe = path / f".probe_{uuid4().hex}"
    try:
        probe.write_bytes(b"ok")
        probe.unlink()
    except OSError as e:
        return Check(str(path), False, f"нет записи ({e.strerror}), владелец {_owner(path)}")
    return Check(str(path), True, f"запись есть, владелец {_owner(path)}")


async def collect(cfg: Config, printer: Printer, scanner: Scanner, test_scan: bool) -> list[Check]:
    user = getpass.getuser()
    groups = sorted({grp.getgrgid(g).gr_name for g in os.getgroups()})
    checks = [
        Check("Пользователь", True, f"{user}, группы: {', '.join(groups) or 'нет'}"),
        Check("Python", sys.version_info >= (3, 11), sys.version.split()[0]),
    ]

    checks += [_writable(p) for p in (cfg.data_base.parent, cfg.upload, cfg.converted, cfg.scans)]

    missing = [t for t in TOOLS if shutil.which(t) is None]
    checks.append(Check("Программы", not missing, "все найдены" if not missing else "нет: " + ", ".join(missing)))

    ready, desc = await printer.status()
    checks.append(Check(f"Принтер {cfg.printer_name}", ready, desc))

    try:
        devices = await scanner.devices()
        found = "device" in devices
        checks.append(Check("Сканеры (scanimage -L)", found, devices or "пусто"))
    except DeviceError as e:
        found = False
        checks.append(Check("Сканеры (scanimage -L)", False, str(e)))

    if test_scan and found:
        if scanner.busy:
            checks.append(Check("Пробный скан", False, "сканер сейчас занят"))
        else:
            try:
                page = await scanner.scan_page("Gray", 75)
                with Image.open(page) as img:
                    size = f"{img.width}×{img.height}"
                Scanner.cleanup([page])
                checks.append(Check("Пробный скан (75 dpi)", True, f"изображение {size}"))
            except Exception as e:
                checks.append(Check("Пробный скан (75 dpi)", False, f"{type(e).__name__}: {e}"))

    return checks
