# Contributing

Thanks for your interest in contributing to operation-reassurance!

## Getting started

```bash
git clone https://github.com/avarga1/operation-reassurance
cd operation-reassurance
poetry install
```

## Before submitting a PR

Always run this first:

```bash
make check
```

That runs lint, format check, and the full test suite — same as CI.

If you have formatting issues, `make fix` will auto-correct them.

## What to work on

Check the [open issues](https://github.com/avarga1/operation-reassurance/issues) — anything labeled `good first issue` is a great starting point.

## PR guidelines

- One feature or fix per PR
- Add tests for new behavior
- Update `CHANGELOG.md` under `[Unreleased]`
- Keep commits clean — describe *what* and *why*

## Project structure

```
reassure/
├── core/          # Parser, symbol extraction, repo walking
├── analyzers/     # The five analysis pillars
├── classifiers/   # Test type classification
├── output/        # Terminal renderer, JSON export
└── gui/           # Streamlit dashboard
```

Questions? Open an issue or leave a comment on the relevant issue thread.
