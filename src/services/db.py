from collections.abc import Iterable

import aiosqlite

from .config import Config

Row = aiosqlite.Row

JOB_FIELDS = {"file_path", "copies", "duplex", "pages", "scale", "status", "error", "message_id"}


class DB:
    def __init__(self, cfg: Config) -> None:
        self.path = cfg.data_base
        self.schema = cfg.data_schema
        self.conn: aiosqlite.Connection | None = None

    @property
    def db(self) -> aiosqlite.Connection:
        if self.conn is None:
            raise RuntimeError("DB не подключена: сначала вызови await db.connect()")
        return self.conn

    async def connect(self) -> None:
        self.conn = await aiosqlite.connect(self.path)
        self.conn.row_factory = aiosqlite.Row
        await self.conn.execute("PRAGMA journal_mode=WAL;")
        await self.conn.execute("PRAGMA foreign_keys=ON;")
        await self.conn.executescript(self.schema.read_text(encoding="utf-8"))
        await self._migrate()
        await self.conn.commit()

    async def _migrate(self) -> None:
        async with self.db.execute("PRAGMA table_info(jobs)") as cur:
            columns = {row["name"] for row in await cur.fetchall()}
        if "scale" not in columns:
            await self.db.execute("ALTER TABLE jobs ADD COLUMN scale TEXT NOT NULL DEFAULT 'fit'")

    async def close(self) -> None:
        if self.conn is not None:
            await self.conn.close()
            self.conn = None


    async def get_user(self, user_id: int) -> aiosqlite.Row | None:
        async with self.db.execute("SELECT * FROM users WHERE id = ?", (user_id,)) as cur:
            return await cur.fetchone()

    async def add_user(self, user_id: int, username: str | None, full_name: str | None) -> bool:
        is_new = await self.get_user(user_id) is None
        await self.db.execute(
            """
            INSERT INTO users (id, username, full_name) VALUES (?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET username = excluded.username,
                                          full_name = excluded.full_name
            """,
            (user_id, username, full_name),
        )
        await self.db.commit()
        return is_new

    async def ensure_user(self, user_id: int, username: str | None, full_name: str | None) -> None:
        await self.db.execute(
            "INSERT OR IGNORE INTO users (id, username, full_name) VALUES (?, ?, ?)",
            (user_id, username, full_name),
        )
        await self.db.commit()

    async def is_allowed(self, user_id: int) -> bool:
        async with self.db.execute(
            "SELECT is_allowed FROM users WHERE id = ?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
        return bool(row and row["is_allowed"])

    async def set_allowed(self, user_id: int, allowed: bool) -> None:
        await self.db.execute(
            """
            INSERT INTO users (id, is_allowed) VALUES (?, ?)
            ON CONFLICT(id) DO UPDATE SET is_allowed = excluded.is_allowed
            """,
            (user_id, int(allowed)),
        )
        await self.db.commit()

    async def all_users(self, limit: int = 50) -> list[aiosqlite.Row]:
        async with self.db.execute(
            "SELECT * FROM users ORDER BY is_allowed DESC, created_at DESC LIMIT ?", (limit,)
        ) as cur:
            return list(await cur.fetchall())


    async def create_job(
        self,
        user_id: int,
        kind: str,
        original_name: str | None,
        file_path: str | None = None,
        status: str = "draft",
    ) -> int:
        cur = await self.db.execute(
            """
            INSERT INTO jobs (user_id, kind, original_name, file_path, status)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, kind, original_name, file_path, status),
        )
        await self.db.commit()
        if cur.lastrowid is None:
            raise RuntimeError("Не удалось создать задание")
        return cur.lastrowid

    async def get_job(self, job_id: int) -> aiosqlite.Row | None:
        async with self.db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)) as cur:
            return await cur.fetchone()

    async def update_job(self, job_id: int, **fields: object) -> None:
        unknown = set(fields) - JOB_FIELDS
        if unknown:
            raise ValueError(f"Неизвестные поля задания: {unknown}")
        if not fields:
            return
        sets = ", ".join(f"{name} = ?" for name in fields)
        await self.db.execute(
            f"UPDATE jobs SET {sets} WHERE id = ?", (*fields.values(), job_id)
        )
        await self.db.commit()

    async def set_status(self, job_id: int, status: str, error: str | None = None) -> None:
        await self.update_job(job_id, status=status, error=error)

    async def user_jobs(self, user_id: int, limit: int = 10) -> list[aiosqlite.Row]:
        async with self.db.execute(
            """
            SELECT * FROM jobs
            WHERE user_id = ? AND status != 'draft'
            ORDER BY id DESC LIMIT ?
            """,
            (user_id, limit),
        ) as cur:
            return list(await cur.fetchall())

    async def jobs_with_status(self, statuses: Iterable[str]) -> list[aiosqlite.Row]:
        statuses = list(statuses)
        marks = ", ".join("?" for _ in statuses)
        async with self.db.execute(
            f"SELECT * FROM jobs WHERE status IN ({marks}) ORDER BY id", statuses
        ) as cur:
            return list(await cur.fetchall())
