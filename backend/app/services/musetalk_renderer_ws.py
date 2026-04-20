"""
MuseTalk 渲染器 WebSocket 客户端

作为 Fay 数字人接口 10002 的"皮肤客户端"，监听 Fay 推送的 audio 消息，
自动调用 MuseTalk 生成唇形同步视频。

架构：Fay(LLM + TTS) -> ws://127.0.0.1:10002 -> 本服务 -> MuseTalk -> 视频
"""

import os
import json
import asyncio
import logging
import time
import shutil
from typing import Optional, Dict, Any
from datetime import datetime

import websockets
from websockets.exceptions import ConnectionClosed, InvalidURI, InvalidHandshake

from app.config import settings

logger = logging.getLogger(__name__)


class MuseTalkRendererWS:
    """
    WebSocket 客户端，连接 Fay 10002 端口。
    监听 Topic=human 的 audio/text/question 消息，
    收到 audio 后触发 MuseTalk 推理。
    """

    def __init__(self, musetalk_service, avatar_service):
        self.musetalk_service = musetalk_service
        self.avatar_service = avatar_service

        self.ws_url = settings.FAY_WS_URL
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self._task: Optional[asyncio.Task] = None
        self._running = False

        # username → avatar_id 绑定表
        self._avatar_bindings: Dict[str, str] = {}
        # 默认 avatar_id（前端上传后可设置）
        self.default_avatar_id: Optional[str] = None

        # 当前上下文（最近收到的 question / text）
        self._current_context: Dict[str, Any] = {
            "question": None,
            "reply_text": "",
            "username": None,
        }

        # 最近一次生成结果（供前端查询）
        self.latest_result: Optional[Dict[str, Any]] = None
        # 历史记录（保留最近 20 条）
        self.history: list = []
        self._history_limit = 20

        # 重连配置
        self._reconnect_delay = 3
        self._max_reconnect_delay = 60
        self._current_delay = self._reconnect_delay
        self._reconnect_count = 0
        self._quiet_after = 1  # 首次失败后即降为 DEBUG 级别
        self._quiet_mode = False

        # 渲染锁（单任务，不并发）
        self._render_lock = asyncio.Lock()
        self._is_rendering = False

        # 音频片段收集（等所有片段到齐再渲染）
        self._audio_chunks: list = []     # [(path, text, duration), ...]
        self._collect_username: Optional[str] = None

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------

    async def start(self):
        """启动后台监听循环"""
        if self._running:
            logger.warning("MuseTalk Renderer WS 已在运行中")
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info(f"MuseTalk Renderer WS 已启动，目标: {self.ws_url}")

    async def stop(self):
        """停止后台监听"""
        self._running = False
        if self.ws:
            await self.ws.close()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("MuseTalk Renderer WS 已停止")

    def bind_avatar(self, username: str, avatar_id: str):
        """将用户名绑定到指定 avatar_id"""
        self._avatar_bindings[username] = avatar_id
        logger.info(f"用户 avatar 绑定: {username} -> {avatar_id}")

    def set_default_avatar(self, avatar_id: str):
        """设置默认 avatar_id"""
        self.default_avatar_id = avatar_id
        logger.info(f"默认 avatar 设置为: {avatar_id}")

    def get_latest_result(self) -> Optional[Dict[str, Any]]:
        """获取最近一次生成结果"""
        return self.latest_result

    def get_history(self, limit: int = 10) -> list:
        """获取历史记录"""
        return self.history[-limit:]

    def get_status(self) -> Dict[str, Any]:
        """获取渲染器状态"""
        return {
            "running": self._running,
            "connected": self.ws is not None and self.ws.open,
            "ws_url": self.ws_url,
            "is_rendering": self._is_rendering,
            "default_avatar_id": self.default_avatar_id,
            "avatar_bindings": dict(self._avatar_bindings),
            "history_count": len(self.history),
            "latest_result": self.latest_result,
        }

    # ------------------------------------------------------------------
    # 内部：连接与消息循环
    # ------------------------------------------------------------------

    async def _run_loop(self):
        """持续连接 + 消息监听主循环，断线自动重连"""
        while self._running:
            try:
                await self._connect_and_listen()
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._reconnect_count += 1
                if self._reconnect_count == 1:
                    logger.warning(
                        f"Fay WebSocket ({self.ws_url}) 连接失败: {e} "
                        f"— Fay 可能未启动，后续重连将静默进行"
                    )
                    self._quiet_mode = True
                else:
                    logger.debug(f"WebSocket 重连失败 (第{self._reconnect_count}次): {e}")
            if self._running:
                logger.debug(f"将在 {self._current_delay}s 后重连...")
                await asyncio.sleep(self._current_delay)
                self._current_delay = min(
                    self._current_delay * 2, self._max_reconnect_delay
                )

    async def _connect_and_listen(self):
        """建立 WS 连接，发送身份注册，进入接收循环"""
        logger.debug(f"正在连接 Fay WebSocket: {self.ws_url}")
        try:
            async with websockets.connect(
                self.ws_url,
                ping_interval=20,
                ping_timeout=10,
                close_timeout=5,
            ) as ws:
                self.ws = ws
                self._current_delay = self._reconnect_delay
                self._reconnect_count = 0
                self._quiet_mode = False
                logger.info("已连接 Fay WebSocket 10002")

                # 注册身份：Username 必须与 Fay 消息中的 Username 一致（默认 "User"），
                # 否则 Fay 的定向推送不会到达此客户端
                await ws.send(json.dumps({
                    "Username": "User",
                    "Output": True,
                }, ensure_ascii=False))
                logger.info("已发送身份注册: Username=User, Output=True")

                async for raw_message in ws:
                    if not self._running:
                        break
                    try:
                        await self._handle_message(raw_message)
                    except Exception as e:
                        logger.error(f"处理消息异常: {e}", exc_info=True)

        except (ConnectionClosed, InvalidURI, InvalidHandshake) as e:
            logger.warning(f"WebSocket 连接关闭/失败: {e}")
        finally:
            self.ws = None

    async def _handle_message(self, raw: str):
        """解析并分发一条 JSON 消息"""
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            return

        topic = msg.get("Topic")
        if topic != "human":
            return

        data = msg.get("Data", {})
        key = data.get("Key")
        username = msg.get("Username")

        if key == "question":
            self._on_question(data, username)
        elif key == "text":
            self._on_text(data, username)
        elif key == "audio":
            await self._on_audio(data, username)
        elif key == "log":
            logger.debug(f"Fay log: {data.get('Value', '')}")

    # ------------------------------------------------------------------
    # 消息处理器
    # ------------------------------------------------------------------

    def _on_question(self, data: dict, username: Optional[str]):
        """记录用户提出的问题"""
        question = data.get("Value", "")
        self._current_context["question"] = question
        self._current_context["username"] = username
        self._current_context["reply_text"] = ""
        logger.info(f"收到问题 [{username}]: {question[:80]}")

    def _on_text(self, data: dict, username: Optional[str]):
        """记录 Fay 回复的文本（可能分段到达）"""
        text = data.get("Value", "")
        is_first = data.get("IsFirst", 0)
        if is_first:
            self._current_context["reply_text"] = text
        else:
            self._current_context["reply_text"] += text
        self._current_context["username"] = username

    async def _on_audio(self, data: dict, username: Optional[str]):
        """
        收到 Fay TTS 生成的音频。
        Fay 会把一段完整回复拆成多个小句子分别合成，每个发一条 audio 消息。
        我们收集所有片段，等 IsEnd=1 时合并成完整音频再启动 MuseTalk。

        Data 包含:
          - Value: 本地绝对路径
          - HttpValue: HTTP URL
          - Text: 对应文本
          - Time: 音频时长(秒)
          - IsFirst / IsEnd
        """
        audio_local_path = data.get("Value", "")
        audio_http_url = data.get("HttpValue", "")
        text = data.get("Text", "")
        audio_time = data.get("Time", 0)
        is_first = data.get("IsFirst", 0)
        is_end = data.get("IsEnd", 0)

        logger.info(
            f"收到音频 [{username}]: path={audio_local_path}, "
            f"text={text[:40]}..., duration={audio_time}s, "
            f"IsFirst={is_first}, IsEnd={is_end}"
        )

        audio_path = self._resolve_audio_path(audio_local_path, audio_http_url)
        if not audio_path:
            logger.warning(f"无法获取有效音频文件: local={audio_local_path}")
            return

        if is_first:
            self._audio_chunks = []
            self._collect_username = username

        self._audio_chunks.append((audio_path, text, audio_time))
        logger.info(
            f"音频片段已缓存 ({len(self._audio_chunks)} 段), "
            f"等待 IsEnd 信号..."
        )

        if not is_end:
            return

        # ── IsEnd=1：所有片段到齐，开始处理 ──
        chunks = list(self._audio_chunks)
        self._audio_chunks = []
        full_text = "".join(t for _, t, _ in chunks)
        total_duration = sum(d for _, _, d in chunks)
        logger.info(
            f"所有音频片段到齐: {len(chunks)} 段, "
            f"总时长={total_duration:.1f}s, 文本={full_text[:60]}..."
        )

        # 合并音频
        if len(chunks) == 1:
            merged_audio = chunks[0][0]
        else:
            merged_audio = await self._merge_audio_files(
                [p for p, _, _ in chunks]
            )
            if not merged_audio:
                logger.error("音频合并失败，跳过渲染")
                self._record_result(
                    username=username, text=full_text,
                    status="failed", error="音频片段合并失败",
                )
                return

        # 校验 avatar
        avatar_id = self._resolve_avatar_id(username)
        if not avatar_id:
            logger.warning(
                f"未找到 avatar 绑定: username={username}, "
                f"default={self.default_avatar_id}"
            )
            self._record_result(
                username=username, text=full_text, audio_path=merged_audio,
                status="skipped", error="无可用 avatar，请先上传视频并绑定",
            )
            return

        avatar_path = self.avatar_service.get_avatar_file(avatar_id, size="original")
        if not avatar_path or not os.path.exists(avatar_path):
            logger.warning(f"Avatar 文件不存在: avatar_id={avatar_id}")
            self._record_result(
                username=username, text=full_text, audio_path=merged_audio,
                status="skipped", error=f"avatar 文件不存在: {avatar_id}",
            )
            return

        _VIDEO_EXTS = (".mp4", ".avi", ".mov", ".mkv", ".webm")
        if not avatar_path.lower().endswith(_VIDEO_EXTS):
            logger.warning(
                f"Avatar 文件不是视频格式 ({avatar_path})，MuseTalk 需要 mp4，跳过"
            )
            self._record_result(
                username=username, text=full_text, audio_path=merged_audio,
                status="skipped",
                error=f"avatar 不是视频格式: {os.path.basename(avatar_path)}",
            )
            return

        asyncio.create_task(
            self._render_video(
                audio_path=merged_audio,
                avatar_path=avatar_path,
                avatar_id=avatar_id,
                username=username or "default",
                text=full_text,
                audio_time=total_duration,
            )
        )

    # ------------------------------------------------------------------
    # 音频合并
    # ------------------------------------------------------------------

    async def _merge_audio_files(self, paths: list) -> Optional[str]:
        """用 ffmpeg 将多个音频片段按顺序拼接成一个文件"""
        import subprocess
        import tempfile

        temp_dir = settings.absolute_temp_dir
        os.makedirs(temp_dir, exist_ok=True)

        list_file = os.path.join(
            temp_dir,
            f"concat_{datetime.now().strftime('%Y%m%d_%H%M%S%f')}.txt",
        )
        out_path = os.path.join(
            temp_dir,
            f"merged_{datetime.now().strftime('%Y%m%d_%H%M%S%f')}.mp3",
        )

        try:
            with open(list_file, "w", encoding="utf-8") as f:
                for p in paths:
                    safe = p.replace("\\", "/").replace("'", "'\\''")
                    f.write(f"file '{safe}'\n")

            ffmpeg = getattr(settings, "FFMPEG_PATH", None) or "ffmpeg"
            cmd = [
                ffmpeg, "-y", "-f", "concat", "-safe", "0",
                "-i", list_file, "-c", "copy", out_path,
            ]
            logger.info(f"合并 {len(paths)} 个音频: {' '.join(cmd)}")

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()

            if proc.returncode != 0:
                logger.error(
                    f"ffmpeg concat 失败 (rc={proc.returncode}): "
                    f"{stderr.decode(errors='replace')[:500]}"
                )
                return None

            logger.info(f"音频合并完成: {out_path}")
            return out_path

        except Exception as e:
            logger.error(f"音频合并异常: {e}")
            return None
        finally:
            if os.path.exists(list_file):
                try:
                    os.remove(list_file)
                except OSError:
                    pass

    # ------------------------------------------------------------------
    # MuseTalk 渲染
    # ------------------------------------------------------------------

    async def _render_video(
        self,
        audio_path: str,
        avatar_path: str,
        avatar_id: str,
        username: str,
        text: str,
        audio_time: float,
    ):
        """调用 MuseTalk 生成唇形同步视频"""
        if self._render_lock.locked():
            logger.warning("MuseTalk 正在渲染中，跳过本次请求")
            self._record_result(
                username=username, text=text, audio_path=audio_path,
                status="skipped", error="渲染器繁忙，已跳过",
            )
            return

        async with self._render_lock:
            self._is_rendering = True
            start = time.time()
            logger.info(
                f"开始 MuseTalk 渲染: avatar={avatar_id}, "
                f"audio={os.path.basename(audio_path)}"
            )

            try:
                if not self.musetalk_service.is_available():
                    raise RuntimeError("MuseTalk 服务不可用")

                result = await self.musetalk_service.generate_lip_sync_video(
                    audio_path=audio_path,
                    avatar_path=avatar_path,
                    username=username,
                )

                elapsed = time.time() - start
                video_url = result.get("video_url")
                logger.info(
                    f"MuseTalk 渲染完成: {video_url} ({elapsed:.1f}s)"
                )

                self._record_result(
                    username=username,
                    text=text,
                    audio_path=audio_path,
                    status="completed",
                    video_url=video_url,
                    video_path=result.get("video_path"),
                    duration=elapsed,
                    audio_duration=audio_time,
                    avatar_id=avatar_id,
                )

            except Exception as e:
                elapsed = time.time() - start
                logger.error(f"MuseTalk 渲染失败 ({elapsed:.1f}s): {e}")
                self._record_result(
                    username=username, text=text, audio_path=audio_path,
                    status="failed", error=str(e), duration=elapsed,
                    avatar_id=avatar_id,
                )
            finally:
                self._is_rendering = False

    # ------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------

    def _resolve_audio_path(
        self, local_path: str, http_url: str
    ) -> Optional[str]:
        """
        解析音频文件路径。
        优先使用本地路径（同机部署）；
        如果本地路径不存在，尝试从 HTTP 下载到临时目录。
        """
        if local_path and os.path.isfile(local_path):
            return local_path

        # 尝试将 Fay 的相对路径转为绝对路径
        if local_path:
            fay_dir = os.path.join(settings.BASE_DIR, "Fay")
            candidate = os.path.join(fay_dir, local_path)
            if os.path.isfile(candidate):
                return candidate

        # 如果有 HTTP URL，下载到本地
        if http_url:
            return self._download_audio(http_url)

        return None

    def _download_audio(self, url: str) -> Optional[str]:
        """从 HTTP URL 下载音频到临时目录"""
        try:
            import urllib.request
            temp_dir = settings.absolute_temp_dir
            os.makedirs(temp_dir, exist_ok=True)
            filename = f"fay_audio_{datetime.now().strftime('%Y%m%d_%H%M%S')}.wav"
            dest = os.path.join(temp_dir, filename)
            urllib.request.urlretrieve(url, dest)
            logger.info(f"已下载音频: {url} -> {dest}")
            return dest
        except Exception as e:
            logger.error(f"下载音频失败: {url}, {e}")
            return None

    def _resolve_avatar_id(self, username: Optional[str]) -> Optional[str]:
        """根据用户名查找绑定的 avatar_id，找不到则用默认值"""
        if username and username in self._avatar_bindings:
            return self._avatar_bindings[username]
        return self.default_avatar_id

    def _record_result(self, **kwargs):
        """记录一次渲染结果"""
        result = {
            "timestamp": datetime.now().isoformat(),
            **kwargs,
        }
        self.latest_result = result
        self.history.append(result)
        if len(self.history) > self._history_limit:
            self.history = self.history[-self._history_limit:]
