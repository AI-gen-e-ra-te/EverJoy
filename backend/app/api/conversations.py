"""
对话管理 API

提供与 Fay 数字人对话的功能
"""

import logging
import os
from typing import Optional
from fastapi import APIRouter, HTTPException, status, Depends, Request
from pydantic import BaseModel, Field
from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()


# 依赖注入
async def get_fay_service(request: Request):
    """获取Fay服务实例"""
    if not hasattr(request.app.state, 'fay_service'):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Fay服务未初始化"
        )
    return request.app.state.fay_service


async def get_tts_service(request: Request):
    """获取TTS服务实例"""
    if not hasattr(request.app.state, 'tts_service'):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="TTS服务未初始化"
        )
    return request.app.state.tts_service


async def get_musetalk_service(request: Request):
    """获取MuseTalk服务实例"""
    if not hasattr(request.app.state, 'musetalk_service'):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MuseTalk服务未初始化"
        )
    return request.app.state.musetalk_service


async def get_avatar_service(request: Request):
    """获取头像服务实例"""
    if not hasattr(request.app.state, 'avatar_service'):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="头像服务未初始化"
        )
    return request.app.state.avatar_service


# 请求/响应模型
class ConversationRequest(BaseModel):
    """对话请求模型"""
    text: str = Field(..., description="用户输入的文本", min_length=1, max_length=1000)
    username: Optional[str] = Field("User", description="用户名（可选）")
    avatar_id: Optional[str] = Field(None, description="关联的Avatar ID（可选）")


class ConversationResponse(BaseModel):
    """对话响应模型"""
    success: bool = Field(..., description="是否成功")
    reply: str = Field(..., description="Fay生成的回复文本")
    username: Optional[str] = Field(None, description="用户名")
    avatar_id: Optional[str] = Field(None, description="关联的Avatar ID")
    processing_time: Optional[float] = Field(None, description="处理时间（秒）")
    audio_url: Optional[str] = Field(None, description="生成的音频文件URL")
    video_url: Optional[str] = Field(None, description="生成的视频文件URL")
    job_id: Optional[str] = Field(None, description="视频生成任务ID")


@router.post("/reply", response_model=ConversationResponse, status_code=status.HTTP_200_OK)
async def generate_reply(
    request: Request,
    conversation_request: ConversationRequest,
    fay_service=Depends(get_fay_service),
    tts_service=Depends(get_tts_service),
    musetalk_service=Depends(get_musetalk_service),
    avatar_service=Depends(get_avatar_service)
) -> ConversationResponse:
    """
    生成 Fay 回复，并转换为音频和视频

    完整流程：
    1. 接收用户文本和可选参数
    2. 调用 Fay 服务生成回复文本
    3. 调用 TTS 服务将回复文本转换为音频
    4. 如果提供了 avatar_id，调用 MuseTalk 服务生成唇形同步视频
    5. 返回生成的回复文本、音频和视频URL

    注意：本阶段已集成TTS和MuseTalk，完整链路接通
    """
    import time
    start_time = time.time()

    # 初始化结果变量
    reply_text = ""
    audio_url = None
    video_url = None
    job_id = None
    success = True
    error_message = None

    try:
        logger.info(f"生成回复请求: 用户='{conversation_request.username}', "
                   f"文本长度={len(conversation_request.text)}, "
                   f"avatar_id={conversation_request.avatar_id}")

        # 1. 调用 Fay 服务生成回复
        reply_text = await fay_service.generate_reply(
            user_text=conversation_request.text,
            username=conversation_request.username
        )

        logger.info(f"Fay回复生成成功，回复长度={len(reply_text)}")

        # 2. 调用 TTS 服务合成音频
        try:
            tts_result = await tts_service.synthesize(
                text=reply_text,
                username=conversation_request.username or "User"
            )
            audio_url = tts_result.get("audio_url")
            logger.info(f"TTS音频合成成功: {audio_url}")
        except Exception as tts_error:
            logger.error(f"TTS合成失败: {tts_error}")
            # TTS失败不影响整体流程，继续执行
            audio_url = None
            error_message = f"TTS合成失败: {tts_error}"

        # 3. 如果提供了avatar_id，调用MuseTalk生成视频
        logger.info(f"检查MuseTalk条件: avatar_id={conversation_request.avatar_id}, audio_url={audio_url}")
        if conversation_request.avatar_id and audio_url:
            try:
                # 获取头像文件路径
                logger.info(f"正在获取头像文件: avatar_id={conversation_request.avatar_id}")
                avatar_path = avatar_service.get_avatar_file(
                    conversation_request.avatar_id,
                    size="original"  # 使用原始尺寸头像
                )
                logger.info(f"获取到头像路径: {avatar_path}")

                if not avatar_path:
                    logger.warning(f"未找到头像文件: {conversation_request.avatar_id}")
                    avatar_path = avatar_service.get_avatar_file("default_male", size="original")
                    logger.info(f"使用默认头像路径: {avatar_path}")

                # MuseTalk 需要视频文件（mp4），PNG/JPG 会导致 landmark 提取失败
                SUPPORTED_VIDEO_EXTS = (".mp4", ".avi", ".mov", ".mkv", ".webm")
                if avatar_path and not avatar_path.lower().endswith(SUPPORTED_VIDEO_EXTS):
                    logger.warning(
                        f"头像文件不是视频格式 ({avatar_path})，MuseTalk 需要 mp4 输入，跳过视频生成"
                    )
                    avatar_path = None

                logger.info(f"头像文件路径: {avatar_path}, 存在: {os.path.exists(avatar_path) if avatar_path else False}")
                if avatar_path and os.path.exists(avatar_path):
                    # 从audio_url提取音频文件路径（去掉/api/audio/前缀）
                    audio_filename = audio_url.replace("/files/audio/", "") if audio_url else None
                    audio_path = os.path.join(settings.absolute_audio_dir, audio_filename) if audio_filename else None
                    logger.info(f"音频文件路径: {audio_path}, 存在: {os.path.exists(audio_path) if audio_path else False}")

                    if audio_path and os.path.exists(audio_path):
                        # 生成视频
                        musetalk_result = await musetalk_service.generate_lip_sync_video(
                            audio_path=audio_path,
                            avatar_path=avatar_path,
                            username=conversation_request.username or "User"
                        )

                        video_url = musetalk_result.get("video_url")
                        job_id = musetalk_result.get("job_id")
                        logger.info(f"MuseTalk视频生成成功: {video_url}")
                    else:
                        logger.warning(f"音频文件不存在: {audio_path}")
                else:
                    logger.warning(f"头像文件不存在: {avatar_path}")
            except Exception as musetalk_error:
                logger.error(f"MuseTalk视频生成失败: {musetalk_error}")
                # MuseTalk失败不影响整体流程
                video_url = None
                if not error_message:
                    error_message = f"视频生成失败: {musetalk_error}"
                else:
                    error_message += f"; 视频生成失败: {musetalk_error}"
        else:
            logger.info(f"跳过MuseTalk: avatar_id={conversation_request.avatar_id}, audio_url={audio_url}")

        processing_time = time.time() - start_time

        logger.info(f"完整流程完成: 处理时间={processing_time:.2f}秒, "
                   f"回复长度={len(reply_text)}, 音频={'有' if audio_url else '无'}, "
                   f"视频={'有' if video_url else '无'}")

        return ConversationResponse(
            success=success,
            reply=reply_text,
            username=conversation_request.username,
            avatar_id=conversation_request.avatar_id,
            processing_time=processing_time,
            audio_url=audio_url,
            video_url=video_url,
            job_id=job_id
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"生成回复失败: {e}", exc_info=True)
        processing_time = time.time() - start_time
        # 返回错误信息，但包含可能已生成的回复文本
        return ConversationResponse(
            success=False,
            reply=reply_text or f"抱歉，生成回复时出现错误: {str(e)}。这是模拟回复。",
            username=conversation_request.username,
            avatar_id=conversation_request.avatar_id,
            processing_time=processing_time,
            audio_url=audio_url,
            video_url=video_url,
            job_id=job_id
        )


@router.post("/reply-stream", status_code=status.HTTP_200_OK)
async def generate_reply_stream(
    request: Request,
    conversation_request: ConversationRequest,
    fay_service=Depends(get_fay_service),
    tts_service=Depends(get_tts_service),
    musetalk_service=Depends(get_musetalk_service),
    avatar_service=Depends(get_avatar_service)
):
    """
    生成流式 Fay 回复，文字流式推送后自动触发 TTS + MuseTalk

    SSE 事件序列：
    1. {"chunk": "..."} — 流式文字片段
    2. {"audio_url": "..."} — TTS 生成的音频 URL
    3. {"video_generating": true} — MuseTalk 已开始生成视频（异步）
    4. {"done": true} — 全部完成
    """
    from fastapi.responses import StreamingResponse
    import json
    import time
    import asyncio

    async def event_generator():
        full_text = ""
        try:
            logger.info(f"生成流式回复请求: 用户='{conversation_request.username}', "
                       f"文本长度={len(conversation_request.text)}")

            fay_client = fay_service.client

            async for chunk in fay_client.generate_reply_stream(
                user_text=conversation_request.text,
                username=conversation_request.username
            ):
                full_text += chunk
                yield f"data: {json.dumps({'chunk': chunk}, ensure_ascii=False)}\n\n"

            logger.info(f"流式文字完成，回复长度={len(full_text)}")

        except Exception as e:
            logger.error(f"流式文字生成失败: {e}")
            yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"
            return

        if not full_text.strip():
            yield f"data: {json.dumps({'done': True})}\n\n"
            return

        # ── TTS ──
        audio_url = None
        try:
            tts_result = await tts_service.synthesize(
                text=full_text,
                username=conversation_request.username or "User"
            )
            audio_url = tts_result.get("audio_url")
            logger.info(f"TTS 音频合成成功: {audio_url}")
            yield f"data: {json.dumps({'audio_url': audio_url}, ensure_ascii=False)}\n\n"
        except Exception as tts_err:
            logger.error(f"TTS 合成失败: {tts_err}")

        # ── MuseTalk（异步启动，不阻塞 SSE） ──
        avatar_id = conversation_request.avatar_id
        if avatar_id and audio_url:
            try:
                avatar_path = avatar_service.get_avatar_file(avatar_id, size="original")
                SUPPORTED_VIDEO_EXTS = (".mp4", ".avi", ".mov", ".mkv", ".webm")
                if avatar_path and not avatar_path.lower().endswith(SUPPORTED_VIDEO_EXTS):
                    logger.warning(f"头像非视频格式 ({avatar_path})，跳过 MuseTalk")
                    avatar_path = None

                if avatar_path and os.path.exists(avatar_path):
                    audio_filename = audio_url.replace("/files/audio/", "") if audio_url else None
                    audio_path = os.path.join(settings.absolute_audio_dir, audio_filename) if audio_filename else None

                    if audio_path and os.path.exists(audio_path):
                        logger.info(f"启动 MuseTalk: avatar={avatar_path}, audio={audio_path}")
                        renderer = getattr(request.app.state, "musetalk_renderer", None)
                        asyncio.create_task(
                            _run_musetalk_background(musetalk_service, audio_path, avatar_path,
                                                     conversation_request.username or "User",
                                                     renderer=renderer, reply_text=full_text)
                        )
                        yield f"data: {json.dumps({'video_generating': True})}\n\n"
                    else:
                        logger.warning(f"音频文件不存在: {audio_path}")
                else:
                    logger.warning(f"头像文件不存在或非视频: {avatar_path}")
            except Exception as mt_err:
                logger.error(f"MuseTalk 启动失败: {mt_err}")

        yield f"data: {json.dumps({'done': True})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


async def _run_musetalk_background(musetalk_service, audio_path: str, avatar_path: str,
                                   username: str, renderer=None, reply_text: str = ""):
    """在后台运行 MuseTalk，不阻塞 SSE 流。完成后更新 renderer 的 latest_result 供前端轮询。"""
    import time
    start = time.time()
    try:
        result = await musetalk_service.generate_lip_sync_video(
            audio_path=audio_path,
            avatar_path=avatar_path,
            username=username
        )
        video_url = result.get("video_url")
        duration = time.time() - start
        logger.info(f"MuseTalk 后台生成完成: {video_url} ({duration:.1f}s)")

        if renderer:
            renderer._record_result(
                status="completed",
                video_url=video_url,
                text=reply_text[:100],
                username=username,
                duration=duration,
                source="text_pipeline",
            )
    except Exception as e:
        duration = time.time() - start
        logger.error(f"MuseTalk 后台生成失败: {e}")
        if renderer:
            renderer._record_result(
                status="failed",
                error=str(e),
                text=reply_text[:100],
                username=username,
                duration=duration,
                source="text_pipeline",
            )


@router.get("/test", status_code=status.HTTP_200_OK)
async def test_conversation(
    request: Request,
    fay_service=Depends(get_fay_service)
):
    """测试对话端点"""
    try:
        # 测试Fay服务连接
        test_text = "你好，请介绍一下你自己"
        reply = await fay_service.generate_reply(test_text)

        return {
            "success": True,
            "test_text": test_text,
            "reply": reply,
            "message": "对话端点测试成功",
            "fay_service_available": True
        }
    except Exception as e:
        logger.error(f"测试对话端点失败: {e}")
        return {
            "success": False,
            "message": f"对话端点测试失败: {str(e)}",
            "fay_service_available": False
        }