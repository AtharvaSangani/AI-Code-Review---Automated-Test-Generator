"""Isolated Deterministic Sandbox Runner for Pytest Execution and Flake8 Linting.

Executes generated tests in disposable temporary environments with timeouts,
capturing stdout/stderr, measuring execution performance, and detecting hallucinations.
"""

import os
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.schemas.models import Flake8Issue, StaticAnalysisReport


@dataclass
class SandboxResult:
    """Result of sandbox test execution."""

    exit_code: int
    passed: bool
    verdict: str  # 'VERIFIED_PASSING' or 'REJECTED_HALLUCINATION'
    stdout: str
    stderr: str
    execution_time_ms: float
    tests_passed: int
    tests_failed: int
    diagnostics: Optional[Dict[str, Any]] = None


def run_tests_in_sandbox(
    source_code: str,
    test_code: str,
    timeout: Optional[int] = None,
) -> SandboxResult:
    """Execute generated tests against source code in a disposable temp directory.

    Args:
        source_code: The implementation code.
        test_code: The unit tests to execute.
        timeout: Maximum seconds to allow execution (defaults to settings.SANDBOX_TIMEOUT_SECONDS).

    Returns:
        SandboxResult with exit code, verdict, stdout/stderr, and timing.
    """
    timeout = timeout or settings.SANDBOX_TIMEOUT_SECONDS
    start_time = time.perf_counter()

    with tempfile.TemporaryDirectory(prefix="sandbox_runner_") as temp_dir:
        # Write the original implementation to target_module.py
        target_path = os.path.join(temp_dir, "target_module.py")
        with open(target_path, "w", encoding="utf-8") as f:
            f.write(source_code)

        # Write test code to test_target.py, importing target_module
        test_path = os.path.join(temp_dir, "test_target.py")
        harness_code = (
            "# Auto-generated test harness\n"
            "from target_module import *\n"
            "import pytest\n\n"
            f"{test_code}\n"
        )
        with open(test_path, "w", encoding="utf-8") as f:
            f.write(harness_code)

        cmd = [
            sys.executable,
            "-m",
            "pytest",
            test_path,
            "-v",
            "--no-header",
            "--tb=short",
        ]

        # Restrict environment variables inside subprocess for security isolation
        env = {
            "PATH": os.environ.get("PATH", ""),
            "PYTHONPATH": temp_dir,
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONUNBUFFERED": "1",
            "VIRTUAL_ENV": os.environ.get("VIRTUAL_ENV", ""),
        }

        try:
            completed = subprocess.run(
                cmd,
                cwd=temp_dir,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
            )
            elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
            stdout = completed.stdout or ""
            stderr = completed.stderr or ""
            exit_code = completed.returncode

            # Parse pytest outcomes
            passed_match = re.search(r"(\d+)\s+passed", stdout)
            failed_match = re.search(r"(\d+)\s+failed", stdout)
            error_match = re.search(r"(\d+)\s+error", stdout)

            tests_passed = int(passed_match.group(1)) if passed_match else 0
            tests_failed = int(failed_match.group(1)) if failed_match else 0
            if error_match:
                tests_failed += int(error_match.group(1))

            if exit_code == 0:
                return SandboxResult(
                    exit_code=0,
                    passed=True,
                    verdict="VERIFIED_PASSING",
                    stdout=stdout,
                    stderr=stderr,
                    execution_time_ms=elapsed_ms,
                    tests_passed=tests_passed,
                    tests_failed=0,
                    diagnostics={
                        "details": "All unit tests passed successfully in isolated sandbox."
                    },
                )
            else:
                # Tests failed or raised assertion error -> Hallucination caught!
                failure_summary = _extract_failure_diagnostics(stdout, stderr)
                return SandboxResult(
                    exit_code=exit_code,
                    passed=False,
                    verdict="REJECTED_HALLUCINATION",
                    stdout=stdout,
                    stderr=stderr,
                    execution_time_ms=elapsed_ms,
                    tests_passed=tests_passed,
                    tests_failed=tests_failed or 1,
                    diagnostics=failure_summary,
                )

        except subprocess.TimeoutExpired:
            elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
            return SandboxResult(
                exit_code=-1,
                passed=False,
                verdict="REJECTED_HALLUCINATION",
                stdout="",
                stderr=f"Sandbox execution timed out after {timeout} seconds.",
                execution_time_ms=elapsed_ms,
                tests_passed=0,
                tests_failed=1,
                diagnostics={
                    "error": "TimeoutExpired",
                    "reason": (
                        f"Tests exceeded deterministic {timeout}s execution budget. "
                        "Likely infinite loop, recursion error, or blocked I/O."
                    ),
                },
            )
        except Exception as e:
            elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
            return SandboxResult(
                exit_code=-2,
                passed=False,
                verdict="REJECTED_HALLUCINATION",
                stdout="",
                stderr=str(e),
                execution_time_ms=elapsed_ms,
                tests_passed=0,
                tests_failed=1,
                diagnostics={
                    "error": "ExecutionError",
                    "reason": f"Subprocess runner encountered internal exception: {str(e)}",
                },
            )


def _extract_failure_diagnostics(stdout: str, stderr: str) -> Dict[str, Any]:
    """Parse failed test names and assertion failures from pytest output."""
    failed_tests = re.findall(r"FAILED\s+test_target\.py::([^\s\-]+)", stdout)
    if not failed_tests:
        failed_tests = re.findall(r"FAILED\s+.*?::([^\s\-]+)", stdout)
    assertion_errors: List[str] = []

    for line in stdout.splitlines():
        line_clean = line.strip()
        if line_clean.startswith("E   ") or "AssertionError" in line_clean:
            assertion_errors.append(line_clean)

    return {
        "failed_test_count": len(failed_tests),
        "failed_test_names": failed_tests,
        "assertion_samples": assertion_errors[:5],
        "hallucination_reason": (
            "One or more generated assertions failed against the implementation logic."
        ),
    }


def run_flake8_analysis(source_code: str) -> StaticAnalysisReport:
    """Run Flake8 linter on the provided source code and return structured issues.

    Args:
        source_code: Python source code string.

    Returns:
        StaticAnalysisReport containing parsed Flake8 issues and clean status.
    """
    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False, encoding="utf-8") as tf:
        tf.write(source_code)
        temp_filename = tf.name

    try:
        cmd = [
            sys.executable,
            "-m",
            "flake8",
            temp_filename,
            "--max-line-length=100",
        ]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=5,
        )

        issues: List[Flake8Issue] = []
        raw_output = (result.stdout or "").strip()

        # Flake8 output line format: <filename>:<line>:<col>: <code> <message>
        pattern = re.compile(r"^.+?:(\d+):(\d+):\s*([A-Z]\d+)\s*(.+)$")
        for line in raw_output.splitlines():
            match = pattern.match(line.strip())
            if match:
                line_no, col_no, code, msg = match.groups()
                issues.append(
                    Flake8Issue(
                        line=int(line_no),
                        col=int(col_no),
                        code=code,
                        message=msg.strip(),
                    )
                )

        return StaticAnalysisReport(
            linter="flake8",
            issue_count=len(issues),
            issues=issues,
            clean=len(issues) == 0,
        )

    finally:
        if os.path.exists(temp_filename):
            try:
                os.remove(temp_filename)
            except OSError:
                pass
