# tinynav-cli

A lightweight command-line interface for TinyNav.

## Install

```bash
pip install tinynav-cli
```

## Commands

```bash
tinynav init
tinynav doctor
tinynav nav
tinynav map build
tinynav map list
tinynav version
```

## Development

```bash
uv sync --dev
uv run tinynav --help
uv run python -m build
uv run twine check dist/*
```
