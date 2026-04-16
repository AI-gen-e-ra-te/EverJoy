"""
Fay HTTP 客户端

用于与 Fay 数字人框架的 OpenAI 兼容接口通信
API地址: http://127.0.0.1:5000/v1/chat/completions
"""

import logging
import httpx
from typing import Dict, List, Optional, Any, AsyncGenerator
from pydantic import BaseModel

from app.config import settings

logger = logging.getLogger(__name__)


class Message(BaseModel):
    """对话消息"""
    role: str  # system, user, assistant
    content: str


class FayClient:
    """Fay HTTP 客户端，支持非流式和流式两种模式"""

    def __init__(self, api_url: Optional[str] = None, timeout: Optional[int] = None):
        self.api_url = api_url or settings.FAY_API_URL
        self.timeout = timeout or settings.FAY_TIMEOUT
        self.client = None
        self.model = "gpt-3.5-turbo"  # Fay 默认使用 GPT-3.5 兼容接口

    async def initialize(self):
        """初始化客户端"""
        self.client = httpx.AsyncClient(
            timeout=self.timeout,
            headers={
                "Content-Type": "application/json"
            }
        )
        logger.info(f"Fay HTTP 客户端初始化完成，API地址: {self.api_url}")

    async def chat_completion(
        self,
        messages: List[Message],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        stream: bool = False
    ) -> Dict[str, Any]:
        """
        Fay 聊天补全（兼容 OpenAI API）

        Args:
            messages: 对话消息列表
            temperature: 温度参数
            max_tokens: 最大令牌数
            stream: 是否使用流式模式

        Returns:
            OpenAI 兼容的响应
        """
        if not self.client:
            await self.initialize()

        data = {
            "model": self.model,
            "messages": [msg.dict() for msg in messages],
            "temperature": temperature,
        }

        if max_tokens:
            data["max_tokens"] = max_tokens
        if stream:
            data["stream"] = True

        try:
            logger.debug(f"发送请求到 Fay API: {self.api_url}")
            logger.debug(f"请求数据: {data}")

            if stream:
                # 流式响应
                async with self.client.stream(
                    "POST",
                    self.api_url,
                    json=data
                ) as response:
                    response.raise_for_status()

                    # 返回流式响应生成器
                    async def response_generator():
                        async for chunk in response.aiter_bytes():
                            yield chunk

                    return response_generator()
            else:
                # 非流式响应
                response = await self.client.post(
                    self.api_url,
                    json=data
                )
                response.raise_for_status()
                result = response.json()
                logger.debug(f"Fay API 响应: {result}")
                return result

        except httpx.HTTPStatusError as e:
            logger.error(f"Fay API 请求失败: {e.response.status_code} - {e.response.text}")
            # 返回模拟响应以便开发
            return self._mock_response(messages)
        except Exception as e:
            logger.error(f"Fay API 调用异常: {e}")
            # 返回模拟响应以便开发
            return self._mock_response(messages)

    def _mock_response(self, messages: List[Message]) -> Dict[str, Any]:
        """生成模拟响应（当Fay服务不可用时）"""
        last_message = messages[-1].content if messages else ""

        # 根据最后一条用户消息生成模拟回复
        mock_replies = {
            "你好": "你好！我是数字人助手，很高兴为你服务。",
            "你是谁": "我是基于Fay框架的数字人助手，可以回答你的问题并进行对话。",
            "今天天气怎么样": "今天天气不错，适合出门散步。",
        }

        reply = mock_replies.get(last_message,
            f"我已收到你的消息：'{last_message}'。这是来自Fay模拟的回复，因为真实Fay服务当前不可用。")

        return {
            "id": "chatcmpl-mock-12345",
            "object": "chat.completion",
            "created": 1677652288,
            "model": self.model,
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": reply
                },
                "finish_reason": "stop"
            }],
            "usage": {
                "prompt_tokens": len(last_message),
                "completion_tokens": len(reply),
                "total_tokens": len(last_message) + len(reply)
            }
        }

    async def generate_reply(self, user_text: str, username: str = "User") -> str:
        """
        生成回复文本

        Args:
            user_text: 用户输入的文本
            username: 用户名（可选）

        Returns:
            助手回复的文本
        """
        messages = [
            Message(
                role="system",
                content="你是一个友好、专业的数字人助手。请用简洁、自然的语言回答用户的问题。"
            ),
            Message(role="user", content=user_text)
        ]

        try:
            response = await self.chat_completion(
                messages=messages,
                temperature=0.7,
                max_tokens=1000,
                stream=False  # 默认使用非流式
            )

            # 处理流式响应（如果意外返回生成器）
            if hasattr(response, '__aiter__'):
                content_parts = []
                async for chunk in response:
                    # 解析流式响应块
                    try:
                        chunk_str = chunk.decode('utf-8')
                        lines = chunk_str.strip().split('\n')
                        for line in lines:
                            if line.startswith('data: '):
                                data = line[6:]
                                if data == '[DONE]':
                                    break
                                # 这里简化处理，实际需要解析JSON
                                content_parts.append(data)
                    except:
                        pass
                return ''.join(content_parts)
            else:
                # 非流式响应
                return response.get("choices", [{}])[0].get("message", {}).get("content", "")

        except Exception as e:
            logger.error(f"生成回复失败: {e}")
            # 返回模拟回复
            return f"抱歉，生成回复时出现错误: {str(e)}。这是模拟回复。"

    async def generate_reply_stream(self, user_text: str, username: str = "User") -> AsyncGenerator[str, None]:
        """
        生成流式回复

        Args:
            user_text: 用户输入的文本
            username: 用户名（可选）

        Yields:
            回复文本的流式片段
        """
        messages = [
            Message(
                role="system",
                content="你是一个友好、专业的数字人助手。请用简洁、自然的语言回答用户的问题。"
            ),
            Message(role="user", content=user_text)
        ]

        try:
            response_generator = await self.chat_completion(
                messages=messages,
                temperature=0.7,
                max_tokens=1000,
                stream=True  # 使用流式模式
            )

            if hasattr(response_generator, '__aiter__'):
                async for chunk in response_generator:
                    try:
                        chunk_str = chunk.decode('utf-8')
                        lines = chunk_str.strip().split('\n')
                        for line in lines:
                            if line.startswith('data: '):
                                data = line[6:]
                                if data == '[DONE]':
                                    break
                                # 简化处理：直接返回数据
                                yield data
                    except Exception as e:
                        logger.error(f"解析流式响应块失败: {e}")
                        continue
            else:
                # 如果返回的不是生成器，则作为普通响应处理
                response = response_generator
                content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
                yield content

        except Exception as e:
            logger.error(f"生成流式回复失败: {e}")
            yield f"抱歉，生成回复时出现错误: {str(e)}。这是模拟回复。"

    async def close(self):
        """关闭客户端"""
        if self.client:
            await self.client.aclose()
            logger.info("Fay HTTP 客户端已关闭")


class FayService:
    """Fay 服务管理器"""

    def __init__(self):
        self.client = None

    async def initialize(self):
        """初始化Fay服务"""
        self.client = FayClient()
        await self.client.initialize()
        logger.info("Fay 服务初始化完成")

    async def generate_reply(self, user_text: str, username: str = "User") -> str:
        """生成回复（对外接口）"""
        if not self.client:
            await self.initialize()
        return await self.client.generate_reply(user_text, username)

    async def close(self):
        """关闭服务"""
        if self.client:
            await self.client.close()
            logger.info("Fay 服务已关闭")


# 全局Fay服务实例
fay_service = FayService()