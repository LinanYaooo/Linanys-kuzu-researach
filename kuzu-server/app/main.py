import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.db import init_db, get_db
from app.routers import query, schema, health, bulk

DB_PATH = os.environ.get("KUZU_DB_PATH", "../kuzu-test/test_db")
BUFFER_POOL_MB = int(os.environ.get("KUZU_BUFFER_POOL_MB", "0"))
POOL_SIZE = int(os.environ.get("KUZU_POOL_SIZE", "8"))

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    db = init_db(DB_PATH, buffer_pool_size=BUFFER_POOL_MB, pool_size=POOL_SIZE)
    print(f"Kuzu database opened: {DB_PATH}")
    print(f"  Nodes: {db.get_node_count():,}")
    print(f"  Edges: {db.get_edge_count():,}")
    print(f"  UI: http://localhost:8000")
    print(f"  API Docs: http://localhost:8000/docs")
    yield
    print("Shutting down...")


app = FastAPI(
    title="Kuzu API Server",
    description="Kuzu 图数据库 REST API 服务\n\n"
                "## 功能\n"
                "- **查询执行**：支持 Cypher 查询（DQL/DML/DDL），提供普通/线程安全/图谱可视化三种模式\n"
                "- **Schema 查询**：获取节点表、边表定义及属性信息\n"
                "- **健康检查**：检查数据库连接状态和统计数据\n"
                "- **查询历史**：服务端保存最近 100 条查询记录\n\n"
                "## 快速测试\n"
                "在 /query 接口输入：`MATCH (n:Account) RETURN n.id, n.name, n.score LIMIT 5`",
    version="1.0.0",
    lifespan=lifespan,
    contact={"name": "Kuzu Graph Explorer"},
    license_info={"name": "MIT"},
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(query.router, prefix="/api/v1", tags=["查询 Query"])
app.include_router(schema.router, prefix="/api/v1", tags=["Schema 元数据"])
app.include_router(health.router, prefix="/api/v1", tags=["健康检查 Health"])
app.include_router(bulk.router, prefix="/api/v1", tags=["批量导入 Bulk"])


@app.get(
    "/",
    summary="首页",
    description="返回可视化前端页面（如存在），否则返回 API 信息 JSON。",
)
async def serve_index():
    index_path = STATIC_DIR / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    return {"message": "Kuzu API Server", "docs": "/docs"}
