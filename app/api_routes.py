"""HTTP API：上传配对、历史、模板下载。"""

from __future__ import annotations

import logging
import shutil
import tempfile
import uuid
from io import BytesIO
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, Response
from openpyxl import Workbook

from app import jobs as jobs_store
from app.matching import build_short_map, process_sku_table
from app.table_io import load_table, write_result_xlsx

logger = logging.getLogger(__name__)

router = APIRouter(tags=["api"])

ALLOWED_SUFFIX = {".csv", ".xlsx", ".xlsm"}


def _suffix(name: str) -> str:
    return Path(name or "").suffix.lower()


def _base_dir(request: Request) -> Path:
    return request.app.state.base_dir


def _template_mapping_bytes() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "配对关系"
    ws.append(["店铺全称", "店铺简称"])
    ws.append(["示例科技有限公司", "DEMO"])
    bio = BytesIO()
    wb.save(bio)
    return bio.getvalue()


def _template_sku_bytes() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "SKU"
    ws.append(["店铺账号", "Custom Label"])
    ws.append(["示例科技有限公司", "DEMO-SKU001- A *2"])
    bio = BytesIO()
    wb.save(bio)
    return bio.getvalue()


@router.get("/api/jobs")
def api_list_jobs(request: Request):
    return jobs_store.list_jobs(_base_dir(request), limit=100)


@router.get("/api/jobs/{job_id}/errors")
def api_job_errors(job_id: str, request: Request):
    job = jobs_store.get_job(_base_dir(request), job_id)
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在")
    return {
        "job_id": job_id,
        "errors": jobs_store.list_job_errors(_base_dir(request), job_id),
    }


@router.get("/api/jobs/{job_id}/download")
def api_download(job_id: str, request: Request):
    base_dir = _base_dir(request)
    job = jobs_store.get_job(base_dir, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在")
    rel = job["result_relpath"]
    try:
        path = jobs_store.result_abs_path(base_dir, rel)
    except ValueError:
        raise HTTPException(status_code=400, detail="结果路径无效") from None
    if not path.is_file():
        logger.error("结果文件缺失 job=%s path=%s", job_id, path)
        raise HTTPException(status_code=404, detail="结果文件不存在")
    return FileResponse(
        path,
        filename=f"SKU匹配结果_{job_id[:8]}.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@router.get("/api/templates/shop-mapping")
def tpl_mapping():
    body = _template_mapping_bytes()
    return Response(
        content=body,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": 'attachment; filename="店铺简称配对关系表模板.xlsx"'
        },
    )


@router.get("/api/templates/sku-pair")
def tpl_sku():
    body = _template_sku_bytes()
    return Response(
        content=body,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="SKU配对表模板.xlsx"'},
    )


@router.post("/api/match")
async def api_match(
    request: Request,
    mapping: UploadFile = File(..., description="店铺简称配对关系表"),
    sku: UploadFile = File(..., description="SKU 配对表"),
):
    base_dir = _base_dir(request)
    msuf = _suffix(mapping.filename or "")
    ssuf = _suffix(sku.filename or "")
    if msuf not in ALLOWED_SUFFIX or ssuf not in ALLOWED_SUFFIX:
        raise HTTPException(
            status_code=400,
            detail="仅支持 .xlsx / .xlsm / .csv（不支持老版 .xls）",
        )

    tmp_parent = base_dir / "data" / "tmp"
    tmp_parent.mkdir(parents=True, exist_ok=True)
    tmp_root = Path(tempfile.mkdtemp(prefix="match-", dir=tmp_parent))
    map_path = tmp_root / f"mapping{msuf}"
    sku_path = tmp_root / f"sku{ssuf}"
    try:
        map_path.write_bytes(await mapping.read())
        sku_path.write_bytes(await sku.read())

        try:
            map_headers, map_rows = load_table(map_path)
            sku_headers, sku_rows = load_table(sku_path)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

        try:
            full_to_short, map_warnings = build_short_map(map_rows, map_headers)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

        try:
            out_rows = process_sku_table(sku_headers, sku_rows, full_to_short)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

        extra_cols = ["匹配SKU", "数量", "匹配状态", "失败原因"]
        out_headers = list(sku_headers) + [c for c in extra_cols if c not in sku_headers]

        ok_count = sum(1 for r in out_rows if r.get("匹配状态") == "成功")
        fail_count = sum(1 for r in out_rows if r.get("匹配状态") == "失败")
        row_errors: list[tuple[int, str]] = []
        for i, r in enumerate(out_rows, start=2):
            if r.get("匹配状态") == "失败":
                reason = str(r.get("失败原因") or "未知原因")
                row_errors.append((i, reason))

        jid = str(uuid.uuid4())
        job_dir = base_dir / "data" / "jobs" / jid
        job_dir.mkdir(parents=True, exist_ok=True)
        result_path = job_dir / "result.xlsx"
        write_result_xlsx(result_path, out_headers, out_rows)
        relpath = str(result_path.relative_to(base_dir))

        jobs_store.insert_job(
            base_dir,
            job_id=jid,
            mapping_name=mapping.filename or "mapping",
            sku_name=sku.filename or "sku",
            ok_count=ok_count,
            fail_count=fail_count,
            row_count=len(out_rows),
            result_relpath=relpath,
            map_warnings=map_warnings,
            row_errors=row_errors,
        )

        logger.info(
            "匹配完成 job=%s ok=%s fail=%s warnings=%s",
            jid,
            ok_count,
            fail_count,
            len(map_warnings),
        )

        return {
            "job_id": jid,
            "ok_count": ok_count,
            "fail_count": fail_count,
            "row_count": len(out_rows),
            "map_warnings": map_warnings,
            "download_url": f"/api/jobs/{jid}/download",
        }
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)
