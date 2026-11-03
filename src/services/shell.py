import asyncio
import os


class DeviceError(Exception):
    pass


async def run(*args: str, timeout: float = 60) -> bytes:
    env = {**os.environ, "LC_ALL": "C"}
    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
    except FileNotFoundError:
        raise DeviceError(f"Программа «{args[0]}» не установлена на сервере")

    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise DeviceError(f"{args[0]}: превышено время ожидания")

    if proc.returncode != 0:
        msg = err.decode(errors="replace").strip()
        raise DeviceError(msg or f"{args[0]} завершился с кодом {proc.returncode}")
    return out
