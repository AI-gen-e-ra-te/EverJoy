"""
对话数据模型

定义对话和消息相关的数据结构和验证规则
"""

from typing import Optional, Dict, Any, List
from datetime import datetime
from enum import Enum

from pydantic import Field

from .base import BaseModel, TimestampMixin, IDMixin, UserMixin, MetadataMixin


class MessageRole(str, Enum):
    """消息角色枚举"""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    FUNCTION = "function"


class ConversationStatus(str, Enum):
    """对话状态枚举"""
    ACTIVE = "active"          # 活跃
    PAUSED = "paused"          # 暂停
    COMPLETED = "completed"    # 完成
    ARCHIVED = "archived"      # 归档


class MessageType(str, Enum):
    """消息类型枚举"""
    TEXT = "text"              # 文本
    AUDIO = "audio"            # 音频
    IMAGE = "image"            # 图像
    VIDEO = "video"            # 视频
    FILE = "file"              # 文件
    SYSTEM = "system"          # 系统消息


class MessageBase(BaseModel):
    """消息基础模型"""
    content: str = Field(..., min_length=1, description="消息内容")
    role: MessageRole = Field(..., description="消息角色")
    message_type: MessageType = Field(MessageType.TEXT, description="消息类型")
    is_ai_response: bool = Field(False, description="是否是AI响应")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="消息元数据")


class MessageCreate(MessageBase):
    """创建消息模型"""
    conversation_id: str = Field(..., description="对话ID")


class MessageInDB(IDMixin, TimestampMixin, MessageBase):
    """数据库中的消息模型"""
    conversation_id: str = Field(..., description="对话ID")
    sequence_number: int = Field(..., description="序列号")
    token_count: Optional[int] = Field(None, description="令牌数量")
    audio_url: Optional[str] = Field(None, description="音频URL")
    video_url: Optional[str] = Field(None, description="视频URL")
    file_urls: List[str] = Field(default_factory=list, description="文件URL列表")
    parent_message_id: Optional[str] = Field(None, description="父消息ID")

    class Config:
        from_attributes = True


class Message(MessageInDB):
    """API返回的消息模型"""
    @classmethod
    def from_orm(cls, obj):
        """从ORM对象创建消息模型"""
        return cls(
            id=obj.id,
            conversation_id=obj.conversation_id,
            sequence_number=obj.sequence_number,
            content=obj.content,
            role=obj.role,
            message_type=obj.message_type,
            is_ai_response=obj.is_ai_response,
            token_count=obj.token_count,
            audio_url=obj.audio_url,
            video_url=obj.video_url,
            file_urls=obj.file_urls,
            parent_message_id=obj.parent_message_id,
            created_at=obj.created_at,
            metadata=obj.metadata
        )


class ConversationBase(BaseModel):
    """对话基础模型"""
    title: Optional[str] = Field(None, max_length=200, description="对话标题")
    status: ConversationStatus = Field(ConversationStatus.ACTIVE, description="对话状态")
    avatar_id: Optional[str] = Field(None, description="使用的头像ID")
    tts_engine: Optional[str] = Field(None, description="TTS引擎")
    tts_voice: Optional[str] = Field(None, description="TTS语音")
    llm_model: Optional[str] = Field(None, description="LLM模型")


class ConversationCreate(ConversationBase, UserMixin):
    """创建对话模型"""
    pass


class ConversationUpdate(BaseModel):
    """更新对话模型"""
    title: Optional[str] = Field(None, max_length=200)
    status: Optional[ConversationStatus] = None
    avatar_id: Optional[str] = None
    tts_engine: Optional[str] = None
    tts_voice: Optional[str] = None
    llm_model: Optional[str] = None


class ConversationInDB(IDMixin, TimestampMixin, MetadataMixin, ConversationBase, UserMixin):
    """数据库中的对话模型"""
    message_count: int = Field(0, description="消息数量")
    last_message_at: Optional[datetime] = Field(None, description="最后消息时间")
    total_tokens: int = Field(0, description="总令牌数")
    duration_seconds: float = Field(0.0, description="对话持续时间（秒）")

    # 关系字段（虚拟）
    messages: List[str] = Field(default_factory=list, description="消息ID列表")

    class Config:
        from_attributes = True


class Conversation(ConversationInDB):
    """API返回的对话模型"""
    @classmethod
    def from_orm(cls, obj):
        """从ORM对象创建对话模型"""
        return cls(
            id=obj.id,
            title=obj.title,
            status=obj.status,
            avatar_id=obj.avatar_id,
            tts_engine=obj.tts_engine,
            tts_voice=obj.tts_voice,
            llm_model=obj.llm_model,
            user_id=obj.user_id,
            username=obj.username,
            created_at=obj.created_at,
            updated_at=obj.updated_at,
            message_count=obj.message_count,
            last_message_at=obj.last_message_at,
            total_tokens=obj.total_tokens,
            duration_seconds=obj.duration_seconds,
            messages=obj.messages,
            metadata=obj.metadata
        )


class ConversationWithMessages(Conversation):
    """包含消息的对话模型"""
    message_list: List[Message] = Field(default_factory=list, description="消息列表")


class ConversationQuery(BaseModel):
    """对话查询模型"""
    user_id: Optional[str] = None
    username: Optional[str] = None
    status: Optional[ConversationStatus] = None
    avatar_id: Optional[str] = None
    created_after: Optional[datetime] = None
    created_before: Optional[datetime] = None
    has_messages: Optional[bool] = None
    limit: int = Field(50, ge=1, le=1000)
    offset: int = Field(0, ge=0)
    order_by: str = Field("last_message_at", description="排序字段")
    order_desc: bool = Field(True, description="是否降序排列")


class ConversationSummary(BaseModel):
    """对话摘要模型"""
    id: str = Field(..., description="对话ID")
    title: Optional[str] = Field(None, description="对话标题")
    status: ConversationStatus = Field(..., description="对话状态")
    message_count: int = Field(..., description="消息数量")
    last_message_at: Optional[datetime] = Field(None, description="最后消息时间")
    created_at: datetime = Field(..., description="创建时间")
    avatar_id: Optional[str] = Field(None, description="头像ID")


class ChatRequest(BaseModel):
    """聊天请求模型"""
    conversation_id: Optional[str] = Field(None, description="对话ID（为空时创建新对话）")
    message: str = Field(..., min_length=1, description="消息内容")
    avatar_id: Optional[str] = Field(None, description="头像ID")
    tts_enabled: bool = Field(True, description="是否启用TTS")
    lip_sync_enabled: bool = Field(True, description="是否启用唇形同步")
    stream: bool = Field(False, description="是否流式响应")


class ChatResponse(BaseModel):
    """聊天响应模型"""
    conversation_id: str = Field(..., description="对话ID")
    message_id: str = Field(..., description="消息ID")
    content: str = Field(..., description="响应内容")
    audio_url: Optional[str] = Field(None, description="音频URL")
    video_url: Optional[str] = Field(None, description="视频URL")
    token_count: int = Field(0, description="令牌数量")
    processing_time: float = Field(0.0, description="处理时间（秒）")