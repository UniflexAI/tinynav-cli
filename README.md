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
tinynav tunnel --serial <serial>
tinynav nav status
tinynav nav start --map-name <map_name>
tinynav nav go [--pois 2,1,0]
tinynav nav stop
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
- `tinynav tunnel --serial <serial>` requests a tunnel config from the Uniflex tunnel API and saves it to `${XDG_DATA_HOME:-$HOME/.local/share}/tinynav/tunnel.json`.
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


## `tinynav nav` commands

The `tinynav nav` workflow is managed inside a tmux session in the running container.
The CLI currently uses the session name `tinynav_nav`.

### Nav states

- `idle`
  - no navigation tmux session exists
- `starting`
  - tmux session exists but required ROS nodes are not all visible yet
- `running`
  - required ROS nodes are all present

Required ROS nodes:

- `/perception_node`
- `/planning_node`
- `/map_node`
- `/cmd_vel_control_node`

### Commands

- `tinynav nav status`
  - reports one of `idle`, `starting`, or `running`
- `tinynav nav start --map-name <map_name>`
  - allowed only in `idle`
  - starts navigation panes in a tmux session inside the container
  - passes the selected map path to `map_node.py`
- `tinynav nav go [--pois 2,1,0]`
  - uses the map name recorded by the running nav tmux session
  - loads `maps/<map_name>/pois.json`
  - if `--pois` is provided, reorders the outer keys to match the requested POI id sequence
  - keeps each POI object's inner `id` unchanged
  - publishes the payload to `/mapping/cmd_pois` as `std_msgs/String`
- `tinynav nav stop`
  - stops the tmux-managed navigation workflow inside the container
