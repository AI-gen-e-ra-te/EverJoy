"""
数字人形象（Avatar）管理 API

提供数字人形象的上传、预处理、查询等功能
"""

import os
import logging
import uuid
from typing import Optional, Dict, Any
from datetime import datetime

from fastapi import APIRouter, HTTPException, status, UploadFile, File, Form, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.services.avatar_service import AvatarService
from app.services.job_service import JobService, JobType

logger = logging.getLogger(__name__)

router = APIRouter()


# 依赖注入
async def get_avatar_service(request: Request) -> AvatarService:
    """获取头像服务实例"""
    return request.app.state.avatar_service


async def get_job_service(request: Request) -> JobService:
    """获取任务服务实例"""
    return request.app.state.job_service


# 请求/响应模型
class AvatarUploadResponse(BaseModel):
    """上传响应模型"""
    success: bool = Field(..., description="是否成功")
    task_id: str = Field(..., description="任务ID")
    avatar_id: str = Field(..., description="Avatar ID")
    message: str = Field(..., description="消息")
    video_path: Optional[str] = Field(None, description="视频保存路径")


class AvatarInfoResponse(BaseModel):
    """Avatar信息响应模型"""
    success: bool = Field(..., description="是否成功")
    avatar_id: str = Field(..., description="Avatar ID")
    info: Optional[Dict[str, Any]] = Field(None, description="Avatar信息")
    message: Optional[str] = Field(None, description="消息")


class AvatarStatusResponse(BaseModel):
    """Avatar状态响应模型"""
    success: bool = Field(..., description="是否成功")
    avatar_id: str = Field(..., description="Avatar ID")
    status: str = Field(..., description="状态")
    task_status: Optional[Dict[str, Any]] = Field(None, description="任务状态")
    message: Optional[str] = Field(None, description="消息")


@router.post("/upload", response_model=AvatarUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_mp4_avatar(
    request: Request,
    file: UploadFile = File(..., description="MP4视频文件"),
    avatar_name: Optional[str] = Form(None, description="Avatar名称（可选）"),
    description: Optional[str] = Form(None, description="描述（可选）"),
    avatar_service: AvatarService = Depends(get_avatar_service),
    job_service: JobService = Depends(get_job_service)
) -> AvatarUploadResponse:
    """
    上传MP4视频文件作为数字人avatar

    步骤：
    1. 保存上传文件到data/uploads目录
    2. 生成唯一的avatar_id和task_id
    3. 创建avatar预处理任务
    4. 返回task_id和avatar_id供前端轮询
    """
    try:
        # 验证文件类型
        if not file.filename.lower().endswith('.mp4'):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="仅支持MP4格式视频文件"
            )

        # 生成唯一ID
        avatar_id = f"avatar_{uuid.uuid4().hex[:8]}_{int(datetime.now().timestamp())}"
        task_id = f"task_{uuid.uuid4().hex[:8]}_{int(datetime.now().timestamp())}"

        # 确保上传目录存在
        from app.config import settings
        upload_dir = settings.absolute_upload_dir
        os.makedirs(upload_dir, exist_ok=True)

        # 保存上传文件
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_filename = f"{avatar_id}_{timestamp}.mp4"
        video_path = os.path.join(upload_dir, safe_filename)

        # 读取并保存文件
        content = await file.read()
        with open(video_path, 'wb') as f:
            f.write(content)

        logger.info(f"MP4文件上传成功: {video_path} ({len(content)} bytes)")

        # 创建avatar预处理任务
        task_parameters = {
            "video_path": video_path,
            "avatar_id": avatar_id,
            "original_filename": file.filename,
            "avatar_name": avatar_name,
            "description": description,
            "file_size": len(content)
        }

        # 创建任务
        job = await job_service.create_job(
            job_type=JobType.AVATAR_PROCESSING,
            parameters=task_parameters,
            user_id="anonymous",  # 第一阶段使用匿名用户
            username="anonymous",
            timeout_seconds=300,  # 5分钟超时
            max_retries=1
        )

        # 更新task_id为job的实际ID
        task_id = job.job_id

        return AvatarUploadResponse(
            success=True,
            task_id=task_id,
            avatar_id=avatar_id,
            message="MP4文件上传成功，已创建avatar预处理任务",
            video_path=video_path
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"上传MP4文件失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"上传失败: {str(e)}"
        )


@router.get("/{avatar_id}/info", response_model=AvatarInfoResponse)
async def get_avatar_info(
    avatar_id: str,
    avatar_service: AvatarService = Depends(get_avatar_service)
) -> AvatarInfoResponse:
    """
    获取Avatar信息

    根据avatar_id获取avatar的详细信息
    """
    try:
        # 获取avatar信息
        avatar_info = avatar_service.get_video_avatar(avatar_id)
        if not avatar_info:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Avatar不存在: {avatar_id}"
            )

        return AvatarInfoResponse(
            success=True,
            avatar_id=avatar_id,
            info=avatar_info,
            message="获取avatar信息成功"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取avatar信息失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取avatar信息失败: {str(e)}"
        )


@router.get("/{avatar_id}/status", response_model=AvatarStatusResponse)
async def get_avatar_status(
    avatar_id: str,
    request: Request,
    avatar_service: AvatarService = Depends(get_avatar_service),
    job_service: JobService = Depends(get_job_service)
) -> AvatarStatusResponse:
    """
    获取Avatar处理状态

    根据avatar_id获取关联的任务状态
    """
    try:
        # 获取avatar信息
        avatar_info = avatar_service.get_video_avatar(avatar_id)
        if not avatar_info:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Avatar不存在: {avatar_id}"
            )

        # 查找与avatar关联的任务
        # 在实际应用中，需要维护avatar_id和task_id的映射关系
        # 这里简化：假设avatar_id包含在任务参数中
        tasks = await job_service.list_jobs(
            job_type=JobType.AVATAR_PROCESSING,
            limit=10
        )

        task_status = None
        for task in tasks:
            if task.get("parameters", {}).get("avatar_id") == avatar_id:
                task_status = task
                break

        if not task_status:
            return AvatarStatusResponse(
                success=True,
                avatar_id=avatar_id,
                status="unknown",
                message="未找到关联的任务"
            )

        # 根据任务状态确定avatar状态
        task_state = task_status.get("status", "unknown")
        avatar_state = "processing"
        if task_state == "completed":
            avatar_state = "ready"
        elif task_state in ["failed", "timeout", "cancelled"]:
            avatar_state = "error"

        return AvatarStatusResponse(
            success=True,
            avatar_id=avatar_id,
            status=avatar_state,
            task_status=task_status,
            message=f"Avatar状态: {avatar_state}"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取avatar状态失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取avatar状态失败: {str(e)}"
        )


@router.get("/{avatar_id}/metadata")
async def get_avatar_metadata(
    avatar_id: str,
    avatar_service: AvatarService = Depends(get_avatar_service)
):
    """
    获取Avatar的metadata.json文件内容
    """
    try:
        avatar_info = avatar_service.get_video_avatar(avatar_id)
        if not avatar_info:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Avatar不存在: {avatar_id}"
            )

        # 直接返回avatar_info（包含metadata）
        return JSONResponse(content=avatar_info)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取avatar metadata失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取avatar metadata失败: {str(e)}"
        )