"""大模型调用封装 - 支持流式输出"""

from typing import Iterator
from openai import OpenAI
from config import get_settings


def create_client() -> OpenAI:
    """创建 OpenAI 客户端"""
    settings = get_settings()
    return OpenAI(
        api_key=settings.CHATBOT_API_KEY.get_secret_value(),
        base_url=settings.CHATBOT_BASE_URL,
    )


def call_llm(messages: list[dict], stream: bool = False) -> Iterator[str] | str:
    """
    调用大模型

    Args:
        messages: 对话历史消息列表
        stream: 是否启用流式输出

    Returns:
        stream=True 时返回逐 token 字符串的迭代器
        stream=False 时返回完整响应用本
    """
    settings = get_settings()
    client = create_client()

    response = client.chat.completions.create(
        model=settings.CHATBOT_MODEL,
        messages=messages,
        temperature=settings.CHATBOT_TEMPERATURE,
        max_tokens=settings.CHATBOT_MAX_TOKENS,
        stream=stream,
    )

    if stream:
        def _stream_iterator() -> Iterator[str]:
            for chunk in response:
                delta = chunk.choices[0].delta
                if delta.content:
                    yield delta.content
        return _stream_iterator()
    else:
        return response.choices[0].message.content or ""
