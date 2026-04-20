"""
API 路由模块

包含所有 API 端点的路由定义
"""

from fastapi import APIRouter

from . import health, tasks, avatars, conversations, renderer, voice

router = APIRouter()

router.include_router(health.router, prefix="/health", tags=["健康检查"])
router.include_router(tasks.router, prefix="/tasks", tags=["任务管理"])
router.include_router(avatars.router, prefix="/avatars", tags=["头像管理"])
router.include_router(conversations.router, prefix="/conversations", tags=["对话管理"])
router.include_router(renderer.router, prefix="/renderer", tags=["MuseTalk渲染器"])
router.include_router(voice.router, prefix="/voice", tags=["语音输入"])

__all__ = ["router"]