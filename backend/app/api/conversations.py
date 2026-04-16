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
    fay_service=Depends(get_fay_service)
):
    """
    生成流式 Fay 回复

    返回 Server-Sent Events (SSE) 流式响应
    """
    from fastapi.responses import StreamingResponse
    import json

    async def event_generator():
        try:
            logger.info(f"生成流式回复请求: 用户='{conversation_request.username}', "
                       f"文本长度={len(conversation_request.text)}")

            # 获取Fay客户端实例
            fay_client = fay_service.client

            # 生成流式回复
            async for chunk in fay_client.generate_reply_stream(
                user_text=conversation_request.text,
                username=conversation_request.username
            ):
                # 发送数据块
                yield f"data: {json.dumps({'chunk': chunk})}\n\n"

            # 发送结束标记
            yield f"data: {json.dumps({'done': True})}\n\n"

        except Exception as e:
            logger.error(f"生成流式回复失败: {e}")
            error_msg = f"data: {json.dumps({'error': str(e)})}\n\n"
            yield error_msg

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # 禁用Nginx缓冲
        }
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