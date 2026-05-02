"""
节点全量抽取 — 从源端表全量抽取数据写入 Kuzu 节点表

用法: python tasks/etl_node_full.py
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from kuzu_etl import ETLTask

task = ETLTask(
    # ── 源端数据库 ──────────────────────────────────────────────
    source_db="sqlite",                    # postgresql / mysql / sqlite
    # source_host="localhost",
    # source_port=5432,
    # source_username="postgres",
    # source_password="______",
    source_database=os.path.join(os.path.dirname(__file__), "source.db"),  # SQLite 文件路径，PG/MySQL 改为数据库名
    source_schema=None,                    # PostgreSQL schema，MySQL/SQLite 留 None
    source_table="______",                 # ← 填写源端表名

    # ── 抽取字段映射 ────────────────────────────────────────────
    # 为空则自动获取全表所有字段（source_field = target_property）
    # 需要改名或转换时手动指定：
    fields=[
        # {"source_field": "id",    "target_property": "id"},
        # {"source_field": "name",  "target_property": "name", "transform": "str(value).strip()"},
        # {"source_field": "score", "target_property": "score", "transform": "float(value or 0)"},
    ],

    # ── 目标 Kuzu ───────────────────────────────────────────────
    target_server="http://127.0.0.1:8000/api/v1",
    target_entity="______",                # ← 填写 Kuzu 节点表名，如 Account

    # ── 批次大小 ────────────────────────────────────────────────
    batch_size=500,
)

result = task.run()
print(f"全量抽取完成: extracted={result.extracted} written={result.written} elapsed={result.elapsed_ms}ms")
if result.error:
    print(f"错误: {result.error}")
