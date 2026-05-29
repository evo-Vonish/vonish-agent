# pytest configuration
# Only use asyncio backend for anyio-marked tests
import pytest


@pytest.fixture
def anyio_backend():
    return "asyncio"
