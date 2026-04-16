"""
用户数据模型

定义用户相关的数据结构和验证规则
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum

from pydantic import Field, validator

from .base import BaseModel, TimestampMixin, IDMixin, MetadataMixin


class UserRole(str, Enum):
    """用户角色枚举"""
    ADMIN = "admin"
    USER = "user"
    GUEST = "guest"


class UserStatus(str, Enum):
    """用户状态枚举"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    DELETED = "deleted"


class UserBase(BaseModel):
    """用户基础模型"""
    username: str = Field(..., min_length=3, max_length=50, description="用户名")
    email: Optional[str] = Field(None, description="邮箱")
    display_name: Optional[str] = Field(None, max_length=100, description="显示名称")
    avatar_url: Optional[str] = Field(None, description="头像URL")
    role: UserRole = Field(UserRole.USER, description="用户角色")
    status: UserStatus = Field(UserStatus.ACTIVE, description="用户状态")

    @validator("username")
    def validate_username(cls, v):
        """验证用户名"""
        # 只允许字母、数字、下划线和连字符
        import re
        if not re.match(r'^[a-zA-Z0-9_-]+$', v):
            raise ValueError("用户名只能包含字母、数字、下划线和连字符")
        return v


class UserCreate(UserBase):
    """创建用户模型"""
    password: str = Field(..., min_length=6, description="密码")


class UserUpdate(BaseModel):
    """更新用户模型"""
    email: Optional[str] = None
    display_name: Optional[str] = Field(None, max_length=100)
    avatar_url: Optional[str] = None
    role: Optional[UserRole] = None
    status: Optional[UserStatus] = None
    password: Optional[str] = Field(None, min_length=6)


class UserInDB(IDMixin, TimestampMixin, MetadataMixin, UserBase):
    """数据库中的用户模型"""
    hashed_password: Optional[str] = Field(None, description="哈希密码")
    last_login_at: Optional[datetime] = Field(None, description="最后登录时间")
    login_count: int = Field(0, description="登录次数")
    preferences: Dict[str, Any] = Field(default_factory=dict, description="用户偏好设置")

    # 关系字段（虚拟）
    avatars: List[str] = Field(default_factory=list, description="用户头像ID列表")
    tasks: List[str] = Field(default_factory=list, description="用户任务ID列表")
    conversations: List[str] = Field(default_factory=list, description="用户对话ID列表")

    class Config:
        from_attributes = True


class User(UserInDB):
    """API返回的用户模型（不包含敏感信息）"""
    hashed_password: Optional[str] = Field(None, exclude=True)  # 排除密码字段

    @classmethod
    def from_orm(cls, obj):
        """从ORM对象创建用户模型"""
        return cls(
            id=obj.id,
            username=obj.username,
            email=obj.email,
            display_name=obj.display_name,
            avatar_url=obj.avatar_url,
            role=obj.role,
            status=obj.status,
            created_at=obj.created_at,
            updated_at=obj.updated_at,
            last_login_at=obj.last_login_at,
            login_count=obj.login_count,
            preferences=obj.preferences,
            metadata=obj.metadata,
            avatars=obj.avatars,
            tasks=obj.tasks,
            conversations=obj.conversations
        )


class UserLogin(BaseModel):
    """用户登录模型"""
    username: str = Field(..., description="用户名")
    password: str = Field(..., description="密码")


class UserToken(BaseModel):
    """用户令牌模型"""
    access_token: str = Field(..., description="访问令牌")
    token_type: str = Field("bearer", description="令牌类型")
    expires_in: int = Field(3600, description="过期时间（秒）")
    refresh_token: Optional[str] = Field(None, description="刷新令牌")
    user: User = Field(..., description="用户信息")


class UserPreferences(BaseModel):
    """用户偏好设置模型"""
    theme: str = Field("light", description="主题（light/dark）")
    language: str = Field("zh-CN", description="语言")
    timezone: str = Field("Asia/Shanghai", description="时区")
    notification_enabled: bool = Field(True, description="是否启用通知")
    auto_save: bool = Field(True, description="是否自动保存")
    tts_engine: str = Field("edge_tts", description="默认TTS引擎")
    tts_voice: str = Field("zh-CN-XiaoxiaoNeural", description="默认TTS语音")
    avatar_id: Optional[str] = Field(None, description="默认头像ID")