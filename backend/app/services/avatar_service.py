"""
数字人形象（头像）服务

管理数字人形象，包括：
1. 头像上传和存储
2. 头像预处理（人脸检测、裁剪、格式转换）
3. 头像元数据管理
4. 默认头像管理
"""

import os
import shutil
import logging
import hashlib
import json
from typing import Optional, Dict, Any, List, Tuple, BinaryIO
from pathlib import Path
from datetime import datetime
from enum import Enum

from PIL import Image, ImageOps
import numpy as np

from app.config import settings

logger = logging.getLogger(__name__)


class AvatarFormat(Enum):
    """头像格式枚举"""
    PNG = "png"
    JPG = "jpg"
    JPEG = "jpeg"
    WEBP = "webp"


class AvatarSize(Enum):
    """头像尺寸枚举"""
    ORIGINAL = "original"      # 原始尺寸
    LARGE = "large"           # 1024x1024
    MEDIUM = "medium"         # 512x512
    SMALL = "small"           # 256x256
    THUMBNAIL = "thumbnail"   # 128x128


class AvatarService:
    """数字人形象服务管理器"""

    def __init__(self):
        self.avatar_dir = settings.absolute_avatar_dir
        self.default_avatar_dir = os.path.join(self.avatar_dir, "default")
        self.user_avatar_dir = os.path.join(self.avatar_dir, "users")
        self.temp_dir = settings.absolute_temp_dir

        # 确保目录存在
        os.makedirs(self.avatar_dir, exist_ok=True)
        os.makedirs(self.default_avatar_dir, exist_ok=True)
        os.makedirs(self.user_avatar_dir, exist_ok=True)
        os.makedirs(self.temp_dir, exist_ok=True)

        # 头像元数据存储
        self.metadata_file = os.path.join(self.avatar_dir, "metadata.json")
        self.metadata = self._load_metadata()

        # 支持的图像格式
        self.supported_formats = [fmt.value for fmt in AvatarFormat]

    def initialize(self):
        """初始化头像服务"""
        try:
            logger.info("正在初始化头像服务...")

            # 检查并创建默认头像
            self._ensure_default_avatars()

            # 检查图像处理库
            try:
                import cv2
                self.cv2_available = True
                logger.debug("OpenCV 可用")
            except ImportError:
                self.cv2_available = False
                logger.warning("OpenCV 不可用，部分功能受限")

            logger.info("头像服务初始化完成")

        except Exception as e:
            logger.error(f"头像服务初始化失败: {e}")
            raise

    def _load_metadata(self) -> Dict[str, Any]:
        """加载头像元数据"""
        try:
            if os.path.exists(self.metadata_file):
                with open(self.metadata_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            else:
                return {"avatars": {}, "users": {}}
        except Exception as e:
            logger.error(f"加载头像元数据失败: {e}")
            return {"avatars": {}, "users": {}}

    def _save_metadata(self):
        """保存头像元数据"""
        try:
            with open(self.metadata_file, 'w', encoding='utf-8') as f:
                json.dump(self.metadata, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存头像元数据失败: {e}")

    def _ensure_default_avatars(self):
        """确保默认头像存在"""
        default_avatars = {
            "male": {
                "name": "默认男性头像",
                "description": "系统默认男性数字人形象",
                "filename": "default_male.png"
            },
            "female": {
                "name": "默认女性头像",
                "description": "系统默认女性数字人形象",
                "filename": "default_female.png"
            },
            "neutral": {
                "name": "默认中性头像",
                "description": "系统默认中性数字人形象",
                "filename": "default_neutral.png"
            }
        }

        for avatar_type, info in default_avatars.items():
            avatar_path = os.path.join(self.default_avatar_dir, info["filename"])

            # 如果默认头像不存在，创建占位符
            if not os.path.exists(avatar_path):
                self._create_placeholder_avatar(avatar_path, avatar_type)

            # 添加到元数据
            avatar_id = f"default_{avatar_type}"
            if avatar_id not in self.metadata["avatars"]:
                self.metadata["avatars"][avatar_id] = {
                    "id": avatar_id,
                    "type": "default",
                    "gender": avatar_type,
                    "name": info["name"],
                    "description": info["description"],
                    "filename": info["filename"],
                    "path": avatar_path,
                    "created_at": datetime.now().isoformat(),
                    "size": {
                        "original": self._get_image_size(avatar_path),
                        "large": None,
                        "medium": None,
                        "small": None,
                        "thumbnail": None
                    },
                    "format": "png",
                    "url": f"/files/avatars/default/{info['filename']}"
                }
                self._save_metadata()

    def _create_placeholder_avatar(self, path: str, avatar_type: str):
        """创建占位符头像"""
        try:
            # 创建不同颜色的占位符图像
            colors = {
                "male": (66, 135, 245),      # 蓝色
                "female": (245, 66, 191),    # 粉色
                "neutral": (128, 128, 128)   # 灰色
            }

            color = colors.get(avatar_type, (128, 128, 128))

            # 创建 512x512 的图像
            img = Image.new('RGB', (512, 512), color=color)

            # 添加简单的圆形表示脸部
            from PIL import ImageDraw
            draw = ImageDraw.Draw(img)

            # 绘制脸部圆形
            face_center = (256, 256)
            face_radius = 200
            draw.ellipse(
                [face_center[0] - face_radius, face_center[1] - face_radius,
                 face_center[0] + face_radius, face_center[1] + face_radius],
                fill=(255, 255, 255)
            )

            # 保存图像
            img.save(path, 'PNG')
            logger.info(f"创建占位符头像: {path}")

        except Exception as e:
            logger.error(f"创建占位符头像失败: {e}")

    def _get_image_size(self, image_path: str) -> Optional[Dict[str, int]]:
        """获取图像尺寸"""
        try:
            with Image.open(image_path) as img:
                width, height = img.size
                return {"width": width, "height": height}
        except Exception as e:
            logger.error(f"获取图像尺寸失败: {e}")
            return None

    async def upload_avatar(
        self,
        user_id: str,
        username: str,
        image_data: bytes,
        filename: str,
        avatar_name: Optional[str] = None,
        description: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        上传用户头像

        Args:
            user_id: 用户ID
            username: 用户名
            image_data: 图像数据
            filename: 原始文件名
            avatar_name: 头像名称（可选）
            description: 头像描述（可选）

        Returns:
            头像信息
        """
        try:
            logger.info(f"用户 {username} 正在上传头像")

            # 创建用户目录
            user_dir = os.path.join(self.user_avatar_dir, user_id)
            os.makedirs(user_dir, exist_ok=True)

            # 生成唯一文件名
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            file_ext = os.path.splitext(filename)[1].lower()
            if file_ext not in ['.png', '.jpg', '.jpeg', '.webp']:
                file_ext = '.png'  # 默认使用 PNG

            unique_filename = f"{username}_{timestamp}{file_ext}"
            original_path = os.path.join(user_dir, f"original_{unique_filename}")

            # 保存原始图像
            with open(original_path, 'wb') as f:
                f.write(image_data)

            # 验证图像格式
            if not self._validate_image(original_path):
                os.remove(original_path)
                raise ValueError("无效的图像文件")

            # 处理图像（人脸检测、裁剪、调整大小）
            processed_paths = await self._process_avatar_image(original_path, user_dir, unique_filename)

            # 生成头像ID
            avatar_id = f"user_{user_id}_{timestamp}"

            # 计算文件哈希
            file_hash = self._calculate_file_hash(original_path)

            # 创建头像信息
            avatar_info = {
                "id": avatar_id,
                "user_id": user_id,
                "username": username,
                "type": "user",
                "name": avatar_name or f"{username}的头像",
                "description": description or f"{username}的个人头像",
                "original_filename": filename,
                "filename": unique_filename,
                "original_path": original_path,
                "processed_paths": processed_paths,
                "file_hash": file_hash,
                "format": file_ext.lstrip('.'),
                "size": {
                    "original": self._get_image_size(original_path),
                    "large": self._get_image_size(processed_paths.get("large")),
                    "medium": self._get_image_size(processed_paths.get("medium")),
                    "small": self._get_image_size(processed_paths.get("small")),
                    "thumbnail": self._get_image_size(processed_paths.get("thumbnail"))
                },
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
                "urls": {
                    "original": f"/files/avatars/users/{user_id}/original_{unique_filename}",
                    "large": f"/files/avatars/users/{user_id}/large_{unique_filename}",
                    "medium": f"/files/avatars/users/{user_id}/medium_{unique_filename}",
                    "small": f"/files/avatars/users/{user_id}/small_{unique_filename}",
                    "thumbnail": f"/files/avatars/users/{user_id}/thumbnail_{unique_filename}"
                }
            }

            # 保存到元数据
            self.metadata["avatars"][avatar_id] = avatar_info

            # 更新用户头像关联
            if user_id not in self.metadata["users"]:
                self.metadata["users"][user_id] = {
                    "user_id": user_id,
                    "username": username,
                    "avatars": []
                }

            self.metadata["users"][user_id]["avatars"].append(avatar_id)
            self._save_metadata()

            logger.info(f"头像上传成功: {avatar_id}")

            return avatar_info

        except Exception as e:
            logger.error(f"上传头像失败: {e}")
            raise

    async def _process_avatar_image(
        self,
        original_path: str,
        output_dir: str,
        base_filename: str
    ) -> Dict[str, str]:
        """
        处理头像图像

        Args:
            original_path: 原始图像路径
            output_dir: 输出目录
            base_filename: 基础文件名

        Returns:
            处理后的图像路径字典
        """
        processed_paths = {}

        try:
            # 打开原始图像
            with Image.open(original_path) as img:
                # 转换为 RGB 模式（如果是 RGBA）
                if img.mode in ('RGBA', 'LA'):
                    background = Image.new('RGB', img.size, (255, 255, 255))
                    if img.mode == 'RGBA':
                        background.paste(img, mask=img.split()[3])
                    else:
                        background.paste(img, mask=img.split()[1])
                    img = background
                elif img.mode != 'RGB':
                    img = img.convert('RGB')

                # 人脸检测和裁剪
                cropped_img = await self._detect_and_crop_face(img)

                # 生成不同尺寸的头像
                sizes = {
                    "large": (1024, 1024),
                    "medium": (512, 512),
                    "small": (256, 256),
                    "thumbnail": (128, 128)
                }

                for size_name, (width, height) in sizes.items():
                    # 调整大小
                    resized_img = cropped_img.resize((width, height), Image.Resampling.LANCZOS)

                    # 保存图像
                    output_path = os.path.join(output_dir, f"{size_name}_{base_filename}")
                    resized_img.save(output_path, 'PNG', quality=95)

                    processed_paths[size_name] = output_path

                # 保存原始裁剪后的图像
                original_cropped_path = os.path.join(output_dir, f"cropped_{base_filename}")
                cropped_img.save(original_cropped_path, 'PNG', quality=95)
                processed_paths["cropped"] = original_cropped_path

            return processed_paths

        except Exception as e:
            logger.error(f"处理头像图像失败: {e}")
            # 如果处理失败，返回原始图像的缩略图
            return self._create_fallback_thumbnails(original_path, output_dir, base_filename)

    async def _detect_and_crop_face(self, img: Image.Image) -> Image.Image:
        """
        检测人脸并裁剪

        Args:
            img: 原始图像

        Returns:
            裁剪后的人脸图像
        """
        try:
            if self.cv2_available:
                import cv2

                # 将 PIL 图像转换为 OpenCV 格式
                img_cv = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)

                # 使用 Haar 级联分类器检测人脸
                face_cascade = cv2.CascadeClassifier(
                    cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
                )

                gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
                faces = face_cascade.detectMultiScale(
                    gray,
                    scaleFactor=1.1,
                    minNeighbors=5,
                    minSize=(100, 100)
                )

                if len(faces) > 0:
                    # 使用最大的人脸
                    x, y, w, h = max(faces, key=lambda f: f[2] * f[3])

                    # 扩展裁剪区域（包含更多上下文）
                    expansion = 0.3  # 扩展30%
                    x_exp = max(0, int(x - w * expansion))
                    y_exp = max(0, int(y - h * expansion))
                    w_exp = min(img_cv.shape[1] - x_exp, int(w * (1 + 2 * expansion)))
                    h_exp = min(img_cv.shape[0] - y_exp, int(h * (1 + 2 * expansion)))

                    # 裁剪人脸区域
                    face_img = img_cv[y_exp:y_exp + h_exp, x_exp:x_exp + w_exp]

                    # 转换回 PIL 图像
                    face_pil = Image.fromarray(cv2.cvtColor(face_img, cv2.COLOR_BGR2RGB))
                    return face_pil

            # 如果没有检测到人脸或 OpenCV 不可用，使用中心裁剪
            logger.debug("使用中心裁剪代替人脸检测")
            return self._center_crop(img)

        except Exception as e:
            logger.warning(f"人脸检测失败，使用中心裁剪: {e}")
            return self._center_crop(img)

    def _center_crop(self, img: Image.Image, target_ratio: float = 1.0) -> Image.Image:
        """中心裁剪图像"""
        width, height = img.size
        current_ratio = width / height

        if current_ratio > target_ratio:
            # 图像过宽，裁剪宽度
            new_width = int(height * target_ratio)
            left = (width - new_width) // 2
            right = left + new_width
            return img.crop((left, 0, right, height))
        else:
            # 图像过高，裁剪高度
            new_height = int(width / target_ratio)
            top = (height - new_height) // 2
            bottom = top + new_height
            return img.crop((0, top, width, bottom))

    def _create_fallback_thumbnails(
        self,
        original_path: str,
        output_dir: str,
        base_filename: str
    ) -> Dict[str, str]:
        """创建回退缩略图"""
        processed_paths = {}

        try:
            with Image.open(original_path) as img:
                # 转换为 RGB
                if img.mode != 'RGB':
                    img = img.convert('RGB')

                # 中心裁剪为正方形
                cropped_img = self._center_crop(img)

                # 生成不同尺寸
                sizes = {
                    "large": (1024, 1024),
                    "medium": (512, 512),
                    "small": (256, 256),
                    "thumbnail": (128, 128)
                }

                for size_name, (width, height) in sizes.items():
                    resized_img = cropped_img.resize((width, height), Image.Resampling.LANCZOS)
                    output_path = os.path.join(output_dir, f"{size_name}_{base_filename}")
                    resized_img.save(output_path, 'PNG', quality=95)
                    processed_paths[size_name] = output_path

                # 保存裁剪后的原始图像
                original_cropped_path = os.path.join(output_dir, f"cropped_{base_filename}")
                cropped_img.save(original_cropped_path, 'PNG', quality=95)
                processed_paths["cropped"] = original_cropped_path

            return processed_paths

        except Exception as e:
            logger.error(f"创建回退缩略图失败: {e}")
            return {}

    def _validate_image(self, image_path: str) -> bool:
        """验证图像文件"""
        try:
            with Image.open(image_path) as img:
                img.verify()  # 验证图像完整性
                return True
        except Exception as e:
            logger.error(f"图像验证失败: {e}")
            return False

    def _calculate_file_hash(self, file_path: str) -> str:
        """计算文件哈希值"""
        try:
            hasher = hashlib.sha256()
            with open(file_path, 'rb') as f:
                for chunk in iter(lambda: f.read(4096), b''):
                    hasher.update(chunk)
            return hasher.hexdigest()
        except Exception as e:
            logger.error(f"计算文件哈希失败: {e}")
            return ""

    def get_avatar(self, avatar_id: str) -> Optional[Dict[str, Any]]:
        """
        获取头像信息

        Args:
            avatar_id: 头像ID

        Returns:
            头像信息
        """
        return self.metadata.get("avatars", {}).get(avatar_id)

    def get_user_avatars(self, user_id: str) -> List[Dict[str, Any]]:
        """
        获取用户的所有头像

        Args:
            user_id: 用户ID

        Returns:
            头像列表
        """
        user_info = self.metadata.get("users", {}).get(user_id)
        if not user_info:
            return []

        avatars = []
        for avatar_id in user_info.get("avatars", []):
            avatar = self.get_avatar(avatar_id)
            if avatar:
                avatars.append(avatar)

        return avatars

    def get_default_avatars(self) -> List[Dict[str, Any]]:
        """获取默认头像列表"""
        default_avatars = []
        for avatar_id, avatar_info in self.metadata.get("avatars", {}).items():
            if avatar_info.get("type") == "default":
                default_avatars.append(avatar_info)

        return default_avatars

    def delete_avatar(self, avatar_id: str, user_id: str) -> bool:
        """
        删除头像

        Args:
            avatar_id: 头像ID
            user_id: 用户ID（用于权限验证）

        Returns:
            是否删除成功
        """
        try:
            avatar_info = self.get_avatar(avatar_id)
            if not avatar_info:
                logger.warning(f"头像不存在: {avatar_id}")
                return False

            # 验证权限
            if avatar_info.get("user_id") != user_id and avatar_info.get("type") != "user":
                logger.warning(f"用户 {user_id} 无权删除头像 {avatar_id}")
                return False

            # 删除文件
            files_to_delete = [
                avatar_info.get("original_path"),
                *[path for path in avatar_info.get("processed_paths", {}).values() if path]
            ]

            for file_path in files_to_delete:
                if file_path and os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                    except Exception as e:
                        logger.warning(f"删除文件失败 {file_path}: {e}")

            # 从元数据中删除
            if avatar_id in self.metadata["avatars"]:
                del self.metadata["avatars"][avatar_id]

            # 从用户头像列表中删除
            if user_id in self.metadata["users"]:
                user_avatars = self.metadata["users"][user_id].get("avatars", [])
                if avatar_id in user_avatars:
                    user_avatars.remove(avatar_id)

            self._save_metadata()

            logger.info(f"头像删除成功: {avatar_id}")
            return True

        except Exception as e:
            logger.error(f"删除头像失败: {e}")
            return False

    def get_avatar_file(self, avatar_id: str, size: str = "original") -> Optional[str]:
        """
        获取头像文件路径

        Args:
            avatar_id: 头像ID
            size: 头像尺寸（original, large, medium, small, thumbnail）

        Returns:
            文件路径
        """
        avatar_info = self.get_avatar(avatar_id)
        if not avatar_info:
            logger.warning(f"未找到头像信息: {avatar_id}")
            return None

        if size == "original":
            path = avatar_info.get("original_path") or avatar_info.get("path")
            if path:
                normalized_path = os.path.normpath(path)
                return normalized_path
            else:
                logger.warning(f"头像 {avatar_id} 没有 {size} 尺寸的路径")
                return None
        elif size in ["large", "medium", "small", "thumbnail"]:
            path = avatar_info.get("processed_paths", {}).get(size)
            if path:
                normalized_path = os.path.normpath(path)
                return normalized_path
            else:
                logger.warning(f"头像 {avatar_id} 没有 {size} 尺寸的路径")
                return None

        logger.warning(f"无效的头像尺寸: {size}")
        return None

    async def process_video_avatar(self, video_path: str, avatar_id: str) -> Dict[str, Any]:
        """
        处理视频文件作为数字人 avatar。
        步骤：
          1. 复制视频到 avatar 目录
          2. 用 ffmpeg 提取第一帧作为静态 avatar 图片
          3. 保存 metadata
        MuseTalk 推理时会自动做 landmark/bbox 提取，此处只需保证源素材可用。

        Args:
            video_path: 上传的视频文件路径
            avatar_id: 生成的avatar ID

        Returns:
            avatar信息字典
        """
        import json
        import shutil
        import subprocess
        from datetime import datetime

        try:
            logger.info(f"开始处理视频avatar: {avatar_id}, 视频路径: {video_path}")

            avatar_dir = os.path.join(self.avatar_dir, avatar_id)
            os.makedirs(avatar_dir, exist_ok=True)

            avatar_video_path = os.path.join(avatar_dir, "source.mp4")
            shutil.copy2(video_path, avatar_video_path)

            # 用 ffmpeg 抽取第一帧作为预览/静态 avatar
            first_frame_path = os.path.join(avatar_dir, "first_frame.png")
            ffmpeg_cmd = settings.FFMPEG_PATH or "ffmpeg"
            try:
                subprocess.run(
                    [ffmpeg_cmd, "-y", "-i", avatar_video_path,
                     "-vframes", "1", "-q:v", "2", first_frame_path],
                    capture_output=True, timeout=30, check=True
                )
                logger.info(f"已提取第一帧: {first_frame_path}")
            except Exception as e:
                logger.warning(f"提取第一帧失败（ffmpeg）: {e}，将仅使用视频作为 avatar")
                first_frame_path = None

            # 尝试获取视频信息
            video_info = {"duration_seconds": 0, "resolution": "unknown", "frame_rate": 0}
            try:
                ffprobe_cmd = "ffprobe"
                if settings.FFMPEG_PATH:
                    ffprobe_candidate = os.path.join(os.path.dirname(settings.FFMPEG_PATH), "ffprobe")
                    if os.path.exists(ffprobe_candidate) or os.path.exists(ffprobe_candidate + ".exe"):
                        ffprobe_cmd = ffprobe_candidate
                result = subprocess.run(
                    [ffprobe_cmd, "-v", "error", "-select_streams", "v:0",
                     "-show_entries", "stream=width,height,r_frame_rate,duration",
                     "-of", "json", avatar_video_path],
                    capture_output=True, text=True, timeout=15
                )
                if result.returncode == 0:
                    probe = json.loads(result.stdout)
                    stream = probe.get("streams", [{}])[0]
                    w = stream.get("width", 0)
                    h = stream.get("height", 0)
                    video_info["resolution"] = f"{w}x{h}"
                    video_info["duration_seconds"] = float(stream.get("duration", 0))
                    rfr = stream.get("r_frame_rate", "0/1")
                    if "/" in str(rfr):
                        num, den = rfr.split("/")
                        video_info["frame_rate"] = round(int(num) / max(int(den), 1), 2)
            except Exception as e:
                logger.warning(f"获取视频信息失败: {e}")

            metadata = {
                "avatar_id": avatar_id,
                "source_video_path": video_path,
                "processed_video_path": avatar_video_path,
                "first_frame_path": first_frame_path,
                "created_at": datetime.now().isoformat(),
                "status": "processed",
                "processing_type": "video_preprocessing",
                "message": "视频avatar预处理完成",
                "metadata": {
                    "original_filename": os.path.basename(video_path),
                    "file_size": os.path.getsize(video_path),
                    **video_info,
                }
            }

            metadata_path = os.path.join(avatar_dir, "metadata.json")
            with open(metadata_path, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, ensure_ascii=False, indent=2)

            self.metadata["avatars"][avatar_id] = {
                "id": avatar_id,
                "type": "video_avatar",
                "source_video": video_path,
                "path": avatar_video_path,
                "original_path": avatar_video_path,
                "first_frame_path": first_frame_path,
                "avatar_dir": avatar_dir,
                "metadata_path": metadata_path,
                "created_at": datetime.now().isoformat(),
                "status": "ready"
            }
            self._save_metadata()

            logger.info(f"视频avatar处理完成: {avatar_id}")
            return metadata

        except Exception as e:
            logger.error(f"处理视频avatar失败: {e}")
            raise

    def get_video_avatar(self, avatar_id: str) -> Optional[Dict[str, Any]]:
        """
        获取视频avatar信息

        Args:
            avatar_id: avatar ID

        Returns:
            avatar信息字典
        """
        avatar_info = self.metadata.get("avatars", {}).get(avatar_id)
        if avatar_info and avatar_info.get("type") == "video_avatar":
            # 尝试读取metadata.json
            metadata_path = avatar_info.get("metadata_path")
            if metadata_path and os.path.exists(metadata_path):
                try:
                    with open(metadata_path, 'r', encoding='utf-8') as f:
                        return json.load(f)
                except Exception as e:
                    logger.warning(f"读取avatar metadata失败: {e}")
        return avatar_info

    def is_available(self) -> bool:
        """检查服务是否可用"""
        return True