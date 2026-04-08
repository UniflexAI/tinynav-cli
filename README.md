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
tinynav sensors
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
- `tinynav sensors` checks connected sensors inside the running container, including RealSense detection and whether a ROS 2 `looper` node is present.
- `tinynav sensors --preview` launches the sensor preview workflow inside the running container via `/tinynav/scripts/run_sensors_preview.sh`.
- `tinynav version` prints the CLI version.
