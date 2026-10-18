.PHONY: check lint format-check typecheck test

check: lint format-check typecheck test

lint:
	ruff check .

format-check:
	ruff format --check .

typecheck:
	mypy

test:
	pytest
