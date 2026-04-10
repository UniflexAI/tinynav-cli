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

## Planned `tinynav map` command spec

The `tinynav map` workflow is planned around three runtime states inferred directly from `ros2 node list`.
No separate state file is used.

### Map states

- `idle`
  - default state when neither recording nor map building is active
- `recording`
  - detected when `ros2 node list` contains `/rosbag2_recorder`
- `building`
  - detected when `ros2 node list` contains `/build_map_node`

State priority:

1. `/build_map_node` → `building`
2. `/rosbag2_recorder` → `recording`
3. otherwise → `idle`

### Planned commands

- `tinynav map status`
  - reports one of `idle`, `recording`, or `building`
- `tinynav map start_record`
  - allowed only in `idle`
  - starts the recording workflow
- `tinynav map stop_record`
  - allowed only in `recording`
  - stops the recording workflow
- `tinynav map list`
  - allowed only in `idle`
  - lists built maps under the maps directory
- `tinynav map build --rosbag-name <rosbag_name>`
  - allowed only in `idle`
  - builds a map from a named rosbag

### Planned data layout

All map-related outputs live under the TinyNav XDG data directory:

- rosbags: `${XDG_DATA_HOME:-$HOME/.local/share}/tinynav/rosbags/`
- maps: `${XDG_DATA_HOME:-$HOME/.local/share}/tinynav/maps/`

The intent is:

- recording outputs go under `rosbags/`
- map build outputs go under `maps/`
- `map build` consumes a rosbag name from `rosbags/` and produces a map directory in `maps/`
