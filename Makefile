.PHONY: check test lint fmt fix install clean gui

# Run everything — same as CI. Do this before pushing.
check: lint test

test:
	python3 -m pytest tests/ -q

lint:
	python3 -m ruff check reassure/ cli.py
	python3 -m ruff format --check reassure/ cli.py

# Auto-fix then check
fix:
	python3 -m ruff check --fix reassure/ cli.py
	python3 -m ruff format reassure/ cli.py

gui:
	PYTHONPATH=$(shell pwd) streamlit run reassure/gui/app.py

install:
	poetry install --no-interaction

clean:
	rm -rf .venv __pycache__ .pytest_cache .ruff_cache .mypy_cache coverage.xml .coverage
