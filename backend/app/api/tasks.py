"""
任务管理 API

提供任务创建、查询、取消等管理功能
"""

import logging
from typing import List, Optional, Dict, Any
from uuid import uuid4
from datetime import datetime

from fastapi import APIRouter, HTTPException, status, Query, Path, Body, Depends, Request
from pydantic import BaseModel, Field

from app.services.job_service import JobService, JobStatus, JobType
from app.models.task import Task, TaskCreate, TaskUpdate, TaskQuery, TaskResult

logger = logging.getLogger(__name__)

router = APIRouter()

# 依赖注入
async def get_job_service(request: Request) -> JobService:
    """获取任务服务实例"""
    return request.app.state.job_service


class TaskResponse(BaseModel):
    """任务响应模型"""
    success: bool = Field(..., description="是否成功")
    task: Optional[Task] = Field(None, description="任务信息")
    message: Optional[str] = Field(None, description="消息")
    error: Optional[str] = Field(None, description="错误信息")


class TasksResponse(BaseModel):
    """任务列表响应模型"""
    success: bool = Field(..., description="是否成功")
    tasks: List[Task] = Field(default_factory=list, description="任务列表")
    total: int = Field(0, description="总任务数")
    page: int = Field(1, description="当前页码")
    page_size: int = Field(50, description="每页数量")


@router.get("/", response_model=TasksResponse)
async def list_tasks(
    job_service: JobService = Depends(get_job_service),
    user_id: Optional[str] = Query(None, description="用户ID筛选"),
    username: Optional[str] = Query(None, description="用户名筛选"),
    task_type: Optional[str] = Query(None, description="任务类型筛选"),
    status: Optional[str] = Query(None, description="状态筛选"),
    limit: int = Query(50, ge=1, le=1000, description="返回数量限制"),
    offset: int = Query(0, ge=0, description="偏移量")
) -> TasksResponse:
    """
    列出任务

    根据筛选条件列出所有任务
    """
    try:
        # 转换任务类型和状态
        job_type = None
        if task_type:
            try:
                job_type = JobType(task_type)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"无效的任务类型: {task_type}"
                )

        job_status = None
        if status:
            try:
                job_status = JobStatus(status)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"无效的任务状态: {status}"
                )

        # 获取任务列表
        jobs = await job_service.list_jobs(
            user_id=user_id,
            job_type=job_type,
            status=job_status,
            limit=limit,
            offset=offset
        )

        # 转换为任务模型
        tasks = []
        for job_data in jobs:
            try:
                task = Task(
                    id=job_data.get("job_id", ""),
                    task_type=job_data.get("job_type", ""),
                    status=job_data.get("status", ""),
                    parameters=job_data.get("parameters", {}),
                    progress=job_data.get("progress", 0.0),
                    error_message=job_data.get("error"),
                    timeout_seconds=job_data.get("timeout_seconds", 300),
                    max_retries=job_data.get("max_retries", 0),
                    retry_count=job_data.get("retry_count", 0),
                    priority=job_data.get("priority", 0),
                    user_id=job_data.get("user_id"),
                    username=job_data.get("username"),
                    created_at=datetime.fromisoformat(job_data.get("created_at")) if job_data.get("created_at") else datetime.now(),
                    updated_at=datetime.fromisoformat(job_data.get("updated_at")) if job_data.get("updated_at") else None,
                    started_at=datetime.fromisoformat(job_data.get("started_at")) if job_data.get("started_at") else None,
                    completed_at=datetime.fromisoformat(job_data.get("completed_at")) if job_data.get("completed_at") else None,
                    result=job_data.get("result"),
                    execution_time=job_data.get("duration"),
                    queue_position=job_data.get("queue_position"),
                    metadata=job_data.get("metadata", {}),
                    duration=job_data.get("duration"),
                    is_active=job_data.get("is_active", False),
                    is_finished=job_data.get("is_finished", False)
                )
                tasks.append(task)
            except Exception as e:
                logger.warning(f"转换任务数据失败: {e}")

        return TasksResponse(
            success=True,
            tasks=tasks,
            total=len(tasks),
            page=offset // limit + 1 if limit > 0 else 1,
            page_size=limit
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"列出任务失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"列出任务失败: {str(e)}"
        )


@router.post("/", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(
    task_create: TaskCreate = Body(..., description="任务创建信息"),
    job_service: JobService = Depends(get_job_service)
) -> TaskResponse:
    """
    创建新任务

    创建一个新的异步任务
    """
    try:
        # 验证任务类型
        try:
            job_type = JobType(task_create.task_type.value)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"无效的任务类型: {task_create.task_type}"
            )

        # 创建任务
        job = await job_service.create_job(
            job_type=job_type,
            parameters=task_create.parameters,
            user_id=task_create.user_id,
            username=task_create.username,
            timeout_seconds=task_create.timeout_seconds,
            max_retries=task_create.max_retries,
            metadata=task_create.metadata or {}
        )

        # 转换为任务模型
        task = Task(
            id=job.job_id,
            task_type=job.job_type.value,
            status=job.status.value,
            parameters=job.parameters,
            progress=job.progress,
            timeout_seconds=job.timeout_seconds,
            max_retries=job.max_retries,
            retry_count=job.retry_count,
            priority=job.priority,
            user_id=job.user_id,
            username=job.username,
            created_at=job.created_at,
            updated_at=job.updated_at,
            metadata=job.metadata
        )

        return TaskResponse(
            success=True,
            task=task,
            message="任务创建成功"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"创建任务失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"创建任务失败: {str(e)}"
        )


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: str = Path(..., description="任务ID"),
    job_service: JobService = Depends(get_job_service)
) -> TaskResponse:
    """
    获取任务信息

    根据任务ID获取任务详细信息
    """
    try:
        job = await job_service.get_job(task_id)
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"任务不存在: {task_id}"
            )

        # 获取任务状态详情
        job_status = await job_service.get_job_status(task_id)
        if not job_status:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"任务状态不存在: {task_id}"
            )

        # 转换为任务模型
        task = Task(
            id=job.job_id,
            task_type=job.job_type.value,
            status=job.status.value,
            parameters=job.parameters,
            progress=job.progress,
            error_message=job.error,
            timeout_seconds=job.timeout_seconds,
            max_retries=job.max_retries,
            retry_count=job.retry_count,
            priority=job.priority,
            user_id=job.user_id,
            username=job.username,
            created_at=job.created_at,
            updated_at=job.updated_at,
            started_at=job.started_at,
            completed_at=job.completed_at,
            result=job.result,
            execution_time=job_status.get("duration"),
            queue_position=job_status.get("queue_position"),
            metadata=job.metadata,
            duration=job_status.get("duration"),
            is_active=job_status.get("is_active", False),
            is_finished=job_status.get("is_finished", False)
        )

        return TaskResponse(
            success=True,
            task=task,
            message="获取任务信息成功"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取任务失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取任务失败: {str(e)}"
        )


@router.put("/{task_id}/cancel", response_model=TaskResponse)
async def cancel_task(
    task_id: str = Path(..., description="任务ID"),
    job_service: JobService = Depends(get_job_service)
) -> TaskResponse:
    """
    取消任务

    取消正在运行或等待中的任务
    """
    try:
        success = await job_service.cancel_job(task_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"无法取消任务: {task_id}"
            )

        # 获取更新后的任务信息
        job = await job_service.get_job(task_id)
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"任务不存在: {task_id}"
            )

        # 转换为任务模型
        task = Task(
            id=job.job_id,
            task_type=job.job_type.value,
            status=job.status.value,
            parameters=job.parameters,
            progress=job.progress,
            error_message=job.error,
            timeout_seconds=job.timeout_seconds,
            max_retries=job.max_retries,
            retry_count=job.retry_count,
            priority=job.priority,
            user_id=job.user_id,
            username=job.username,
            created_at=job.created_at,
            updated_at=job.updated_at,
            started_at=job.started_at,
            completed_at=job.completed_at,
            result=job.result,
            metadata=job.metadata
        )

        return TaskResponse(
            success=True,
            task=task,
            message="任务取消成功"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"取消任务失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"取消任务失败: {str(e)}"
        )


@router.put("/{task_id}/retry", response_model=TaskResponse)
async def retry_task(
    task_id: str = Path(..., description="任务ID"),
    job_service: JobService = Depends(get_job_service)
) -> TaskResponse:
    """
    重试任务

    重试失败或超时的任务
    """
    try:
        success = await job_service.retry_job(task_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"无法重试任务: {task_id}"
            )

        # 获取更新后的任务信息
        job = await job_service.get_job(task_id)
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"任务不存在: {task_id}"
            )

        # 转换为任务模型
        task = Task(
            id=job.job_id,
            task_type=job.job_type.value,
            status=job.status.value,
            parameters=job.parameters,
            progress=job.progress,
            error_message=job.error,
            timeout_seconds=job.timeout_seconds,
            max_retries=job.max_retries,
            retry_count=job.retry_count,
            priority=job.priority,
            user_id=job.user_id,
            username=job.username,
            created_at=job.created_at,
            updated_at=job.updated_at,
            started_at=job.started_at,
            completed_at=job.completed_at,
            result=job.result,
            metadata=job.metadata
        )

        return TaskResponse(
            success=True,
            task=task,
            message="任务重试成功"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"重试任务失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"重试任务失败: {str(e)}"
        )


@router.delete("/{task_id}", response_model=TaskResponse)
async def delete_task(
    task_id: str = Path(..., description="任务ID"),
    job_service: JobService = Depends(get_job_service)
) -> TaskResponse:
    """
    删除任务记录

    删除已完成的任务记录（不会取消运行中的任务）
    """
    try:
        job = await job_service.get_job(task_id)
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"任务不存在: {task_id}"
            )

        if job.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"无法删除活跃中的任务: {task_id}"
            )

        # 从任务列表中移除
        # 注意：这里只是从内存中移除，在实际应用中可能需要更复杂的逻辑
        if task_id in job_service.jobs:
            del job_service.jobs[task_id]

        return TaskResponse(
            success=True,
            message="任务记录删除成功"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除任务失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"删除任务失败: {str(e)}"
        )


@router.get("/{task_id}/status", response_model=TaskResult)
async def get_task_status(
    task_id: str = Path(..., description="任务ID"),
    job_service: JobService = Depends(get_job_service)
) -> TaskResult:
    """
    获取任务状态

    获取任务的当前状态和进度
    """
    try:
        job_status = await job_service.get_job_status(task_id)
        if not job_status:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"任务不存在: {task_id}"
            )

        return TaskResult(
            task_id=job_status.get("job_id", task_id),
            status=job_status.get("status", ""),
            result=job_status.get("result"),
            error_message=job_status.get("error"),
            duration=job_status.get("duration"),
            progress=job_status.get("progress", 0.0)
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取任务状态失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取任务状态失败: {str(e)}"
        )


@router.put("/{task_id}/progress")
async def update_task_progress(
    task_id: str = Path(..., description="任务ID"),
    progress: float = Body(..., ge=0.0, le=1.0, description="进度 (0.0-1.0)"),
    message: Optional[str] = Body(None, description="进度消息"),
    job_service: JobService = Depends(get_job_service)
) -> Dict[str, Any]:
    """
    更新任务进度

    更新任务的进度信息（通常由任务处理器调用）
    """
    try:
        await job_service.update_job_progress(task_id, progress, message)
        return {
            "success": True,
            "message": "进度更新成功",
            "task_id": task_id,
            "progress": progress
        }
    except Exception as e:
        logger.error(f"更新任务进度失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"更新任务进度失败: {str(e)}"
        )