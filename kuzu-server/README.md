# Kuzu API Server

基于 FastAPI 的 Kuzu 图数据库 REST API 服务，内置可视化前端，支持 Swagger 交互式测试。

## 项目结构

```
kuzu-server/
├── server.py                  # 启动入口（uvicorn）
├── requirements.txt           # Python 依赖
├── README.md                  # 项目文档
├── .gitignore
├── schemas/
│   └── test_db/
│       └── init.cypher        # 数据库建表语句（20节点表 + 17边表）
├── app/
│   ├── __init__.py
│   ├── main.py                # FastAPI 应用：生命周期、CORS、路由注册、静态文件、Swagger 配置
│   ├── db.py                  # Kuzu 数据库封装：连接池、查询、结果转换（dict/graph）
│   ├── models.py              # Pydantic 请求/响应模型（含 Field 描述和示例值）
│   ├── static/
│   │   └── index.html         # 可视化前端 SPA（Vue 3 + vis-network + Element Plus 暗色主题）
│   └── routers/
│       ├── __init__.py
│       ├── query.py           # 查询执行、图谱查询、历史记录（含中文 Swagger 注释）
│       ├── schema.py          # Schema 元数据查询（含中文 Swagger 注释）
│       └── health.py          # 健康检查（含中文 Swagger 注释）
```

## 快速启动

```bash
# 安装依赖
pip install -r requirements.txt

# 启动服务（默认连接 ../kuzu-test/test_db）
python server.py

# 指定数据库路径
KUZU_DB_PATH=/path/to/your_db python server.py

# 自定义连接池大小和缓冲区
KUZU_DB_PATH=./my_db KUZU_POOL_SIZE=16 KUZU_BUFFER_POOL_MB=2048 python server.py
```

启动后访问：
- 可视化界面：http://localhost:8000
- Swagger API 文档：http://localhost:8000/docs（支持在线测试所有接口）
- ReDoc 文档：http://localhost:8000/redoc

## 环境变量

| 变量 | 默认值 | 说明 |
|---|---|---|
| `KUZU_DB_PATH` | `../kuzu/test_db` | Kuzu 数据库文件路径 |
| `KUZU_BUFFER_POOL_MB` | `0` | 缓冲池大小（MB），0 为自动 |
| `KUZU_POOL_SIZE` | `8` | 连接池大小 |

## API 端点

所有端点均已在 Swagger（`/docs`）中标注中文说明、请求/响应模型和示例值，可直接在线测试。

### 查询

#### `POST /api/v1/query`
执行 Cypher 查询，返回扁平行数据。支持 DDL/DML/DQL 全部语句。

```json
// 请求
{ "query": "MATCH (n:Account) RETURN n.id, n.name LIMIT 5" }

// 响应
{
  "results": [
    { "n.id": 0, "n.name": "rowpsuqt" },
    { "n.id": 1, "n.name": "ekrzbmkr" }
  ],
  "count": 2,
  "elapsed_ms": 5.23
}
```

#### `POST /api/v1/query/safe`
线程安全的查询执行（加锁串行化），适用于写操作。请求/响应格式同上。

#### `POST /api/v1/query/graph`
执行图谱可视化查询，返回节点+边分离格式。仅适用于返回 NODE/REL 类型列的查询。

```json
// 请求
{ "query": "MATCH (a:Account)-[e:AccountCreatesPost]->(p:PostItem) RETURN a,e,p LIMIT 3" }

// 响应
{
  "nodes": [
    { "id": "0_450543", "label": "rowpsuqt", "group": "Account", "properties": { "id": 0, "name": "rowpsuqt", ... } },
    { "id": "6_951861", "label": "cwbdehst", "group": "PostItem", "properties": { "id": 22566, ... } }
  ],
  "edges": [
    { "from_": "0_450543", "to": "6_951861", "label": "AccountCreatesPost", "properties": { "since": 2025, ... } }
  ],
  "node_count": 2,
  "edge_count": 1,
  "elapsed_ms": 42.5
}
```

#### `GET /api/v1/query/history`
返回服务端内存中最近 100 条查询历史。

```json
[
  { "id": "0d41c4ec", "query": "MATCH (n) RETURN n LIMIT 10", "timestamp": 1777602704.45, "result_count": 10, "elapsed_ms": 5.23 }
]
```

#### `DELETE /api/v1/query/history`
清空查询历史。

### Schema

#### `GET /api/v1/schema`
返回完整数据库 Schema，含所有节点表和边表的属性定义。

```json
{
  "node_tables": [
    { "name": "Account", "properties": [ {"name": "id", "type": "INT64"}, {"name": "name", "type": "STRING"}, ... ] }
  ],
  "rel_tables": [
    { "name": "AccountCreatesPost", "src": "Account", "dst": "PostItem", "properties": [ {"name": "since", "type": "INT64"}, ... ] }
  ]
}
```

#### `GET /api/v1/schema/nodes`
仅返回节点表列表。

#### `GET /api/v1/schema/edges`
仅返回边表列表。

### 健康检查

#### `GET /api/v1/health`

```json
{ "status": "ok", "db_path": "../data/test_db", "node_count": 20000000, "edge_count": 39000000 }
```

## 数据库 Schema

当前数据库包含 20 个节点表（各 60 属性）和 17 个边表，详见 `schemas/test_db/init.cypher`。

**节点表**：Account, Product, OrderItem, Category, Tag, CommentItem, PostItem, GroupItem, EventItem, LocationItem, Company, Department, ProjectItem, TaskItem, ReviewItem, PhotoItem, VideoItem, ArticleItem, CourseItem, CertificateItem

**边表**：

| 边表 | 起点 → 终点 |
|---|---|
| AccountCreatesPost | Account → PostItem |
| AccountWritesComment | Account → CommentItem |
| AccountJoinsGroup | Account → GroupItem |
| AccountPlacesOrder | Account → OrderItem |
| AccountWritesReview | Account → ReviewItem |
| AccountWorksAtCompany | Account → Company |
| AccountAttendsEvent | Account → EventItem |
| AccountEnrollsCourse | Account → CourseItem |
| AccountEarnsCert | Account → CertificateItem |
| PostHasTag | PostItem → Tag |
| PostInCategory | PostItem → Category |
| ProductInCategory | Product → Category |
| ProductHasReview | Product → ReviewItem |
| OrderContainsProduct | OrderItem → Product |
| CompanyHasDept | Company → Department |
| ProjectHasTask | ProjectItem → TaskItem |
| EventAtLocation | EventItem → LocationItem |

## 可视化前端

内置单文件 Vue 3 SPA，通过 `http://localhost:8000` 访问。

### 功能

- **Cypher 编辑器** — 代码输入，Ctrl+Enter 执行，方向键/光标操作正常
- **Schema 侧边栏** — 浏览节点表/边表及属性，点击生成示例查询
- **History 侧边栏** — 查询历史记录，点击回填编辑器（localStorage 持久化 + 服务端缓存）
- **结果三格式展示**
  - **Graph** — vis-network 力导向图，节点按表类型着色，支持拖拽/缩放/点击查看属性详情
  - **Table** — Element Plus 暗色主题数据表格，列排序、分页（50行/页）
  - **JSON** — 原始 JSON 语法高亮
- **健康状态** — 右上角显示 DB 连接状态和节点/边总数（30秒自动刷新）

### 技术栈

| 组件 | 技术 |
|---|---|
| 框架 | Vue 3 (CDN) |
| 图谱可视化 | vis-network |
| UI 组件库 | Element Plus (暗色主题 + dark/css-vars) |
| 托管 | FastAPI StaticFiles |

## 核心架构

### 连接池

`KuzuDatabase` 内置基于 `Queue` 的连接池（默认 8 连接），避免每次请求创建 `kuzu.Connection` 的开销。8GB 数据库下创建连接约需 2 秒，复用后单次查询降至毫秒级。

```
请求 → Queue.get(conn) → conn.execute(query) → Queue.put(conn) → 响应
```

### 结果转换

- `result_to_dicts()` — 扁平行数据，适用于 Table/JSON 展示
- `result_to_graph()` — 解析 Kuzu 内部 `_id`/`_src`/`_dst` 结构，拆分为节点+边，适用于 Graph 展示

### 并发安全

- `/query` — 无锁并发，适合读多写少场景
- `/query/safe` — 加 `threading.Lock` 串行化，适合写操作和 DDL

### Swagger 集成

- 所有端点标注中文 `summary`/`description`/`docstring`
- Pydantic 模型字段均有 `Field(description=...)` 和 `examples`
- 路由标签使用中文名（"查询 Query"、"Schema 元数据"、"健康检查 Health"）
- 访问 `/docs` 可直接在线测试全部接口

## Cypher 脚本示例

以下示例可通过 Swagger（`/docs`）、可视化前端或 `POST /api/v1/query` 执行。

### DDL — 建表

```cypher
-- 创建节点表
CREATE NODE TABLE Person (id INT64, name STRING, age INT64, email STRING, PRIMARY KEY (id));

-- 创建边表（多对多关系）
CREATE REL TABLE Knows (FROM Person TO Person, since INT64, weight DOUBLE);

-- 创建边表（一对多关系）
CREATE REL TABLE HasPost (FROM Person TO PostItem, created_at STRING);
```

### DDL — 修改表结构

```cypher
-- 删除表（会同时删除关联的边表中引用该表的记录）
DROP TABLE Person;

-- 添加属性（Kuzu 通过 ALTER TABLE 支持）
ALTER TABLE Person ADD nickname STRING DEFAULT '';
```

### DML — 创建节点和边

```cypher
-- 创建单个节点
CREATE (p:Person {id: 1, name: 'Alice', age: 30, email: 'alice@example.com'});

-- 批量创建节点
CREATE (p1:Person {id: 2, name: 'Bob', age: 25, email: 'bob@example.com'}),
       (p2:Person {id: 3, name: 'Charlie', age: 35, email: 'charlie@example.com'});

-- 创建带关系的节点（一步完成）
CREATE (a:Person {id: 4, name: 'David', age: 28, email: 'david@example.com'})-[:Knows {since: 2023, weight: 0.8}]->(b:Person {id: 5, name: 'Eve', age: 26, email: 'eve@example.com'});

-- 为已有节点创建边
MATCH (a:Person {id: 1}), (b:Person {id: 2})
CREATE (a)-[:Knows {since: 2020, weight: 1.0}]->(b);
```

### DML — 更新与删除

```cypher
-- 更新节点属性
MATCH (p:Person {id: 1})
SET p.age = 31, p.email = 'alice_new@example.com';

-- 删除节点（需先删除关联的边）
MATCH (p:Person {id: 5})-[e]-()
DELETE e, p;

-- 删除所有边（保留节点）
MATCH ()-[e:Knows]->()
DELETE e;
```

### DML — 批量导入（COPY FROM）

```cypher
-- 从 CSV 文件导入节点（需先建表）
COPY Person FROM "/path/to/person.csv" (HEADER=true);

-- 从 CSV 文件导入边
COPY Knows FROM "/path/to/knows.csv" (HEADER=true);
```

### 查询 — 基础

```cypher
-- 主键点查
MATCH (n:Account {id: 0}) RETURN n.name, n.email, n.score;

-- 全表扫描 + LIMIT
MATCH (n:Account) RETURN n.id, n.name, n.score LIMIT 10;

-- 计数
MATCH (n:Account) RETURN count(n);

-- 全库计数
MATCH (n) RETURN count(n);
MATCH ()-[e]->() RETURN count(e);
```

### 查询 — 条件过滤

```cypher
-- 数值过滤
MATCH (n:Account) WHERE n.score > 90 RETURN n.id, n.name, n.score;

-- 多条件组合
MATCH (n:Account) WHERE n.score > 80 AND n.age < 30 RETURN n.id, n.name, n.score, n.age;

-- OR 条件
MATCH (n:Account) WHERE n.score > 99 OR n.id < 5 RETURN n.id, n.name, n.score;

-- 字符串精确匹配
MATCH (n:Account) WHERE n.city = 'Beijing' RETURN n.id, n.name, n.city;

-- 字符串前缀
MATCH (n:Account) WHERE n.name STARTS WITH 'aaa' RETURN n.id, n.name;

-- 布尔过滤
MATCH (n:Account) WHERE n.flag_a = true AND n.flag_b = false RETURN n.id, n.name;
```

### 查询 — 聚合与排序

```cypher
-- 平均值
MATCH (n:Account) RETURN avg(n.score);

-- 最小/最大值
MATCH (n:Account) RETURN min(n.balance), max(n.income);

-- GROUP BY + 聚合
MATCH (n:Account) RETURN n.country, count(n), avg(n.score) ORDER BY count(n) DESC;

-- 分桶统计
MATCH (n:Account) RETURN floor(n.score / 10) AS bucket, count(n) ORDER BY bucket;

-- Top-N 排序
MATCH (n:Account) RETURN n.id, n.name, n.score ORDER BY n.score DESC LIMIT 10;
```

### 查询 — 图遍历

```cypher
-- 1-hop：从 Account 出发的所有直接关系
MATCH (a:Account {id: 0})-[e]->(b) RETURN labels(b), e.since, b.id, b.name;

-- 1-hop：指定边类型
MATCH (a:Account)-[:AccountCreatesPost]->(p:PostItem) RETURN a.id, p.id, p.name LIMIT 10;

-- 2-hop：Account → Order → Product
MATCH (a:Account)-[:AccountPlacesOrder]->(o:OrderItem)-[:OrderContainsProduct]->(p:Product)
RETURN a.id, a.name, p.id, p.name LIMIT 10;

-- 2-hop：Account → Post → Tag
MATCH (a:Account)-[:AccountCreatesPost]->(p:PostItem)-[:PostHasTag]->(t:Tag)
RETURN a.id, a.name, t.id, t.name LIMIT 10;

-- 反向遍历：哪些 Account 创建了这个 Post
MATCH (a:Account)-[:AccountCreatesPost]->(p:PostItem {id: 100})
RETURN a.id, a.name;

-- 可变长度路径（1-3跳）
MATCH (a:Account {id: 0})-[e*1..3]->(b)
RETURN DISTINCT b.id, labels(b) LIMIT 20;
```

### 查询 — 度中心性

```cypher
-- 节点出度（从该节点出发的边数）
MATCH (a:Account)-[e]->() RETURN a.id, a.name, count(e) AS out_degree ORDER BY out_degree DESC LIMIT 10;

-- 节点入度（到达该节点的边数）
MATCH ()-[e]->(p:Product) RETURN p.id, p.name, count(e) AS in_degree ORDER BY in_degree DESC LIMIT 10;
```

### 查询 — Schema 内省

```cypher
-- 列出所有表
CALL show_tables() RETURN *;

-- 查看表属性
CALL table_info('Account') RETURN *;

-- 查看边表的连接关系
CALL show_connection('AccountCreatesPost') RETURN *;
```

### 查询 — 可视化专用

以下查询返回 NODE/REL 类型列，适配 `/query/graph` 接口和前端 Graph 视图：

```cypher
-- 单跳关系可视化
MATCH (a:Account)-[e:AccountCreatesPost]->(p:PostItem) RETURN a, e, p LIMIT 25;

-- 多类型关系可视化
MATCH (a:Account)-[e]->(b) WHERE a.id < 5 RETURN a, e, b LIMIT 30;

-- 2-hop 路径可视化
MATCH (a:Account)-[e1:AccountPlacesOrder]->(o:OrderItem)-[e2:OrderContainsProduct]->(p:Product)
RETURN a, e1, o, e2, p LIMIT 15;
```

## 性能参考

测试环境：8.1GB 数据库，20M 节点 + 39M 边，Python 3.13，Windows 11

| 查询类型 | HTTP 延迟 (p50) |
|---|---|
| 主键点查 | 17ms |
| 单表 COUNT | 26ms |
| 数值过滤 | 44ms |
| 聚合 | 55ms |
| GROUP BY | 257ms |
| 1-hop 遍历 | 203ms |
| 2-hop 遍历 | 421ms |
| 混合并发吞吐 (10 workers) | 34 QPS |

内存占用：8.1GB 数据库，冷启动后首次全库扫描内存约 497MB（占磁盘 6%）。
