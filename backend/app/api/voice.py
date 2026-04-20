"""
语音输入 API

提供 one-shot 录音上传接口：
  POST /api/voice/oneshot
  - 接收浏览器录制的音频 blob
  - 转换为 Fay 可接受的 PCM 格式
  - 推送到 Fay TCP 10001
  - 在 Fay WS 10002 上等待 ASR + LLM 回复
  - 返回 { question, answer, audio_path }
"""

import logging
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Request, status
from typing import Optional

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/oneshot")
async def voice_oneshot(
    request: Request,
    file: UploadFile = File(..., description="浏览器录制的音频文件（webm/wav/ogg）"),
    username: Optional[str] = Form("User"),
):
    """
    一次性语音输入：录音 → Fay ASR → LLM → TTS

    流程：
    1. 接收前端上传的音频 blob
    2. ffmpeg 转换为 16 kHz / mono / s16le PCM
    3. 推送到 Fay TCP 10001
    4. 在 Fay WS 10002 上等待回复
    5. 返回识别文本、LLM 回复、音频路径

    MuseTalk 视频生成由已连接的 musetalk_renderer_ws 自动处理。
    """
    from app.services.audio_convert_service import AudioConvertService
    from app.services.fay_voice_bridge import FayVoiceBridge
    from app.config import settings

    # 读取上传的音频
    blob = await file.read()
    if not blob:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="音频文件为空")

    logger.info(f"收到语音输入: {file.filename}, {len(blob)} bytes, content_type={file.content_type}")

    # 推断输入格式
    ext = "webm"
    if file.filename:
        ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ext
    if file.content_type:
        ct = file.content_type.lower()
        if "wav" in ct:
            ext = "wav"
        elif "ogg" in ct:
            ext = "ogg"
        elif "mp4" in ct or "m4a" in ct:
            ext = "m4a"

    # 1) 转换格式
    converter = AudioConvertService()
    try:
        pcm_data = await converter.convert_blob_to_pcm(blob, input_format=ext)
    except Exception as e:
        logger.error(f"音频转换失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"音频转换失败: {e}",
        )

    duration = len(pcm_data) / (16000 * 2)
    if duration < 0.3:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="录音时间过短（<0.3 秒），请重新录制",
        )

    logger.info(f"PCM 转换完成: {len(pcm_data)} bytes, {duration:.1f}s")

    # 2) 推送到 Fay 并等待回复
    bridge = FayVoiceBridge(
        fay_host=settings.FAY_HOST,
        tcp_port=10001,
        ws_port=settings.FAY_PORT,
        timeout=settings.FAY_TIMEOUT,
    )

    try:
        result = await bridge.send_audio_oneshot(pcm_data, username=username or "User")
    except Exception as e:
        logger.error(f"Fay 语音桥接失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Fay 语音处理失败: {e}",
        )

    if not result.get("success"):
        logger.warning(f"Fay 未返回完整结果: {result}")

    return {
        "success": result.get("success", False),
        "question": result.get("question"),
        "answer": result.get("answer"),
        "audio_path": result.get("audio_path"),
        "duration": round(duration, 1),
    }
