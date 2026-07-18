"""贴文相关 API 端点。

当前提供手动（重新）发布贴文到 Binance Square 的端点，
用于自动发布失败后重试，或手动触发发布。

发布采用异步管道：请求入队后立即返回 202（pending），
实际发布结果由 publisher worker 异步完成并回写 PostRecord
（published_at / share_link / publish_error）。
调用方通过 GET 贴文详情轮询发布结果。
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from trading_service.api.deps import PublisherDep, TradingStoreDep
from trading_service.content.publisher import resolve_base_asset

logger = logging.getLogger(__name__)

router = APIRouter(tags=["posts"])


@router.post("/{post_id}/publish")
async def publish_post(
    post_id: str,
    store: TradingStoreDep,
    publisher: PublisherDep,
) -> JSONResponse:
    """手动（重新）发布指定贴文到 Binance Square（异步管道）。

    请求入队后立即返回 202，实际发布由 worker 异步完成，
    结果回写 PostRecord 的 published_at / share_link / publish_error。
    调用方通过 GET 贴文详情轮询结果。
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
    publisher.enqueue(
        publish_id=post_id,
        base_asset=base_asset,
        content=post.post_text,
    )
    logger.info(f"贴文 {post_id} 已入队 Binance Square 发布管道")

    return JSONResponse(
        status_code=202,
        content={
            "status": "pending",
            "post_id": post_id,
            "publish_id": post_id,
        },
    )

