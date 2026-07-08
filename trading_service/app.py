from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from trading_service.api import positions, orders, signals, timeline, strategies
from trading_service.config import settings

logging.basicConfig(
    level=logging.INFO if not settings.debug else logging.DEBUG,
    format="%(asctime)s UTC %(levelname)s %(module)s.%(funcName)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """服务生命周期管理。"""
    logger.info(f"🚀 Trading Service starting on {settings.host}:{settings.port}")
    logger.info(f"📦 Database: {settings.db_path}")
    logger.info(f"🌐 News Service: {settings.news_service_base_url}")
    yield
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


@app.get("/")
async def root() -> dict:
    """根路径健康检查。"""
    return {
        "service": "trading-service",
        "version": "0.1.0",
        "status": "ok",
    }


@app.get("/health")
async def health() -> dict:
    """健康检查端点。"""
    return {
        "status": "healthy",
        "service": "trading-service",
    }
