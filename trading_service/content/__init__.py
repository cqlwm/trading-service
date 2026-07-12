"""内容生成模块：从交易故事线生成社交媒体贴文。"""

from trading_service.content.llm_client import LLMClient, create_openai_client
from trading_service.content.post_generator import IPostGenerator, PostGenerator
from trading_service.content.styles import ContentPostStyle, PostStyle, TradingPostStyle

__all__ = [
    "IPostGenerator",
    "PostGenerator",
    "PostStyle",
    "TradingPostStyle",
    "ContentPostStyle",
    "LLMClient",
    "create_openai_client",
]
