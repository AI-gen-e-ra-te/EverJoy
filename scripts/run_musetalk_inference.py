#!/usr/bin/env python3
"""
MuseTalk 唇形同步推理脚本

该脚本负责调用 MuseTalk 生成唇形同步视频。
可以从命令行直接调用，也可以作为 Python 模块导入。

用法:
    python run_musetalk_inference.py --audio audio.wav --image avatar.png --output output.mp4
    python run_musetalk_inference.py --batch --input-dir input/ --output-dir output/
"""

import argparse
import asyncio
import json
import logging
import os
import sys
import subprocess
import time
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
import tempfile

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "backend"))

try:
    from app.config import settings
except ImportError:
    # 如果没有找到配置，使用默认值
    class Settings:
        MUSETALK_PATH = "./MuseTalk"
        MUSETALK_MODEL_VERSION = "v15"
        MUSETALK_USE_FLOAT16 = True
        DATA_DIR = "./data"

    settings = Settings()

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MuseTalkInference:
    """MuseTalk 唇形同步推理器"""

    def __init__(
        self,
        musetalk_path: Optional[str] = None,
        model_version: str = "v15",
        use_float16: bool = True,
        device: str = "cuda",
        verbose: bool = False
    ):
        """
        初始化 MuseTalk 推理器

        Args:
            musetalk_path: MuseTalk 项目路径
            model_version: 模型版本 (v15 或 v1)
            use_float16: 是否使用 float16 模式
            device: 推理设备 (cuda 或 cpu)
            verbose: 是否显示详细输出
        """
        self.musetalk_path = Path(musetalk_path or settings.MUSETALK_PATH)
        self.model_version = model_version or settings.MUSETALK_MODEL_VERSION
        self.use_float16 = use_float16 if hasattr(settings, 'MUSETALK_USE_FLOAT16') else use_float16
        self.device = device
        self.verbose = verbose

        # 检查 MuseTalk 目录
        if not self.musetalk_path.exists():
            raise FileNotFoundError(f"MuseTalk 目录不存在: {self.musetalk_path}")

        # 检查模型目录
        if self.model_version == "v15":
            self.model_dir = self.musetalk_path / "models" / "musetalkV15"
        else:
            self.model_dir = self.musetalk_path / "models" / "musetalk"

        if not self.model_dir.exists():
            logger.warning(f"模型目录不存在: {self.model_dir}")
            logger.info("请先下载 MuseTalk 模型文件")

        # 检查 Python 脚本
        self.realtime_script = self.musetalk_path / "scripts" / "realtime_inference.py"
        self.batch_script = self.musetalk_path / "scripts" / "inference.py"

        if not self.realtime_script.exists() and not self.batch_script.exists():
            raise FileNotFoundError(f"MuseTalk 推理脚本不存在: {self.realtime_script} 或 {self.batch_script}")

        logger.info(f"MuseTalk 推理器初始化完成")
        logger.info(f"  项目路径: {self.musetalk_path}")
        logger.info(f"  模型版本: {self.model_version}")
        logger.info(f"  模型目录: {self.model_dir}")
        logger.info(f"  使用 float16: {self.use_float16}")
        logger.info(f"  设备: {self.device}")

    def check_dependencies(self) -> bool:
        """检查所有依赖是否满足"""
        try:
            # 检查 Python
            python_version = subprocess.run(
                [sys.executable, "--version"],
                capture_output=True,
                text=True,
                check=True
            )
            logger.info(f"Python 版本: {python_version.stdout.strip()}")

            # 检查 torch
            import importlib.util
            torch_spec = importlib.util.find_spec("torch")
            if torch_spec is None:
                logger.error("未找到 PyTorch，请先安装")
                return False

            # 检查 CUDA 可用性
            if self.device == "cuda":
                import torch
                if not torch.cuda.is_available():
                    logger.warning("CUDA 不可用，将使用 CPU")
                    self.device = "cpu"

            # 检查 MuseTalk 依赖
            requirements_file = self.musetalk_path / "requirements.txt"
            if requirements_file.exists():
                logger.info(f"MuseTalk 依赖文件存在: {requirements_file}")
            else:
                logger.warning(f"MuseTalk 依赖文件不存在: {requirements_file}")

            return True

        except Exception as e:
            logger.error(f"检查依赖失败: {e}")
            return False

    def run_realtime_inference(
        self,
        audio_path: str,
        image_path: str,
        output_path: str,
        fps: int = 25,
        crop_face: bool = True,
        still_mode: bool = True,
        enhancer: str = "gfpgan",
        background_enhancer: Optional[str] = None,
        face_swap: bool = False,
        batch_size: int = 1
    ) -> Tuple[bool, str]:
        """
        运行实时推理模式

        Args:
            audio_path: 音频文件路径
            image_path: 头像图片路径
            output_path: 输出视频路径
            fps: 输出视频帧率
            crop_face: 是否裁剪人脸区域
            still_mode: 是否使用静态模式
            enhancer: 增强器类型
            background_enhancer: 背景增强器
            face_swap: 是否启用换脸
            batch_size: 批量大小

        Returns:
            (成功标志, 消息或错误信息)
        """
        try:
            # 验证输入文件
            audio_path = Path(audio_path)
            image_path = Path(image_path)
            output_path = Path(output_path)

            if not audio_path.exists():
                return False, f"音频文件不存在: {audio_path}"

            if not image_path.exists():
                return False, f"头像文件不存在: {image_path}"

            # 确保输出目录存在
            output_path.parent.mkdir(parents=True, exist_ok=True)

            # 构建命令参数
            cmd = [
                sys.executable,
                str(self.realtime_script),
                "--audio_path", str(audio_path),
                "--image_path", str(image_path),
                "--output_path", str(output_path),
                "--fps", str(fps),
                "--model_version", self.model_version,
                "--device", self.device,
                "--batch_size", str(batch_size)
            ]

            # 添加可选参数
            if crop_face:
                cmd.append("--crop_face")

            if still_mode:
                cmd.append("--still")

            if enhancer:
                cmd.extend(["--enhancer", enhancer])

            if background_enhancer:
                extend(["--background_enhancer", background_enhancer])

            if face_swap:
                cmd.append("--face_swap")

            if self.use_float16:
                cmd.append("--use_float16")

            if self.verbose:
                cmd.append("--verbose")

            # 切换到 MuseTalk 目录
            original_cwd = os.getcwd()
            os.chdir(self.musetalk_path)

            try:
                logger.info(f"运行 MuseTalk 实时推理...")
                logger.info(f"命令: {' '.join(cmd)}")

                start_time = time.time()

                # 运行命令
                process = subprocess.run(
                    cmd,
                    capture_output=not self.verbose,
                    text=True,
                    check=False
                )

                elapsed_time = time.time() - start_time

                if process.returncode == 0:
                    # 检查输出文件
                    if output_path.exists() and output_path.stat().st_size > 0:
                        logger.info(f"视频生成成功: {output_path}")
                        logger.info(f"文件大小: {output_path.stat().st_size / 1024 / 1024:.2f} MB")
                        logger.info(f"生成时间: {elapsed_time:.2f} 秒")

                        return True, f"视频生成成功: {output_path}"
                    else:
                        logger.warning(f"输出文件不存在或为空: {output_path}")
                        return False, "输出文件不存在或为空"
                else:
                    error_msg = f"MuseTalk 执行失败 (返回码: {process.returncode})"
                    if process.stderr:
                        error_msg += f"\n错误输出:\n{process.stderr}"
                    logger.error(error_msg)
                    return False, error_msg

            finally:
                os.chdir(original_cwd)

        except Exception as e:
            error_msg = f"运行实时推理失败: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return False, error_msg

    def run_batch_inference(
        self,
        input_dir: str,
        output_dir: str,
        audio_extension: str = ".wav",
        image_extension: str = ".png",
        fps: int = 25,
        batch_size: int = 4,
        num_workers: int = 2
    ) -> Tuple[bool, List[str], List[str]]:
        """
        运行批量推理模式

        Args:
            input_dir: 输入目录，包含成对的音频和图像文件
            output_dir: 输出目录
            audio_extension: 音频文件扩展名
            image_extension: 图像文件扩展名
            fps: 输出视频帧率
            batch_size: 批量大小
            num_workers: 工作进程数

        Returns:
            (成功标志, 成功文件列表, 失败文件列表)
        """
        try:
            input_dir = Path(input_dir)
            output_dir = Path(output_dir)

            if not input_dir.exists():
                return False, [], [f"输入目录不存在: {input_dir}"]

            # 确保输出目录存在
            output_dir.mkdir(parents=True, exist_ok=True)

            # 查找匹配的文件对
            audio_files = list(input_dir.glob(f"*{audio_extension}"))
            image_files = list(input_dir.glob(f"*{image_extension}"))

            if not audio_files:
                return False, [], ["未找到音频文件"]

            if not image_files:
                return False, [], ["未找到图像文件"]

            # 构建批量处理文件列表
            batch_file = input_dir / "batch_list.txt"
            with open(batch_file, "w", encoding="utf-8") as f:
                for audio_file in audio_files:
                    # 查找对应的图像文件
                    stem = audio_file.stem
                    image_file = input_dir / f"{stem}{image_extension}"

                    if image_file.exists():
                        f.write(f"{audio_file}|{image_file}\n")
                    else:
                        logger.warning(f"找不到对应的图像文件: {audio_file}")

            # 构建命令参数
            cmd = [
                sys.executable,
                str(self.batch_script),
                "--batch_list", str(batch_file),
                "--output_dir", str(output_dir),
                "--fps", str(fps),
                "--model_version", self.model_version,
                "--device", self.device,
                "--batch_size", str(batch_size),
                "--num_workers", str(num_workers)
            ]

            if self.use_float16:
                cmd.append("--use_float16")

            if self.verbose:
                cmd.append("--verbose")

            # 切换到 MuseTalk 目录
            original_cwd = os.getcwd()
            os.chdir(self.musetalk_path)

            try:
                logger.info(f"运行 MuseTalk 批量推理...")
                logger.info(f"处理 {len(audio_files)} 个音频文件")
                logger.info(f"命令: {' '.join(cmd)}")

                start_time = time.time()

                # 运行命令
                process = subprocess.run(
                    cmd,
                    capture_output=not self.verbose,
                    text=True,
                    check=False
                )

                elapsed_time = time.time() - start_time

                if process.returncode == 0:
                    # 收集成功和失败的文件
                    success_files = []
                    failed_files = []

                    # 检查输出文件
                    for audio_file in audio_files:
                        stem = audio_file.stem
                        output_video = output_dir / f"{stem}.mp4"

                        if output_video.exists() and output_video.stat().st_size > 0:
                            success_files.append(str(output_video))
                        else:
                            failed_files.append(stem)

                    logger.info(f"批量处理完成")
                    logger.info(f"成功: {len(success_files)} 个文件")
                    logger.info(f"失败: {len(failed_files)} 个文件")
                    logger.info(f"总时间: {elapsed_time:.2f} 秒")

                    return True, success_files, failed_files
                else:
                    error_msg = f"批量处理失败 (返回码: {process.returncode})"
                    if process.stderr:
                        error_msg += f"\n错误输出:\n{process.stderr}"
                    logger.error(error_msg)
                    return False, [], [error_msg]

            finally:
                os.chdir(original_cwd)
                # 清理临时文件
                if batch_file.exists():
                    batch_file.unlink()

        except Exception as e:
            error_msg = f"运行批量推理失败: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return False, [], [error_msg]

    async def run_async_inference(
        self,
        audio_path: str,
        image_path: str,
        output_path: str,
        **kwargs
    ) -> Tuple[bool, str]:
        """
        异步运行推理

        Args:
            audio_path: 音频文件路径
            image_path: 头像图片路径
            output_path: 输出视频路径
            **kwargs: 其他参数传递给 run_realtime_inference

        Returns:
            (成功标志, 消息或错误信息)
        """
        loop = asyncio.get_event_loop()

        # 在线程池中运行阻塞操作
        return await loop.run_in_executor(
            None,
            lambda: self.run_realtime_inference(audio_path, image_path, output_path, **kwargs)
        )

    def get_status(self) -> Dict[str, Any]:
        """获取推理器状态"""
        return {
            "musetalk_path": str(self.musetalk_path),
            "model_version": self.model_version,
            "model_dir": str(self.model_dir),
            "use_float16": self.use_float16,
            "device": self.device,
            "realtime_script_exists": self.realtime_script.exists(),
            "batch_script_exists": self.batch_script.exists(),
            "model_exists": self.model_dir.exists(),
            "dependencies_ok": self.check_dependencies()
        }


def main():
    """命令行入口函数"""
    parser = argparse.ArgumentParser(description="MuseTalk 唇形同步推理脚本")
    parser.add_argument("--mode", choices=["realtime", "batch"], default="realtime",
                       help="推理模式: realtime (单文件) 或 batch (批量)")

    # 实时模式参数
    parser.add_argument("--audio", type=str, help="音频文件路径 (实时模式)")
    parser.add_argument("--image", type=str, help="头像图像路径 (实时模式)")
    parser.add_argument("--output", type=str, help="输出视频路径 (实时模式)")

    # 批量模式参数
    parser.add_argument("--input-dir", type=str, help="输入目录 (批量模式)")
    parser.add_argument("--output-dir", type=str, help="输出目录 (批量模式)")

    # 通用参数
    parser.add_argument("--fps", type=int, default=25, help="输出视频帧率")
    parser.add_argument("--model-version", choices=["v15", "v1"], default="v15",
                       help="MuseTalk 模型版本")
    parser.add_argument("--device", choices=["cuda", "cpu"], default="cuda",
                       help="推理设备")
    parser.add_argument("--use-float16", action="store_true", default=True,
                       help="使用 float16 模式")
    parser.add_argument("--no-float16", action="store_false", dest="use_float16",
                       help="禁用 float16 模式")
    parser.add_argument("--crop-face", action="store_true", default=True,
                       help="裁剪人脸区域")
    parser.add_argument("--no-crop-face", action="store_false", dest="crop_face",
                       help="不裁剪人脸区域")
    parser.add_argument("--still", action="store_true", default=True,
                       help="使用静态模式")
    parser.add_argument("--no-still", action="store_false", dest="still",
                       help="不使用静态模式")
    parser.add_argument("--enhancer", type=str, default="gfpgan",
                       choices=["gfpgan", "restoreformer", None],
                       help="面部增强器")
    parser.add_argument("--verbose", action="store_true",
                       help="显示详细输出")
    parser.add_argument("--status", action="store_true",
                       help="显示服务状态并退出")

    # 批量模式特定参数
    parser.add_argument("--batch-size", type=int, default=4,
                       help="批量大小 (批量模式)")
    parser.add_argument("--num-workers", type=int, default=2,
                       help="工作进程数 (批量模式)")
    parser.add_argument("--audio-extension", type=str, default=".wav",
                       help="音频文件扩展名 (批量模式)")
    parser.add_argument("--image-extension", type=str, default=".png",
                       help="图像文件扩展名 (批量模式)")

    args = parser.parse_args()

    # 创建推理器
    try:
        inference = MuseTalkInference(
            model_version=args.model_version,
            use_float16=args.use_float16,
            device=args.device,
            verbose=args.verbose
        )
    except Exception as e:
        logger.error(f"初始化 MuseTalk 推理器失败: {e}")
        sys.exit(1)

    # 显示状态
    if args.status:
        status = inference.get_status()
        print(json.dumps(status, indent=2, ensure_ascii=False))
        sys.exit(0)

    # 检查依赖
    if not inference.check_dependencies():
        logger.error("依赖检查失败")
        sys.exit(1)

    # 根据模式执行推理
    if args.mode == "realtime":
        # 实时模式
        if not args.audio or not args.image or not args.output:
            parser.error("实时模式需要 --audio, --image 和 --output 参数")

        success, message = inference.run_realtime_inference(
            audio_path=args.audio,
            image_path=args.image,
            output_path=args.output,
            fps=args.fps,
            crop_face=args.crop_face,
            still_mode=args.still,
            enhancer=args.enhancer,
            batch_size=1
        )

        if success:
            logger.info(f"成功: {message}")
            sys.exit(0)
        else:
            logger.error(f"失败: {message}")
            sys.exit(1)

    elif args.mode == "batch":
        # 批量模式
        if not args.input_dir or not args.output_dir:
            parser.error("批量模式需要 --input-dir 和 --output-dir 参数")

        success, success_files, failed_files = inference.run_batch_inference(
            input_dir=args.input_dir,
            output_dir=args.output_dir,
            audio_extension=args.audio_extension,
            image_extension=args.image_extension,
            fps=args.fps,
            batch_size=args.batch_size,
            num_workers=args.num_workers
        )

        if success:
            logger.info(f"批量处理完成")
            logger.info(f"成功文件: {len(success_files)} 个")
            if success_files:
                logger.info(f"第一个成功文件: {success_files[0]}")
            logger.info(f"失败文件: {len(failed_files)} 个")
            if failed_files:
                logger.info(f"前5个失败文件: {failed_files[:5]}")
            sys.exit(0)
        else:
            logger.error(f"批量处理失败")
            if failed_files:
                for error in failed_files[:3]:  # 显示前3个错误
                    logger.error(f"  - {error}")
            sys.exit(1)


if __name__ == "__main__":
    main()