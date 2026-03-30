"""任务历史：SQLite + 结果 xlsx 路径。"""

from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def db_path(base_dir: Path) -> Path:
    p = base_dir / "data" / "jobs.sqlite"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def init_db(base_dir: Path) -> None:
    path = db_path(base_dir)
    con = sqlite3.connect(path)
    try:
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS jobs (
              id TEXT PRIMARY KEY,
              created_at TEXT NOT NULL,
              mapping_name TEXT,
              sku_name TEXT,
              ok_count INTEGER NOT NULL,
              fail_count INTEGER NOT NULL,
              row_count INTEGER NOT NULL,
              result_relpath TEXT NOT NULL,
              map_warnings_json TEXT
            );
            CREATE TABLE IF NOT EXISTS job_row_errors (
              job_id TEXT NOT NULL,
              row_index INTEGER NOT NULL,
              reason TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_job_row_errors_job ON job_row_errors(job_id);
            """
        )
        con.commit()
    finally:
        con.close()
    logger.info("数据库就绪: %s", path)


def insert_job(
    base_dir: Path,
    *,
    job_id: str | None = None,
    mapping_name: str,
    sku_name: str,
    ok_count: int,
    fail_count: int,
    row_count: int,
    result_relpath: str,
    map_warnings: list[str],
    row_errors: list[tuple[int, str]],
) -> tuple[str, str]:
    jid = job_id or str(uuid.uuid4())
    created_at = _utc_now_iso()
    path = db_path(base_dir)
    con = sqlite3.connect(path)
    try:
        con.execute(
            """
            INSERT INTO jobs (
              id, created_at, mapping_name, sku_name,
              ok_count, fail_count, row_count, result_relpath, map_warnings_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                jid,
                created_at,
                mapping_name,
                sku_name,
                ok_count,
                fail_count,
                row_count,
                result_relpath,
                json.dumps(map_warnings, ensure_ascii=False) if map_warnings else None,
            ),
        )
        for row_index, reason in row_errors:
            con.execute(
                "INSERT INTO job_row_errors (job_id, row_index, reason) VALUES (?, ?, ?)",
                (jid, row_index, reason),
            )
        con.commit()
    finally:
        con.close()
    logger.info(
        "任务已记录 id=%s ok=%s fail=%s",
        jid,
        ok_count,
        fail_count,
    )
    return jid, created_at


def list_jobs(base_dir: Path, limit: int = 100) -> list[dict[str, Any]]:
    path = db_path(base_dir)
    if not path.exists():
        return []
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    try:
        cur = con.execute(
            """
            SELECT id, created_at, mapping_name, sku_name,
                   ok_count, fail_count, row_count, result_relpath, map_warnings_json
            FROM jobs
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = [dict(r) for r in cur.fetchall()]
        for r in rows:
            r["map_warnings"] = (
                json.loads(r["map_warnings_json"])
                if r.get("map_warnings_json")
                else []
            )
            del r["map_warnings_json"]
        return rows
    finally:
        con.close()


def get_job(base_dir: Path, job_id: str) -> dict[str, Any] | None:
    path = db_path(base_dir)
    if not path.exists():
        return None
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    try:
        cur = con.execute(
            """
            SELECT id, created_at, mapping_name, sku_name,
                   ok_count, fail_count, row_count, result_relpath, map_warnings_json
            FROM jobs WHERE id = ?
            """,
            (job_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        d = dict(row)
        d["map_warnings"] = (
            json.loads(d["map_warnings_json"]) if d.get("map_warnings_json") else []
        )
        del d["map_warnings_json"]
        return d
    finally:
        con.close()


def list_job_errors(base_dir: Path, job_id: str) -> list[dict[str, Any]]:
    path = db_path(base_dir)
    if not path.exists():
        return []
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    try:
        cur = con.execute(
            """
            SELECT row_index, reason FROM job_row_errors
            WHERE job_id = ?
            ORDER BY row_index
            """,
            (job_id,),
        )
        return [{"row_index": r["row_index"], "reason": r["reason"]} for r in cur.fetchall()]
    finally:
        con.close()


def result_abs_path(base_dir: Path, relpath: str) -> Path:
    root = base_dir.resolve()
    p = (root / relpath).resolve()
    try:
        p.relative_to(root)
    except ValueError as e:
        raise ValueError("非法结果路径") from e
    return p
