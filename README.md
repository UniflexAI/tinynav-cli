# tinynav-cli

A lightweight command-line interface for TinyNav.

## Install

```bash
pip install tinynav
```

## Commands

```bash
tinynav init
tinynav doctor
tinynav example
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

## Typical flow

```bash
tinynav init
tinynav doctor
tinynav example
```

- `tinynav init` prepares the container environment and builds models.
- `tinynav doctor` prints a machine report for debugging.
- `tinynav example` launches the rosbag example workflow inside the running container.
- `tinynav version` prints the CLI version.
