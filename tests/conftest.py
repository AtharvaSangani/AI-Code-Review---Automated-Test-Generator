"""Pytest configuration and shared fixtures."""

import pytest
import pytest_asyncio
import httpx
from httpx import ASGITransport

from app.main import app


@pytest_asyncio.fixture
async def async_client():
    """Async HTTP client bound to the FastAPI ASGI application."""
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
def valid_binary_search_code() -> str:
    """Correct implementation of binary search algorithm."""
    return (
        "def binary_search(arr, target):\n"
        "    left, right = 0, len(arr) - 1\n"
        "    while left <= right:\n"
        "        mid = (left + right) // 2\n"
        "        if arr[mid] == target:\n"
        "            return mid\n"
        "        elif arr[mid] < target:\n"
        "            left = mid + 1\n"
        "        else:\n"
        "            right = mid - 1\n"
        "    return -1\n"
    )


@pytest.fixture
def buggy_binary_search_code() -> str:
    """Buggy implementation that always returns an incorrect index."""
    return (
        "def binary_search(arr, target):\n"
        "    # Deliberate bug to trigger test failure\n"
        "    return 999999\n"
    )


@pytest.fixture
def malicious_socket_code() -> str:
    """Code attempting unauthorized network socket access."""
    return (
        "import socket\n\n"
        "def steal_data():\n"
        "    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)\n"
        "    s.connect(('127.0.0.1', 8080))\n"
        "    return 'pwned'\n"
    )


@pytest.fixture
def malicious_eval_code() -> str:
    """Code attempting arbitrary code execution via eval."""
    return (
        "def dangerous_exec():\n"
        "    payload = \"__import__('os').system('ls')\"\n"
        "    return eval(payload)\n"
    )


@pytest.fixture
def quadratic_algorithm_code() -> str:
    """Quadratic time complexity algorithm with nested loops."""
    return (
        "def find_duplicates(nums):\n"
        "    duplicates = []\n"
        "    for i in range(len(nums)):\n"
        "        for j in range(i + 1, len(nums)):\n"
        "            if nums[i] == nums[j]:\n"
        "                duplicates.append(nums[i])\n"
        "    return duplicates\n"
    )
