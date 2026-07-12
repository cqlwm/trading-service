"""LLM 客户端协议与工厂。

LLMClient 协议定义贴文生成器所需的 LLM 能力子集，
create_openai_client 工厂创建 OpenAI 兼容客户端并适配到协议。
"""
from __future__ import annotations

from typing import Protocol

import openai


class LLMClient(Protocol):
    """LLM 客户端协议：只需 chat.completions.create。"""

    def chat_completions_create(
        self, model: str, messages: list[dict[str, str]], temperature: float = 0.8,
    ) -> str:
        """调用 LLM 生成文本，返回回复内容。"""
        ...


def create_openai_client(base_url: str, api_key: str, model: str) -> tuple[LLMClient, str] | None:
    """创建 OpenAI 兼容客户端。api_key 为空时返回 None。"""
    if not api_key:
        return None

    client = openai.OpenAI(base_url=base_url, api_key=api_key)

    class _Adapter:
        """适配 openai SDK 到 LLMClient 协议。"""

        def chat_completions_create(
            self, model: str, messages: list[dict[str, str]], temperature: float = 0.8,
        ) -> str:
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": m["role"], "content": m["content"]} for m in messages],  # type: ignore[list-item]
                temperature=temperature,
            )
            content = resp.choices[0].message.content
            return content if content is not None else ""

    return _Adapter(), model
