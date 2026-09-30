"""Unit tests for the isolated subprocess sandbox runner and Flake8 linter."""

from app.services.sandbox_runner import (
    run_tests_in_sandbox,
    run_flake8_analysis,
)


def test_sandbox_runner_passing_test():
    """Verify that correct implementation and passing tests yield VERIFIED_PASSING."""
    source_code = (
        "def multiply(x, y):\n"
        "    return x * y\n"
    )
    test_code = (
        "def test_multiply_positive():\n"
        "    assert multiply(3, 4) == 12\n\n"
        "def test_multiply_zero():\n"
        "    assert multiply(5, 0) == 0\n"
    )

    result = run_tests_in_sandbox(source_code, test_code, timeout=5)
    assert result.exit_code == 0
    assert result.passed is True
    assert result.verdict == "VERIFIED_PASSING"
    assert result.tests_passed == 2
    assert result.tests_failed == 0
    assert result.execution_time_ms > 0
    assert "passed" in result.stdout


def test_sandbox_runner_failing_test_hallucination_caught():
    """Verify that incorrect assertions trigger REJECTED_HALLUCINATION with diagnostics."""
    source_code = (
        "def divide(a, b):\n"
        "    return a / b\n"
    )
    # Hallucinated test: claims 10 / 2 == 99
    test_code = (
        "def test_divide_hallucination():\n"
        "    assert divide(10, 2) == 99\n"
    )

    result = run_tests_in_sandbox(source_code, test_code, timeout=5)
    assert result.exit_code != 0
    assert result.passed is False
    assert result.verdict == "REJECTED_HALLUCINATION"
    assert result.tests_failed >= 1
    assert result.diagnostics is not None
    assert "test_divide_hallucination" in result.diagnostics.get("failed_test_names", [])
    assert len(result.diagnostics.get("assertion_samples", [])) > 0


def test_sandbox_runner_timeout_infinite_loop():
    """Verify that infinite loops are terminated and rejected within the timeout budget."""
    source_code = (
        "def infinite_loop():\n"
        "    while True:\n"
        "        pass\n"
    )
    test_code = (
        "def test_infinite():\n"
        "    infinite_loop()\n"
    )

    result = run_tests_in_sandbox(source_code, test_code, timeout=1)
    assert result.exit_code == -1
    assert result.passed is False
    assert result.verdict == "REJECTED_HALLUCINATION"
    assert "timed out" in result.stderr
    assert result.diagnostics.get("error") == "TimeoutExpired"


def test_flake8_linter_detects_violations():
    """Verify that Flake8 correctly parses PEP 8 style issues."""
    sloppy_code = "x=1\ny=2 \n\ndef foo():\n return 10\n"
    report = run_flake8_analysis(sloppy_code)

    assert report.linter == "flake8"
    assert report.clean is False
    assert report.issue_count > 0
    assert any(issue.code.startswith("E") or issue.code.startswith("W") for issue in report.issues)


def test_flake8_linter_clean_code():
    """Verify that cleanly formatted code returns clean=True with 0 issues."""
    clean_code = (
        "def calculate_area(length: float, width: float) -> float:\n"
        "    return length * width\n"
    )
    report = run_flake8_analysis(clean_code)
    assert report.clean is True
    assert report.issue_count == 0
    assert len(report.issues) == 0
