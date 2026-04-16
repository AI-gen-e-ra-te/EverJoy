"""
LLM 客户端服务（备用实现）

注意：本项目主架构通过 Fay 服务集成 LLM，不直接调用 LLM API。
此模块为备用实现，仅用于特殊场景或未来可能的架构变更。

架构原则：
1. 前端 → 本项目后端 → Fay API → 本地 LLM (Ollama/vLLM等)
2. 所有 LLM 交互应由 Fay 处理，包括对话逻辑、记忆管理、工具调用等
3. 本项目应仅关注与 Fay 的接口集成，不涉及 LLM 内部逻辑

当前推荐使用 `fay_client.py` 中的 FayClient 与 Fay 服务交互。

如需使用此备用实现，请明确了解架构变更的影响。
"""



import logging
from typing import Dict, List, Optional, Any, AsyncGenerator
import httpx
from pydantic import BaseModel

from app.config import settings

logger = logging.getLogger(__name__)


class Message(BaseModel):
    """对话消息"""
    role: str  # system, user, assistant
    content: str


class LLMClient:
    """LLM 客户端基类"""

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        self.api_key = api_key
        self.base_url = base_url
        self.client = None
        self.model = "gpt-3.5-turbo"  # 默认模型

    async def initialize(self):
        """初始化客户端"""
        self.client = httpx.AsyncClient(
            timeout=30.0,
            headers=self._get_headers()
        )
        logger.info(f"LLM 客户端初始化完成: {self.__class__.__name__}")

    def _get_headers(self) -> Dict[str, str]:
        """获取请求头"""
        headers = {
            "Content-Type": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def chat_completion(
        self,
        messages: List[Message],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        stream: bool = False
    ) -> Dict[str, Any]:
        """聊天补全"""
        raise NotImplementedError("子类必须实现此方法")

    async def generate_text(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 1000
    ) -> str:
        """生成文本"""
        messages = []
        if system_prompt:
            messages.append(Message(role="system", content=system_prompt))
        messages.append(Message(role="user", content=prompt))

        response = await self.chat_completion(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens
        )
        return response.get("choices", [{}])[0].get("message", {}).get("content", "")

    async def close(self):
        """关闭客户端"""
        if self.client:
            await self.client.aclose()
            logger.info("LLM 客户端已关闭")


class OpenAIClient(LLMClient):
    """OpenAI 兼容客户端"""

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        super().__init__(api_key, base_url)
        self.base_url = base_url or "https://api.openai.com/v1"
        self.model = "gpt-3.5-turbo"

    async def chat_completion(
        self,
        messages: List[Message],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        stream: bool = False
    ) -> Dict[str, Any]:
        """OpenAI 聊天补全"""
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
            response = await self.client.post(
                f"{self.base_url}/chat/completions",
                json=data
            )
            response.raise_for_status()
            return response.json()

        except httpx.HTTPStatusError as e:
            logger.error(f"OpenAI API 请求失败: {e.response.status_code} - {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"OpenAI API 调用异常: {e}")
            raise


class DeepSeekClient(LLMClient):
    """DeepSeek 客户端"""

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        super().__init__(api_key, base_url)
        self.base_url = base_url or "https://api.deepseek.com"
        self.model = "deepseek-chat"

    async def chat_completion(
        self,
        messages: List[Message],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        stream: bool = False
    ) -> Dict[str, Any]:
        """DeepSeek 聊天补全"""
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
            response = await self.client.post(
                f"{self.base_url}/chat/completions",
                json=data
            )
            response.raise_for_status()
            return response.json()

        except httpx.HTTPStatusError as e:
            logger.error(f"DeepSeek API 请求失败: {e.response.status_code} - {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"DeepSeek API 调用异常: {e}")
            raise


class LocalLLMClient(LLMClient):
    """本地 LLM 客户端（如 Ollama）"""

    def __init__(self, base_url: Optional[str] = None, model: str = "llama2"):
        super().__init__(None, base_url)
        self.base_url = base_url or "http://localhost:11434"
        self.model = model

    async def chat_completion(
        self,
        messages: List[Message],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        stream: bool = False
    ) -> Dict[str, Any]:
        """本地 LLM 聊天补全"""
        if not self.client:
            await self.initialize()

        data = {
            "model": self.model,
            "messages": [msg.dict() for msg in messages],
            "temperature": temperature,
            "stream": stream,
        }

        if max_tokens:
            data["max_tokens"] = max_tokens

        try:
            endpoint = f"{self.base_url}/api/chat" if "ollama" in self.base_url else f"{self.base_url}/v1/chat/completions"
            response = await self.client.post(
                endpoint,
                json=data
            )
            response.raise_for_status()
            return response.json()

        except httpx.HTTPStatusError as e:
            logger.error(f"本地 LLM API 请求失败: {e.response.status_code} - {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"本地 LLM API 调用异常: {e}")
            raise


class LLMService:
    """LLM 服务管理器"""

    def __init__(self):
        self.clients = {}
        self.default_client = None

    async def initialize(self):
        """
        初始化 LLM 服务

        警告：本项目主架构应通过 Fay 服务集成 LLM，不直接调用 LLM API。
        此服务为备用实现，仅在特殊场景下使用。

        当前默认使用本地 LLM（如 Ollama），但建议使用 `fay_service` 进行 LLM 交互。
        """
        # 根据配置创建客户端
        # 这里可以根据环境变量配置不同的客户端
        logger.info("正在初始化 LLM 服务（备用实现）...")
        logger.warning("注意：本项目主架构应通过 Fay 服务集成 LLM，建议使用 `fay_service` 模块。")

        # 示例：创建 OpenAI 客户端
        # if settings.OPENAI_API_KEY:
        #     openai_client = OpenAIClient(
        #         api_key=settings.OPENAI_API_KEY,
        #         base_url=settings.OPENAI_BASE_URL
        #     )
        #     await openai_client.initialize()
        #     self.clients["openai"] = openai_client
        #     self.default_client = openai_client

        # 如果没有配置任何客户端，使用本地模式
        if not self.default_client:
            local_client = LocalLLMClient()
            await local_client.initialize()
            self.clients["local"] = local_client
            self.default_client = local_client

        logger.info(f"LLM 服务初始化完成，默认客户端: {self.default_client.__class__.__name__}")

    async def generate_response(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        client_name: Optional[str] = None,
        **kwargs
    ) -> str:
        """生成响应"""
        client = self.clients.get(client_name) if client_name else self.default_client
        if not client:
            raise ValueError(f"未找到 LLM 客户端: {client_name}")

        return await client.generate_text(prompt, system_prompt, **kwargs)

    async def chat(
        self,
        messages: List[Message],
        client_name: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """聊天"""
        client = self.clients.get(client_name) if client_name else self.default_client
        if not client:
            raise ValueError(f"未找到 LLM 客户端: {client_name}")

        return await client.chat_completion(messages, **kwargs)

    async def close(self):
        """关闭所有客户端"""
        for name, client in self.clients.items():
            try:
                await client.close()
                logger.info(f"已关闭 LLM 客户端: {name}")
            except Exception as e:
                logger.error(f"关闭 LLM 客户端 {name} 时发生错误: {e}")

    def get_available_clients(self) -> List[str]:
        """获取可用的客户端列表"""
        return list(self.clients.keys())