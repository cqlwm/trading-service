#!/usr/bin/env python3
"""Trading Service 启动入口。"""

import uvicorn

from trading_service.config import settings


def main() -> None:
    """启动服务。"""
    uvicorn.run(
        "trading_service.app:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )


if __name__ == "__main__":
    main()
