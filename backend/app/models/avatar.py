"""
数字人形象数据模型

定义头像相关的数据结构和验证规则
"""

from typing import Optional, Dict, Any, List
from datetime import datetime
from enum import Enum

from pydantic import Field, HttpUrl

from .base import BaseModel, TimestampMixin, IDMixin, UserMixin, MetadataMixin


class AvatarType(str, Enum):
    """头像类型枚举"""
    DEFAULT = "default"    # 默认头像
    USER = "user"          # 用户上传头像
    SYSTEM = "system"      # 系统头像


class AvatarFormat(str, Enum):
    """头像格式枚举"""
    PNG = "png"
    JPG = "jpg"
    JPEG = "jpeg"
    WEBP = "webp"


class AvatarSize(str, Enum):
    """头像尺寸枚举"""
    ORIGINAL = "original"      # 原始尺寸
    LARGE = "large"           # 1024x1024
    MEDIUM = "medium"         # 512x512
    SMALL = "small"           # 256x256
    THUMBNAIL = "thumbnail"   # 128x128


class AvatarGender(str, Enum):
    """头像性别枚举"""
    MALE = "male"
    FEMALE = "female"
    NEUTRAL = "neutral"
    UNSPECIFIED = "unspecified"


class AvatarBase(BaseModel):
    """头像基础模型"""
    name: str = Field(..., min_length=1, max_length=100, description="头像名称")
    description: Optional[str] = Field(None, max_length=500, description="头像描述")
    avatar_type: AvatarType = Field(..., description="头像类型")
    gender: AvatarGender = Field(AvatarGender.UNSPECIFIED, description="头像性别")
    format: AvatarFormat = Field(AvatarFormat.PNG, description="头像格式")
    is_public: bool = Field(False, description="是否公开")
    tags: List[str] = Field(default_factory=list, description="标签")


class AvatarCreate(AvatarBase, UserMixin):
    """创建头像模型"""
    file_data: Optional[bytes] = Field(None, description="文件数据（Base64编码）")
    file_url: Optional[HttpUrl] = Field(None, description="文件URL")
    file_path: Optional[str] = Field(None, description="文件路径")


class AvatarUpdate(BaseModel):
    """更新头像模型"""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    gender: Optional[AvatarGender] = None
    is_public: Optional[bool] = None
    tags: Optional[List[str]] = None


class ImageSize(BaseModel):
    """图像尺寸模型"""
    width: int = Field(..., gt=0, description="宽度（像素）")
    height: int = Field(..., gt=0, description="高度（像素）")


class AvatarFileInfo(BaseModel):
    """头像文件信息模型"""
    original: Optional[str] = Field(None, description="原始文件路径")
    large: Optional[str] = Field(None, description="大尺寸文件路径")
    medium: Optional[str] = Field(None, description="中尺寸文件路径")
    small: Optional[str] = Field(None, description="小尺寸文件路径")
    thumbnail: Optional[str] = Field(None, description="缩略图文件路径")
    cropped: Optional[str] = Field(None, description="裁剪后文件路径")


class AvatarInDB(IDMixin, TimestampMixin, MetadataMixin, AvatarBase, UserMixin):
    """数据库中的头像模型"""
    file_info: AvatarFileInfo = Field(default_factory=AvatarFileInfo, description="文件信息")
    file_hash: Optional[str] = Field(None, description="文件哈希值")
    file_size: int = Field(0, description="文件大小（字节）")
    image_size: Optional[ImageSize] = Field(None, description="图像尺寸")
    download_count: int = Field(0, description="下载次数")
    use_count: int = Field(0, description="使用次数")

    # URLs
    urls: Dict[AvatarSize, Optional[str]] = Field(
        default_factory=dict,
        description="各尺寸的URL"
    )

    class Config:
        from_attributes = True


class Avatar(AvatarInDB):
    """API返回的头像模型"""
    @classmethod
    def from_orm(cls, obj):
        """从ORM对象创建头像模型"""
        return cls(
            id=obj.id,
            name=obj.name,
            description=obj.description,
            avatar_type=obj.avatar_type,
            gender=obj.gender,
            format=obj.format,
            is_public=obj.is_public,
            tags=obj.tags,
            user_id=obj.user_id,
            username=obj.username,
            created_at=obj.created_at,
            updated_at=obj.updated_at,
            file_info=obj.file_info,
            file_hash=obj.file_hash,
            file_size=obj.file_size,
            image_size=obj.image_size,
            download_count=obj.download_count,
            use_count=obj.use_count,
            urls=obj.urls,
            metadata=obj.metadata
        )


class AvatarURLs(BaseModel):
    """头像URLs模型"""
    original: Optional[str] = Field(None, description="原始尺寸URL")
    large: Optional[str] = Field(None, description="大尺寸URL")
    medium: Optional[str] = Field(None, description="中尺寸URL")
    small: Optional[str] = Field(None, description="小尺寸URL")
    thumbnail: Optional[str] = Field(None, description="缩略图URL")


class AvatarQuery(BaseModel):
    """头像查询模型"""
    user_id: Optional[str] = None
    username: Optional[str] = None
    avatar_type: Optional[AvatarType] = None
    gender: Optional[AvatarGender] = None
    is_public: Optional[bool] = None
    tags: Optional[List[str]] = None
    created_after: Optional[datetime] = None
    created_before: Optional[datetime] = None
    limit: int = Field(50, ge=1, le=1000)
    offset: int = Field(0, ge=0)
    order_by: str = Field("created_at", description="排序字段")
    order_desc: bool = Field(True, description="是否降序排列")


class AvatarUploadResponse(BaseModel):
    """头像上传响应模型"""
    avatar_id: str = Field(..., description="头像ID")
    name: str = Field(..., description="头像名称")
    urls: AvatarURLs = Field(..., description="各尺寸URL")
    file_size: int = Field(..., description="文件大小")
    image_size: ImageSize = Field(..., description="图像尺寸")
    message: str = Field(..., description="消息")