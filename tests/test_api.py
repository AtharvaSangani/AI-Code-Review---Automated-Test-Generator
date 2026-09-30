"""Integration tests for FastAPI REST API endpoints using httpx.AsyncClient."""

import pytest
from httpx import AsyncClient

from app.services.llm_client import MockLLMClient


@pytest.mark.asyncio
async def test_health_endpoint(async_client: AsyncClient):
    """Verify health endpoint returns status, uptime, and provider."""
    response = await async_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "uptime_seconds" in data
    assert data["uptime_seconds"] >= 0
    assert data["llm_provider"] in ("mock", "aws_bedrock")
    assert "version" in data
    assert "environment" in data


@pytest.mark.asyncio
async def test_root_endpoint(async_client: AsyncClient):
    """Verify root endpoint returns metadata and documentation paths."""
    response = await async_client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "service" in data
    assert data["docs"] == "/docs"
    assert data["health"] == "/health"


@pytest.mark.asyncio
async def test_timing_middleware_header(async_client: AsyncClient):
    """Verify custom X-Process-Time-Ms header is injected into responses."""
    response = await async_client.get("/health")
    assert "x-process-time-ms" in response.headers
    process_time = float(response.headers["x-process-time-ms"])
    assert process_time >= 0


@pytest.mark.asyncio
async def test_generate_tests_verified_passing(
    async_client: AsyncClient, valid_binary_search_code: str
):
    """Verify valid code generation produces VERIFIED_PASSING verdict."""
    payload = {
        "function_name": "binary_search",
        "source_code": valid_binary_search_code,
        "framework": "pytest",
    }
    response = await async_client.post("/api/v1/generate-tests", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "success"
    assert data["verdict"] == "VERIFIED_PASSING"
    assert data["tests_generated"] >= 1
    assert "test_binary_search" in data["test_code"]
    assert data["execution_time_ms"] > 0
    assert "passed" in data["stdout"]


@pytest.mark.asyncio
async def test_generate_tests_rejected_hallucination(async_client: AsyncClient):
    """Verify that hallucinated/failing code is caught and marked REJECTED_HALLUCINATION."""
    # Use the SIMULATE_HALLUCINATION marker to test detection
    source_code = (
        "# SIMULATE_HALLUCINATION\n"
        "def compute_total(items):\n"
        "    return sum(items)\n"
    )
    payload = {
        "function_name": "compute_total",
        "source_code": source_code,
        "framework": "pytest",
    }
    response = await async_client.post("/api/v1/generate-tests", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "failed"
    assert data["verdict"] == "REJECTED_HALLUCINATION"
    assert data["tests_generated"] >= 1
    assert data["diagnostics"] is not None
    assert "FAILED" in data["stdout"] or "AssertionError" in str(data["diagnostics"])


@pytest.mark.asyncio
async def test_generate_tests_blocks_malicious_source_code_socket(
    async_client: AsyncClient, malicious_socket_code: str
):
    """Verify that submitting source code importing socket is stopped by AST safety filter."""
    payload = {
        "function_name": "steal_data",
        "source_code": malicious_socket_code,
        "framework": "pytest",
    }
    response = await async_client.post("/api/v1/generate-tests", json=payload)
    assert response.status_code == 400
    data = response.json()
    assert "MaliciousSourceCodeDetected" in str(data)
    assert any("socket" in v for v in data["detail"]["violations"])


@pytest.mark.asyncio
async def test_generate_tests_blocks_malicious_source_code_eval(
    async_client: AsyncClient, malicious_eval_code: str
):
    """Verify that submitting source code calling eval is stopped by AST safety filter."""
    payload = {
        "function_name": "dangerous_exec",
        "source_code": malicious_eval_code,
        "framework": "pytest",
    }
    response = await async_client.post("/api/v1/generate-tests", json=payload)
    assert response.status_code == 400
    data = response.json()
    assert "MaliciousSourceCodeDetected" in str(data)
    assert any("eval" in v for v in data["detail"]["violations"])


@pytest.mark.asyncio
async def test_generate_tests_catches_unsafe_llm_generation(async_client: AsyncClient):
    """Verify that if an LLM returns malicious test code, the AST safety filter rejects it."""
    class MaliciousLLMClient(MockLLMClient):
        async def generate_tests(
            self, function_name: str, source_code: str, framework: str = "pytest"
        ):
            return {
                "tests_generated": 1,
                "test_code": (
                    "import subprocess\n"
                    "def test_hack():\n"
                    "    subprocess.run(['rm', '-rf', '/'])\n"
                ),
            }

    from app.api.endpoints import get_llm_client
    from app.main import app

    app.dependency_overrides[get_llm_client] = lambda: MaliciousLLMClient()

    try:
        payload = {
            "function_name": "clean_func",
            "source_code": "def clean_func(): return 1\n",
            "framework": "pytest",
        }
        response = await async_client.post("/api/v1/generate-tests", json=payload)
        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "failed"
        assert data["verdict"] == "REJECTED_HALLUCINATION"
        assert data["diagnostics"]["error"] == "ASTSecurityViolation"
        assert any("subprocess" in v for v in data["diagnostics"]["violations"])
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_review_code_endpoint(
    async_client: AsyncClient, quadratic_algorithm_code: str
):
    """Verify code review returns Flake8 static analysis and Big-O evaluation."""
    payload = {
        "source_code": quadratic_algorithm_code,
    }
    response = await async_client.post("/api/v1/review-code", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "success"
    # Static analysis
    assert "static_analysis" in data
    assert data["static_analysis"]["linter"] == "flake8"
    assert "issue_count" in data["static_analysis"]

    # LLM algorithmic review
    llm_review = data["llm_review"]
    assert "time_complexity" in llm_review
    assert "space_complexity" in llm_review
    assert "O(N^2)" in llm_review["time_complexity"]
    assert len(llm_review["missing_edge_cases"]) > 0
    assert len(llm_review["suggested_improvements"]) > 0
