"""REST API route handlers for test generation, code review, and health checking."""

import time
from fastapi import APIRouter, Depends, HTTPException, status

from app.core.config import settings
from app.core.security import validate_code_safety
from app.schemas.models import (
    GenerateTestsRequest,
    GenerateTestsResponse,
    HealthResponse,
    ReviewCodeRequest,
    ReviewCodeResponse,
)
from app.services.llm_client import BaseLLMClient, get_llm_client
from app.services.sandbox_runner import run_flake8_analysis, run_tests_in_sandbox

router = APIRouter()
start_timestamp: float = time.time()


@router.post(
    "/api/v1/generate-tests",
    response_model=GenerateTestsResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate unit tests with deterministic verification",
    description=(
        "Submits source code, prompts LLM for unit tests, subjects output to AST safety "
        "filtering, and deterministically executes them in an isolated sandbox."
    ),
)
async def generate_tests(
    payload: GenerateTestsRequest,
    llm_client: BaseLLMClient = Depends(get_llm_client),
) -> GenerateTestsResponse:
    """End-to-end pipeline: LLM generation -> AST safety filter -> Pytest sandbox."""
    # 1. Pre-validation of input source code safety
    source_safety = validate_code_safety(payload.source_code)
    if not source_safety.is_safe:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "MaliciousSourceCodeDetected",
                "message": (
                    "Submitted source code contains prohibited operations or syntax errors."
                ),
                "violations": source_safety.violations,
            },
        )

    # 2. Prompt LLM for unit test synthesis
    try:
        generation_result = await llm_client.generate_tests(
            function_name=payload.function_name,
            source_code=payload.source_code,
            framework=payload.framework,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"LLM test generation failed: {str(exc)}",
        )

    test_code = generation_result.get("test_code", "")
    tests_generated = generation_result.get("tests_generated", 0)

    # 3. CRITICAL VERIFICATION SANDBOX - Step A: Static AST Safety Check
    test_safety = validate_code_safety(test_code)
    if not test_safety.is_safe:
        # Generated code attempted prohibited action -> Hallucination / Dangerous code
        return GenerateTestsResponse(
            status="failed",
            tests_generated=tests_generated,
            verdict="REJECTED_HALLUCINATION",
            test_code=test_code,
            execution_time_ms=0.0,
            stdout="",
            stderr="Generated test code was rejected by AST security inspection.",
            diagnostics={
                "error": "ASTSecurityViolation",
                "violations": test_safety.violations,
                "hallucination_reason": (
                    "Generated test code attempted forbidden imports or unsafe operations."
                ),
            },
        )

    # 4. CRITICAL VERIFICATION SANDBOX - Step B & C: Deterministic Sandbox Execution
    sandbox_result = run_tests_in_sandbox(
        source_code=payload.source_code,
        test_code=test_code,
        timeout=settings.SANDBOX_TIMEOUT_SECONDS,
    )

    status_val = "success" if sandbox_result.passed else "failed"

    return GenerateTestsResponse(
        status=status_val,
        tests_generated=tests_generated,
        verdict=sandbox_result.verdict,  # "VERIFIED_PASSING" or "REJECTED_HALLUCINATION"
        test_code=test_code,
        execution_time_ms=sandbox_result.execution_time_ms,
        stdout=sandbox_result.stdout,
        stderr=sandbox_result.stderr,
        diagnostics=sandbox_result.diagnostics,
    )


@router.post(
    "/api/v1/review-code",
    response_model=ReviewCodeResponse,
    status_code=status.HTTP_200_OK,
    summary="Perform static and LLM code review",
    description="Combines Flake8 PEP 8 linting with LLM Big-O and edge case analysis.",
)
async def review_code(
    payload: ReviewCodeRequest,
    llm_client: BaseLLMClient = Depends(get_llm_client),
) -> ReviewCodeResponse:
    """Run dual-track analysis: Flake8 static linter + LLM architectural analysis."""
    # 1. Run Flake8 static analysis
    static_report = run_flake8_analysis(payload.source_code)

    # 2. Run LLM Big-O and edge-case evaluation
    try:
        llm_review = await llm_client.review_code(payload.source_code)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"LLM code review failed: {str(exc)}",
        )

    return ReviewCodeResponse(
        status="success",
        static_analysis=static_report,
        llm_review=llm_review,
    )


@router.get(
    "/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Microservice health and telemetry",
)
async def health_check(
    llm_client: BaseLLMClient = Depends(get_llm_client),
) -> HealthResponse:
    """Return health status, uptime, and active LLM provider mode."""
    uptime = round(time.time() - start_timestamp, 2)
    return HealthResponse(
        status="healthy",
        uptime_seconds=uptime,
        llm_provider=llm_client.provider_name,
        version=settings.APP_VERSION,
        environment=settings.ENVIRONMENT,
    )
