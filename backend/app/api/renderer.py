"""
MuseTalk 渲染器 API

提供渲染器状态查询、avatar 绑定、最新生成结果等接口。
"""

import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter()


# ------------------------------------------------------------------
# 依赖注入
# ------------------------------------------------------------------

def _get_renderer(request: Request):
    renderer = getattr(request.app.state, "musetalk_renderer", None)
    if renderer is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MuseTalk 渲染器未初始化",
        )
    return renderer


# ------------------------------------------------------------------
# 请求 / 响应模型
# ------------------------------------------------------------------

class BindAvatarRequest(BaseModel):
    username: str = Field(..., description="Fay 用户名")
    avatar_id: str = Field(..., description="要绑定的 avatar ID")


class SetDefaultAvatarRequest(BaseModel):
    avatar_id: str = Field(..., description="默认 avatar ID")


# ------------------------------------------------------------------
# 接口
# ------------------------------------------------------------------

@router.get("/status")
async def renderer_status(request: Request):
    """获取渲染器运行状态"""
    renderer = _get_renderer(request)
    return renderer.get_status()


@router.get("/latest")
async def latest_result(request: Request):
    """获取最近一次生成结果"""
    renderer = _get_renderer(request)
    result = renderer.get_latest_result()
    if result is None:
        return {"has_result": False, "result": None}
    return {"has_result": True, "result": result}


@router.get("/history")
async def render_history(request: Request, limit: int = 10):
    """获取渲染历史记录"""
    renderer = _get_renderer(request)
    return {"history": renderer.get_history(limit=min(limit, 50))}


@router.post("/bind-avatar")
async def bind_avatar(request: Request, body: BindAvatarRequest):
    """将 Fay 用户名绑定到指定 avatar"""
    renderer = _get_renderer(request)
    renderer.bind_avatar(body.username, body.avatar_id)
    return {
        "success": True,
        "message": f"已绑定 {body.username} -> {body.avatar_id}",
    }


@router.post("/set-default-avatar")
async def set_default_avatar(request: Request, body: SetDefaultAvatarRequest):
    """设置默认 avatar（未绑定用户的兜底）"""
    renderer = _get_renderer(request)
    renderer.set_default_avatar(body.avatar_id)
    return {
        "success": True,
        "message": f"默认 avatar 已设置为 {body.avatar_id}",
    }
