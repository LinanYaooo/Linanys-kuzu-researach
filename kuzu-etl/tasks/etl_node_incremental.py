"""
节点增量抽取 — 从源端表按水位线增量抽取写入 Kuzu 节点表

用法: python tasks/etl_node_incremental.py
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from kuzu_etl import ETLTask

task = ETLTask(
    # ── 源端数据库 ──────────────────────────────────────────────
    source_db="sqlite",
    source_database=os.path.join(os.path.dirname(__file__), "source.db"),
    source_table="______",                 # ← 填写源端表名

    # ── 抽取字段映射 ────────────────────────────────────────────
    fields=[
        # {"source_field": "id",    "target_property": "id"},
        # {"source_field": "name",  "target_property": "name"},
    ],

    # ── 目标 Kuzu ───────────────────────────────────────────────
    target_server="http://127.0.0.1:8000/api/v1",
    target_entity="______",                # ← 填写 Kuzu 节点表名

    # ── 增量配置 ────────────────────────────────────────────────
    incremental=True,
    where_fragment="______ > '${watermark}'",  # ← 填写过滤字段，如 updated_at > '${watermark}'
    watermark_field="______",              # ← 填写水位线字段名，如 updated_at
    watermark_value="______",              # ← 填写初始水位线值，如 2025-01-01

    batch_size=500,
)

result = task.run()
print(f"增量抽取完成: extracted={result.extracted} written={result.written} elapsed={result.elapsed_ms}ms")
print(f"水位线更新为: {task.incremental.watermark_value}")
if result.error:
    print(f"错误: {result.error}")
