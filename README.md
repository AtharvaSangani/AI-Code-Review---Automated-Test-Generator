# AI Code Review & Automated Test Generator

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110%2B-009688.svg)](https://fastapi.tiangolo.com/)
[![Pydantic v2](https://img.shields.io/badge/Pydantic-v2-E92063.svg)](https://docs.pydantic.dev/latest/)
[![AWS Bedrock](https://img.shields.io/badge/AWS-Bedrock%20SDK-FF9900.svg)](https://aws.amazon.com/bedrock/)
[![Code Style: Flake8](https://img.shields.io/badge/Code%20Style-Flake8-black.svg)](https://flake8.pycqa.org/)
[![Tests](https://img.shields.io/badge/Tests-Pytest%2039%2F39%20Passing-brightgreen.svg)](https://docs.pytest.org/)

> **A Production-Grade Developer Microservice Built for Deterministic AI Code Verification.**
> Designed for an Amazon SDE Portfolio, showcasing how deterministic static inspection and isolated sandbox execution eliminate Large Language Model (LLM) code hallucinations.

---

## 1. Architectural Philosophy: The "Critical AI Verification" Thesis

### The Problem: Probabilistic Hallucination in Mission-Critical Software
Generative AI and Large Language Models (LLMs) are probabilistic token predictors. When developers prompt LLMs to write code or unit tests, models frequently:
1. **Hallucinate APIs and parameters** that do not exist.
2. **Assert false invariants** that cause flaky builds or pass invalid logic.
3. **Attempt dangerous sandbox escapes** (e.g., importing `socket` or invoking `eval()` to execute external commands).

In enterprise engineering organizations like Amazon, shipping hallucinated unit tests breaks CI/CD pipelines, inflates operational burden, and compromises service availability.

### The Solution: Deterministic Dual-Gate Sandbox Verification
This microservice treats LLM output as **untrusted user input**. Generated unit tests must clear two independent deterministic gates before they are returned to the developer:

```
+---------------------------------------------------------------------------------------+
|                                API Request (Code / Diff)                             |
+-------------------------------------------+-------------------------------------------+
                                            |
                                            v
+---------------------------------------------------------------------------------------+
|                            LLM Synthesis Layer (Bedrock / Mock)                       |
+-------------------------------------------+-------------------------------------------+
                                            |
                                            v  (Generated Test Code)
+---------------------------------------------------------------------------------------+
|  GATE 1: Static AST Security Inspection (app/core/security.py)                        |
|  - ast.parse() abstract syntax tree traversal                                         |
|  - Blocks dangerous modules: os, sys, subprocess, socket, shutil, pty, ctypes        |
|  - Blocks dangerous built-ins: eval, exec, open, compile, __import__                  |
|  - Blocks sandbox escape dunder introspection: __subclasses__, __globals__            |
+---------------------+-------------------------------------+---------------------------+
                      | Passes                              | Violates Security Policy
                      v                                     v
+-------------------------------------------+   +---------------------------------------+
|  GATE 2: Isolated Tempfile Pytest Sandbox |   | Verdict: REJECTED_HALLUCINATION       |
|  - tempfile.TemporaryDirectory()          |   | (Immediate 0ms rejection with AST log)|
|  - subprocess.run(["pytest", ...])        |   +---------------------------------------+
|  - Strict 5-second deterministic timeout  |
|  - Isolated PYTHONPATH & execution env    |
+---------------------+---------------------+
                      |
        +-------------+-------------+
        |                           |
        v Exit Code == 0            v Exit Code != 0 or TimeoutExpired
+-----------------------+   +---------------------------------------+
| Verdict:              |   | Verdict: REJECTED_HALLUCINATION       |
| VERIFIED_PASSING      |   | (Extracts failed assertions & traces) |
+-----------------------+   +---------------------------------------+
```

1. **Gate 1 (Static AST Inspection)**: Scans the Abstract Syntax Tree using Python's standard library `ast` module. Disallows network sockets, OS interactions, process spawns, and dynamic execution before a single line of test code touches the CPU.
2. **Gate 2 (Isolated Deterministic Execution)**: Mounts the target function and generated tests in a disposable temporary directory (`tempfile`). Executes `pytest` as an isolated subprocess with a strict 5-second timeout.
3. **Verdict Determination**:
   - `VERIFIED_PASSING`: Pytest exit code is `0`. All assertions executed and passed.
   - `REJECTED_HALLUCINATION`: Pytest exit code is non-zero or timed out. Assertion diagnostics, standard error, and traces are packaged into a structured diagnostic response.

---

## 2. Amazon Leadership Principles (LP) Alignment

This project was engineered to exemplify Amazon's software engineering ethos:

- **Customer Obsession**: Engineers waste hours debugging broken tests created by AI tools. This microservice delivers only verified, guaranteed-to-pass test suites directly into developer workflows.
- **Bias for Action & Frugality**: Features an automatic zero-cost **Mock LLM Mode** that synthesizes realistic tests and AST Big-O analysis offline, allowing any developer to clone and run the repo without AWS billings.
- **Earn Trust & Highest Standards**: Treats all AI-generated code as untrusted. Enforces strict AST safety boundaries and automated verification before returning code artifacts.
- **Deliver Results**: Comprehensive test coverage across 39 automated integration, security, and sandbox runner tests with strict Flake8 PEP 8 compliance.

---

## 3. Technology Stack

- **Language**: Python 3.10+
- **Web Framework**: FastAPI with Starlette ASGI
- **Data Validation & Settings**: Pydantic v2 & `pydantic-settings`
- **AI / LLM SDK**: AWS Bedrock Runtime (`boto3`) with seamless `MockLLMClient` fallback
- **Static Analysis & Linting**: Flake8 and Python standard library `ast`
- **Execution Sandbox**: Subprocess with temporary directory isolation (`tempfile`) and deterministic timeouts
- **Testing**: Pytest & `pytest-asyncio` with `httpx` ASGI client
- **Containerization**: Docker (multi-stage non-root container) & Docker Compose

---

## 4. Project Structure

```
ai-code-verifier/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI application, CORS, and latency telemetry
│   ├── api/
│   │   ├── __init__.py
│   │   └── endpoints.py     # Route handlers (/generate-tests, /review-code, /health)
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py        # Pydantic v2 BaseSettings configuration
│   │   └── security.py      # AST safety inspection & forbidden import checker
│   ├── services/
│   │   ├── __init__.py
│   │   ├── llm_client.py    # AWS Bedrock Claude client + MockLLMClient fallback
│   │   └── sandbox_runner.py # Disposable tempfile & subprocess pytest/flake8 runner
│   └── schemas/
│       ├── __init__.py
│       └── models.py        # Pydantic v2 request/response data contracts
├── tests/
│   ├── __init__.py
│   ├── conftest.py          # Shared pytest fixtures & async client
│   ├── test_api.py          # End-to-end REST API integration tests
│   ├── test_security.py     # AST parser & dangerous import tests
│   └── test_runner.py       # Subprocess pytest runner & Flake8 test cases
├── Dockerfile               # Production non-root container image
├── docker-compose.yml       # Multi-environment orchestrator
├── requirements.txt         # Pinned production dependencies
└── README.md
```

---

## 5. Quickstart & Installation

### Option A: Local Python Environment (Recommended)

1. **Clone the repository:**
   ```bash
   git clone https://github.com/example/ai-code-verifier.git
   cd quick-mendel
   ```

2. **Create and activate a virtual environment:**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Launch the development server:**
   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```

5. **Access interactive documentation:**
   - Swagger UI: [http://localhost:8000/docs](http://localhost:8000/docs)
   - ReDoc: [http://localhost:8000/redoc](http://localhost:8000/redoc)

---

### Option B: Docker & Docker Compose

Run the microservice in an isolated, non-root Linux container:

```bash
# Build and run with Docker Compose
docker compose up --build -d

# Check service health
curl -s http://localhost:8000/health | jq .

# View logs
docker compose logs -f
```

---

## 6. Zero-Cost Mock LLM Mode

By default, if no AWS credentials are configured, the microservice automatically switches to **Mock LLM Mode**:

```json
{
  "status": "healthy",
  "uptime_seconds": 12.4,
  "llm_provider": "mock",
  "version": "1.0.0",
  "environment": "production"
}
```

The `MockLLMClient` uses AST inspection to synthesize realistic, functional unit tests and compute algorithmic Big-O reviews locally.

### Enabling Production AWS Bedrock
To connect to AWS Bedrock with Claude 3.5 Sonnet:

```bash
export LLM_PROVIDER="bedrock"
export AWS_REGION="us-east-1"
export AWS_ACCESS_KEY_ID="your-access-key-id"
export AWS_SECRET_ACCESS_KEY="your-secret-access-key"
export BEDROCK_MODEL_ID="anthropic.claude-3-5-sonnet-20240620-v1:0"
```

---

## 7. API Reference & Sample Requests

### 1. Generate & Verify Unit Tests (`POST /api/v1/generate-tests`)

#### Request: Binary Search
```bash
curl -X POST "http://localhost:8000/api/v1/generate-tests" \
  -H "Content-Type: application/json" \
  -d '{
    "function_name": "binary_search",
    "source_code": "def binary_search(arr, target):\n    left, right = 0, len(arr) - 1\n    while left <= right:\n        mid = (left + right) // 2\n        if arr[mid] == target:\n            return mid\n        elif arr[mid] < target:\n            left = mid + 1\n        else:\n            right = mid - 1\n    return -1",
    "framework": "pytest"
  }' | jq .
```

#### Successful Response (`VERIFIED_PASSING`):
```json
{
  "status": "success",
  "tests_generated": 5,
  "verdict": "VERIFIED_PASSING",
  "test_code": "def test_binary_search_found_middle():\n    arr = [1, 3, 5, 7, 9, 11]\n    assert binary_search(arr, 7) == 3\n...",
  "execution_time_ms": 348.21,
  "stdout": "test_target.py::test_binary_search_found_middle PASSED\ntest_target.py::test_binary_search_found_first PASSED\n...",
  "stderr": "",
  "diagnostics": {
    "details": "All unit tests passed successfully in isolated sandbox."
  }
}
```

---

### 2. Hallucination Detection & Diagnostic Extraction

Submitting code or tests where assertions fail triggers the verification engine to mark the output as a hallucination:

```bash
curl -X POST "http://localhost:8000/api/v1/generate-tests" \
  -H "Content-Type: application/json" \
  -d '{
    "function_name": "compute_total",
    "source_code": "# SIMULATE_HALLUCINATION\ndef compute_total(items):\n    return sum(items)",
    "framework": "pytest"
  }' | jq .
```

#### Response (`REJECTED_HALLUCINATION`):
```json
{
  "status": "failed",
  "tests_generated": 1,
  "verdict": "REJECTED_HALLUCINATION",
  "test_code": "def test_compute_total_hallucinated_assertion():\n    result = compute_total([1, 2, 3])\n    assert result == 'IMPOSSIBLE_HALLUCINATED_VALUE'\n",
  "execution_time_ms": 320.45,
  "stdout": "FAILED test_target.py::test_compute_total_hallucinated_assertion - AssertionError\n...",
  "stderr": "",
  "diagnostics": {
    "failed_test_count": 1,
    "failed_test_names": [
      "test_compute_total_hallucinated_assertion"
    ],
    "assertion_samples": [
      "E   AssertionError: assert 6 == 'IMPOSSIBLE_HALLUCINATED_VALUE'"
    ],
    "hallucination_reason": "One or more generated assertions failed against the implementation logic."
  }
}
```

---

### 3. AST Security Filter Block (Malicious Code Attempt)

Attempting to submit code that accesses system resources (e.g. `socket`, `subprocess`, `os`, `eval`) is stopped by Gate 1:

```bash
curl -i -X POST "http://localhost:8000/api/v1/generate-tests" \
  -H "Content-Type: application/json" \
  -d '{
    "function_name": "steal_data",
    "source_code": "import socket\ndef steal_data():\n    s = socket.socket()\n    s.connect((\"1.2.3.4\", 80))",
    "framework": "pytest"
  }'
```

#### Response (`HTTP 400 Bad Request`):
```json
{
  "detail": {
    "error": "MaliciousSourceCodeDetected",
    "message": "Submitted source code contains prohibited operations or syntax errors.",
    "violations": [
      "Line 1: Prohibited module import 'socket'"
    ]
  }
}
```

---

### 4. Code Review & Complexity Analysis (`POST /api/v1/review-code`)

```bash
curl -X POST "http://localhost:8000/api/v1/review-code" \
  -H "Content-Type: application/json" \
  -d '{
    "source_code": "def find_duplicates(nums):\n    res = []\n    for i in range(len(nums)):\n        for j in range(i+1, len(nums)):\n            if nums[i] == nums[j]:\n                res.append(nums[i])\n    return res\n"
  }' | jq .
```

#### Response:
```json
{
  "status": "success",
  "static_analysis": {
    "linter": "flake8",
    "issue_count": 2,
    "issues": [
      {
        "line": 4,
        "col": 24,
        "code": "E226",
        "message": "missing whitespace around arithmetic operator"
      }
    ],
    "clean": false
  },
  "llm_review": {
    "time_complexity": "O(N^2)",
    "space_complexity": "O(N)",
    "analysis": "Nested loops detected with depth 2, yielding polynomial time complexity. Auxiliary data structures dynamically allocated.",
    "missing_edge_cases": [
      "Empty collection handling (e.g. empty list or string `[]`, `\"\"`)",
      "Null / None type input validation"
    ],
    "suggested_improvements": [
      "Utilize a hash set or dictionary to reduce O(N^2) complexity to O(N).",
      "Add explicit type hints (PEP 484) to improve contract clarity."
    ]
  }
}
```

---

### 5. Health & Telemetry (`GET /health`)

```bash
curl -X GET "http://localhost:8000/health" | jq .
```

---

## 8. Automated Testing & Code Quality

Run the test suite:
```bash
# Run 39 tests with verbose output
pytest tests/ -v

# Run with test coverage
pytest tests/ --cov=app --cov-report=term-missing
```

Run PEP 8 Flake8 compliance:
```bash
flake8 app/ tests/ --max-line-length=100
```

---

## 9. Security & Hardening Highlights

1. **AST Node Traverser**: Rejects unauthorized syntax before code reaches any Python interpreter process.
2. **Subprocess Sandboxing**: Pytest is invoked with an isolated `PYTHONPATH`, stripped environment variables, disabled bytecode caching (`PYTHONDONTWRITEBYTECODE=1`), and a strict wall-clock timeout budget.
3. **Container Isolation**: Multi-stage Docker container runs under an unprivileged `appuser` (UID 10000) with no root privileges.
4. **Latency Telemetry**: Automatic request duration measurement via `X-Process-Time-Ms` response headers.
