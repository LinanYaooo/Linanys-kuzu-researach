"""
自定义 SQL 抽取 — 用自定义查询语句从源端抽取，支持增量 WHERE 追加

用法: python tasks/etl_custom_sql.py
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from kuzu_etl import ETLTask

task = ETLTask(
    # ── 源端数据库 ──────────────────────────────────────────────
    source_db="postgresql",
    source_host="localhost",
    source_port=5432,
    source_username="______",              # ← 填写用户名
    source_password="______",              # ← 填写密码
    source_database="______",              # ← 填写数据库名

    # ── 自定义查询 SQL ──────────────────────────────────────────
    # 设置 source_query 后忽略 source_table 和 fields
    # 增量模式时，WHERE 片段会自动追加（已有 WHERE 则追加 AND）
    source_query="""
        SELECT id, name, score
        FROM account
        WHERE active = true
    """,

    # ── 抽取字段映射 ────────────────────────────────────────────
    # 自定义 SQL 必须手动指定映射（无法自动检测列名）
    fields=[
        {"source_field": "id",    "target_property": "id"},
        {"source_field": "name",  "target_property": "name"},
        {"source_field": "score", "target_property": "score"},
    ],

    # ── 目标 Kuzu ───────────────────────────────────────────────
    target_server="http://127.0.0.1:8000/api/v1",
    target_entity="______",                # ← 填写 Kuzu 节点表名

    # ── 增量配置（可选） ────────────────────────────────────────
    # 启用后，where_fragment 会追加到 source_query 末尾
    # incremental=True,
    # where_fragment="updated_at > '${watermark}'",
    # watermark_field="updated_at",
    # watermark_value="2025-01-01",

    batch_size=500,
)

result = task.run()
print(f"自定义 SQL 抽取完成: extracted={result.extracted} written={result.written} elapsed={result.elapsed_ms}ms")
if result.error:
    print(f"错误: {result.error}")
