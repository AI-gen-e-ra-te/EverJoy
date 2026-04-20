"""
Fay 语音桥接服务

负责将用户录音推送到 Fay 的 TCP 10001 端口（原始 PCM），
同时在 WebSocket 10002 上监听 Fay 回传的 question / text / audio 消息，
把结果聚合后返回给调用方。

协议要点（源自 Fay 源码）：
  10001 TCP
    - 无应用层握手，连上即可推原始 PCM（16 kHz / mono / s16le）
    - 用户名绑定：发送 UTF-8 文本 <username>xxx</username>
    - Fay 内部 VAD 通过 ~0.5 s 静音检测断句
    - 服务端每 ~10 s 发心跳 b'\\xf0…\\xf8'，客户端只需 recv 丢弃

  10002 WebSocket
    - 注册：{"Username":"xx","Output":true}
    - 收到 Topic=human 的 JSON，Key 为 question/text/audio/log

  关键时序（实测）：
    TCP 连接 → Fay 录音器启动 "聆听中": ~1.5-2 秒
    "聆听中" → 阿里云 ASR WebSocket 就绪:  ~0.5-1 秒
    总计: 连接后至少等 4 秒再推音频，否则 ASR 收不到数据
"""

import asyncio
import json
import logging
import socket
import time
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

_DEFAULT_FAY_HOST = "127.0.0.1"
_TCP_PORT = 10001
_WS_PORT = 10002
_CHUNK_SIZE = 2048
# 2048 bytes @16kHz/16bit = 64ms 音频，间隔 60ms ≈ 1.07x 实时速
_CHUNK_INTERVAL = 0.060
_WARMUP_DELAY = 4.0              # TCP 连接后等待 Fay 录音器 + ASR 初始化
_SILENCE_DURATION = 2.0           # 发完音频后追加的静音时长（秒），需 > VAD 的 0.5s 阈值
_RESPONSE_TIMEOUT = 120           # 等待 Fay 完整响应的超时


class FayVoiceBridge:
    """一次性语音桥接：推音频到 10001，等结果从 10002 回来"""

    def __init__(
        self,
        fay_host: str = _DEFAULT_FAY_HOST,
        tcp_port: int = _TCP_PORT,
        ws_port: int = _WS_PORT,
        timeout: int = _RESPONSE_TIMEOUT,
    ):
        self.fay_host = fay_host
        self.tcp_port = tcp_port
        self.ws_port = ws_port
        self.timeout = timeout

    async def send_audio_oneshot(
        self,
        pcm_data: bytes,
        username: str = "User",
    ) -> Dict[str, Any]:
        """
        将 PCM 音频推给 Fay，等待 ASR + LLM + TTS 结果。

        Args:
            pcm_data: 16 kHz / mono / s16le 原始 PCM 字节
            username: 用于绑定 Fay 会话

        Returns:
            {
                "question": "ASR 识别到的用户语句",
                "answer":   "LLM 回复的文本",
                "audio_path": "Fay TTS 生成的音频本地路径",
                "success": True/False
            }
        """
        result: Dict[str, Any] = {
            "question": None,
            "answer": None,
            "audio_path": None,
            "success": False,
        }

        got_answer = asyncio.Event()

        # ── 10002 监听协程 ──
        async def listen_ws():
            import websockets
            ws_url = f"ws://{self.fay_host}:{self.ws_port}"
            try:
                async with websockets.connect(
                    ws_url, ping_interval=20, ping_timeout=10, close_timeout=5,
                ) as ws:
                    await ws.send(json.dumps({
                        "Username": username,
                        "Output": True,
                    }))
                    logger.info(f"语音桥 10002 已连接，注册用户名={username}")

                    while True:
                        try:
                            raw = await asyncio.wait_for(ws.recv(), timeout=self.timeout)
                        except asyncio.TimeoutError:
                            logger.warning("语音桥 10002 等待超时")
                            return

                        try:
                            msg = json.loads(raw)
                        except json.JSONDecodeError:
                            continue

                        if msg.get("Topic") != "human":
                            continue

                        data = msg.get("Data", {})
                        key = data.get("Key")

                        if key == "question":
                            result["question"] = data.get("Value", "")
                            logger.info(f"语音桥收到 question: {result['question'][:80]}")

                        elif key == "text":
                            is_first = data.get("IsFirst", 0)
                            text_val = data.get("Value", "")
                            if is_first:
                                result["answer"] = text_val
                            else:
                                result["answer"] = (result["answer"] or "") + text_val

                        elif key == "audio":
                            result["audio_path"] = data.get("Value", "")
                            result["success"] = True
                            logger.info(f"语音桥收到 audio: {result['audio_path']}")
                            got_answer.set()
                            return

                        elif key == "log":
                            logger.debug(f"语音桥 log: {data.get('Value', '')}")

            except Exception as e:
                logger.error(f"语音桥 10002 异常: {e}")

        # ── 10001 推送协程 ──
        async def push_audio():
            # 先让 10002 listener 有时间连上
            await asyncio.sleep(0.3)

            loop = asyncio.get_event_loop()
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(10)

            try:
                await loop.run_in_executor(
                    None, sock.connect, (self.fay_host, self.tcp_port)
                )
                logger.info("语音桥 TCP 10001 已连接")

                # 发用户名绑定（单独发一个包，避免和 PCM 混在一起）
                tag = f"<username>{username}</username>".encode("utf-8")
                await loop.run_in_executor(None, sock.sendall, tag)

                # ★ 关键：等待 Fay 录音器和阿里云 ASR 完成初始化
                # 实测 Fay 需要 ~2-3 秒：DeviceInputListener → Recorder → ASR WebSocket
                logger.info(f"等待 Fay 录音器 + ASR 初始化 ({_WARMUP_DELAY}s)...")
                await asyncio.sleep(_WARMUP_DELAY)

                # 以近实时速度发送 PCM，让 Fay 的 VAD 和 ASR 能正常处理
                # 2048 bytes @16kHz/16bit = 64ms 音频，间隔 60ms ≈ 1.07x 实时速
                total = len(pcm_data)
                sent = 0
                t0 = time.time()
                while sent < total:
                    end = min(sent + _CHUNK_SIZE, total)
                    await loop.run_in_executor(None, sock.sendall, pcm_data[sent:end])
                    sent = end
                    await asyncio.sleep(_CHUNK_INTERVAL)

                elapsed = time.time() - t0
                audio_dur = total / (16000 * 2)
                logger.info(
                    f"语音数据发送完毕: {total} bytes, "
                    f"音频时长 {audio_dur:.1f}s, 实际发送耗时 {elapsed:.1f}s"
                )

                # 追加静音让 VAD 断句
                # Fay VAD 需要 >0.5s 壁钟时间的持续静音才触发 end()
                # 以实时速度发送 2 秒静音 = ~128000 bytes
                silence_total = int(16000 * 2 * _SILENCE_DURATION)
                silence_chunk = b"\x00" * _CHUNK_SIZE
                silence_sent = 0
                while silence_sent < silence_total:
                    await loop.run_in_executor(None, sock.sendall, silence_chunk)
                    silence_sent += _CHUNK_SIZE
                    await asyncio.sleep(_CHUNK_INTERVAL)

                logger.info(f"静音追加完毕 ({_SILENCE_DURATION}s)")

                # 保持 TCP 连接，等待 Fay 处理完毕（通过 10002 收到 audio 事件）
                # 同时吞掉心跳包
                sock.settimeout(2)
                deadline = time.time() + self.timeout
                while time.time() < deadline:
                    if got_answer.is_set():
                        break
                    try:
                        await loop.run_in_executor(None, sock.recv, 4096)
                    except socket.timeout:
                        pass
                    await asyncio.sleep(0.5)

            except Exception as e:
                logger.error(f"语音桥 TCP 10001 异常: {e}")
            finally:
                sock.close()
                logger.info("语音桥 TCP 10001 已关闭")

        # ── 并发执行 ──
        await asyncio.gather(listen_ws(), push_audio())

        if not result["success"] and result["answer"]:
            result["success"] = True

        return result
