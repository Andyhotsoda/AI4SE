# Coding Agent Harness

A Python-based Coding Agent Harness that wraps an LLM into a reliable, governed coding agent. Built as an **AI4SE Final Project (Type A: Coding Agent Harness)**.

**Core principle:** Agent = LLM + Harness. The LLM only decides what to do next; the harness provides all the engineering to make it reliable, safe, and self-correcting.

## Architecture

The harness implements six dimensions, with **Governance** as the main contribution:

| Dimension | Module | Description |
|-----------|--------|-------------|
| **Decision** | `harness/core/` | Agent main loop: context → LLM → parse → dispatch → feedback → stop |
| **Tools** | `harness/tools/` | File I/O, shell execution, tool registry |
| **Governance ★** | `harness/governance/` | DangerClassifier → PolicyEngine → HITL → ScopeFence → Sandbox → ActionInterceptor |
| **Feedback** | `harness/feedback/` | Test runner, failure classifier, feedback injector |
| **Memory** | `harness/memory/` | Session history, project conventions, cross-session persistence |
| **Config** | `harness/config/` | YAML config, Pydantic schema, secure credential storage |

## Key Design Principles

- **All mechanisms are CODE, not prompts.** Every mechanism is deterministic and testable with a mock LLM.
- **Mock LLM for testing.** All 150 core tests run without network or real LLM.
- **Governance as a pipeline.** Five independently testable subsystems that compose into a single interceptor.
- **HITL as a state machine.** Pure function `(State, Event) → State`, fully deterministic and testable.

## Quick Start

### Prerequisites
- Python 3.11+
- pip

### Install
```bash
git clone <repo-url>
cd coding-agent-harness
pip install -e ".[dev]"
```

### Run Tests (no network, no API key needed)
```bash
make test
# or
python -m pytest tests/ -v
```

### Run Mechanism Demos (no API key needed)
```bash
make demo
# or individually:
python demos/demo_guardrail_intercept.py
python demos/demo_feedback_self_correction.py
python demos/demo_deep_governance.py
```

### CLI Commands
```bash
# Setup API key (stored in system keyring)
harness setup-key

# Check key status (does not reveal full key)
harness key-status

# Delete stored key
harness delete-key

# Run a single task
harness run -t "Write a Python function to calculate fibonacci numbers"

# Interactive session
harness interactive

# Start WebUI
harness web

# Run demos
harness demo

# Run tests
harness test
```

## API Key Setup

The harness uses the system keyring for secure credential storage (Windows Credential Manager / macOS Keychain / Linux Secret Service). In Docker or headless environments where keyring is unavailable, it automatically falls back to the `DEEPSEEK_API_KEY` environment variable.

**Three-layer priority:**
1. Explicit `api_key` parameter
2. System keyring (`harness setup-key`)
3. Environment variable (`DEEPSEEK_API_KEY` or `ANTHROPIC_API_KEY`)

## Docker

```bash
# Build
docker build -t coding-agent-harness .

# Run tests (no API key needed)
docker run --rm coding-agent-harness python -m pytest tests/ -v

# Run demos (no API key needed)
docker run --rm coding-agent-harness python demos/demo_guardrail_intercept.py

# Run WebUI with DeepSeek API key
docker run --rm -p 8000:8000 \
  -e DEEPSEEK_API_KEY=sk-your-key-here \
  -v $(pwd):/workspace \
  coding-agent-harness

# Or using an .env file
docker run --rm -p 8000:8000 \
  --env-file .env \
  -v $(pwd):/workspace \
  coding-agent-harness
```

> **Note:** Docker containers don't have a system keyring backend. Pass your API key via the `DEEPSEEK_API_KEY` environment variable. The harness will automatically fall back to environment variables when keyring is unavailable.

## Configuration

The harness can be configured via:
1. `harness.yaml` in the project root
2. Environment variables (prefixed with `HARNESS_`)
3. CLI arguments

See `harness/config/defaults.yaml` for all options.

### Governance Policies

Three preset policies are available:
- **default** (recommended): CRITICAL → DENY, DANGEROUS → ASK, SAFE/WARNING → ALLOW
- **strict**: CRITICAL → DENY, DANGEROUS/WARNING → ASK, SAFE → ALLOW
- **permissive**: CRITICAL → DENY, everything else → ALLOW

Custom policies can be defined in YAML files. See `harness/governance/policies/`.

## Project Structure

```
coding-agent-harness/
├── harness/                          # Core source code
│   ├── core/                         # Agent main loop, context builder, action parser, stop decision
│   ├── llm/                          # LLM abstraction (base, mock, deepseek, anthropic)
│   ├── tools/                        # Tool system (file, shell, registry)
│   ├── governance/                   # ★ MAIN CONTRIBUTION: guardrail system
│   │   └── policies/                 # Default and strict policy files
│   ├── feedback/                     # Test runner, failure classifier, feedback injector
│   ├── memory/                       # Session and project memory
│   └── config/                       # Config schema, loader, secrets
├── cli/                              # CLI entry point
├── tests/                            # Unit and integration tests
│   ├── unit/governance/              # Governance tests (largest test suite)
│   └── integration/                  # Full loop + mechanism demo tests
├── demos/                            # Mechanism demonstration scripts
├── webui.py                          # FastAPI + SSE WebUI server
├── Dockerfile                        # Docker distribution
├── SPEC.md                           # Design document
├── PLAN.md                           # Implementation plan
├── SPEC_PROCESS.md                   # Process documentation
├── REFLECTION.md                     # Reflection report
├── README.md                         # This file
├── Makefile                          # Build and test commands
├── pyproject.toml                    # Package configuration
└── .github/workflows/ci.yml          # CI configuration
```

## Safety

- API keys are NEVER hardcoded, committed to git, or logged
- All dangerous actions are intercepted by the governance guardrail BEFORE execution
- Scope fence prevents operations outside allowed directories
- Sandbox isolates warning-level operations
- `.env`, `.pem`, `.key`, `credentials`, `.git/` files are automatically denied

## CI/CD

GitHub Actions runs `make test` on every push, plus Docker build. See `.github/workflows/ci.yml`.

## Known Limitations

- Docker sandboxing requires Docker daemon (falls back to subprocess)
- Real LLM integration requires DeepSeek or Anthropic API key
- Keyring backend may not be available in Docker/CI environments (falls back to env vars)
- WebUI auto-approves HITL requests (in production, HITL requires console interaction)

## Deliverables

This project includes all required deliverables for the AI4SE Final Project:

| # | Deliverable | File |
|---|-------------|------|
| 1 | Design Document | `SPEC.md` |
| 2 | Implementation Plan | `PLAN.md` |
| 3 | Process Documentation | `SPEC_PROCESS.md` |
| 4 | Source Code | `harness/`, `cli/`, `webui.py` |
| 5 | Tests (150 passing) | `tests/` |
| 6 | Mechanism Demos | `demos/` |
| 7 | Docker Distribution | `Dockerfile` |
| 8 | CI Configuration | `.github/workflows/ci.yml` |
| 9 | Reflection Report | `REFLECTION.md` |
| 10 | README | `README.md` |

## License

MIT