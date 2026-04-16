"""
数据模型模块

包含应用程序的所有数据模型定义
"""

# 导入所有模型以便于访问
from .base import BaseModel
from .user import User, UserCreate, UserUpdate, UserInDB
from .task import Task, TaskCreate, TaskUpdate, TaskStatus
from .avatar import Avatar, AvatarCreate, AvatarUpdate
from .conversation import Conversation, Message, ConversationCreate

__all__ = [
    "BaseModel",
    "User", "UserCreate", "UserUpdate", "UserInDB",
    "Task", "TaskCreate", "TaskUpdate", "TaskStatus",
    "Avatar", "AvatarCreate", "AvatarUpdate",
    "Conversation", "Message", "ConversationCreate"
]