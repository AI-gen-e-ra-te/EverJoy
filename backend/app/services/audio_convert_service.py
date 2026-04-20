"""
音频格式转换服务

使用 ffmpeg 将浏览器录制的音频（webm/wav/ogg）转换为 Fay 可接受的格式：
  16 kHz / mono / 16-bit signed PCM (little-endian) / 无 WAV 头
"""

import os
import asyncio
import logging
import tempfile
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)


class AudioConvertService:
    """音频转换服务——依赖系统 ffmpeg"""

    def __init__(self):
        self.ffmpeg = settings.FFMPEG_PATH or "ffmpeg"
        self.sample_rate = 16000
        self.channels = 1

    async def convert_blob_to_pcm(self, blob: bytes, input_format: str = "webm") -> bytes:
        """
        将内存中的音频 blob 转成 16 kHz / mono / s16le 原始 PCM。

        Args:
            blob: 原始音频字节
            input_format: 输入格式后缀（webm / wav / ogg …）

        Returns:
            PCM bytes（无头）
        """
        temp_dir = settings.absolute_temp_dir
        os.makedirs(temp_dir, exist_ok=True)

        in_path = os.path.join(temp_dir, f"voice_in_{id(blob)}.{input_format}")
        out_path = os.path.join(temp_dir, f"voice_out_{id(blob)}.pcm")

        try:
            with open(in_path, "wb") as f:
                f.write(blob)

            cmd = [
                self.ffmpeg, "-y",
                "-i", in_path,
                "-f", "s16le",
                "-acodec", "pcm_s16le",
                "-ar", str(self.sample_rate),
                "-ac", str(self.channels),
                out_path,
            ]

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()

            if proc.returncode != 0:
                err_msg = stderr.decode("utf-8", errors="replace")
                logger.error(f"ffmpeg 转换失败 (rc={proc.returncode}): {err_msg[:500]}")
                raise RuntimeError(f"ffmpeg 转换失败: {err_msg[:200]}")

            with open(out_path, "rb") as f:
                pcm_data = f.read()

            duration = len(pcm_data) / (self.sample_rate * 2)
            logger.info(f"音频转换完成: {input_format} -> PCM, {len(pcm_data)} bytes, {duration:.1f}s")
            return pcm_data

        finally:
            for p in (in_path, out_path):
                try:
                    os.remove(p)
                except OSError:
                    pass

    async def convert_blob_to_wav(self, blob: bytes, input_format: str = "webm") -> str:
        """
        将 blob 转成 16 kHz / mono WAV 文件，返回文件路径。
        用于需要带 WAV 头的场景（如直接播放或 MuseTalk 输入）。
        """
        temp_dir = settings.absolute_temp_dir
        os.makedirs(temp_dir, exist_ok=True)

        in_path = os.path.join(temp_dir, f"voice_in_{id(blob)}.{input_format}")
        out_path = os.path.join(
            settings.absolute_audio_dir,
            f"voice_{id(blob)}.wav",
        )
        os.makedirs(os.path.dirname(out_path), exist_ok=True)

        try:
            with open(in_path, "wb") as f:
                f.write(blob)

            cmd = [
                self.ffmpeg, "-y",
                "-i", in_path,
                "-ar", str(self.sample_rate),
                "-ac", str(self.channels),
                out_path,
            ]

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()

            if proc.returncode != 0:
                raise RuntimeError(stderr.decode("utf-8", errors="replace")[:200])

            logger.info(f"音频转换完成: {input_format} -> WAV, {out_path}")
            return out_path

        finally:
            try:
                os.remove(in_path)
            except OSError:
                pass
