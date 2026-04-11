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
tinynav map status
tinynav map start_record
tinynav map stop_record
tinynav map build --rosbag-name <rosbag_name>
tinynav map edit_pois --map-name <map_name>
tinynav map list
tinynav sensors
tinynav sensors --preview
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

## `tinynav map` commands

The `tinynav map` workflow uses three runtime states inferred directly from `ros2 node list`.
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

### Commands

- `tinynav map status`
  - reports one of `idle`, `recording`, or `building`
- `tinynav map start_record`
  - allowed only in `idle`
  - starts the recording workflow in a tmux session inside the container
- `tinynav map stop_record`
  - allowed only in `recording`
  - stops the recording workflow
- `tinynav map list`
  - allowed only in `idle`
  - lists rosbags in a formatted table with size, built status, and POI count
- `tinynav map build --rosbag-name <rosbag_name>`
  - allowed only in `idle`
  - starts the map build workflow in a tmux session inside the container
- `tinynav map edit_pois --map-name <map_name>`
  - allowed only in `idle`
  - starts the POI editor for an existing map in a tmux session inside the container
  - opens `http://localhost:8080/` in the default browser when possible
  - reads and writes `pois.json` under the selected map directory

### Planned data layout

All map-related outputs live under the TinyNav XDG data directory:

- rosbags: `${XDG_DATA_HOME:-$HOME/.local/share}/tinynav/rosbags/`
- maps: `${XDG_DATA_HOME:-$HOME/.local/share}/tinynav/maps/`

The intent is:

- recording outputs go under `rosbags/`
- map build outputs go under `maps/`
- `map build` consumes a rosbag name from `rosbags/` and produces a map directory in `maps/`
