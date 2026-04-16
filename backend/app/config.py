"""
DigiPeople Core 配置管理 - 最小配置

使用 pydantic-settings 管理环境变量配置
"""

import os
from typing import List, Optional
from pydantic_settings import BaseSettings
from pydantic import validator, Field


class Settings(BaseSettings):
    """应用配置 - 最小配置"""

    # 后端服务监听地址和端口
    BACKEND_HOST: str = "0.0.0.0"
    BACKEND_PORT: int = 8002

    # 是否启用调试模式
    DEBUG: bool = True

    # 日志级别
    LOG_LEVEL: str = "INFO"

    # 项目根目录
    BASE_DIR: str = Field(default_factory=lambda: os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

    # 数据根目录
    DATA_DIR: str = "./data"

    # 子目录配置
    UPLOAD_DIR: str = "./data/uploads"
    AVATAR_DIR: str = "./data/avatars"
    TEMP_DIR: str = "./data/temp"
    AUDIO_DIR: str = "./data/audio"
    VIDEO_DIR: str = "./data/videos"

    # CORS 允许的源
    CORS_ORIGINS: List[str] = ["http://localhost:8002", "http://127.0.0.1:8002"]

    # Fay 服务配置
    FAY_API_URL: str = "http://127.0.0.1:5000/v1/chat/completions"  # OpenAI兼容接口
    FAY_HOST: str = "127.0.0.1"  # Fay WebSocket主机
    FAY_PORT: int = 10002  # Fay WebSocket端口
    FAY_WS_URL: str = "ws://127.0.0.1:10002"  # Fay WebSocket URL
    FAY_TIMEOUT: int = 120  # 请求超时时间（秒）- Fay 需要调用 embedding + LLM，可能较慢
    FAY_ADMIN_PORT: int = 5000  # Fay 管理界面端口
    FAY_MCP_PORT: int = 5010  # Fay MCP 服务端口

    # MuseTalk 配置
    MUSETALK_PATH: str = "./MuseTalk"  # MuseTalk项目路径
    MUSETALK_MODEL_VERSION: str = "v15"  # v15 或 v1，推荐 v15
    MUSETALK_USE_FLOAT16: bool = True  # 是否使用 float16 模式
    MUSETALK_BBOX_SHIFT: int = 0  # 边界框偏移
    MUSETALK_FPS: int = 25  # 视频帧率
    FFMPEG_PATH: Optional[str] = None  # FFmpeg路径（如果不在系统PATH中）
    MUSETALK_PYTHON_PATH: Optional[str] = None  # MuseTalk Python解释器路径（如果使用特定环境）

    # LLM 配置（预留，当前通过 Fay 集成）
    # 注意：当前版本所有LLM调用通过Fay进行，这些配置仅为占位符
    OLLAMA_BASE_URL: str = "http://localhost:11434/v1"
    OLLAMA_MODEL: str = "llama3.2"
    VLLM_BASE_URL: str = "http://localhost:8000/v1"
    VLLM_MODEL: str = "Qwen/Qwen2.5-7B-Instruct"

    # TTS 配置（第一版使用mock TTS）
    TTS_ENGINE: str = "mock"  # mock, edge_tts, cosy_voice, vits
    TTS_VOICE: str = "zh-CN-XiaoxiaoNeural"  # 默认语音
    TTS_SPEED: float = 1.0  # 语速
    TTS_PITCH: float = 1.0  # 音高
    TTS_VOLUME: float = 1.0  # 音量

    # 性能配置
    MAX_UPLOAD_SIZE: int = 100  # 最大上传文件大小（MB）
    MAX_CONCURRENT_TASKS: int = 2  # 并发任务数
    VIDEO_GENERATION_TIMEOUT: int = 300  # 视频生成超时时间（秒）
    RELOAD: bool = True  # 是否启用热重载（开发环境）
    VERBOSE_LOGGING: bool = False  # 是否启用详细日志

    # ======================
    # 验证器
    # ======================

    @validator("CORS_ORIGINS", pre=True)
    def parse_cors_origins(cls, v):
        """解析 CORS_ORIGINS 字符串为列表"""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v

    @validator("LOG_LEVEL")
    def validate_log_level(cls, v):
        """验证日志级别"""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in valid_levels:
            raise ValueError(f"无效的日志级别: {v}，有效级别: {valid_levels}")
        return v.upper()

    # ======================
    # 计算属性
    # ======================

    @property
    def absolute_data_dir(self) -> str:
        """获取绝对路径的数据目录"""
        if os.path.isabs(self.DATA_DIR):
            return self.DATA_DIR
        return os.path.join(self.BASE_DIR, self.DATA_DIR)

    @property
    def absolute_upload_dir(self) -> str:
        """获取绝对路径的上传目录"""
        if os.path.isabs(self.UPLOAD_DIR):
            return self.UPLOAD_DIR
        return os.path.join(self.BASE_DIR, self.UPLOAD_DIR)

    @property
    def absolute_avatar_dir(self) -> str:
        """获取绝对路径的头像目录"""
        if os.path.isabs(self.AVATAR_DIR):
            return self.AVATAR_DIR
        return os.path.join(self.BASE_DIR, self.AVATAR_DIR)

    @property
    def absolute_temp_dir(self) -> str:
        """获取绝对路径的临时目录"""
        if os.path.isabs(self.TEMP_DIR):
            return self.TEMP_DIR
        return os.path.join(self.BASE_DIR, self.TEMP_DIR)

    @property
    def absolute_audio_dir(self) -> str:
        """获取绝对路径的音频目录"""
        if os.path.isabs(self.AUDIO_DIR):
            return self.AUDIO_DIR
        return os.path.join(self.BASE_DIR, self.AUDIO_DIR)

    @property
    def absolute_video_dir(self) -> str:
        """获取绝对路径的视频目录"""
        if os.path.isabs(self.VIDEO_DIR):
            return self.VIDEO_DIR
        return os.path.join(self.BASE_DIR, self.VIDEO_DIR)

    @property
    def absolute_musetalk_path(self) -> str:
        """获取绝对路径的 MuseTalk 目录"""
        if os.path.isabs(self.MUSETALK_PATH):
            return self.MUSETALK_PATH
        return os.path.join(self.BASE_DIR, self.MUSETALK_PATH)

    @property
    def musetalk_root(self) -> str:
        """MuseTalk 根目录（与 absolute_musetalk_path 相同）"""
        return self.absolute_musetalk_path

    @property
    def musetalk_unet_model_path(self) -> str:
        """获取 UNet 模型路径"""
        model_filename = "unet.pth" if self.MUSETALK_MODEL_VERSION == "v15" else "pytorch_model.bin"
        model_dir = "musetalkV15" if self.MUSETALK_MODEL_VERSION == "v15" else "musetalk"
        return os.path.join(self.absolute_musetalk_path, "models", model_dir, model_filename)

    @property
    def musetalk_unet_config_path(self) -> str:
        """获取 UNet 配置文件路径"""
        model_dir = "musetalkV15" if self.MUSETALK_MODEL_VERSION == "v15" else "musetalk"
        return os.path.join(self.absolute_musetalk_path, "models", model_dir, "musetalk.json")

    @property
    def musetalk_whisper_dir(self) -> str:
        """获取 Whisper 模型目录路径"""
        return os.path.join(self.absolute_musetalk_path, "models", "whisper")

    @property
    def musetalk_temp_config_dir(self) -> str:
        """获取临时配置文件目录"""
        temp_dir = os.path.join(self.absolute_temp_dir, "musetalk_configs")
        os.makedirs(temp_dir, exist_ok=True)
        return temp_dir

    @property
    def musetalk_ffmpeg_path(self) -> Optional[str]:
        """获取 FFmpeg 路径"""
        return self.FFMPEG_PATH

    # ======================
    # Pydantic 配置
    # ======================

    class Config:
        env_file = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env")
        env_file_encoding = "utf-8"
        case_sensitive = False


# 全局配置实例
settings = Settings()