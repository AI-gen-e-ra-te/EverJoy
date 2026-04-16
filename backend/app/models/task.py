"""
任务数据模型

定义任务相关的数据结构和验证规则
"""

from typing import Optional, Dict, Any, List
from datetime import datetime
from enum import Enum

from pydantic import Field

from .base import BaseModel, TimestampMixin, IDMixin, UserMixin, MetadataMixin


class TaskStatus(str, Enum):
    """任务状态枚举"""
    PENDING = "pending"        # 等待中
    RUNNING = "running"        # 运行中
    COMPLETED = "completed"    # 已完成
    FAILED = "failed"          # 失败
    CANCELLED = "cancelled"    # 已取消
    TIMEOUT = "timeout"        # 超时


class TaskType(str, Enum):
    """任务类型枚举"""
    TTS_SYNTHESIS = "tts_synthesis"          # TTS 合成
    LIP_SYNC = "lip_sync"                    # 唇形同步
    AVATAR_PROCESSING = "avatar_processing"  # 头像处理
    LLM_INFERENCE = "llm_inference"          # LLM 推理
    VIDEO_GENERATION = "video_generation"    # 视频生成
    AUDIO_PROCESSING = "audio_processing"    # 音频处理
    CUSTOM = "custom"                        # 自定义任务


class TaskBase(BaseModel):
    """任务基础模型"""
    task_type: TaskType = Field(..., description="任务类型")
    status: TaskStatus = Field(TaskStatus.PENDING, description="任务状态")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="任务参数")
    progress: float = Field(0.0, ge=0.0, le=1.0, description="进度 (0.0-1.0)")
    error_message: Optional[str] = Field(None, description="错误信息")
    timeout_seconds: int = Field(300, gt=0, description="超时时间（秒）")
    max_retries: int = Field(0, ge=0, description="最大重试次数")
    retry_count: int = Field(0, ge=0, description="当前重试次数")
    priority: int = Field(0, description="优先级（数字越大优先级越高）")


class TaskCreate(TaskBase, UserMixin):
    """创建任务模型"""
    pass


class TaskUpdate(BaseModel):
    """更新任务模型"""
    status: Optional[TaskStatus] = None
    progress: Optional[float] = Field(None, ge=0.0, le=1.0)
    error_message: Optional[str] = None
    result: Optional[Dict[str, Any]] = None


class TaskInDB(IDMixin, TimestampMixin, MetadataMixin, TaskBase, UserMixin):
    """数据库中的任务模型"""
    started_at: Optional[datetime] = Field(None, description="开始时间")
    completed_at: Optional[datetime] = Field(None, description="完成时间")
    result: Optional[Dict[str, Any]] = Field(None, description="任务结果")
    execution_time: Optional[float] = Field(None, description="执行时间（秒）")
    queue_position: Optional[int] = Field(None, description="队列位置")

    class Config:
        from_attributes = True

    @property
    def duration(self) -> Optional[float]:
        """计算任务持续时间（秒）"""
        if self.started_at:
            end_time = self.completed_at or datetime.now()
            return (end_time - self.started_at).total_seconds()
        return None

    @property
    def is_active(self) -> bool:
        """检查任务是否活跃（等待中或运行中）"""
        return self.status in [TaskStatus.PENDING, TaskStatus.RUNNING]

    @property
    def is_finished(self) -> bool:
        """检查任务是否已完成"""
        return self.status in [
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
            TaskStatus.TIMEOUT
        ]


class Task(TaskInDB):
    """API返回的任务模型"""
    duration: Optional[float] = Field(None, description="持续时间（秒）")
    is_active: bool = Field(False, description="是否活跃")
    is_finished: bool = Field(False, description="是否已完成")

    @classmethod
    def from_orm(cls, obj):
        """从ORM对象创建任务模型"""
        return cls(
            id=obj.id,
            task_type=obj.task_type,
            status=obj.status,
            parameters=obj.parameters,
            progress=obj.progress,
            error_message=obj.error_message,
            timeout_seconds=obj.timeout_seconds,
            max_retries=obj.max_retries,
            retry_count=obj.retry_count,
            priority=obj.priority,
            user_id=obj.user_id,
            username=obj.username,
            created_at=obj.created_at,
            updated_at=obj.updated_at,
            started_at=obj.started_at,
            completed_at=obj.completed_at,
            result=obj.result,
            execution_time=obj.execution_time,
            queue_position=obj.queue_position,
            metadata=obj.metadata,
            duration=obj.duration,
            is_active=obj.is_active,
            is_finished=obj.is_finished
        )


class TaskResult(BaseModel):
    """任务结果模型"""
    task_id: str = Field(..., description="任务ID")
    status: TaskStatus = Field(..., description="任务状态")
    result: Optional[Dict[str, Any]] = Field(None, description="任务结果")
    error_message: Optional[str] = Field(None, description="错误信息")
    duration: Optional[float] = Field(None, description="持续时间（秒）")
    progress: float = Field(0.0, ge=0.0, le=1.0, description="进度")


class TaskQuery(BaseModel):
    """任务查询模型"""
    user_id: Optional[str] = None
    username: Optional[str] = None
    task_type: Optional[TaskType] = None
    status: Optional[TaskStatus] = None
    created_after: Optional[datetime] = None
    created_before: Optional[datetime] = None
    limit: int = Field(50, ge=1, le=1000)
    offset: int = Field(0, ge=0)
    order_by: str = Field("created_at", description="排序字段")
    order_desc: bool = Field(True, description="是否降序排列")