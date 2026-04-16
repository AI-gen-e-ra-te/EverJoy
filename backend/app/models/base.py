"""
基础数据模型

定义所有模型共享的基础字段和功能
"""

from datetime import datetime
from typing import Optional, Any, Dict
from pydantic import BaseModel as PydanticBaseModel, ConfigDict, Field


class BaseModel(PydanticBaseModel):
    """基础模型类"""
    model_config = ConfigDict(
        from_attributes=True,  # 支持从ORM对象转换
        populate_by_name=True,  # 支持别名
        arbitrary_types_allowed=True,
    )


class TimestampMixin(BaseModel):
    """时间戳混入类"""
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: Optional[datetime] = None


class IDMixin(BaseModel):
    """ID混入类"""
    id: str = Field(..., description="唯一标识符")


class UserMixin(BaseModel):
    """用户混入类"""
    user_id: Optional[str] = Field(None, description="用户ID")
    username: Optional[str] = Field(None, description="用户名")


class StatusMixin(BaseModel):
    """状态混入类"""
    status: str = Field("active", description="状态")
    is_active: bool = Field(True, description="是否活跃")


class MetadataMixin(BaseModel):
    """元数据混入类"""
    metadata: Dict[str, Any] = Field(default_factory=dict, description="额外元数据")