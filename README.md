# Linany's Kuzu Research

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.13](https://img.shields.io/badge/Python-3.13-blue.svg)](https://www.python.org/)
[![Kuzu](https://img.shields.io/badge/Kuzu-0.11.3-green.svg)](https://kuzudb.com/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg)](https://fastapi.tiangolo.com/)

基于 [Kuzu](https://kuzudb.com/) 图数据库的全栈研究项目，涵盖 REST API 服务、ETL 数据管道、性能基准测试与压力测试，以及内置的可视化前端。

## 项目架构

```
Linany's/
├── kuzu-server/            # FastAPI REST API 服务 + 可视化前端
├── kuzu-etl/               # 关系型数据库 → Kuzu 的 ETL 工具
├── kuzu-test/              # 基准测试 & 内存分析（20M 节点 + 39M 边）
├── kuzu-server-stress/     # HTTP 压力测试套件（7 阶段压测 + HTML 报告）
└── data/                   # 共享数据库文件
```

## 子项目概览

| 子项目 | 语言/框架 | 用途 |
|--------|-----------|------|
| **kuzu-server** | Python / FastAPI / Vue 3 | Kuzu 图数据库 REST API，含 Swagger 文档与 vis-network 图谱可视化前端 |
| **kuzu-etl** | Python / SQLAlchemy / httpx | 从 PostgreSQL / MySQL / SQLite 抽取数据写入 Kuzu，支持全量/增量/自定义 SQL |
| **kuzu-test** | Python / kuzu | 生成 20M 节点 + 39M 边的大规模合成数据集，运行 26 项查询基准测试与内存占用分析 |
| **kuzu-server-stress** | Python / urllib | 对 kuzu-server 全部 API 执行 7 阶段压力测试，输出暗色主题 HTML 报告 |

---

## kuzu-server — REST API 服务

基于 FastAPI 的 Kuzu 图数据库 REST API 服务，内置可视化前端，支持 Swagger 交互式测试。

### 快速启动

```bash
cd kuzu-server
pip install -r requirements.txt
python server.py
```

启动后访问：
- 可视化界面：http://localhost:8000
- Swagger API 文档：http://localhost:8000/docs
- ReDoc 文档：http://localhost:8000/redoc

### 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `KUZU_DB_PATH` | `../kuzu-test/test_db` | Kuzu 数据库文件路径 |
| `KUZU_BUFFER_POOL_MB` | `0` | 缓冲池大小（MB），0 为自动 |
| `KUZU_POOL_SIZE` | `8` | 连接池大小 |

### API 端点

#### 查询

| 方法 | 端点 | 说明 |
|------|------|------|
| `POST` | `/api/v1/query` | 执行 Cypher 查询，返回扁平行数据（无锁并发，适合读操作） |
| `POST` | `/api/v1/query/safe` | 线程安全查询（加锁串行化，适合写操作） |
| `POST` | `/api/v1/query/graph` | 图谱可视化查询，返回节点+边分离格式 |
| `GET` | `/api/v1/query/history` | 获取最近 100 条查询历史 |
| `DELETE` | `/api/v1/query/history` | 清空查询历史 |

#### Schema

| 方法 | 端点 | 说明 |
|------|------|------|
| `GET` | `/api/v1/schema` | 完整数据库 Schema（含属性定义） |
| `GET` | `/api/v1/schema/nodes` | 节点表列表 |
| `GET` | `/api/v1/schema/edges` | 边表列表 |

#### 批量导入

| 方法 | 端点 | 说明 |
|------|------|------|
| `POST` | `/api/v1/import/{table_name}` | 上传 CSV 批量导入（Content-Type: text/csv） |

#### 健康检查

| 方法 | 端点 | 说明 |
|------|------|------|
| `GET` | `/api/v1/health` | 数据库连接状态与统计 |

### 核心架构

- **连接池**：`KuzuDatabase` 内置基于 `Queue` 的连接池，避免每次请求创建连接的开销（8GB 数据库下创建连接约需 2 秒，复用后降至毫秒级）
- **结果转换**：`result_to_dicts()` 输出扁平行数据，`result_to_graph()` 解析 Kuzu 内部 `_id`/`_src`/`_dst` 结构，拆分为节点+边
- **并发安全**：`/query` 无锁并发（读多写少），`/query/safe` 加 `threading.Lock` 串行化（写操作）

### 可视化前端

内置单文件 Vue 3 SPA（512 行），暗色主题，功能包括：

- Cypher 编辑器（Ctrl+Enter 执行）
- Schema 侧边栏（点击生成示例查询）
- History 侧边栏（localStorage 持久化 + 服务端缓存）
- 结果三格式展示：Graph（vis-network 力导向图）、Table（Element Plus 数据表格）、JSON（语法高亮）
- 健康状态指示灯（30 秒自动刷新）

技术栈：Vue 3 (CDN) + vis-network + Element Plus (暗色主题)

### 项目结构

```
kuzu-server/
├── server.py                  # 启动入口（uvicorn）
├── requirements.txt           # Python 依赖
├── schemas/
│   └── test_db/
│       └── init.cypher        # 数据库建表语句（20 节点表 + 17 边表）
├── app/
│   ├── main.py                # FastAPI 应用：生命周期、CORS、路由注册
│   ├── db.py                  # Kuzu 数据库封装：连接池、查询、结果转换
│   ├── models.py              # Pydantic 请求/响应模型
│   ├── static/
│   │   └── index.html         # 可视化前端 SPA
│   └── routers/
│       ├── query.py           # 查询执行、图谱查询、历史记录
│       ├── schema.py          # Schema 元数据查询
│       ├── health.py          # 健康检查
│       └── bulk.py            # CSV 批量导入
```

---

## kuzu-etl — ETL 工具

从关系型数据库（PostgreSQL / MySQL / SQLite）抽取数据写入 Kuzu 图数据库。

### 工作原理

```
源端数据库 ──extract──▶ 字段映射/转换 ──write──▶ Kuzu Server HTTP API
```

- **Extract**：通过 SQLAlchemy 流式读取，按批次返回
- **Transform**：按字段映射重命名，支持 `transform` 表达式做值转换
- **Load**：生成 Cypher 语句，通过 `/api/v1/import` 批量写入

### 安装

```bash
cd kuzu-etl
pip install -r requirements.txt
```

### 使用示例

**节点全量抽取**：

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
    fields=[
        {"source_field": "id",    "target_property": "id"},
        {"source_field": "name",  "target_property": "name", "transform": "str(value).strip()"},
    ],
    target_entity="Account",
)
result = task.run()
print(result)  # extracted=100 written=100 elapsed_ms=523.4
```

**节点增量抽取**：

```python
task = ETLTask(
    source_db="postgresql",
    # ... 源端配置 ...
    incremental=True,
    where_fragment="updated_at > '${watermark}'",
    watermark_field="updated_at",
    watermark_value="2025-01-01",
    target_entity="Account",
)
result = task.run()
```

**边（关系）写入**：

```python
task = ETLTask(
    # ... 源端配置 ...
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
```

### 任务模板

`tasks/` 目录提供即用模板：

| 模板 | 用途 |
|------|------|
| `etl_node_full.py` | 节点全量抽取 |
| `etl_node_incremental.py` | 节点增量抽取 |
| `etl_rel.py` | 边表写入 |
| `etl_custom_sql.py` | 自定义 SQL 抽取 |

### 关键特性

- 支持 PostgreSQL、MySQL、SQLite 三种源端数据库
- 自动映射源端列名到 Kuzu 属性（同名映射），也可手动指定字段映射与转换表达式
- 增量模式按水位线抽取新增/变更数据，水位线自动更新
- 自动建表：ETL 时若目标表不存在，根据源端列类型自动创建
- 多线程并行写入（4 写线程 + 队列缓冲），带进度条显示

---

## kuzu-test — 基准测试与内存分析

基于大规模合成数据集对 Kuzu 进行系统化性能评测。

### 数据集规模

| 指标 | 数量 |
|------|------|
| 节点表 | 20 个（Account, Product, OrderItem, ...） |
| 每表行数 | 1,000,000 行 |
| 每表属性 | 60 个（INT64 / DOUBLE / STRING / BOOL） |
| 节点总数 | 20,000,000 |
| 边表 | 17 个 |
| 边总数 | ~39,000,000 |

### 安装与运行

```bash
cd kuzu-test
pip install -r requirements.txt

# 1. 生成测试数据并建库（首次运行耗时较长）
python seed.py

# 2. 查询性能基准测试（26 项，每项 5 轮）
python benchmark.py

# 3. 内存占用分析（需额外安装 psutil）
pip install psutil
python mem_profile.py
```

### 基准测试覆盖场景

| 类别 | 测试项 |
|------|--------|
| 计数 | 单表 COUNT / 全图 COUNT / 全边 COUNT |
| 主键点查 | 不同 id 值的精确匹配 |
| 数值过滤 | 单条件 / 多条件 WHERE |
| 字符串过滤 | 精确匹配 / 前缀匹配 |
| 聚合 | AVG / MIN/MAX / GROUP BY + COUNT |
| 排序+分页 | ORDER BY + LIMIT |
| 多列投影 | 5 列 / 20 列 + LIMIT 1000 |
| 1 跳遍历 | 单边类型 / 带过滤条件 |
| 2 跳遍历 | 双跳路径 |
| 边聚合 | 出度 / 入度统计 |

### 数据模型

**节点表（20 个）**：Account, Product, OrderItem, Category, Tag, CommentItem, PostItem, GroupItem, EventItem, LocationItem, Company, Department, ProjectItem, TaskItem, ReviewItem, PhotoItem, VideoItem, ArticleItem, CourseItem, CertificateItem

**边表（17 个）**：

| 边名 | 起点 → 终点 | 数量 |
|------|-------------|------|
| AccountCreatesPost | Account → PostItem | 3M |
| AccountWritesComment | Account → CommentItem | 5M |
| AccountJoinsGroup | Account → GroupItem | 2M |
| AccountPlacesOrder | Account → OrderItem | 4M |
| AccountWritesReview | Account → ReviewItem | 3M |
| AccountWorksAtCompany | Account → Company | 1M |
| AccountAttendsEvent | Account → EventItem | 2M |
| AccountEnrollsCourse | Account → CourseItem | 1.5M |
| AccountEarnsCert | Account → CertificateItem | 1M |
| PostHasTag | PostItem → Tag | 2M |
| PostInCategory | PostItem → Category | 1M |
| ProductInCategory | Product → Category | 1M |
| ProductHasReview | Product → ReviewItem | 3M |
| OrderContainsProduct | OrderItem → Product | 6M |
| CompanyHasDept | Company → Department | 0.5M |
| ProjectHasTask | ProjectItem → TaskItem | 2M |
| EventAtLocation | EventItem → LocationItem | 1M |

---

## kuzu-server-stress — 压力测试套件

面向 kuzu-server 全部 API 接口执行 7 阶段压力测试，生成暗色主题 HTML 报告。

### 运行

```bash
cd kuzu-server-stress
python stress_test.py [--base URL] [--concurrency 1,5,10,20,50] [--requests 20] [--output report.html]
```

### 压测阶段

| 阶段 | 说明 |
|------|------|
| 1. Sequential Baseline | 顺序基线，逐个请求测量原始延迟 |
| 2. Concurrent Test | 多并发级别并发测试（avg / p50 / p90 / p95 / p99 / stdev / QPS） |
| 3. Concurrency Scaling | 1→N 并发扩展性追踪，观察延迟随并发增长趋势 |
| 4. Throughput Test | 最大并发下吞吐量测试 |
| 5. Mixed Workload | 全查询类型交织混合负载 |
| 6. Sustained Load | 60 秒持续负载稳定性测试 |
| 7. Conclusions | 自动生成压测结论（吞吐量/延迟/稳定性/扩展性/慢查询识别） |

### 测试覆盖接口

覆盖 kuzu-server 全部端点：`GET /health`、`GET /schema`、`GET /schema/nodes`、`GET /schema/edges`、`GET /query/history`、`DELETE /query/history`、`POST /query`（7 种查询）、`POST /query/safe`（7 种查询）、`POST /query/graph`（6 种查询）

---

## 性能参考

测试环境：8.1GB 数据库，20M 节点 + 39M 边，Python 3.13，Windows 11

| 查询类型 | HTTP 延迟 (p50) |
|----------|----------------|
| 主键点查 | 17ms |
| 单表 COUNT | 26ms |
| 数值过滤 | 44ms |
| 聚合 | 55ms |
| GROUP BY | 257ms |
| 1-hop 遍历 | 203ms |
| 2-hop 遍历 | 421ms |
| 混合并发吞吐 (10 workers) | 34 QPS |

内存占用：8.1GB 数据库，冷启动后首次全库扫描内存约 497MB（占磁盘 6%）。

---

## 技术栈总览

| 层级 | 技术 |
|------|------|
| 图数据库 | [Kuzu](https://kuzudb.com/) >= 0.11.3 |
| Web 框架 | FastAPI + Uvicorn |
| 数据验证 | Pydantic v2 |
| ETL 源端 | SQLAlchemy 2.0 + psycopg2 / pymysql |
| HTTP 客户端 | httpx |
| 前端 | Vue 3 + Element Plus + vis-network |
| 语言 | Python 3.13 |

## License

MIT
