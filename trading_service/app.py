from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from trading_service.api import positions, orders, signals, timeline, strategies, posts
from trading_service.api.deps import get_strategy_scheduler, get_publisher, set_publisher_loop
from trading_service.config import settings
from trading_service.migration_check import check_migrations, run_migrations

logging.basicConfig(
    level=logging.INFO if not settings.debug else logging.DEBUG,
    format="%(asctime)s UTC %(levelname)s %(module)s.%(funcName)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def validate_migrations() -> None:
    """校验数据库迁移是否是最新的。"""
    is_latest, current_rev, head_rev = check_migrations(settings.db_path)

    if is_latest:
        logger.info(f"✅ Database schema is up to date (revision: {current_rev})")
    else:
        logger.warning(f"⚠️  Database schema is outdated!")
        logger.warning(f"   Current revision: {current_rev}")
        logger.warning(f"   Latest revision:  {head_rev}")
        logger.warning("   Auto-running migrations...")
        run_migrations(settings.db_path)
        logger.info("✅ Migrations completed successfully")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[Any, None]:
    """服务生命周期管理。"""
    logger.info(f"🚀 Trading Service starting on {settings.host}:{settings.port}")
    logger.info(f"📦 Database: {settings.db_path}")
    logger.info(f"🌐 News Service: {settings.news_service_base_url}")

    # 启动时校验并运行数据库迁移
    validate_migrations()

    # 启动策略调度器，恢复关闭前的运行状态
    scheduler = get_strategy_scheduler()
    await scheduler.start()
    logger.info("⏰ 策略调度器已启动")

    # 为 postx 发布器注入事件循环（lifespan 在 loop 线程运行）
    # publisher worker 通过该 loop 把 async 回调调度回事件循环
    set_publisher_loop()

    yield

    # 关闭策略调度器
    await scheduler.shutdown()

    # 关闭 postx 发布器（释放浏览器资源）
    publisher = get_publisher()
    if publisher is not None:
        publisher.close()
        logger.info("🔒 postx 发布器已关闭")

    logger.info("👋 Trading Service shutdown complete")


app = FastAPI(
    title="Trading Service API",
    description="独立交易服务 - 策略引擎、仓位管理、订单执行",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(positions.router, prefix="/api/positions")
app.include_router(orders.router, prefix="/api/orders")
app.include_router(signals.router, prefix="/api/signals")
app.include_router(timeline.router, prefix="/api")
app.include_router(strategies.router, prefix="/api/strategies")
app.include_router(posts.router, prefix="/api/posts")


@app.get("/")
async def root() -> dict[str, str]:
    """根路径健康检查。"""
    return {
        "service": "trading-service",
        "version": "0.1.0",
        "status": "ok",
    }


@app.get("/health")
async def health() -> dict[str, str]:
    """健康检查端点。"""
    return {
        "status": "healthy",
        "service": "trading-service",
    }
