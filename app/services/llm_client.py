"""AWS Bedrock SDK integration with automatic MockLLMClient fallback.

Provides zero-cost local execution for development/demo while supporting
production AWS Bedrock Claude 3.5 Sonnet when AWS credentials are present.
"""

import ast
import json
import logging
import os
import re
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.schemas.models import LLMCodeReview

logger = logging.getLogger("uvicorn.error")


class BaseLLMClient(ABC):
    """Abstract interface for LLM client implementations."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Name of the active LLM provider."""
        pass

    @abstractmethod
    async def generate_tests(
        self, function_name: str, source_code: str, framework: str = "pytest"
    ) -> Dict[str, Any]:
        """Generate unit tests for the target function."""
        pass

    @abstractmethod
    async def review_code(self, source_code: str) -> LLMCodeReview:
        """Perform algorithmic and edge-case code review."""
        pass


class BedrockLLMClient(BaseLLMClient):
    """Production AWS Bedrock client using Claude 3.5 Sonnet."""

    def __init__(self, region_name: Optional[str] = None):
        import boto3
        from botocore.config import Config

        self._region = region_name or settings.AWS_REGION
        config = Config(
            region_name=self._region,
            retries={"max_attempts": 3, "mode": "standard"},
            connect_timeout=10,
            read_timeout=30,
        )
        kwargs: Dict[str, Any] = {"config": config}
        if settings.AWS_ACCESS_KEY_ID and settings.AWS_SECRET_ACCESS_KEY:
            kwargs["aws_access_key_id"] = settings.AWS_ACCESS_KEY_ID
            kwargs["aws_secret_access_key"] = settings.AWS_SECRET_ACCESS_KEY
            if settings.AWS_SESSION_TOKEN:
                kwargs["aws_session_token"] = settings.AWS_SESSION_TOKEN

        self.client = boto3.client("bedrock-runtime", **kwargs)
        self.model_id = settings.BEDROCK_MODEL_ID

    @property
    def provider_name(self) -> str:
        return "aws_bedrock"

    async def generate_tests(
        self, function_name: str, source_code: str, framework: str = "pytest"
    ) -> Dict[str, Any]:
        """Call AWS Bedrock Claude with strict JSON schema prompt."""
        prompt = (
            f"You are a Principal Test Engineer. Generate comprehensive unit tests "
            f"using {framework} for the following Python function.\n\n"
            "IMPORTANT INSTRUCTIONS:\n"
            "1. Do NOT import unauthorized or dangerous modules like os, sys, subprocess, socket.\n"
            "2. Return ONLY a valid JSON object matching this schema:\n"
            "{\n"
            '    "tests_generated": <integer count of test functions>,\n'
            '    "test_code": "<raw python code containing pytest test functions>"\n'
            "}\n"
            "3. Do not include markdown codeblocks outside the JSON. Return pure JSON.\n\n"
            f"Target Function Name: {function_name}\n"
            f"Source Code:\n{source_code}\n"
        )
        payload = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 3000,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
        }

        try:
            response = self.client.invoke_model(
                modelId=self.model_id,
                body=json.dumps(payload),
                contentType="application/json",
                accept="application/json",
            )
            response_body = json.loads(response["body"].read().decode("utf-8"))
            content_text = response_body["content"][0]["text"].strip()

            # Clean any stray markdown formatting
            if content_text.startswith("```json"):
                content_text = content_text[7:]
            if content_text.startswith("```"):
                content_text = content_text[3:]
            if content_text.endswith("```"):
                content_text = content_text[:-3]

            data = json.loads(content_text.strip())
            return {
                "test_code": data.get("test_code", ""),
                "tests_generated": data.get("tests_generated", 0),
            }
        except Exception as e:
            logger.error(f"Error calling AWS Bedrock invoke_model: {e}")
            raise RuntimeError(f"Bedrock invocation failed: {str(e)}") from e

    async def review_code(self, source_code: str) -> LLMCodeReview:
        """Call AWS Bedrock Claude for Big-O analysis and edge case detection."""
        prompt = (
            "You are a Principal Software Engineer conducting a thorough code review.\n"
            "Analyze the following Python source code for algorithmic time complexity, "
            "auxiliary space complexity, unhandled edge cases, and architectural improvements.\n\n"
            "Return ONLY a valid JSON object matching this schema:\n"
            "{\n"
            '    "time_complexity": "<e.g., O(N) or O(N log N)>",\n'
            '    "space_complexity": "<e.g., O(1) or O(N)>",\n'
            '    "analysis": "<detailed rationale for complexity and algorithmic behavior>",\n'
            '    "missing_edge_cases": ["<edge case 1>", "<edge case 2>"],\n'
            '    "suggested_improvements": ["<recommendation 1>", "<recommendation 2>"]\n'
            "}\n\n"
            f"Source Code:\n{source_code}\n"
        )
        payload = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 2048,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
        }

        try:
            response = self.client.invoke_model(
                modelId=self.model_id,
                body=json.dumps(payload),
                contentType="application/json",
                accept="application/json",
            )
            response_body = json.loads(response["body"].read().decode("utf-8"))
            content_text = response_body["content"][0]["text"].strip()

            if content_text.startswith("```json"):
                content_text = content_text[7:]
            if content_text.startswith("```"):
                content_text = content_text[3:]
            if content_text.endswith("```"):
                content_text = content_text[:-3]

            data = json.loads(content_text.strip())
            return LLMCodeReview(
                time_complexity=data.get("time_complexity", "O(N)"),
                space_complexity=data.get("space_complexity", "O(1)"),
                analysis=data.get("analysis", "Algorithmic review completed."),
                missing_edge_cases=data.get("missing_edge_cases", []),
                suggested_improvements=data.get("suggested_improvements", []),
            )
        except Exception as e:
            logger.error(f"Error calling AWS Bedrock for code review: {e}")
            raise RuntimeError(f"Bedrock code review failed: {str(e)}") from e


class MockLLMClient(BaseLLMClient):
    """Intelligent local fallback LLM client.

    Uses static AST analysis and pattern heuristics to synthesize realistic,
    functional pytest test suites and Big-O reviews without AWS credentials or costs.
    """

    @property
    def provider_name(self) -> str:
        return "mock"

    async def generate_tests(
        self, function_name: str, source_code: str, framework: str = "pytest"
    ) -> Dict[str, Any]:
        """Synthesize unit tests using AST inspection of function arguments and patterns."""
        # Check if the caller intentionally requested a simulated hallucination
        simulate_hallucination = (
            "# SIMULATE_HALLUCINATION" in source_code
            or "hallucinate" in function_name.lower()
        )

        test_code = self._synthesize_tests(function_name, source_code, simulate_hallucination)
        test_count = len(re.findall(r"def test_\w+\(", test_code))

        return {
            "test_code": test_code,
            "tests_generated": test_count,
        }

    def _synthesize_tests(
        self, function_name: str, source_code: str, simulate_hallucination: bool
    ) -> str:
        """Construct pytest functions tailored to the target function."""
        # Hallucination test case for demonstrating verification failure
        if simulate_hallucination:
            return (
                f"# Intentionally hallucinated test suite for demonstration\n\n"
                f"def test_{function_name}_hallucinated_assertion():\n"
                f"    # Asserts impossible condition to verify sandbox rejection\n"
                f"    result = {function_name}([1, 2, 3])\n"
                f"    assert result == 'IMPOSSIBLE_HALLUCINATED_VALUE'\n"
            )

        # Inspect AST to analyze signature
        param_names: List[str] = []
        try:
            tree = ast.parse(source_code)
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef) and node.name == function_name:
                    param_names = [arg.arg for arg in node.args.args if arg.arg != "self"]
                    break
        except Exception:
            pass

        # Synthesize based on function signature & name patterns
        fn_lower = function_name.lower()

        if "binary_search" in fn_lower or (len(param_names) == 2 and "target" in param_names):
            return (
                f"def test_{function_name}_found_middle():\n"
                f"    arr = [1, 3, 5, 7, 9, 11]\n"
                f"    assert {function_name}(arr, 7) == 3\n\n"
                f"def test_{function_name}_found_first():\n"
                f"    arr = [2, 4, 6, 8, 10]\n"
                f"    assert {function_name}(arr, 2) == 0\n\n"
                f"def test_{function_name}_found_last():\n"
                f"    arr = [1, 2, 3, 4, 5]\n"
                f"    assert {function_name}(arr, 5) == 4\n\n"
                f"def test_{function_name}_not_found():\n"
                f"    arr = [10, 20, 30, 40]\n"
                f"    assert {function_name}(arr, 99) == -1\n\n"
                f"def test_{function_name}_empty_array():\n"
                f"    assert {function_name}([], 5) == -1\n"
            )

        if "two_sum" in fn_lower or "2sum" in fn_lower:
            return (
                f"def test_{function_name}_standard():\n"
                f"    nums = [2, 7, 11, 15]\n"
                f"    target = 9\n"
                f"    res = {function_name}(nums, target)\n"
                f"    assert res in ([0, 1], [1, 0], (0, 1), (1, 0))\n\n"
                f"def test_{function_name}_negative_values():\n"
                f"    nums = [-3, 4, 3, 90]\n"
                f"    target = 0\n"
                f"    res = {function_name}(nums, target)\n"
                f"    assert res in ([0, 2], [2, 0], (0, 2), (2, 0))\n"
            )

        if "find_duplicate" in fn_lower or "duplicates" in fn_lower:
            return (
                f"def test_{function_name}_with_duplicates():\n"
                f"    result = {function_name}([1, 2, 3, 2, 4, 1])\n"
                f"    assert sorted(list(set(result))) == [1, 2]\n\n"
                f"def test_{function_name}_no_duplicates():\n"
                f"    assert {function_name}([1, 2, 3, 4]) == []\n\n"
                f"def test_{function_name}_empty():\n"
                f"    assert {function_name}([]) == []\n"
            )

        if "palindrome" in fn_lower:
            return (
                f"def test_{function_name}_true():\n"
                f"    assert bool({function_name}('racecar')) is True\n\n"
                f"def test_{function_name}_false():\n"
                f"    assert bool({function_name}('hello')) is False\n\n"
                f"def test_{function_name}_single_char():\n"
                f"    assert bool({function_name}('a')) is True\n"
            )

        if "fib" in fn_lower:
            return (
                f"def test_{function_name}_base_cases():\n"
                f"    assert {function_name}(0) == 0\n"
                f"    assert {function_name}(1) == 1\n\n"
                f"def test_{function_name}_recursive():\n"
                f"    assert {function_name}(5) == 5\n"
                f"    assert {function_name}(6) == 8\n"
            )

        if "reverse" in fn_lower:
            return (
                f"def test_{function_name}_string():\n"
                f"    assert {function_name}('abc') == 'cba'\n\n"
                f"def test_{function_name}_empty():\n"
                f"    assert {function_name}('') == ''\n"
            )

        if "add" in fn_lower:
            return (
                f"def test_{function_name}_positive():\n"
                f"    assert {function_name}(2, 3) == 5\n\n"
                f"def test_{function_name}_negative():\n"
                f"    assert {function_name}(-1, 1) == 0\n\n"
                f"def test_{function_name}_zero():\n"
                f"    assert {function_name}(0, 0) == 0\n"
            )

        # Generic synthesis based on parameter count
        if len(param_names) == 1:
            return (
                f"def test_{function_name}_basic():\n"
                f"    # Executed with standard input argument\n"
                f"    res = {function_name}([1, 2, 3])\n"
                f"    assert res is not None\n\n"
                f"def test_{function_name}_boundary():\n"
                f"    # Executed with boundary condition\n"
                f"    res = {function_name}([0])\n"
                f"    assert res is not None\n"
            )
        elif len(param_names) == 2:
            return (
                f"def test_{function_name}_integers():\n"
                f"    res = {function_name}(10, 5)\n"
                f"    assert res is not None\n\n"
                f"def test_{function_name}_zero_case():\n"
                f"    res = {function_name}(0, 1)\n"
                f"    assert res is not None\n"
            )

        # Fallback generic test
        return (
            f"def test_{function_name}_invocation():\n"
            f"    # Verifies function can be safely imported and inspected\n"
            f"    assert callable({function_name})\n"
        )

    async def review_code(self, source_code: str) -> LLMCodeReview:
        """Inspect AST to estimate algorithmic complexity and edge cases."""
        time_comp = "O(1)"
        space_comp = "O(1)"
        analysis_parts: List[str] = []
        edge_cases: List[str] = []
        improvements: List[str] = []

        try:
            tree = ast.parse(source_code)
            fn_names = set()

            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    fn_names.add(node.name)

            class LoopVisitor(ast.NodeVisitor):
                def __init__(self):
                    self.current_depth = 0
                    self.max_depth = 0
                    self.has_recursion = False
                    self.allocations = 0

                def visit_For(self, node: ast.For):
                    self.current_depth += 1
                    self.max_depth = max(self.max_depth, self.current_depth)
                    self.generic_visit(node)
                    self.current_depth -= 1

                def visit_While(self, node: ast.While):
                    self.current_depth += 1
                    self.max_depth = max(self.max_depth, self.current_depth)
                    self.generic_visit(node)
                    self.current_depth -= 1

                def visit_Call(self, node: ast.Call):
                    if isinstance(node.func, ast.Name) and node.func.id in fn_names:
                        self.has_recursion = True
                    if isinstance(node.func, ast.Name) and node.func.id in {"list", "dict", "set"}:
                        self.allocations += 1
                    self.generic_visit(node)

                def visit_ListComp(self, node: ast.ListComp):
                    self.allocations += 1
                    self.generic_visit(node)

            visitor = LoopVisitor()
            visitor.visit(tree)

            # Algorithmic complexity evaluation
            if "while left <= right" in source_code or "// 2" in source_code:
                time_comp = "O(log N)"
                analysis_parts.append(
                    "Binary search pattern detected with logarithmic divide-and-conquer."
                )
            elif visitor.has_recursion:
                time_comp = "O(2^N)" if "fib" in source_code.lower() else "O(N)"
                space_comp = "O(N)"
                analysis_parts.append(
                    "Recursive call detected; call stack depth scales with input size."
                )
            elif visitor.max_depth >= 2:
                time_comp = f"O(N^{visitor.max_depth})"
                analysis_parts.append(
                    f"Nested loops detected with depth {visitor.max_depth}, "
                    "yielding polynomial time complexity."
                )
            elif visitor.max_depth == 1:
                time_comp = "O(N)"
                analysis_parts.append("Single iterative traversal over the input elements.")
            else:
                time_comp = "O(1)"
                analysis_parts.append("Constant time execution with no loops or recursive calls.")

            if visitor.allocations > 0:
                space_comp = "O(N)"
                analysis_parts.append(
                    "Auxiliary data structures (list/set/dict) dynamically allocated."
                )
            else:
                space_comp = "O(1)"
                analysis_parts.append("In-place operations with O(1) auxiliary memory.")

            # Identify missing edge cases
            if "if not " not in source_code and "len(" in source_code:
                edge_cases.append(
                    "Empty collection handling (e.g. empty list or string `[]`, `\"\"`)"
                )
            if "None" not in source_code:
                edge_cases.append("Null / None type input validation")
            if "/" in source_code or "//" in source_code:
                if "== 0" not in source_code:
                    edge_cases.append("ZeroDivisionError prevention for divisor = 0")
            if "< 0" not in source_code and "> 0" not in source_code:
                edge_cases.append("Negative numeric input boundaries")

            # Suggestions
            if visitor.max_depth >= 2:
                improvements.append(
                    "Utilize a hash set or dictionary to reduce O(N^2) complexity to O(N)."
                )
            improvements.append("Add explicit type hints (PEP 484) to improve contract clarity.")
            if not edge_cases:
                edge_cases.append("Very large input datasets leading to memory or timeout limits.")

        except Exception as e:
            analysis_parts.append(f"Static analysis completed with heuristic review ({e}).")

        return LLMCodeReview(
            time_complexity=time_comp,
            space_complexity=space_comp,
            analysis=" ".join(analysis_parts),
            missing_edge_cases=edge_cases,
            suggested_improvements=improvements,
        )


def get_llm_client() -> BaseLLMClient:
    """Factory function providing the appropriate LLM client.

    If LLM_PROVIDER is explicitly set to 'mock', returns MockLLMClient.
    If 'bedrock', attempts to initialize BedrockLLMClient.
    If 'auto', checks for AWS credentials in environment or config. If present,
    initializes BedrockLLMClient; otherwise seamlessly falls back to MockLLMClient.
    """
    mode = settings.LLM_PROVIDER.lower().strip()

    if mode == "mock":
        logger.info("LLM Client: Forced MOCK mode via configuration.")
        return MockLLMClient()

    if mode == "bedrock":
        logger.info("LLM Client: BEDROCK mode requested.")
        return BedrockLLMClient()

    # 'auto' mode: check whether AWS credentials are available
    has_env_credentials = bool(
        os.getenv("AWS_ACCESS_KEY_ID")
        or os.getenv("AWS_PROFILE")
        or settings.AWS_ACCESS_KEY_ID
    )

    if has_env_credentials:
        try:
            import boto3
            session = boto3.Session()
            creds = session.get_credentials()
            if creds:
                logger.info(
                    "LLM Client: AWS credentials detected. Initializing AWS Bedrock client."
                )
                return BedrockLLMClient()
        except Exception as err:
            logger.warning(
                f"LLM Client: AWS credential lookup encountered '{err}'. "
                "Falling back to MockLLMClient."
            )

    logger.info(
        "LLM Client: No AWS credentials detected. Running in zero-cost MockLLMClient mode."
    )
    return MockLLMClient()
