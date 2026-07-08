# Coding Agent Harness

A Python-based Coding Agent Harness that wraps an LLM into a reliable, governed coding agent. Built as an AI4SE final project.

**Core principle:** Agent = LLM + Harness. The LLM only decides what to do next; the harness provides all the engineering to make it reliable, safe, and self-correcting.

## Architecture

The harness implements six dimensions:

| Dimension | Description |
|-----------|-------------|
| **Decision** | Agent main loop: context → LLM → parse → dispatch → feedback → stop |
| **Tools** | File I/O, shell execution, test running |
| **Memory** | Session history, project conventions, cross-session persistence |
| **Governance** ★ | Danger classification, HITL state machine, scope fence, sandbox, policy engine |
| **Feedback** | Test runner, result parser, failure classifier, feedback injection |
| **Config** | YAML config, Pydantic schema, secure credential storage |

★ **Main contribution**: The governance/guardrail system is the deepest dimension, with a full pipeline of DangerClassifier → PolicyEngine → HITL StateMachine → ScopeFence → Sandbox.

## Key Design Decisions

- **All mechanisms are CODE, not prompts.** Every mechanism is deterministic and testable with a mock LLM.
- **Mock LLM for testing.** All core mechanisms have unit tests that run without network or real LLM.
- **Governance as a pipeline.** Five independently testable subsystems that compose into a single interceptor.
- **HITL as a state machine.** Pure function (state, event) → state, fully deterministic and testable.

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

### Run Tests
```bash
# All unit tests (no network, no LLM required)
make test

# With coverage
make test-cov
```

### Run Mechanism Demos
```bash
make demo
# Or individually:
python demos/demo_guardrail_intercept.py
python demos/demo_feedback_self_correction.py
python demos/demo_deep_governance.py
```

### CLI
```bash
# Setup API key securely
harness setup-key

# Check key status
harness key-status

# Run mechanism demos
harness demo

# Run tests
harness test
```

## API Key Setup

The harness uses the system keyring for secure credential storage:
- **Windows**: Credential Manager
- **macOS**: Keychain
- **Linux**: Secret Service / KWallet

Run `harness setup-key` to securely store your Anthropic API key.

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

> **Note:** Docker containers don't have a system keyring backend. Pass your API key via the `DEEPSEEK_API_KEY` environment variable (or `ANTHROPIC_API_KEY` for Anthropic). The harness will automatically fall back to environment variables when keyring is unavailable.

## Configuration

The harness can be configured via:
1. `harness.yaml` in the project root
2. Environment variables (prefixed with `HARNESS_`)
3. CLI arguments

See `harness/config/defaults.yaml` for all options.

## Project Structure

```
coding-agent-harness/
├── harness/                  # Core source code
│   ├── core/                 # Agent main loop, context builder, action parser
│   ├── llm/                  # LLM abstraction (base, mock, anthropic)
│   ├── tools/                # Tool system (file, shell, registry)
│   ├── governance/           # ★ MAIN CONTRIBUTION: guardrail system
│   │   ├── policies/         # Default and strict policy files
│   ├── feedback/             # Test runner, failure classifier, feedback injector
│   ├── memory/               # Session and project memory
│   └── config/               # Config schema, loader, secrets
├── cli/                      # CLI entry point
├── tests/                    # Unit and integration tests
│   ├── unit/governance/      # Governance tests (largest test suite)
│   └── integration/          # Full loop + mechanism demo tests
├── demos/                    # Mechanism demonstration scripts
└── Dockerfile                # Docker distribution
```

## Safety

- API keys are NEVER hardcoded, committed to git, or logged
- All dangerous actions are intercepted by the governance guardrail BEFORE execution
- Scope fence prevents operations outside allowed directories
- Sandbox isolates warning-level operations

## CI/CD

GitHub Actions runs `make test` on every push. See `.github/workflows/ci.yml`.

## Known Limitations

- Docker sandboxing requires Docker daemon (falls back to subprocess)
- Real LLM integration requires Anthropic API key
- Keyring backend may not be available in all Docker/CI environments