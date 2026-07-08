"""pytest 配置。"""

import pytest


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
