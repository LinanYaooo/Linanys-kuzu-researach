import csv
import io
import os
import tempfile
import time

from fastapi import APIRouter, HTTPException, Request

from app.db import get_db
from app.models import QueryResponse

router = APIRouter()


@router.post(
    "/import/{table_name}",
    response_model=QueryResponse,
    summary="批量导入 CSV 数据",
    description="上传 CSV 内容并通过 COPY FROM 批量导入到指定节点表或边表。"
                "请求体直接为 CSV 文本（Content-Type: text/csv），首行必须为列名（与表属性对应）。"
                "比逐条 CREATE 快一个数量级，适合大批量数据导入。",
    responses={400: {"description": "导入失败"}},
)
async def bulk_import(table_name: str, request: Request):
    db = get_db()
    start = time.perf_counter()
    try:
        text_content = (await request.body()).decode("utf-8")

        reader = csv.reader(io.StringIO(text_content))
        try:
            header = next(reader)
        except StopIteration:
            raise ValueError("CSV file is empty")

        tmp_path = None
        try:
            fd, tmp_path = tempfile.mkstemp(suffix=".csv")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(text_content)

            # Use forward slashes to avoid Cypher escape issues on Windows
            safe_path = tmp_path.replace("\\", "/")
            query = f"COPY {table_name} FROM '{safe_path}' (HEADER=true)"
            with db._lock:
                conn = db._get_conn()
                try:
                    result = conn.execute(query)
                finally:
                    db._put_conn(conn)

            rows = db.result_to_dicts(result)
            elapsed_ms = (time.perf_counter() - start) * 1000
            return QueryResponse(results=rows, count=len(rows), elapsed_ms=round(elapsed_ms, 2))
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
