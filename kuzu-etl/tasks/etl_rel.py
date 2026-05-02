"""
边表写入 — 从源端关系表抽取数据写入 Kuzu 边表

用法: python tasks/etl_rel.py
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from kuzu_etl import ETLTask

task = ETLTask(
    # ── 源端数据库 ──────────────────────────────────────────────
    source_db="sqlite",
    source_database=os.path.join(os.path.dirname(__file__), "source.db"),
    source_table="______",                 # ← 填写源端关系表名

    # ── 抽取字段映射 ────────────────────────────────────────────
    # _from_id / _to_id 是特殊的目标属性，用于 MATCH 起点终点节点
    fields=[
        {"source_field": "______", "target_property": "_from_id"},  # ← 起点节点 ID 的源字段
        {"source_field": "______", "target_property": "_to_id"},    # ← 终点节点 ID 的源字段
        # {"source_field": "since",  "target_property": "since"},
    ],

    # ── 目标 Kuzu 边表 ──────────────────────────────────────────
    target_server="http://127.0.0.1:8000/api/v1",
    target_entity="______",                # ← 填写 Kuzu 边表名，如 AccountCreatesPost
    target_is_rel=True,
    target_rel_from="______",              # ← 起点实体名，如 Account
    target_rel_to="______",                # ← 终点实体名，如 PostItem

    batch_size=500,
)

result = task.run()
print(f"边表写入完成: extracted={result.extracted} written={result.written} elapsed={result.elapsed_ms}ms")
if result.error:
    print(f"错误: {result.error}")
