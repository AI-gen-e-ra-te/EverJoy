#!/usr/bin/env python3
"""
DigiPeople Core 后端主程序

启动命令:
    uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
"""

import os
import sys
import logging
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse
from contextlib import asynccontextmanager

from app.config import settings
from app.api import router as api_router
from app.services.job_service import JobService
from app.services.avatar_service import AvatarService
from app.services.fay_client import fay_service
from app.services.tts_service import TTSService
from app.services.musetalk_service import MuseTalkService
from app.services.musetalk_renderer_ws import MuseTalkRendererWS

# 配置日志（Windows 终端使用 UTF-8 避免中文乱码）
_log_handler = logging.StreamHandler(
    stream=open(sys.stdout.fileno(), mode="w", encoding="utf-8", closefd=False)
)
_log_handler.setFormatter(logging.Formatter(
    "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
))
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    handlers=[_log_handler],
)
logger = logging.getLogger(__name__)

# 全局服务实例（第三阶段接入TTS和MuseTalk）
# 注：第三阶段接入Fay、TTS和MuseTalk，完整链路接通

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理 - 第三阶段加入TTS和MuseTalk"""
    # 启动时日志
    logger.info("第三阶段后端服务启动中...")

    # 初始化服务
    try:
        # 初始化任务服务
        job_service = JobService()
        await job_service.initialize()

        # 初始化头像服务
        avatar_service = AvatarService()
        avatar_service.initialize()

        # 初始化Fay服务
        await fay_service.initialize()

        # 初始化TTS服务
        tts_service = TTSService()
        await tts_service.initialize()

        # 初始化MuseTalk服务
        musetalk_service = MuseTalkService()
        musetalk_service.initialize()

        # 注册任务处理器
        from app.services.job_service import JobType
        async def handle_avatar_processing(parameters: dict):
            """处理avatar预处理任务"""
            video_path = parameters.get("video_path")
            avatar_id = parameters.get("avatar_id")
            if not video_path or not avatar_id:
                raise ValueError("缺少video_path或avatar_id参数")

            # 调用avatar_service处理视频
            result = await avatar_service.process_video_avatar(video_path, avatar_id)
            return result

        job_service.register_handler(JobType.AVATAR_PROCESSING, handle_avatar_processing)

        # 初始化 MuseTalk 渲染器 WebSocket 客户端（连接 Fay 10002）
        musetalk_renderer = MuseTalkRendererWS(
            musetalk_service=musetalk_service,
            avatar_service=avatar_service,
        )
        await musetalk_renderer.start()

        # 将服务实例存储到app.state中，以便API路由使用
        app.state.job_service = job_service
        app.state.avatar_service = avatar_service
        app.state.fay_service = fay_service
        app.state.tts_service = tts_service
        app.state.musetalk_service = musetalk_service
        app.state.musetalk_renderer = musetalk_renderer

        logger.info("服务初始化完成（含 MuseTalk 渲染器 WS 客户端）")
    except Exception as e:
        logger.error(f"服务初始化失败: {e}")
        raise

    yield

    # 关闭时日志
    logger.info("第三阶段后端服务关闭中...")

    # 清理服务
    try:
        if hasattr(app.state, 'musetalk_renderer'):
            await app.state.musetalk_renderer.stop()
        if hasattr(app.state, 'job_service'):
            await app.state.job_service.cleanup()
        if hasattr(app.state, 'fay_service'):
            await app.state.fay_service.close()
    except Exception as e:
        logger.error(f"服务清理失败: {e}")

# 创建 FastAPI 应用
app = FastAPI(
    title="DigiPeople Core API",
    description="基于 Fay 和 MuseTalk 的数字人系统",
    version="1.0.0",
    lifespan=lifespan
)

# 添加 CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API 路由必须在静态文件挂载之前注册，否则 StaticFiles 会拦截 POST 等请求并返回 405
app.include_router(api_router, prefix="/api")

# 挂载静态文件目录
frontend_dir = os.path.join(settings.BASE_DIR, "frontend")
app.mount("/static", StaticFiles(directory=frontend_dir), name="static")

# 挂载音频和视频文件目录（路径使用 /files/ 前缀，避免与 /api/ 路由冲突）
app.mount("/files/audio", StaticFiles(directory=settings.absolute_audio_dir), name="audio")
app.mount("/files/videos", StaticFiles(directory=settings.absolute_video_dir), name="videos")
app.mount("/files/avatars", StaticFiles(directory=settings.absolute_avatar_dir), name="avatars")

# 健康检查端点
@app.get("/health")
@app.get("/api/health/")  # 兼容前端调用的路径
async def health_check():
    """健康检查接口 - 第三阶段已接入TTS和MuseTalk"""
    # 检查Fay服务是否可用
    fay_available = hasattr(app.state, 'fay_service') and app.state.fay_service is not None

    tts_available = hasattr(app.state, 'tts_service') and app.state.tts_service is not None and app.state.tts_service.is_available()
    musetalk_available = hasattr(app.state, 'musetalk_service') and app.state.musetalk_service is not None and app.state.musetalk_service.is_available()

    renderer = getattr(app.state, 'musetalk_renderer', None)
    renderer_connected = renderer is not None and renderer.ws is not None and renderer.ws.open if renderer else False

    return {
        "status": "healthy",
        "services": {
            "backend": True,
            "fay": fay_available,
            "musetalk": musetalk_available,
            "tts": tts_available,
            "renderer_ws": renderer_connected,
        },
        "message": "第四阶段：Fay WS 皮肤客户端模式",
        "version": "2.0.0"
    }

# 根路径返回前端页面
@app.get("/")
async def read_root():
    """重定向到前端页面"""
    return RedirectResponse(url="/static/index.html")

# 全局异常处理
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """全局异常处理器"""
    logger.error(f"未处理的异常: {exc}", exc_info=True)
    return {
        "detail": "服务器内部错误",
        "message": str(exc)
    }, 500

# 导出应用实例
__all__ = ["app"]

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.BACKEND_HOST,
        port=settings.BACKEND_PORT,
        reload=settings.DEBUG,
        log_level=settings.LOG_LEVEL.lower()
    )