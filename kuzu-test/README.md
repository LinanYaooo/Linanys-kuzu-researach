# kuzu-test

Kuzu 图数据库的基准测试与内存分析工具。基于大规模合成数据集（20M 节点 + ~39M 边），对 [Kuzu](https://kuzudb.com/) 的查询性能和内存占用进行系统化评测。

## 数据集规模

| 指标 | 数量 |
|------|------|
| 节点表 | 20 个（Account, Product, OrderItem, ...） |
| 每表行数 | 1,000,000 行 |
| 每表属性 | 60 个（INT64 / DOUBLE / STRING / BOOL） |
| 节点总数 | 20,000,000 |
| 边表 | 17 个（AccountCreatesPost, OrderContainsProduct, ...） |
| 边总数 | ~39,000,000 |

## 安装

```bash
pip install -r requirements.txt
```

依赖：`kuzu>=0.11.3`，内存分析额外需要 `psutil`（`pip install psutil`）。

## 使用流程

### 1. 生成测试数据并建库

```bash
python seed.py
```

该脚本会依次完成：

1. 创建 20 个节点表（每表 60 个属性，主键 `id`）
2. 生成节点 CSV 文件到 `csv_data/`
3. 通过 `COPY FROM` 导入节点数据
4. 创建 17 个边表（每条边含 `since`, `weight`, `label` 属性）
5. 生成边 CSV 文件到 `csv_data/`
6. 通过 `COPY FROM` 导入边数据

运行后在当前目录生成 `test_db` 数据库文件和 `csv_data/` 目录。

> 首次运行耗时较长（生成 CSV + 导入），后续可跳过此步骤直接跑基准测试。

### 2. 查询性能基准测试

```bash
python benchmark.py
```

对测试数据库执行 26 项查询，每项跑 5 轮取统计值，覆盖以下场景：

| 类别 | 测试项 | 示例查询 |
|------|--------|----------|
| 计数 | 单表 COUNT / 全图 COUNT / 全边 COUNT | `MATCH (n:Account) RETURN count(n)` |
| 主键点查 | 不同 id 值的精确匹配 | `MATCH (n:Account {id: 500000}) RETURN ...` |
| 数值过滤 | 单条件 / 多条件 WHERE | `WHERE n.score > 80 AND n.age < 30` |
| 字符串过滤 | 精确匹配 / 前缀匹配 | `WHERE n.name STARTS WITH "aaa"` |
| 聚合 | AVG / MIN/MAX / GROUP BY + COUNT | `RETURN n.city, count(n) ORDER BY count(n) DESC` |
| 排序+分页 | ORDER BY + LIMIT | `ORDER BY n.score DESC LIMIT 10` |
| 多列投影 | 5 列 / 20 列 + LIMIT 1000 | `RETURN n.id, n.name, ... LIMIT 1000` |
| 1 跳遍历 | 单边类型 / 带过滤条件 | `MATCH (a:Account)-[:AccountCreatesPost]->(p)` |
| 2 跳遍历 | 双跳路径 | `MATCH (a)-[:...]->(o)-[:...]->(p)` |
| 边聚合 | 出度 / 入度统计 | `RETURN a.id, count(e) ORDER BY count(e) DESC` |

输出格式：

```
1. Count single table (1M rows)             rows=1          avg=0.0032s  med=0.0031s  min=0.0029s  max=0.0038s
```

### 3. 内存占用分析

```bash
pip install psutil   # 首次使用需安装
python mem_profile.py
```

逐步测量每个操作的进程 RSS 内存增量：

1. Python 基线内存
2. `Database()` 加载后
3. `Connection()` 建立后
4. COUNT 全节点后
5. COUNT 全边后
6. 主键点查后
7. 获取 1000 行宽表后
8. 获取 10000 行窄表后
9. 聚合查询后
10. GROUP BY 查询后
11. ORDER BY + LIMIT 后
12. 1 跳遍历后
13. 2 跳遍历后

同时输出数据库文件磁盘大小和 Kuzu 净内存开销。

## 目录结构

```
kuzu-test/
├── seed.py           # 生成测试数据并建库
├── benchmark.py      # 查询性能基准测试（26 项）
├── mem_profile.py    # 内存占用分析
├── requirements.txt  # Python 依赖
├── csv_data/         # 生成的 CSV 数据文件（seed.py 输出）
└── test_db           # Kuzu 数据库文件（seed.py 输出）
```

## 数据模型

### 节点表（20 个）

Account, Product, OrderItem, Category, Tag, CommentItem, PostItem, GroupItem, EventItem, LocationItem, Company, Department, ProjectItem, TaskItem, ReviewItem, PhotoItem, VideoItem, ArticleItem, CourseItem, CertificateItem

每表 60 个属性，包括：id, name, email, phone, address, city, country, score, rating, balance, age, views, likes, followers, 各类 flag/metric/desc 字段，以及 created_at / updated_at 等时间字段。

### 边表（17 个）

| 边名 | 起点 | 终点 | 数量 |
|------|------|------|------|
| AccountCreatesPost | Account | PostItem | 3M |
| AccountWritesComment | Account | CommentItem | 5M |
| AccountJoinsGroup | Account | GroupItem | 2M |
| AccountPlacesOrder | Account | OrderItem | 4M |
| AccountWritesReview | Account | ReviewItem | 3M |
| AccountWorksAtCompany | Account | Company | 1M |
| AccountAttendsEvent | Account | EventItem | 2M |
| AccountEnrollsCourse | Account | CourseItem | 1.5M |
| AccountEarnsCert | Account | CertificateItem | 1M |
| PostHasTag | PostItem | Tag | 2M |
| PostInCategory | PostItem | Category | 1M |
| ProductInCategory | Product | Category | 1M |
| ProductHasReview | Product | ReviewItem | 3M |
| OrderContainsProduct | OrderItem | Product | 6M |
| CompanyHasDept | Company | Department | 0.5M |
| ProjectHasTask | ProjectItem | TaskItem | 2M |
| EventAtLocation | EventItem | LocationItem | 1M |
