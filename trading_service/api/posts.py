"""贴文相关 API 端点。

当前提供手动（重新）发布贴文到 Binance Square 的端点，
用于自动发布失败后重试，或手动触发发布。
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from trading_service.api.deps import PublisherDep, TradingStoreDep
from trading_service.content.publisher import resolve_base_asset

logger = logging.getLogger(__name__)

router = APIRouter(tags=["posts"])


@router.post("/{post_id}/publish")
async def publish_post(
    post_id: str,
    store: TradingStoreDep,
    publisher: PublisherDep,
) -> dict[str, str | None]:
    """手动（重新）发布指定贴文到 Binance Square。

    用于自动发布失败后重试，或手动触发发布。
    发布成功返回 share_link，失败返回 500 并记录错误。
    """
    post = store.get_post(post_id)
    if post is None:
        raise HTTPException(status_code=404, detail=f"贴文不存在: {post_id}")

    if not post.post_text:
        raise HTTPException(status_code=400, detail="贴文内容为空，无法发布")

    if not post.symbol:
        raise HTTPException(status_code=400, detail="贴文缺少 symbol，无法发布")

    if publisher is None:
        raise HTTPException(
            status_code=503,
            detail="postx 发布功能未启用（postx_enabled=False）",
        )

    base_asset = resolve_base_asset(post.symbol)
    try:
        share_link = await asyncio.to_thread(
            publisher.publish_postx,
            base_asset=base_asset,
            content=post.post_text,
        )
    except Exception as e:
        logger.warning(f"手动发布贴文 {post_id} 失败: {e}")
        store.update_post_publish_result(
            post_id=post_id,
            published_at=None,
            share_link=None,
            publish_error=str(e),
        )
        raise HTTPException(status_code=500, detail=f"发布失败: {e}")

    store.update_post_publish_result(
        post_id=post_id,
        published_at=datetime.now(timezone.utc),
        share_link=share_link,
        publish_error=None,
    )
    logger.info(f"贴文 {post_id} 手动发布成功: {share_link}")

    return {
        "status": "ok",
        "post_id": post_id,
        "share_link": share_link,
    }
