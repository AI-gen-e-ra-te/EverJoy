"""
MuseTalk 唇形同步服务

用于调用 MuseTalk 模型生成唇形同步视频
"""

import os
import asyncio
import logging
import subprocess
import json
from typing import Optional, Dict, Any, List
from pathlib import Path
from datetime import datetime

from app.config import settings

logger = logging.getLogger(__name__)


class MuseTalkService:
    """MuseTalk 服务管理器"""

    def __init__(self):
        self.model_version = settings.MUSETALK_MODEL_VERSION
        self.musetalk_path = settings.absolute_musetalk_path
        self.use_float16 = settings.MUSETALK_USE_FLOAT16
        self.bbox_shift = settings.MUSETALK_BBOX_SHIFT
        self.fps = settings.MUSETALK_FPS
        self.ffmpeg_path = settings.FFMPEG_PATH
        self.musetalk_python_path = settings.MUSETALK_PYTHON_PATH

        self.model_dir = os.path.join(
            self.musetalk_path,
            "models",
            "musetalkV15" if self.model_version == "v15" else "musetalk"
        )

        self.available = False
        self.active_jobs = {}

    def _resolve_python_path(self) -> str:
        """
        解析 MuseTalk 使用的 Python 解释器路径。
        优先级：
          1. .env 中显式指定的 MUSETALK_PYTHON_PATH
          2. MuseTalk/venv 下的解释器
          3. 当前 sys.executable
        """
        import sys

        if self.musetalk_python_path and os.path.isfile(self.musetalk_python_path):
            return self.musetalk_python_path

        venv_candidates = [
            os.path.join(self.musetalk_path, "venv", "Scripts", "python.exe"),
            os.path.join(self.musetalk_path, "venv", "bin", "python"),
            os.path.join(self.musetalk_path, ".venv", "Scripts", "python.exe"),
            os.path.join(self.musetalk_path, ".venv", "bin", "python"),
        ]
        for candidate in venv_candidates:
            if os.path.isfile(candidate):
                logger.info(f"自动检测到 MuseTalk venv Python: {candidate}")
                return candidate

        logger.warning(
            f"未找到 MuseTalk 专用 Python（配置={self.musetalk_python_path}），"
            f"回退到 sys.executable={sys.executable}"
        )
        return sys.executable

    def preflight_check(self) -> Dict[str, Any]:
        """
        MuseTalk 预检检查

        返回包含检查结果的字典
        """
        import sys
        import subprocess
        import json
        from pathlib import Path

        checks = {}

        try:
            # 1. 检查 Python 解释器
            python_path = self.musetalk_python_path or sys.executable
            checks["python_path"] = python_path
            checks["python_exists"] = os.path.exists(python_path)

            if checks["python_exists"]:
                # 检查 Python 版本
                try:
                    result = subprocess.run(
                        [python_path, "--version"],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )
                    checks["python_version"] = result.stdout.strip() if result.returncode == 0 else f"Error: {result.stderr}"
                except Exception as e:
                    checks["python_version"] = f"Check failed: {e}"

            # 2. 检查 MuseTalk 目录和脚本
            checks["musetalk_path"] = self.musetalk_path
            checks["musetalk_exists"] = os.path.exists(self.musetalk_path)

            inference_script = os.path.join(self.musetalk_path, "scripts", "inference.py")
            checks["inference_script"] = inference_script
            checks["inference_script_exists"] = os.path.exists(inference_script)

            # 3. 检查模型文件
            model_checks = {}
            required_models = [
                ("unet_model", self.model_dir),
                ("whisper", os.path.join(self.musetalk_path, "models", "whisper")),
                ("sd-vae", os.path.join(self.musetalk_path, "models", "sd-vae")),
                ("dwpose", os.path.join(self.musetalk_path, "models", "dwpose")),
                ("syncnet", os.path.join(self.musetalk_path, "models", "syncnet")),
                ("face-parse-bisent", os.path.join(self.musetalk_path, "models", "face-parse-bisent")),
            ]

            for name, path in required_models:
                exists = os.path.exists(path)
                model_checks[name] = {
                    "path": path,
                    "exists": exists,
                    "files": list(Path(path).glob("*")) if exists and os.path.isdir(path) else []
                }

            checks["models"] = model_checks

            # 4. 检查 FFmpeg
            ffmpeg_path = self.ffmpeg_path or "ffmpeg"
            checks["ffmpeg_path"] = ffmpeg_path
            try:
                result = subprocess.run(
                    [ffmpeg_path, "-version"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                checks["ffmpeg_available"] = result.returncode == 0
                checks["ffmpeg_version"] = result.stdout.split('\\n')[0] if result.returncode == 0 else f"Error: {result.stderr}"
            except Exception as e:
                checks["ffmpeg_available"] = False
                checks["ffmpeg_version"] = f"Check failed: {e}"

            # 5. 检查 Python 包导入
            import_checks = {}
            packages_to_check = ["torch", "cv2", "numpy", "omegaconf", "transformers", "mmcv", "mmdet", "mmpose"]

            for pkg in packages_to_check:
                try:
                    __import__(pkg)
                    import_checks[pkg] = {"available": True}
                except ImportError as e:
                    import_checks[pkg] = {"available": False, "error": str(e)}

            checks["imports"] = import_checks

            # 6. 总体评估
            critical_failures = []
            if not checks.get("python_exists"):
                critical_failures.append("Python interpreter not found")
            if not checks.get("musetalk_exists"):
                critical_failures.append("MuseTalk directory not found")
            if not checks.get("inference_script_exists"):
                critical_failures.append("inference.py script not found")
            if not checks.get("ffmpeg_available"):
                critical_failures.append("FFmpeg not available")

            # 检查关键模型
            unet_model_path = os.path.join(self.model_dir, "unet.pth" if self.model_version == "v15" else "pytorch_model.bin")
            if not os.path.exists(unet_model_path):
                critical_failures.append(f"UNet model not found: {unet_model_path}")

            checks["critical_failures"] = critical_failures
            checks["all_passed"] = len(critical_failures) == 0

            logger.info(f"MuseTalk preflight check: {'PASSED' if checks['all_passed'] else 'FAILED'}")
            if critical_failures:
                logger.error(f"Critical failures: {critical_failures}")

        except Exception as e:
            logger.error(f"Preflight check failed with exception: {e}")
            checks["error"] = str(e)
            checks["all_passed"] = False

        return checks

    def initialize(self):
        """初始化 MuseTalk 服务——只检查文件系统，不在后端进程中 import MuseTalk 的重型依赖"""
        try:
            if not os.path.exists(self.musetalk_path):
                logger.error(f"MuseTalk 目录不存在: {self.musetalk_path}")
                return

            if not os.path.exists(self.model_dir):
                logger.error(f"MuseTalk 模型目录不存在: {self.model_dir}")
                logger.info("请运行 MuseTalk/download_models.py 下载模型")
                return

            unet_file = "unet.pth" if self.model_version == "v15" else "pytorch_model.bin"
            unet_path = os.path.join(self.model_dir, unet_file)
            if not os.path.exists(unet_path):
                logger.error(f"UNet 模型文件不存在: {unet_path}")
                return

            inference_script = os.path.join(self.musetalk_path, "scripts", "inference.py")
            if not os.path.exists(inference_script):
                logger.error(f"推理脚本不存在: {inference_script}")
                return

            python_path = self._resolve_python_path()
            logger.info(f"MuseTalk Python 解释器: {python_path}")

            self.available = True
            logger.info(f"MuseTalk 服务初始化完成，模型版本: {self.model_version}")

        except Exception as e:
            logger.error(f"MuseTalk 服务初始化失败: {e}")
            self.available = False

    async def generate_lip_sync_video(
        self,
        audio_path: str,
        avatar_path: str,
        output_path: Optional[str] = None,
        username: str = "User",
        job_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        生成唇形同步视频

        Args:
            audio_path: 音频文件路径
            avatar_path: 头像图片路径
            output_path: 输出视频路径（可选）
            username: 用户名
            job_id: 任务ID（可选）

        Returns:
            包含视频信息和任务状态的结果
        """
        if not self.available:
            raise RuntimeError("MuseTalk 服务不可用")

        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"音频文件不存在: {audio_path}")

        if not os.path.exists(avatar_path):
            raise FileNotFoundError(f"头像文件不存在: {avatar_path}")

        # 生成任务ID
        if not job_id:
            job_id = f"musetalk_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        # 生成输出路径
        if not output_path:
            video_dir = settings.absolute_video_dir
            os.makedirs(video_dir, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = os.path.join(video_dir, f"{username}_{timestamp}.mp4")

        try:
            # 将任务添加到活动任务列表
            self.active_jobs[job_id] = {
                "status": "running",
                "start_time": datetime.now(),
                "audio_path": audio_path,
                "avatar_path": avatar_path,
                "output_path": output_path,
                "username": username
            }

            logger.info(f"开始生成唇形同步视频: job_id={job_id}")
            logger.info(f"音频: {audio_path}")
            logger.info(f"头像: {avatar_path}")
            logger.info(f"输出: {output_path}")

            # 调用 MuseTalk 推理脚本
            result = await self._run_musetalk_inference(
                audio_path, avatar_path, output_path
            )

            # 更新任务状态
            self.active_jobs[job_id].update({
                "status": "completed",
                "end_time": datetime.now(),
                "result": result
            })

            logger.info(f"唇形同步视频生成完成: {output_path}")

            return {
                "job_id": job_id,
                "status": "success",
                "video_path": output_path,
                "video_url": f"/files/videos/{os.path.basename(output_path)}",
                "duration": result.get("duration", 0),
                "frame_count": result.get("frame_count", 0),
                "message": "唇形同步视频生成成功"
            }

        except Exception as e:
            logger.error(f"生成唇形同步视频失败: {e}")

            # 更新任务状态为失败
            if job_id in self.active_jobs:
                self.active_jobs[job_id].update({
                    "status": "failed",
                    "end_time": datetime.now(),
                    "error": str(e)
                })

            raise

    async def _run_musetalk_inference(
        self,
        audio_path: str,
        avatar_path: str,
        output_path: str
    ) -> Dict[str, Any]:
        """
        运行 MuseTalk 推理

        Args:
            audio_path: 音频文件路径
            avatar_path: 头像/视频文件路径（MuseTalk 的 video_path 参数）
            output_path: 期望的最终输出视频路径

        Returns:
            推理结果信息
        """
        try:
            import sys
            import uuid

            temp_dir = settings.absolute_temp_dir
            os.makedirs(temp_dir, exist_ok=True)

            config_filename = f"musetalk_config_{uuid.uuid4().hex[:8]}.yaml"
            config_path = os.path.join(temp_dir, config_filename)

            avatar_path_fixed = os.path.abspath(avatar_path).replace('\\', '/')
            audio_path_fixed = os.path.abspath(audio_path).replace('\\', '/')

            with open(config_path, 'w', encoding='utf-8') as f:
                f.write(f"task_0:\n")
                f.write(f"  video_path: \"{avatar_path_fixed}\"\n")
                f.write(f"  audio_path: \"{audio_path_fixed}\"\n")
                f.write(f"  bbox_shift: {self.bbox_shift}\n")

            logger.info(f"MuseTalk 配置文件: {config_path}")

            output_vid_name = os.path.basename(output_path)
            result_dir = os.path.join(settings.absolute_video_dir, "musetalk_results")
            os.makedirs(result_dir, exist_ok=True)

            python_path = self._resolve_python_path()

            unet_model_path = os.path.join(
                self.musetalk_path, "models",
                "musetalkV15" if self.model_version == "v15" else "musetalk",
                "unet.pth" if self.model_version == "v15" else "pytorch_model.bin"
            )
            unet_config = os.path.join(
                self.musetalk_path, "models",
                "musetalkV15" if self.model_version == "v15" else "musetalk",
                "musetalk.json"
            )
            whisper_dir = os.path.join(self.musetalk_path, "models", "whisper")

            cmd = [
                python_path, "-m", "scripts.inference",
                "--inference_config", os.path.abspath(config_path),
                "--result_dir", result_dir,
                "--version", self.model_version,
                "--bbox_shift", str(self.bbox_shift),
                "--fps", str(self.fps),
                "--output_vid_name", output_vid_name,
                "--unet_model_path", unet_model_path,
                "--unet_config", unet_config,
                "--whisper_dir", whisper_dir,
                "--batch_size", "4",
            ]

            if self.use_float16:
                cmd.append("--use_float16")

            if self.ffmpeg_path:
                cmd.extend(["--ffmpeg_path", self.ffmpeg_path])

            cwd = self.musetalk_path

            logger.info(f"MuseTalk 命令: {' '.join(cmd)}")
            logger.info(f"工作目录: {cwd}")

            env = os.environ.copy()
            env["PYTHONPATH"] = cwd + os.pathsep + env.get("PYTHONPATH", "")

            process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=cwd,
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await process.communicate()

            try:
                os.remove(config_path)
            except OSError:
                pass

            stdout_msg = stdout.decode('utf-8', errors='ignore')
            stderr_msg = stderr.decode('utf-8', errors='ignore')

            if process.returncode != 0:
                logger.error(f"MuseTalk 推理失败 (code={process.returncode})")
                logger.error(f"stderr: {stderr_msg[-2000:]}")
                logger.error(f"stdout: {stdout_msg[-2000:]}")
                raise RuntimeError(
                    f"MuseTalk 推理失败 (code={process.returncode}): "
                    f"{stderr_msg[-500:] or stdout_msg[-500:] or '未知错误'}"
                )

            logger.info(f"MuseTalk 推理完成，stdout: {stdout_msg[-500:]}")

            actual_output = os.path.join(result_dir, self.model_version, output_vid_name)
            if not os.path.exists(actual_output):
                candidates = []
                version_dir = os.path.join(result_dir, self.model_version)
                if os.path.isdir(version_dir):
                    candidates = [
                        os.path.join(version_dir, f)
                        for f in os.listdir(version_dir)
                        if f.endswith('.mp4') and '_concat' not in f
                    ]
                if candidates:
                    candidates.sort(key=os.path.getmtime, reverse=True)
                    actual_output = candidates[0]
                    logger.info(f"使用候选输出文件: {actual_output}")
                else:
                    logger.error(f"未找到输出文件，期望: {actual_output}，版本目录: {version_dir}")
                    raise FileNotFoundError(f"MuseTalk 未生成输出文件: {actual_output}")

            import shutil
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            shutil.move(actual_output, output_path)
            logger.info(f"输出视频已移动到: {output_path}")

            video_info = await self._get_video_info(output_path)

            return {
                "duration": video_info.get("duration", 0),
                "frame_count": video_info.get("frame_count", 0),
                "width": video_info.get("width", 0),
                "height": video_info.get("height", 0),
                "output": stdout_msg[-200:]
            }

        except Exception as e:
            logger.error(f"运行 MuseTalk 推理时发生错误: {e}")
            raise

    async def _get_video_info(self, video_path: str) -> Dict[str, Any]:
        """
        获取视频文件信息

        Args:
            video_path: 视频文件路径

        Returns:
            视频信息
        """
        try:
            if not os.path.exists(video_path):
                return {"error": "视频文件不存在"}

            # 使用 ffprobe 获取视频信息
            if self.ffmpeg_path:
                ffprobe_path = os.path.join(os.path.dirname(self.ffmpeg_path), "ffprobe")
                if not os.path.exists(ffprobe_path):
                    ffprobe_path = "ffprobe"
            else:
                ffprobe_path = "ffprobe"

            cmd = [
                ffprobe_path,
                "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=duration,width,height,nb_frames",
                "-of", "json",
                video_path
            ]

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await process.communicate()

            if process.returncode == 0:
                info = json.loads(stdout.decode('utf-8'))
                stream = info.get("streams", [{}])[0]

                return {
                    "duration": float(stream.get("duration", 0)),
                    "width": int(stream.get("width", 0)),
                    "height": int(stream.get("height", 0)),
                    "frame_count": int(stream.get("nb_frames", 0))
                }
            else:
                logger.warning(f"获取视频信息失败: {stderr.decode('utf-8')}")
                return {}

        except Exception as e:
            logger.warning(f"获取视频信息时发生错误: {e}")
            return {}

    async def generate_realtime_video(
        self,
        audio_stream_url: str,
        avatar_path: str,
        username: str = "User"
    ) -> str:
        """
        生成实时唇形同步视频（流式）

        Args:
            audio_stream_url: 音频流URL
            avatar_path: 头像图片路径
            username: 用户名

        Returns:
            视频流URL
        """
        if not self.available:
            raise RuntimeError("MuseTalk 服务不可用")

        # TODO: 实现实时推理
        # 当前版本暂时不支持实时推理，返回占位符
        logger.warning("实时推理功能暂未实现，使用占位符")

        # 生成任务ID
        job_id = f"realtime_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        return {
            "job_id": job_id,
            "status": "not_implemented",
            "message": "实时推理功能暂未实现",
            "video_stream_url": None
        }

    def get_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """
        获取任务状态

        Args:
            job_id: 任务ID

        Returns:
            任务状态信息
        """
        if job_id in self.active_jobs:
            job = self.active_jobs[job_id]
            status = job["status"]

            result = {
                "job_id": job_id,
                "status": status,
                "username": job.get("username"),
                "audio_path": job.get("audio_path"),
                "avatar_path": job.get("avatar_path"),
                "output_path": job.get("output_path"),
                "start_time": job.get("start_time").isoformat() if job.get("start_time") else None,
                "end_time": job.get("end_time").isoformat() if job.get("end_time") else None,
            }

            if status == "completed":
                result["video_url"] = f"/files/videos/{os.path.basename(job.get('output_path', ''))}"
                result["duration"] = job.get("result", {}).get("duration", 0)
                result["frame_count"] = job.get("result", {}).get("frame_count", 0)
            elif status == "failed":
                result["error"] = job.get("error")

            return result

        return None

    def list_jobs(self, username: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        列出所有任务

        Args:
            username: 筛选用户名（可选）

        Returns:
            任务列表
        """
        jobs = []

        for job_id, job in self.active_jobs.items():
            if username and job.get("username") != username:
                continue

            job_info = self.get_job_status(job_id)
            if job_info:
                jobs.append(job_info)

        return jobs

    def cancel_job(self, job_id: str) -> bool:
        """
        取消任务

        Args:
            job_id: 任务ID

        Returns:
            是否成功取消
        """
        if job_id in self.active_jobs:
            job = self.active_jobs[job_id]
            if job["status"] == "running":
                # TODO: 实现任务取消逻辑
                job["status"] = "cancelled"
                job["end_time"] = datetime.now()
                logger.info(f"任务已取消: {job_id}")
                return True
            else:
                logger.warning(f"无法取消非运行中的任务: {job_id}, 状态: {job['status']}")
                return False
        else:
            logger.warning(f"任务不存在: {job_id}")
            return False

    def cleanup(self):
        """清理资源"""
        # 清理已完成的任务记录（保留最近100条）
        job_ids = list(self.active_jobs.keys())
        if len(job_ids) > 100:
            for job_id in job_ids[:-100]:
                del self.active_jobs[job_id]
            logger.info(f"清理了 {len(job_ids) - 100} 条旧任务记录")

        logger.info("MuseTalk 服务资源清理完成")

    def is_available(self) -> bool:
        """检查服务是否可用"""
        return self.available