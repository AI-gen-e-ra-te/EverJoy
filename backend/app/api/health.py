"""
健康检查 API

提供系统健康状态检查端点
"""

import logging
from datetime import datetime
from fastapi import APIRouter, Request
from typing import Dict, Any

from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/")
async def health_check(request: Request) -> Dict[str, Any]:
    """
    健康检查接口

    从 app.state 读取各服务的真实可用状态
    """
    fay_available = (
        hasattr(request.app.state, "fay_service")
        and request.app.state.fay_service is not None
    )

    tts_available = (
        hasattr(request.app.state, "tts_service")
        and request.app.state.tts_service is not None
        and request.app.state.tts_service.is_available()
    )

    musetalk_available = (
        hasattr(request.app.state, "musetalk_service")
        and request.app.state.musetalk_service is not None
        and request.app.state.musetalk_service.is_available()
    )

    renderer = getattr(request.app.state, "musetalk_renderer", None)
    renderer_connected = (
        renderer is not None
        and renderer.ws is not None
        and renderer.ws.open
    ) if renderer else False

    services_status = {
        "backend": True,
        "fay": fay_available,
        "musetalk": musetalk_available,
        "tts": tts_available,
        "renderer_ws": renderer_connected,
    }

    status = "healthy" if services_status["backend"] else "degraded"

    return {
        "status": status,
        "services": services_status,
        "version": "2.0.0",
        "environment": "development" if settings.DEBUG else "production",
        "timestamp": datetime.now().isoformat(),
        "message": "第四阶段：Fay WS 皮肤客户端模式",
    }


@router.get("/ready")
async def readiness_check(request: Request) -> Dict[str, Any]:
    """就绪检查接口"""
    tts_ok = (
        hasattr(request.app.state, "tts_service")
        and request.app.state.tts_service is not None
        and request.app.state.tts_service.is_available()
    )
    musetalk_ok = (
        hasattr(request.app.state, "musetalk_service")
        and request.app.state.musetalk_service is not None
        and request.app.state.musetalk_service.is_available()
    )

    critical_services = {
        "backend": True,
        "tts": tts_ok,
        "musetalk": musetalk_ok,
    }
    is_ready = all(critical_services.values())

    return {
        "ready": is_ready,
        "critical_services": critical_services,
        "timestamp": datetime.now().isoformat(),
    }


@router.get("/live")
async def liveness_check() -> Dict[str, Any]:
    """存活检查接口"""
    return {
        "alive": True,
        "timestamp": datetime.now().isoformat(),
    }
