"""AST Safety Inspection & Forbidden Module Checker.

This module provides static validation of code before execution, preventing
arbitrary code execution, unauthorized filesystem access, and network calls.
"""

import ast
from dataclasses import dataclass, field
from typing import List, Optional, Set


# Blocked modules that pose security risks in the sandboxed environment
FORBIDDEN_MODULES: Set[str] = {
    # System and OS access
    "os",
    "sys",
    "subprocess",
    "socket",
    "posix",
    "resource",
    "signal",
    "pty",
    "commands",
    "shutil",
    # Introspection and code execution
    "importlib",
    "builtins",
    "__builtin__",
    "code",
    "codeop",
    # Serialization vulnerabilities
    "pickle",
    "cPickle",
    "marshal",
    "shelve",
    # Memory and binary exploitation
    "ctypes",
    # Concurrency manipulation
    "multiprocessing",
    "threading",
    # Network libraries
    "urllib",
    "http",
    "requests",
    "httpx",
    "aiohttp",
    "socketserver",
    "ftplib",
    "poplib",
    "imaplib",
    "smtplib",
    "telnetlib",
}

# Dangerous built-in function names that should not be invoked directly
FORBIDDEN_CALLS: Set[str] = {
    "eval",
    "exec",
    "__import__",
    "open",
    "compile",
    "input",
    "globals",
    "locals",
    "setattr",
    "delattr",
}

# Prohibited dunder attributes commonly used in Python sandbox escapes
FORBIDDEN_ATTRIBUTES: Set[str] = {
    "__subclasses__",
    "__bases__",
    "__mro__",
    "__globals__",
    "__code__",
    "__reduce__",
    "__reduce_ex__",
}


@dataclass
class SafetyCheckResult:
    """Result of static AST safety inspection."""

    is_safe: bool
    violations: List[str] = field(default_factory=list)
    syntax_error: Optional[str] = None


class SecurityViolationError(Exception):
    """Raised when code violates security policies."""

    def __init__(self, violations: List[str]):
        super().__init__(f"Security policy violations: {'; '.join(violations)}")
        self.violations = violations


class ASTSecurityValidator(ast.NodeVisitor):
    """AST Visitor that traverses syntax trees to detect unsafe operations."""

    def __init__(self):
        self.violations: List[str] = []

    def visit_Import(self, node: ast.Import) -> None:
        """Inspect 'import xyz' statements."""
        for alias in node.names:
            base_module = alias.name.split(".")[0]
            if base_module in FORBIDDEN_MODULES:
                self.violations.append(
                    f"Line {node.lineno}: Prohibited module import '{alias.name}'"
                )
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        """Inspect 'from xyz import abc' statements."""
        if node.module:
            base_module = node.module.split(".")[0]
            if base_module in FORBIDDEN_MODULES:
                self.violations.append(
                    f"Line {node.lineno}: Prohibited module import from '{node.module}'"
                )
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        """Inspect function and method calls."""
        # Simple identifier calls: eval(), exec(), open(), etc.
        if isinstance(node.func, ast.Name):
            if node.func.id in FORBIDDEN_CALLS:
                self.violations.append(
                    f"Line {node.lineno}: Prohibited call to dangerous builtin '{node.func.id}()'"
                )

        # Attribute calls: getattr(os, 'system') or builtins.eval()
        elif isinstance(node.func, ast.Attribute):
            if node.func.attr in FORBIDDEN_CALLS:
                self.violations.append(
                    f"Line {node.lineno}: Prohibited call to dangerous method '{node.func.attr}()'"
                )

        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        """Inspect attribute lookups for Python sandbox escape vectors."""
        if node.attr in FORBIDDEN_ATTRIBUTES:
            self.violations.append(
                f"Line {node.lineno}: Prohibited dunder attribute access '{node.attr}'"
            )
        self.generic_visit(node)


def validate_code_safety(code: str) -> SafetyCheckResult:
    """Parse Python code using ast.parse and check against security rules.

    Args:
        code: The Python source code string to inspect.

    Returns:
        SafetyCheckResult with is_safe flag, list of violations, and any syntax error.
    """
    if not code or not code.strip():
        return SafetyCheckResult(is_safe=False, violations=["Empty code provided"])

    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return SafetyCheckResult(
            is_safe=False,
            violations=[f"Syntax error at line {e.lineno}: {e.msg}"],
            syntax_error=f"Line {e.lineno}, col {e.offset}: {e.msg}",
        )

    validator = ASTSecurityValidator()
    validator.visit(tree)

    if validator.violations:
        return SafetyCheckResult(is_safe=False, violations=validator.violations)

    return SafetyCheckResult(is_safe=True, violations=[])
