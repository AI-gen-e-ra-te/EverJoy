"""
任务管理服务

管理异步任务，包括：
1. 任务创建和状态跟踪
2. 任务队列管理
3. 任务结果存储
4. 任务超时和重试
"""

import asyncio
import logging
import uuid
import json
import time
from typing import Optional, Dict, Any, List, Callable, Union, Coroutine
from enum import Enum
from datetime import datetime, timedelta
from dataclasses import dataclass, field, asdict
from concurrent.futures import ThreadPoolExecutor

from app.config import settings

logger = logging.getLogger(__name__)


class JobStatus(Enum):
    """任务状态枚举"""
    PENDING = "pending"        # 等待中
    RUNNING = "running"        # 运行中
    COMPLETED = "completed"    # 已完成
    FAILED = "failed"          # 失败
    CANCELLED = "cancelled"    # 已取消
    TIMEOUT = "timeout"        # 超时


class JobType(Enum):
    """任务类型枚举"""
    TTS_SYNTHESIS = "tts_synthesis"          # TTS 合成
    LIP_SYNC = "lip_sync"                    # 唇形同步
    AVATAR_PROCESSING = "avatar_processing"  # 头像处理
    LLM_INFERENCE = "llm_inference"          # LLM 推理
    VIDEO_GENERATION = "video_generation"    # 视频生成
    AUDIO_PROCESSING = "audio_processing"    # 音频处理
    CUSTOM = "custom"                        # 自定义任务


@dataclass
class Job:
    """任务数据结构"""
    job_id: str
    job_type: JobType
    status: JobStatus = JobStatus.PENDING
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    user_id: Optional[str] = None
    username: Optional[str] = None
    parameters: Dict[str, Any] = field(default_factory=dict)
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    progress: float = 0.0  # 0.0 - 1.0
    timeout_seconds: int = 300  # 默认5分钟超时
    max_retries: int = 0
    retry_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        data = asdict(self)
        data["job_type"] = self.job_type.value
        data["status"] = self.status.value
        data["created_at"] = self.created_at.isoformat()
        if self.started_at:
            data["started_at"] = self.started_at.isoformat()
        if self.completed_at:
            data["completed_at"] = self.completed_at.isoformat()
        return data

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
        return self.status in [JobStatus.PENDING, JobStatus.RUNNING]

    @property
    def is_finished(self) -> bool:
        """检查任务是否已完成"""
        return self.status in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED, JobStatus.TIMEOUT]


class JobService:
    """任务管理服务"""

    def __init__(self):
        self.jobs: Dict[str, Job] = {}
        self.job_queue = asyncio.Queue()
        self.max_concurrent_jobs = 2  # 第一阶段硬编码值
        self.active_tasks: Dict[str, asyncio.Task] = {}
        self.executor = ThreadPoolExecutor(max_workers=self.max_concurrent_jobs)
        self.is_running = False
        self.cleanup_interval = 3600  # 清理间隔（秒）
        self.max_job_history = 1000   # 最大历史任务数

        # 任务处理器注册表
        self.job_handlers: Dict[JobType, Callable] = {}

    async def initialize(self):
        """初始化任务服务"""
        try:
            logger.info("正在初始化任务服务...")

            # 启动任务处理循环
            self.is_running = True
            asyncio.create_task(self._job_processing_loop())
            asyncio.create_task(self._cleanup_loop())

            logger.info(f"任务服务初始化完成，最大并发任务数: {self.max_concurrent_jobs}")

        except Exception as e:
            logger.error(f"任务服务初始化失败: {e}")
            raise

    async def _job_processing_loop(self):
        """任务处理循环"""
        while self.is_running:
            try:
                # 等待任务
                job = await self.job_queue.get()

                # 检查是否超过最大并发数
                if len(self.active_tasks) >= self.max_concurrent_jobs:
                    logger.warning(f"达到最大并发任务数 ({self.max_concurrent_jobs})，等待空闲")
                    # 等待一个任务完成
                    while len(self.active_tasks) >= self.max_concurrent_jobs:
                        await asyncio.sleep(1)

                # 创建异步任务处理
                task = asyncio.create_task(self._process_job(job))
                self.active_tasks[job.job_id] = task

                # 任务完成后清理
                task.add_done_callback(lambda t, jid=job.job_id: self._handle_task_completion(t, jid))

            except asyncio.CancelledError:
                logger.info("任务处理循环被取消")
                break
            except Exception as e:
                logger.error(f"任务处理循环异常: {e}")

    async def _process_job(self, job: Job):
        """处理任务"""
        try:
            # 更新任务状态
            job.status = JobStatus.RUNNING
            job.started_at = datetime.now()
            self.jobs[job.job_id] = job

            logger.info(f"开始处理任务: {job.job_id} ({job.job_type.value})")

            # 获取任务处理器
            handler = self.job_handlers.get(job.job_type)
            if not handler:
                raise ValueError(f"未注册的任务处理器: {job.job_type}")

            # 设置超时
            try:
                result = await asyncio.wait_for(
                    handler(job.parameters),
                    timeout=job.timeout_seconds
                )

                # 更新任务结果
                job.status = JobStatus.COMPLETED
                job.completed_at = datetime.now()
                job.result = result
                job.progress = 1.0

                logger.info(f"任务完成: {job.job_id}")

            except asyncio.TimeoutError:
                job.status = JobStatus.TIMEOUT
                job.completed_at = datetime.now()
                job.error = f"任务超时 ({job.timeout_seconds}秒)"
                logger.warning(f"任务超时: {job.job_id}")

            except Exception as e:
                # 检查是否需要重试
                if job.retry_count < job.max_retries:
                    job.retry_count += 1
                    job.status = JobStatus.PENDING
                    job.started_at = None
                    job.error = f"重试 {job.retry_count}/{job.max_retries}: {str(e)}"

                    # 重新加入队列（延迟重试）
                    retry_delay = min(2 ** job.retry_count, 60)  # 指数退避，最大60秒
                    logger.info(f"任务重试: {job.job_id}，延迟 {retry_delay}秒")

                    asyncio.create_task(self._delayed_enqueue(job, retry_delay))
                else:
                    job.status = JobStatus.FAILED
                    job.completed_at = datetime.now()
                    job.error = str(e)
                    logger.error(f"任务失败: {job.job_id}, 错误: {e}")

        except Exception as e:
            logger.error(f"处理任务时发生未预期错误: {job.job_id}, 错误: {e}")
            job.status = JobStatus.FAILED
            job.completed_at = datetime.now()
            job.error = f"未预期错误: {str(e)}"

        finally:
            self.jobs[job.job_id] = job

    async def _delayed_enqueue(self, job: Job, delay: int):
        """延迟加入队列"""
        await asyncio.sleep(delay)
        await self.job_queue.put(job)

    def _handle_task_completion(self, task: asyncio.Task, job_id: str):
        """处理任务完成"""
        try:
            if job_id in self.active_tasks:
                del self.active_tasks[job_id]

            # 检查任务是否有异常
            if task.exception():
                logger.error(f"任务执行异常: {job_id}, 异常: {task.exception()}")
        except Exception as e:
            logger.error(f"处理任务完成时发生错误: {e}")

    async def _cleanup_loop(self):
        """清理循环"""
        while self.is_running:
            try:
                await asyncio.sleep(self.cleanup_interval)
                await self._cleanup_old_jobs()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"清理循环异常: {e}")

    async def _cleanup_old_jobs(self):
        """清理旧任务"""
        try:
            now = datetime.now()
            job_ids_to_remove = []

            for job_id, job in self.jobs.items():
                # 清理已完成超过24小时的任务
                if job.is_finished:
                    completed_time = job.completed_at or job.started_at or job.created_at
                    if now - completed_time > timedelta(hours=24):
                        job_ids_to_remove.append(job_id)

                # 限制历史任务数量
                if len(self.jobs) > self.max_job_history:
                    # 按创建时间排序，移除最早的任务
                    sorted_jobs = sorted(
                        self.jobs.items(),
                        key=lambda x: x[1].created_at
                    )
                    oldest_jobs = sorted_jobs[:len(self.jobs) - self.max_job_history]
                    job_ids_to_remove.extend(job_id for job_id, _ in oldest_jobs)

            # 移除任务
            for job_id in set(job_ids_to_remove):
                if job_id in self.jobs:
                    del self.jobs[job_id]

            if job_ids_to_remove:
                logger.info(f"清理了 {len(set(job_ids_to_remove))} 个旧任务")

        except Exception as e:
            logger.error(f"清理旧任务失败: {e}")

    def register_handler(self, job_type: JobType, handler: Callable):
        """
        注册任务处理器

        Args:
            job_type: 任务类型
            handler: 处理器函数
        """
        self.job_handlers[job_type] = handler
        logger.info(f"注册任务处理器: {job_type.value}")

    async def create_job(
        self,
        job_type: Union[JobType, str],
        parameters: Dict[str, Any],
        user_id: Optional[str] = None,
        username: Optional[str] = None,
        timeout_seconds: int = 300,
        max_retries: int = 0,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Job:
        """
        创建新任务

        Args:
            job_type: 任务类型
            parameters: 任务参数
            user_id: 用户ID
            username: 用户名
            timeout_seconds: 超时时间（秒）
            max_retries: 最大重试次数
            metadata: 额外元数据

        Returns:
            创建的任务对象
        """
        try:
            # 转换任务类型
            if isinstance(job_type, str):
                job_type = JobType(job_type)

            # 生成任务ID
            job_id = str(uuid.uuid4())

            # 创建任务对象
            job = Job(
                job_id=job_id,
                job_type=job_type,
                user_id=user_id,
                username=username,
                parameters=parameters,
                timeout_seconds=timeout_seconds,
                max_retries=max_retries,
                metadata=metadata or {}
            )

            # 保存任务
            self.jobs[job_id] = job

            # 加入队列
            await self.job_queue.put(job)

            logger.info(f"创建任务: {job_id} ({job_type.value})")

            return job

        except Exception as e:
            logger.error(f"创建任务失败: {e}")
            raise

    async def get_job(self, job_id: str) -> Optional[Job]:
        """
        获取任务信息

        Args:
            job_id: 任务ID

        Returns:
            任务对象
        """
        return self.jobs.get(job_id)

    async def get_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """
        获取任务状态

        Args:
            job_id: 任务ID

        Returns:
            任务状态信息
        """
        job = await self.get_job(job_id)
        if not job:
            return None

        status_info = job.to_dict()
        status_info["is_active"] = job.is_active
        status_info["is_finished"] = job.is_finished
        status_info["duration"] = job.duration

        # 添加任务队列位置信息
        if job.status == JobStatus.PENDING:
            # 估算队列位置（近似值）
            queue_position = 0
            for q_job in list(self.job_queue._queue):
                if q_job.job_id == job_id:
                    break
                queue_position += 1
            status_info["queue_position"] = queue_position

        return status_info

    async def list_jobs(
        self,
        user_id: Optional[str] = None,
        job_type: Optional[Union[JobType, str]] = None,
        status: Optional[Union[JobStatus, str]] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        列出任务

        Args:
            user_id: 筛选用户ID
            job_type: 筛选任务类型
            status: 筛选状态
            limit: 返回数量限制
            offset: 偏移量

        Returns:
            任务列表
        """
        filtered_jobs = []

        # 转换筛选条件
        if isinstance(job_type, str):
            job_type = JobType(job_type)
        if isinstance(status, str):
            status = JobStatus(status)

        for job in self.jobs.values():
            # 应用筛选条件
            if user_id and job.user_id != user_id:
                continue
            if job_type and job.job_type != job_type:
                continue
            if status and job.status != status:
                continue

            filtered_jobs.append(job)

        # 按创建时间排序（最新的在前）
        filtered_jobs.sort(key=lambda j: j.created_at, reverse=True)

        # 分页
        paginated_jobs = filtered_jobs[offset:offset + limit]

        return [await self.get_job_status(job.job_id) for job in paginated_jobs]

    async def update_job_progress(self, job_id: str, progress: float, message: Optional[str] = None):
        """
        更新任务进度

        Args:
            job_id: 任务ID
            progress: 进度 (0.0 - 1.0)
            message: 进度消息（可选）
        """
        job = await self.get_job(job_id)
        if job and job.status == JobStatus.RUNNING:
            job.progress = max(0.0, min(1.0, progress))
            if message:
                job.metadata["progress_message"] = message
            self.jobs[job_id] = job

    async def cancel_job(self, job_id: str) -> bool:
        """
        取消任务

        Args:
            job_id: 任务ID

        Returns:
            是否成功取消
        """
        job = await self.get_job(job_id)
        if not job:
            logger.warning(f"任务不存在: {job_id}")
            return False

        if not job.is_active:
            logger.warning(f"任务 {job_id} 不是活跃状态，无法取消")
            return False

        # 更新任务状态
        job.status = JobStatus.CANCELLED
        job.completed_at = datetime.now()
        self.jobs[job_id] = job

        # 尝试取消正在运行的任务
        if job_id in self.active_tasks:
            task = self.active_tasks[job_id]
            task.cancel()
            logger.info(f"已取消任务: {job_id}")

        return True

    async def retry_job(self, job_id: str) -> bool:
        """
        重试任务

        Args:
            job_id: 任务ID

        Returns:
            是否成功重试
        """
        job = await self.get_job(job_id)
        if not job:
            logger.warning(f"任务不存在: {job_id}")
            return False

        if job.status not in [JobStatus.FAILED, JobStatus.TIMEOUT]:
            logger.warning(f"任务 {job_id} 状态为 {job.status.value}，无法重试")
            return False

        # 重置任务状态
        job.status = JobStatus.PENDING
        job.started_at = None
        job.completed_at = None
        job.error = None
        job.progress = 0.0
        job.retry_count += 1

        # 重新加入队列
        await self.job_queue.put(job)
        self.jobs[job_id] = job

        logger.info(f"已重试任务: {job_id} (重试次数: {job.retry_count})")

        return True

    async def cleanup(self):
        """清理资源"""
        self.is_running = False

        # 取消所有活动任务
        for task in self.active_tasks.values():
            task.cancel()

        # 等待所有任务完成
        if self.active_tasks:
            await asyncio.gather(*self.active_tasks.values(), return_exceptions=True)

        # 关闭线程池
        self.executor.shutdown(wait=True)

        logger.info("任务服务清理完成")

    def is_available(self) -> bool:
        """检查服务是否可用"""
        return self.is_running