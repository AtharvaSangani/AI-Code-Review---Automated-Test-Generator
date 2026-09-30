"""Unit tests for AST security verification and forbidden module detection."""

import pytest
from app.core.security import validate_code_safety


def test_safe_code_passes_validation():
    """Verify that legitimate algorithms and tests pass inspection."""
    code = (
        "import math\n"
        "from typing import List\n\n"
        "def compute_hypotenuse(a: float, b: float) -> float:\n"
        "    return math.sqrt(a**2 + b**2)\n\n"
        "def test_compute_hypotenuse():\n"
        "    assert compute_hypotenuse(3.0, 4.0) == 5.0\n"
    )
    result = validate_code_safety(code)
    assert result.is_safe is True
    assert len(result.violations) == 0
    assert result.syntax_error is None


@pytest.mark.parametrize(
    "module_name",
    ["os", "sys", "subprocess", "socket", "shutil", "pty", "pickle", "ctypes"],
)
def test_forbidden_module_direct_import_blocked(module_name: str):
    """Ensure direct imports of prohibited modules are caught."""
    code = f"import {module_name}\nprint({module_name})"
    result = validate_code_safety(code)
    assert result.is_safe is False
    assert any(module_name in v for v in result.violations)


@pytest.mark.parametrize(
    "module_name,symbol",
    [
        ("os", "system"),
        ("sys", "exit"),
        ("subprocess", "Popen"),
        ("socket", "socket"),
        ("shutil", "rmtree"),
        ("urllib.request", "urlopen"),
    ],
)
def test_forbidden_module_from_import_blocked(module_name: str, symbol: str):
    """Ensure 'from x import y' statements for forbidden modules are caught."""
    code = f"from {module_name} import {symbol}"
    result = validate_code_safety(code)
    assert result.is_safe is False
    assert any(module_name.split(".")[0] in v for v in result.violations)


@pytest.mark.parametrize(
    "call_name",
    ["eval", "exec", "__import__", "open", "compile", "globals", "locals"],
)
def test_forbidden_builtin_calls_blocked(call_name: str):
    """Ensure calls to dangerous builtins are stopped."""
    code = f"def exploit():\n    return {call_name}('some_arg')\n"
    result = validate_code_safety(code)
    assert result.is_safe is False
    assert any(call_name in v for v in result.violations)


def test_sandbox_dunder_escape_blocked():
    """Ensure introspection dunders like __subclasses__ and __globals__ are stopped."""
    code = "def escape():\n    return ().__class__.__bases__[0].__subclasses__()\n"
    result = validate_code_safety(code)
    assert result.is_safe is False
    assert any("__subclasses__" in v or "__bases__" in v for v in result.violations)


def test_syntax_error_handling():
    """Ensure invalid Python syntax is cleanly rejected without throwing unhandled exceptions."""
    malformed_code = "def broken_func(\n    return 42"
    result = validate_code_safety(malformed_code)
    assert result.is_safe is False
    assert result.syntax_error is not None
    assert any("Syntax error" in v for v in result.violations)


def test_empty_code_handling():
    """Ensure empty or whitespace-only code strings are rejected."""
    result = validate_code_safety("   \n\t  ")
    assert result.is_safe is False
    assert "Empty code" in result.violations[0]
