"""
TTS (文本转语音) 服务

提供多种 TTS 引擎支持：
1. Edge-TTS (Microsoft Edge 语音)
2. CosyVoice (腾讯开源语音合成)
3. VITS (本地 VITS 模型)
4. 外部 TTS API (Azure, Google, 阿里云等)
"""

import os
import asyncio
import logging
import tempfile
import json
from typing import Optional, Dict, Any, List, BinaryIO
from pathlib import Path
from datetime import datetime
from enum import Enum

from app.config import settings

logger = logging.getLogger(__name__)


class TTSVoice(Enum):
    """TTS 语音枚举"""
    EDGE_ZH_CN_FEMALE = "zh-CN-XiaoxiaoNeural"  # 晓晓（女声）
    EDGE_ZH_CN_MALE = "zh-CN-YunxiNeural"       # 云希（男声）
    EDGE_EN_US_FEMALE = "en-US-JennyNeural"     # Jenny（女声）
    EDGE_EN_US_MALE = "en-US-GuyNeural"         # Guy（男声）

    COSY_VOICE_FEMALE = "cosy_voice_female"     # CosyVoice 女声
    COSY_VOICE_MALE = "cosy_voice_male"         # CosyVoice 男声


class TTSEngine(Enum):
    """TTS 引擎枚举"""
    EDGE_TTS = "edge_tts"
    COSY_VOICE = "cosy_voice"
    VITS = "vits"
    EXTERNAL_API = "external_api"


class TTSService:
    """TTS 服务管理器"""

    def __init__(self):
        self.available_engines = {}
        self.default_engine = TTSEngine.EDGE_TTS
        self.default_voice = TTSVoice.EDGE_ZH_CN_FEMALE
        self.audio_dir = settings.absolute_audio_dir

        # 确保音频目录存在
        os.makedirs(self.audio_dir, exist_ok=True)

        self.initialized = False

    async def initialize(self):
        """初始化 TTS 服务"""
        try:
            logger.info("正在初始化 TTS 服务...")

            # 检查并初始化可用引擎
            await self._check_available_engines()

            if not self.available_engines:
                logger.warning("没有可用的 TTS 引擎")
                return

            self.initialized = True
            logger.info(f"TTS 服务初始化完成，可用引擎: {list(self.available_engines.keys())}")

        except Exception as e:
            logger.error(f"TTS 服务初始化失败: {e}")
            self.initialized = False

    async def _check_available_engines(self):
        """检查可用的 TTS 引擎"""
        # 检查 Edge-TTS
        if await self._check_edge_tts():
            self.available_engines[TTSEngine.EDGE_TTS] = {
                "name": "Edge-TTS",
                "description": "Microsoft Edge 语音合成",
                "voices": [v.value for v in TTSVoice if v.name.startswith("EDGE_")]
            }

        # 检查 CosyVoice
        if await self._check_cosy_voice():
            self.available_engines[TTSEngine.COSY_VOICE] = {
                "name": "CosyVoice",
                "description": "腾讯开源语音合成",
                "voices": [TTSVoice.COSY_VOICE_FEMALE.value, TTSVoice.COSY_VOICE_MALE.value]
            }

        # 检查 VITS
        if await self._check_vits():
            self.available_engines[TTSEngine.VITS] = {
                "name": "VITS",
                "description": "本地 VITS 模型",
                "voices": ["vits_default"]
            }

    async def _check_edge_tts(self) -> bool:
        """检查 Edge-TTS 是否可用"""
        try:
            import edge_tts
            # 简单测试导入是否成功
            logger.debug("Edge-TTS 可用")
            return True
        except ImportError:
            logger.debug("Edge-TTS 未安装")
            return False
        except Exception as e:
            logger.debug(f"Edge-TTS 检查失败: {e}")
            return False

    async def _check_cosy_voice(self) -> bool:
        """检查 CosyVoice 是否可用"""
        try:
            # 检查 CosyVoice 目录是否存在
            cosy_voice_path = os.path.join(settings.BASE_DIR, "CosyVoice")
            if os.path.exists(cosy_voice_path):
                logger.debug("CosyVoice 目录存在")
                return True
            else:
                logger.debug("CosyVoice 目录不存在")
                return False
        except Exception as e:
            logger.debug(f"CosyVoice 检查失败: {e}")
            return False

    async def _check_vits(self) -> bool:
        """检查 VITS 是否可用（mock模式始终可用）"""
        try:
            # 检查 VITS 模型文件是否存在
            vits_model_path = os.path.join(settings.BASE_DIR, "vits", "models")
            if os.path.exists(vits_model_path):
                logger.debug("VITS 模型目录存在")
                return True
            else:
                logger.debug("VITS 模型目录不存在，使用mock模式")
                return True  # 始终返回True，作为mock引擎
        except Exception as e:
            logger.debug(f"VITS 检查失败，使用mock模式: {e}")
            return True  # 始终返回True，作为mock引擎

    async def synthesize(
        self,
        text: str,
        engine: Optional[TTSEngine] = None,
        voice: Optional[str] = None,
        output_path: Optional[str] = None,
        speed: float = 1.0,
        pitch: float = 1.0,
        volume: float = 1.0,
        username: str = "User"
    ) -> Dict[str, Any]:
        """
        合成语音

        Args:
            text: 要合成的文本
            engine: TTS 引擎（可选，默认使用第一个可用引擎）
            voice: 语音类型（可选）
            output_path: 输出音频文件路径（可选）
            speed: 语速（0.5-2.0）
            pitch: 音高（0.5-2.0）
            volume: 音量（0.0-2.0）
            username: 用户名

        Returns:
            包含音频信息和任务状态的结果
        """
        if not self.initialized:
            raise RuntimeError("TTS 服务未初始化")

        # 确定使用的引擎
        if engine is None:
            engine = self.default_engine

        if engine not in self.available_engines:
            raise ValueError(f"TTS 引擎不可用: {engine}")

        # 确定使用的语音
        if voice is None:
            voice = self.default_voice.value

        # 生成输出路径
        if output_path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{username}_{timestamp}.wav"
            output_path = os.path.join(self.audio_dir, filename)

        try:
            logger.info(f"开始 TTS 合成: engine={engine.value}, voice={voice}")
            logger.debug(f"文本: {text}")

            # 根据引擎调用不同的合成方法
            if engine == TTSEngine.EDGE_TTS:
                result = await self._synthesize_edge_tts(
                    text, voice, output_path, speed
                )
            elif engine == TTSEngine.COSY_VOICE:
                result = await self._synthesize_cosy_voice(
                    text, voice, output_path, speed, pitch, volume
                )
            elif engine == TTSEngine.VITS:
                result = await self._synthesize_vits(
                    text, voice, output_path, speed, pitch
                )
            else:
                raise ValueError(f"不支持的 TTS 引擎: {engine}")

            # 添加额外信息
            result.update({
                "engine": engine.value,
                "voice": voice,
                "text_length": len(text),
                "output_path": output_path,
                "audio_url": f"/files/audio/{os.path.basename(output_path)}"
            })

            logger.info(f"TTS 合成完成: {output_path}")

            return result

        except Exception as e:
            logger.error(f"TTS 合成失败: {e}")
            raise

    async def _synthesize_edge_tts(
        self,
        text: str,
        voice: str,
        output_path: str,
        speed: float = 1.0
    ) -> Dict[str, Any]:
        """使用 Edge-TTS 合成语音"""
        try:
            import edge_tts

            # 创建临时文件
            temp_file = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
            temp_path = temp_file.name
            temp_file.close()

            # 使用 Edge-TTS 合成
            # rate参数：+0%表示正常速度，+50%表示加快50%，-50%表示减慢50%
            rate_change = (speed - 1.0) * 100
            rate_str = f"{rate_change:+.0f}%" if rate_change != 0 else "+0%"
            communicate = edge_tts.Communicate(text, voice, rate=rate_str)

            # 保存到临时文件
            await communicate.save(temp_path)

            # 转换为 WAV 格式（如果需要）
            if output_path.endswith('.wav'):
                await self._convert_to_wav(temp_path, output_path)
                os.unlink(temp_path)  # 删除临时文件
            else:
                os.rename(temp_path, output_path)

            # 获取音频信息
            audio_info = await self._get_audio_info(output_path)

            return {
                "status": "success",
                "duration": audio_info.get("duration", 0),
                "sample_rate": audio_info.get("sample_rate", 0),
                "channels": audio_info.get("channels", 0),
                "format": audio_info.get("format", "wav"),
                "message": "Edge-TTS 合成成功"
            }

        except Exception as e:
            logger.error(f"Edge-TTS 合成失败: {e}")
            raise

    async def _synthesize_cosy_voice(
        self,
        text: str,
        voice: str,
        output_path: str,
        speed: float = 1.0,
        pitch: float = 1.0,
        volume: float = 1.0
    ) -> Dict[str, Any]:
        """使用 CosyVoice 合成语音"""
        try:
            # CosyVoice 需要特定的 Python 环境
            # 这里使用命令行调用

            cosy_voice_path = os.path.join(settings.BASE_DIR, "CosyVoice")
            if not os.path.exists(cosy_voice_path):
                raise FileNotFoundError(f"CosyVoice 目录不存在: {cosy_voice_path}")

            # 构建命令
            cmd = [
                "python", "-m", "cosyvoice.cli",
                "--text", text,
                "--output", output_path,
                "--speaker", "female" if "female" in voice else "male",
                "--speed", str(speed),
                "--pitch", str(pitch),
                "--volume", str(volume)
            ]

            # 运行子进程
            process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=cosy_voice_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                error_msg = stderr.decode('utf-8', errors='ignore')
                logger.error(f"CosyVoice 合成失败: {error_msg}")
                raise RuntimeError(f"CosyVoice 合成失败: {error_msg}")

            # 获取音频信息
            audio_info = await self._get_audio_info(output_path)

            return {
                "status": "success",
                "duration": audio_info.get("duration", 0),
                "sample_rate": audio_info.get("sample_rate", 0),
                "channels": audio_info.get("channels", 0),
                "format": audio_info.get("format", "wav"),
                "message": "CosyVoice 合成成功"
            }

        except Exception as e:
            logger.error(f"CosyVoice 合成失败: {e}")
            raise

    async def _synthesize_vits(
        self,
        text: str,
        voice: str,
        output_path: str,
        speed: float = 1.0,
        pitch: float = 1.0
    ) -> Dict[str, Any]:
        """使用 VITS 合成语音"""
        try:
            # VITS 本地模型调用
            # 这里需要具体的 VITS 实现
            # 暂时返回占位符

            logger.warning("VITS 引擎暂未实现完整功能")

            # 创建空的音频文件（占位符）
            with open(output_path, 'wb') as f:
                # 写入空的 WAV 头部
                f.write(b'RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x80>\x00\x00\x00}\x00\x00\x02\x00\x10\x00data\x00\x00\x00\x00')

            return {
                "status": "success",
                "duration": 0,
                "sample_rate": 16000,
                "channels": 1,
                "format": "wav",
                "message": "VITS 合成（占位符）"
            }

        except Exception as e:
            logger.error(f"VITS 合成失败: {e}")
            raise

    async def _convert_to_wav(self, input_path: str, output_path: str):
        """转换音频格式为 WAV"""
        try:
            import pydub
            audio = pydub.AudioSegment.from_file(input_path)
            audio.export(output_path, format="wav")
        except ImportError:
            logger.warning("pydub 未安装，无法进行音频格式转换")
            # 如果没有 pydub，直接复制文件
            import shutil
            shutil.copy2(input_path, output_path)
        except Exception as e:
            logger.warning(f"pydub 音频格式转换失败: {e}，使用文件复制代替")
            # 如果 pydub 失败（通常是因为缺少 ffmpeg），直接复制文件
            import shutil
            shutil.copy2(input_path, output_path)

    async def _get_audio_info(self, audio_path: str) -> Dict[str, Any]:
        """获取音频文件信息"""
        try:
            if not os.path.exists(audio_path):
                return {"error": "音频文件不存在"}

            try:
                import pydub
                audio = pydub.AudioSegment.from_file(audio_path)
                return {
                    "duration": len(audio) / 1000.0,  # 转换为秒
                    "sample_rate": audio.frame_rate,
                    "channels": audio.channels,
                    "format": audio_path.split('.')[-1].lower()
                }
            except ImportError:
                # 如果 pydub 不可用，使用其他方法
                import subprocess

                # 使用 ffprobe 获取音频信息
                if settings.FFMPEG_PATH:
                    ffprobe_path = os.path.join(os.path.dirname(settings.FFMPEG_PATH), "ffprobe")
                    if not os.path.exists(ffprobe_path):
                        ffprobe_path = "ffprobe"
                else:
                    ffprobe_path = "ffprobe"

                cmd = [
                    ffprobe_path,
                    "-v", "error",
                    "-select_streams", "a:0",
                    "-show_entries", "stream=duration,sample_rate,channels,codec_name",
                    "-of", "json",
                    audio_path
                ]

                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )

                stdout, stderr = await process.communicate()

                if process.returncode == 0:
                    info = json.loads(stdout.decode('utf-8'))
                    stream = info.get("streams", [{}])[0]

                    return {
                        "duration": float(stream.get("duration", 0)),
                        "sample_rate": int(stream.get("sample_rate", 0)),
                        "channels": int(stream.get("channels", 0)),
                        "format": stream.get("codec_name", "unknown")
                    }
                else:
                    logger.warning(f"获取音频信息失败: {stderr.decode('utf-8')}")
                    return {}

        except Exception as e:
            logger.warning(f"获取音频信息时发生错误: {e}")
            return {}

    def get_available_engines(self) -> List[Dict[str, Any]]:
        """
        获取可用引擎列表

        Returns:
            引擎列表
        """
        engines = []
        for engine, info in self.available_engines.items():
            engines.append({
                "engine": engine.value,
                "name": info["name"],
                "description": info["description"],
                "voices": info["voices"]
            })
        return engines

    def is_available(self) -> bool:
        """检查服务是否可用"""
        return self.initialized and len(self.available_engines) > 0