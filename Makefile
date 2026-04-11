.PHONY: check test lint fmt fix install clean gui api dev

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

# Start FastAPI backend (port 7474)
api:
	PYTHONPATH=$(shell pwd) uvicorn reassure.api.server:app --reload --port 7474

# Start TSX GUI dev server (port 5173, proxies /api → 7474)
gui:
	cd gui && npm run dev

# Start both in parallel (requires a terminal that supports it)
dev:
	make api & make gui

install:
	poetry install --no-interaction
	cd gui && npm install

clean:
	rm -rf .venv __pycache__ .pytest_cache .ruff_cache .mypy_cache coverage.xml .coverage
	cd gui && rm -rf dist node_modules
