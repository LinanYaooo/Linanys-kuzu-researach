# kuzu-etl

从关系型数据库（PostgreSQL / MySQL / SQLite）抽取数据，写入 [Kuzu](https://kuzudb.com/) 图数据库的 ETL 工具。

## 工作原理

```
源端数据库 ──extract──▶ 字段映射/转换 ──write──▶ Kuzu Server HTTP API
```

- **Extract**：通过 SQLAlchemy 流式读取源端数据，按批次返回
- **Transform**：按字段映射重命名，支持 `transform` 表达式做值转换
- **Load**：生成 Cypher 语句，通过 Kuzu Server 的 `/api/v1/query/safe` 接口批量写入

## 安装

```bash
pip install -r requirements.txt
```

依赖：`pydantic` `httpx` `sqlalchemy` `psycopg2-binary` `pymysql`

> PostgreSQL 用户需要 `psycopg2-binary`，MySQL 用户需要 `pymysql`，SQLite 无额外依赖。

## 前置条件

Kuzu Server 需要已启动并可访问，默认地址 `http://127.0.0.1:8000`：

```bash
kuzu-server --port 8000 /path/to/your.kuzu
```

## 快速开始

### 1. 节点全量抽取

从源端表全量读取所有行写入 Kuzu 节点表：

```python
from kuzu_etl import ETLTask

task = ETLTask(
    source_db="postgresql",
    source_host="localhost",
    source_port=5432,
    source_username="postgres",
    source_password="your_password",
    source_database="mydb",
    source_table="account",

    # 留空则自动映射源端所有列（列名 = 属性名）
    # 需要改名或转换时手动指定：
    fields=[
        {"source_field": "id",    "target_property": "id"},
        {"source_field": "name",  "target_property": "name", "transform": "str(value).strip()"},
    ],

    target_entity="Account",
)

result = task.run()
print(result)  # extracted=100 written=100 elapsed_ms=523.4
```

也可直接编辑 `tasks/etl_node_full.py` 模板然后运行：

```bash
python tasks/etl_node_full.py
```

### 2. 节点增量抽取

按水位线只抽取新增/变更数据：

```python
task = ETLTask(
    source_db="postgresql",
    source_host="localhost",
    source_username="postgres",
    source_password="your_password",
    source_database="mydb",
    source_table="account",

    incremental=True,
    where_fragment="updated_at > '${watermark}'",
    watermark_field="updated_at",
    watermark_value="2025-01-01",  # 首次运行的起始水位线

    target_entity="Account",
)

result = task.run()
# 运行后水位线自动更新，下次 run() 只抽取新数据
print(f"新水位线: {task.incremental.watermark_value}")
```

### 3. 边（关系）写入

从关系表抽取数据写入 Kuzu 边表：

```python
task = ETLTask(
    source_db="postgresql",
    source_host="localhost",
    source_username="postgres",
    source_password="your_password",
    source_database="mydb",
    source_table="account_post",

    # _from_id 和 _to_id 是特殊属性，用于 MATCH 起终点节点
    fields=[
        {"source_field": "account_id", "target_property": "_from_id"},
        {"source_field": "post_id",    "target_property": "_to_id"},
        {"source_field": "since",      "target_property": "since"},
    ],

    target_entity="Creates",
    target_is_rel=True,
    target_rel_from="Account",
    target_rel_to="PostItem",
)

result = task.run()
```

### 4. 自定义 SQL

使用自定义查询语句抽取，支持增量 WHERE 追加：

```python
task = ETLTask(
    source_db="postgresql",
    source_host="localhost",
    source_username="postgres",
    source_password="your_password",
    source_database="mydb",

    # 设置 source_query 后忽略 source_table 和 fields 的自动检测
    # 增量模式时，where_fragment 自动追加到 SQL 末尾
    source_query="""
        SELECT id, name, score
        FROM account
        WHERE active = true
    """,

    # 自定义 SQL 必须手动指定字段映射
    fields=[
        {"source_field": "id",    "target_property": "id"},
        {"source_field": "name",  "target_property": "name"},
        {"source_field": "score", "target_property": "score"},
    ],

    target_entity="ActiveAccount",

    # 增量可选
    # incremental=True,
    # where_fragment="updated_at > '${watermark}'",
    # watermark_field="updated_at",
    # watermark_value="2025-01-01",
)

result = task.run()
```

## 参数说明

### 源端配置

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `source_db` | 数据库类型：`postgresql` / `mysql` / `sqlite` | `sqlite` |
| `source_host` | 主机地址（SQLite 不需要） | `None` |
| `source_port` | 端口（PG 默认 5432，MySQL 默认 3306） | `None` |
| `source_username` | 用户名 | `None` |
| `source_password` | 密码 | `None` |
| `source_database` | 数据库名 / SQLite 文件路径 | `""` |
| `source_schema` | PostgreSQL schema | `None` |
| `source_table` | 源端表名 | `""` |
| `source_query` | 自定义 SQL（设置后忽略 `source_table`） | `None` |

### 字段映射

| 字段 | 说明 |
|------|------|
| `source_field` | 源端列名 |
| `target_property` | Kuzu 端属性名 |
| `transform` | 值转换表达式，可选。如 `"str(value).strip()"`、`"int(value or 0)"` |

`fields` 留空时，自动获取源端表所有列并同名映射。

### 目标配置

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `target_server` | Kuzu Server 地址 | `http://127.0.0.1:8000/api/v1` |
| `target_entity` | Kuzu 节点表名或边表名 | `""` |
| `target_is_rel` | 是否写入边表 | `False` |
| `target_rel_from` | 边起点实体名（`target_is_rel=True` 时必填） | `None` |
| `target_rel_to` | 边终点实体名（`target_is_rel=True` 时必填） | `None` |

### 增量配置

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `incremental` | 是否启用增量模式 | `False` |
| `where_fragment` | WHERE 条件片段，支持 `${watermark}` 占位符 | `""` |
| `watermark_field` | 水位线字段名（如 `updated_at`） | `None` |
| `watermark_value` | 水位线初始值（如 `2025-01-01`） | `None` |

### 其他

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `batch_size` | 每批次抽取行数 | `500` |

## 任务模板

`tasks/` 目录提供即用模板，填写 `______` 部分后直接运行：

| 模板 | 用途 |
|------|------|
| `etl_node_full.py` | 节点全量抽取 |
| `etl_node_incremental.py` | 节点增量抽取 |
| `etl_rel.py` | 边表写入 |
| `etl_custom_sql.py` | 自定义 SQL 抽取 |

```bash
# 编辑模板后运行
python tasks/etl_node_full.py
```

## 运行结果

`task.run()` 返回 `RunResult` 对象：

| 字段 | 说明 |
|------|------|
| `extracted` | 从源端读取的行数 |
| `written` | 成功写入 Kuzu 的行数 |
| `elapsed_ms` | 耗时（毫秒） |
| `error` | 错误信息，为空表示成功 |
