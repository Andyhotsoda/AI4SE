.PHONY: test test-real test-cov demo install clean lint

# Run all tests with mock LLM (no network required)
test:
	python -m pytest tests/ -v

# Run tests with coverage
test-cov:
	python -m pytest tests/ -v --cov=harness --cov-report=term-missing

# Run real LLM integration tests (requires ANTHROPIC_API_KEY)
test-real:
	python -m pytest tests/integration/ -v -m "real_llm"

# Run mechanism demonstrations
demo:
	python demos/demo_guardrail_intercept.py
	python demos/demo_feedback_self_correction.py
	python demos/demo_deep_governance.py

# Install the package in development mode
install:
	pip install -e ".[dev]"

# Clean build artifacts
clean:
	rm -rf build/ dist/ *.egg-info/ .pytest_cache/ __pycache__/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true

# Lint
lint:
	python -m flake8 harness/ cli/ --max-line-length=100 || true