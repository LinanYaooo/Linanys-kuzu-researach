from fastapi import APIRouter

from app.db import get_db
from app.models import HealthResponse

router = APIRouter()


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="健康检查",
    description="检查数据库连接状态，返回数据库路径、节点总数和边总数。"
                "状态为 ok 表示数据库正常可用，否则表示连接异常。"
                "前端每 30 秒自动调用此接口更新状态指示灯。",
)
async def health_check():
    """数据库健康检查

    返回:
    - status: 连接状态，"ok" 表示正常
    - db_path: 数据库文件路径
    - node_count: 数据库中节点总数
    - edge_count: 数据库中边总数
    """
    db = get_db()
    node_count = db.get_node_count()
    edge_count = db.get_edge_count()
    return HealthResponse(
        status="ok",
        db_path=db.db_path,
        node_count=node_count,
        edge_count=edge_count,
    )
