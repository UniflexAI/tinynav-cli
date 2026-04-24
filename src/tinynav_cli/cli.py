from __future__ import annotations

import getpass
import grp
import json
import os
import platform
import random
import shlex
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Union

import tyro
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from typing_extensions import Annotated

from .version import __version__

DEFAULT_IMAGE = "uniflexai/tinynav:latest"
CN_MIRROR_IMAGE = "5c7c62600f1f8ae01acce9399f1f59ba.d.1ms.run/uniflexai/tinynav:latest"
CN_HF_ENDPOINT = "https://hf-mirror.com"
CN_PIP_INDEX_URL = "https://mirrors.aliyun.com/pypi/simple/"
CN_PIP_TRUSTED_HOST = "mirrors.aliyun.com"
DEFAULT_CONTAINER_NAME = "tinynav_cli"
CONTAINER_WORKSPACE_DIR = "/root/.local/share/tinynav"
CONTAINER_WORKDIR = "/tinynav"
MAP_RECORD_SESSION = "tinynav_map_record"
MAP_BUILD_SESSION = "tinynav_map_build"
MAP_EDIT_POIS_SESSION = "tinynav_map_edit_pois"
NAV_SESSION = "tinynav_nav"
TUNNEL_API_URL = "https://calqyoxlwnfdkfjuapej.supabase.co/functions/v1/clever-action"
TUNNEL_API_AUTH = (
    "Bearer "
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImNhbHF5b3hsd25m"
    "ZGtmanVhcGVqIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzcwMjgwNjgsImV4cCI6MjA5MjYwNDA2OH0."
    "SA7ME0H5xbipC-Vx-rbexSSmLXOyTHLqCdqVYxR7hy0"
)


def _default_workspace_dir() -> str:
    data_home = Path(os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share")))
    return str(data_home / "tinynav")


@dataclass
class InitCommand:
    """Initialize the local TinyNav CLI workspace."""

    docker_image: str = DEFAULT_IMAGE
    container_name: str = DEFAULT_CONTAINER_NAME
    workspace_dir: str = field(default_factory=_default_workspace_dir)
    skip_docker_pull: bool = False
    yes: bool = False
    ros_domain_id: int | None = None
    cn_mode: bool = False


@dataclass
class DoctorCommand:
    """Inspect the local environment and report common setup issues."""

    verbose: bool = False


@dataclass
class NavStatusCommand:
    """Show the current navigation workflow status."""

    container_name: str = DEFAULT_CONTAINER_NAME


@dataclass
class NavStartCommand:
    """Start the navigation workflow."""

    map_name: Annotated[str, tyro.conf.arg(name="map-name")]
    container_name: str = DEFAULT_CONTAINER_NAME


@dataclass
class NavGoCommand:
    """Publish POIs for navigation."""

    pois: str | None = None
    container_name: str = DEFAULT_CONTAINER_NAME


@dataclass
class ExampleCommand:
    """Run the rosbag example workflow inside the tinynav container."""

    container_name: str = DEFAULT_CONTAINER_NAME


@dataclass
class TunnelCommand:
    """Create a TinyNav tunnel config and save it locally."""

    serial: str


@dataclass
class VersionCommand:
    """Print the tinynav CLI version."""


@dataclass
class MapStatusCommand:
    """Show the current map workflow status."""

    container_name: str = DEFAULT_CONTAINER_NAME


@dataclass
class MapStartRecordCommand:
    """Start map recording."""

    container_name: str = DEFAULT_CONTAINER_NAME


@dataclass
class MapStopRecordCommand:
    """Stop map recording."""

    container_name: str = DEFAULT_CONTAINER_NAME


@dataclass
class MapBuildCommand:
    """Build a map from a recorded rosbag."""

    rosbag_name: Annotated[str, tyro.conf.arg(name="rosbag-name")]
    container_name: str = DEFAULT_CONTAINER_NAME


@dataclass
class MapEditPoisCommand:
    """Edit POIs for an existing map."""

    map_name: Annotated[str, tyro.conf.arg(name="map-name")]
    container_name: str = DEFAULT_CONTAINER_NAME


@dataclass
class MapListCommand:
    """List known maps."""

    container_name: str = DEFAULT_CONTAINER_NAME


@dataclass
class SensorsCommand:
    """Inspect connected sensors and optionally preview them."""

    container_name: str = DEFAULT_CONTAINER_NAME
    preview: bool = False


MapStatus = Annotated[MapStatusCommand, tyro.conf.subcommand(name="status")]
MapStartRecord = Annotated[MapStartRecordCommand, tyro.conf.subcommand(name="start_record")]
MapStopRecord = Annotated[MapStopRecordCommand, tyro.conf.subcommand(name="stop_record")]
MapBuild = Annotated[MapBuildCommand, tyro.conf.subcommand(name="build")]
MapEditPois = Annotated[MapEditPoisCommand, tyro.conf.subcommand(name="edit_pois")]
MapList = Annotated[MapListCommand, tyro.conf.subcommand(name="list")]
MapCommand = Union[MapStatus, MapStartRecord, MapStopRecord, MapBuild, MapEditPois, MapList]

@dataclass
class NavStopCommand:
    """Stop the navigation workflow."""

    container_name: str = DEFAULT_CONTAINER_NAME


NavStatus = Annotated[NavStatusCommand, tyro.conf.subcommand(name="status")]
NavStart = Annotated[NavStartCommand, tyro.conf.subcommand(name="start")]
NavGo = Annotated[NavGoCommand, tyro.conf.subcommand(name="go")]
NavStop = Annotated[NavStopCommand, tyro.conf.subcommand(name="stop")]
NavCommand = Union[NavStatus, NavStart, NavGo, NavStop]

Init = Annotated[InitCommand, tyro.conf.subcommand(name="init")]
Doctor = Annotated[DoctorCommand, tyro.conf.subcommand(name="doctor")]
Nav = Annotated[NavCommand, tyro.conf.subcommand(name="nav")]
Example = Annotated[ExampleCommand, tyro.conf.subcommand(name="example")]
Tunnel = Annotated[TunnelCommand, tyro.conf.subcommand(name="tunnel")]
Version = Annotated[VersionCommand, tyro.conf.subcommand(name="version")]
Map = Annotated[MapCommand, tyro.conf.subcommand(name="map")]
Sensors = Annotated[SensorsCommand, tyro.conf.subcommand(name="sensors")]
Command = Union[Init, Doctor, Nav, Example, Tunnel, Version, Map, Sensors]


@dataclass
class CheckResult:
    name: str
    ok: bool
    message: str
    hint: str | None = None


def _run(command: list[str], timeout: float | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, check=False, timeout=timeout)


def _run_streaming(command: list[str]) -> int:
    completed = subprocess.run(command, check=False)
    return completed.returncode


def _read_text_file(path: str) -> str | None:
    file_path = Path(path)
    if not file_path.exists():
        return None
    return file_path.read_text().strip()


def _command_output(command: list[str]) -> str:
    result = _run(command)
    if result.returncode != 0:
        return result.stderr.strip() or result.stdout.strip() or "command failed"
    return result.stdout.strip()


def _check_docker_installed() -> CheckResult:
    if shutil.which("docker") is None:
        return CheckResult(
            name="docker",
            ok=False,
            message="Docker is not installed.",
            hint="Install it with: sudo apt-get update && sudo apt-get install -y docker.io",
        )
    return CheckResult(name="docker", ok=True, message="Docker is installed.")


def _check_docker_group() -> CheckResult:
    try:
        docker_group = grp.getgrnam("docker")
    except KeyError:
        return CheckResult(
            name="docker-group",
            ok=False,
            message="docker group does not exist on this machine.",
            hint="Create or reinstall Docker so the docker group is available.",
        )

    current_user = getpass.getuser()
    current_gid = os.getgid()
    if current_gid == docker_group.gr_gid or current_user in docker_group.gr_mem:
        return CheckResult(name="docker-group", ok=True, message="Current user is in the docker group.")

    return CheckResult(
        name="docker-group",
        ok=False,
        message="Current user is not in the docker group.",
        hint=f"Run: sudo usermod -aG docker {current_user} && newgrp docker",
    )


def _check_docker_access() -> CheckResult:
    result = _run(["docker", "info"])
    if result.returncode != 0:
        return CheckResult(
            name="docker-daemon",
            ok=False,
            message="Docker is not running or not accessible.",
            hint="Try: sudo systemctl start docker; also ensure your user is in the docker group.",
        )
    return CheckResult(name="docker-daemon", ok=True, message="Docker daemon is running and accessible.")


def _check_nvidia_runtime() -> CheckResult:
    result = _run(["docker", "info"])
    if result.returncode != 0:
        return CheckResult(
            name="docker-nvidia-runtime",
            ok=False,
            message="Cannot inspect Docker runtimes because docker info failed.",
        )
    combined = f"{result.stdout}\n{result.stderr}"
    if "nvidia" not in combined.lower():
        return CheckResult(
            name="docker-nvidia-runtime",
            ok=False,
            message="NVIDIA runtime is not available in Docker.",
            hint="Install with: sudo apt-get install -y nvidia-container-toolkit && sudo nvidia-ctk runtime configure --runtime=docker && sudo systemctl restart docker",
        )
    return CheckResult(name="docker-nvidia-runtime", ok=True, message="NVIDIA runtime is available in Docker.")


def _check_git_lfs() -> CheckResult:
    if shutil.which("git-lfs") is None:
        return CheckResult(
            name="git-lfs",
            ok=False,
            message="git-lfs is not installed.",
            hint="Install it with: sudo apt-get update && sudo apt-get install -y git-lfs && git lfs install",
        )
    return CheckResult(name="git-lfs", ok=True, message="git-lfs is installed.")


def _check_architecture() -> CheckResult:
    arch = platform.machine().lower()
    if arch in {"aarch64", "arm64"} or arch.startswith("arm"):
        return CheckResult(name="architecture", ok=True, message="ARM platform detected.")
    return CheckResult(name="architecture", ok=True, message=f"{platform.machine()} platform detected.")


def _collect_prerequisite_results() -> list[CheckResult]:
    docker_installed = _check_docker_installed()
    results = [docker_installed]
    if docker_installed.ok:
        results.append(_check_docker_group())
    else:
        results.append(
            CheckResult(
                name="docker-group",
                ok=False,
                message="Skipped docker group check because Docker is not installed.",
            )
        )

    docker_access = _check_docker_access()
    results.append(docker_access)
    if docker_access.ok:
        results.append(_check_nvidia_runtime())
    else:
        results.append(
            CheckResult(
                name="docker-nvidia-runtime",
                ok=False,
                message="Skipped NVIDIA runtime check because Docker is not ready.",
            )
        )

    results.extend([
        _check_git_lfs(),
        _check_architecture(),
    ])
    return results


def _print_result(result: CheckResult) -> None:
    prefix = "✅" if result.ok else "❌"
    print(f"{prefix} {result.message}")
    if result.hint is not None:
        print(f"   👉 {result.hint}")


def _docker_image_exists(image: str) -> bool:
    result = _run(["docker", "image", "inspect", image])
    return result.returncode == 0


def _confirm_pull(image: str, assume_yes: bool) -> bool:
    if assume_yes:
        return True
    if not sys.stdin.isatty():
        print(f"Docker image {image} is not present locally. Re-run with --yes to download it automatically.")
        return False
    answer = input(f"Docker image {image} is not present locally. Download it now? [y/N]: ").strip().lower()
    return answer in {"y", "yes"}


def _choose_ros_domain_id(current_value: int | None) -> int | None:
    if current_value is not None:
        return current_value
    if not sys.stdin.isatty():
        return None
    answer = input("Do you want to specify ROS_DOMAIN_ID? [y/N]: ").strip().lower()
    if answer not in {"y", "yes"}:
        return None
    default_value = random.randint(1, 101)
    raw = input(f"ROS_DOMAIN_ID [{default_value}]: ").strip()
    if raw == "":
        return default_value
    try:
        value = int(raw)
    except ValueError as exc:
        raise SystemExit(f"Invalid ROS_DOMAIN_ID: {raw}") from exc
    if not (0 <= value <= 232):
        raise SystemExit("ROS_DOMAIN_ID must be between 0 and 232.")
    return value


def _confirm_cn_mirror() -> bool:
    if not sys.stdin.isatty():
        return False
    answer = input("Use the CN mirror (docker.1ms.run) and CN-optimized environment settings? [y/N]: ").strip().lower()
    return answer in {"y", "yes"}


def _pull_image_with_optional_cn_mirror(image: str, use_cn_mirror: bool) -> CheckResult:
    source_image = CN_MIRROR_IMAGE if use_cn_mirror else image
    pull_result = _docker_pull(source_image)
    if not pull_result.ok:
        return pull_result
    if use_cn_mirror:
        tag_result = _run(["docker", "tag", source_image, image])
        if tag_result.returncode != 0:
            detail = tag_result.stderr.strip() or tag_result.stdout.strip() or "docker tag failed"
            return CheckResult(
                name="docker-tag",
                ok=False,
                message=f"Failed to tag {source_image} as {image}.",
                hint=detail,
            )
        return CheckResult(name="docker-pull", ok=True, message=f"Docker image ready via CN mirror: {image}")
    return pull_result


def _docker_pull(image: str) -> CheckResult:
    print(f"Pulling Docker image: {image}")
    returncode = _run_streaming(["docker", "pull", image])
    if returncode != 0:
        return CheckResult(
            name="docker-pull",
            ok=False,
            message=f"Failed to pull Docker image {image}.",
            hint="docker pull returned a non-zero exit code.",
        )
    return CheckResult(name="docker-pull", ok=True, message=f"Docker image ready: {image}")


def _gpu_probe_command(args: list[str]) -> list[str]:
    return [
        "docker",
        "run",
        "--rm",
        "--network",
        "host",
        *args,
        "--entrypoint",
        "sh",
        DEFAULT_IMAGE,
        "-lc",
        "exit 0",
    ]


def _detect_gpu_run_args() -> tuple[list[str], str | None]:
    candidates = [
        (["--device", "nvidia.com/gpu=all"], "cdi"),
        (["--gpus", "all"], "gpus"),
        (["--runtime", "nvidia"], "runtime"),
    ]
    for args, name in candidates:
        result = _run(_gpu_probe_command(args))
        if result.returncode == 0:
            return args, name
    return [], None


def _workspace_mount_arg(workspace_dir: str) -> list[str]:
    return ["-v", f"{Path(workspace_dir).expanduser()}:{CONTAINER_WORKSPACE_DIR}"]


def _ensure_workspace_dir(workspace_dir: str) -> None:
    Path(workspace_dir).expanduser().mkdir(parents=True, exist_ok=True)


def _container_exists(name: str) -> bool:
    result = _run(["docker", "ps", "-a", "--filter", f"name=^{name}$", "--format", "{{.Names}}"])
    return result.returncode == 0 and any(line.strip() == name for line in result.stdout.splitlines())


def _remove_container(name: str) -> CheckResult:
    result = _run(["docker", "rm", "-f", name])
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "docker rm failed"
        return CheckResult(
            name="docker-rm",
            ok=False,
            message=f"Failed to remove existing container {name}.",
            hint=detail,
        )
    return CheckResult(name="docker-rm", ok=True, message=f"Removed existing container {name}.")


def _cn_env_args(enabled: bool) -> list[str]:
    if not enabled:
        return []
    return [
        "-e", f"HF_ENDPOINT={CN_HF_ENDPOINT}",
        "-e", f"PIP_INDEX_URL={CN_PIP_INDEX_URL}",
        "-e", f"PIP_TRUSTED_HOST={CN_PIP_TRUSTED_HOST}",
    ]


def _docker_run(command: InitCommand) -> CheckResult:
    if _container_exists(command.container_name):
        remove_result = _remove_container(command.container_name)
        _print_result(remove_result)
        if not remove_result.ok:
            return remove_result

    gpu_args, gpu_mode = _detect_gpu_run_args()
    if gpu_mode is None:
        return CheckResult(
            name="docker-gpu",
            ok=False,
            message="Failed to determine a working Docker GPU mode.",
            hint="Tried CDI (--device nvidia.com/gpu=all), --gpus all, and --runtime nvidia.",
        )

    print(f"Using GPU mode: {gpu_mode}")

    docker_command = [
        "docker",
        "run",
        "-d",
        "--name",
        command.container_name,
        *gpu_args,
        "--privileged",
        "--network",
        "host",
        "-v",
        "/tmp/.X11-unix:/tmp/.X11-unix",
        "-v",
        "/dev:/dev",
        "-v",
        "/etc/localtime:/etc/localtime",
        "--device-cgroup-rule=c 81:* rwm",
        "--device-cgroup-rule=c 234:* rwm",
        "--shm-size=16gb",
        *_workspace_mount_arg(command.workspace_dir),
        "-e",
        f"DISPLAY={os.environ.get('DISPLAY', ':0')}",
        "-e",
        "GDK_SCALE=2",
        *([] if command.ros_domain_id is None else ["-e", f"ROS_DOMAIN_ID={command.ros_domain_id}"]),
        *_cn_env_args(command.cn_mode),
        "-w",
        CONTAINER_WORKDIR,
        "--entrypoint",
        "",
        command.docker_image,
        "tail",
        "-f",
        "/dev/null",
    ]
    result = _run(docker_command)
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "docker run failed"
        return CheckResult(
            name="docker-run",
            ok=False,
            message=f"Failed to start container {command.container_name}.",
            hint=detail,
        )
    container_id = result.stdout.strip().splitlines()[0] if result.stdout.strip() else command.container_name
    return CheckResult(name="docker-run", ok=True, message=f"Container {command.container_name} started ({container_id[:12]}).")


def _build_models(command: InitCommand) -> CheckResult:
    print("Building TensorRT models inside the container...")
    process = subprocess.Popen(
        [
            "docker",
            "exec",
            command.container_name,
            "bash",
            "-lc",
            "cd /tinynav/tinynav/models && make all",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    lines = deque(maxlen=12)
    with Live(refresh_per_second=8, transient=True) as live:
        assert process.stdout is not None
        for line in process.stdout:
            lines.append(line.rstrip())
            rendered = "\n".join(lines) if lines else "Waiting for build output..."
            live.update(Panel(Text(rendered), title="make all (latest output)"))
    returncode = process.wait()
    if returncode != 0:
        detail = "\n".join(lines) if lines else "model build failed"
        return CheckResult(
            name="model-build",
            ok=False,
            message="Failed to build TensorRT models inside the container.",
            hint=detail,
        )
    return CheckResult(name="model-build", ok=True, message="TensorRT models built successfully.")


def _container_running(name: str) -> bool:
    result = _run(["docker", "ps", "--filter", f"name=^{name}$", "--format", "{{.Names}}"])
    return result.returncode == 0 and any(line.strip() == name for line in result.stdout.splitlines())


def _ensure_example_container_running(name: str) -> CheckResult:
    if _container_running(name):
        return CheckResult(name="example-container", ok=True, message=f"Container {name} is already running.")

    if _container_exists(name):
        result = _run(["docker", "start", name])
        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip() or "docker start failed"
            return CheckResult(
                name="example-container",
                ok=False,
                message=f"Failed to start existing container {name}.",
                hint=detail,
            )
        return CheckResult(name="example-container", ok=True, message=f"Started existing container {name}.")

    return CheckResult(
        name="example-container",
        ok=False,
        message=f"Container {name} does not exist.",
        hint="Run `tinynav init` first.",
    )


def _docker_info_text() -> str:
    result = _run(["docker", "info"])
    if result.returncode != 0:
        return result.stderr.strip() or result.stdout.strip() or "docker info failed"
    return result.stdout.strip()


def run_init(command: InitCommand) -> int:
    results = _collect_prerequisite_results()

    failures = 0
    for result in results:
        _print_result(result)
        if not result.ok:
            failures += 1

    if failures > 0:
        print(f"\ninit failed: {failures} prerequisite check(s) failed.")
        return 1

    _ensure_workspace_dir(command.workspace_dir)
    command.ros_domain_id = _choose_ros_domain_id(command.ros_domain_id)
    if command.ros_domain_id is None:
        print("ROS_DOMAIN_ID not specified; container will use its default behavior.")
    else:
        print(f"Using ROS_DOMAIN_ID={command.ros_domain_id}")

    if command.skip_docker_pull:
        print("⏭️  Skipping docker pull as requested.")
        return 0

    if _docker_image_exists(command.docker_image):
        print(f"ℹ️  Docker image already present locally: {command.docker_image}")
        if not command.yes and not _confirm_pull(command.docker_image, True):
            print("⏭️  Docker pull skipped.")
            return 0
    else:
        if not _confirm_pull(command.docker_image, command.yes):
            print("⏭️  Docker pull skipped.")
            return 0

    use_cn_mirror = _confirm_cn_mirror()
    command.cn_mode = use_cn_mirror
    pull_result = _pull_image_with_optional_cn_mirror(command.docker_image, use_cn_mirror)
    _print_result(pull_result)
    if not pull_result.ok:
        return 1

    run_result = _docker_run(command)
    _print_result(run_result)
    if not run_result.ok:
        return 1

    build_result = _build_models(command)
    _print_result(build_result)
    if not build_result.ok:
        return 1

    print("\nNext step: start with `tinynav example`.")
    return 0


def _run_xhost_local() -> CheckResult:
    if shutil.which("xhost") is None:
        return CheckResult(
            name="xhost",
            ok=False,
            message="xhost is not installed.",
            hint="Install x11-xserver-utils or run the command manually before tinynav example.",
        )
    result = _run(["xhost", "+local:*"])
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "xhost failed"
        return CheckResult(
            name="xhost",
            ok=False,
            message="Failed to run xhost +local:*.",
            hint=detail,
        )
    return CheckResult(name="xhost", ok=True, message="Enabled local X11 access with xhost +local:*.")


def _container_running(name: str) -> bool:
    result = _run(["docker", "ps", "--filter", f"name=^{name}$", "--format", "{{.Names}}"])
    return result.returncode == 0 and any(line.strip() == name for line in result.stdout.splitlines())


def _ensure_example_container_running(name: str) -> CheckResult:
    if _container_running(name):
        return CheckResult(name="example-container", ok=True, message=f"Container {name} is already running.")

    if _container_exists(name):
        result = _run(["docker", "start", name])
        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip() or "docker start failed"
            return CheckResult(
                name="example-container",
                ok=False,
                message=f"Failed to start existing container {name}.",
                hint=detail,
            )
        return CheckResult(name="example-container", ok=True, message=f"Started existing container {name}.")

    return CheckResult(
        name="example-container",
        ok=False,
        message=f"Container {name} does not exist.",
        hint="Run `tinynav init` first.",
    )


def _docker_exec_output(container_name: str, shell_command: str) -> subprocess.CompletedProcess[str]:
    return _run([
        "docker",
        "exec",
        container_name,
        "bash",
        "-lc",
        shell_command,
    ])


def _list_realsense_sensor(container_name: str) -> CheckResult:
    result = _docker_exec_output(container_name, "rs-enumerate-devices -s")
    output = (result.stdout or "") + (result.stderr or "")
    if result.returncode != 0:
        detail = output.strip() or "rs-enumerate-devices failed"
        return CheckResult(
            name="realsense",
            ok=False,
            message="Failed to inspect RealSense devices.",
            hint=detail,
        )
    if "No device detected. Is it plugged in?" in output:
        return CheckResult(name="realsense", ok=False, message="RealSense sensor not detected.")

    lines = [line.rstrip() for line in output.splitlines() if line.strip()]
    data_lines = [line for line in lines if not line.lstrip().startswith(tuple(str(i).zfill(2) for i in range(13))) and "ERROR" not in line and not line.startswith("Device Name")]
    device_line = next((line for line in data_lines if "Intel RealSense" in line), None)
    message = "RealSense sensor detected."
    if device_line is not None:
        message = f"RealSense sensor detected: {device_line.strip()}"
    return CheckResult(name="realsense", ok=True, message=message)


def _list_looper_sensor(container_name: str) -> CheckResult:
    result = _docker_exec_output(container_name, "source /opt/ros/*/setup.bash >/dev/null 2>&1 && ros2 node list")
    output = ((result.stdout or "") + (result.stderr or "")).strip()
    if result.returncode != 0:
        return CheckResult(
            name="looper",
            ok=False,
            message="Failed to inspect ROS 2 nodes for looper.",
            hint=output or "ros2 node list failed",
        )
    nodes = [line.strip() for line in output.splitlines() if line.strip()]
    if "/insight_full" in nodes:
        return CheckResult(name="looper", ok=True, message="Looper sensor detected (/insight_full node found).")
    return CheckResult(name="looper", ok=False, message="Looper sensor not detected (/insight_full node not found).")


def _ensure_runtime_container(name: str) -> bool:
    ensure_result = _ensure_example_container_running(name)
    _print_result(ensure_result)
    return ensure_result.ok


def _ros2_node_names(container_name: str) -> list[str]:
    result = _docker_exec_output(container_name, "source /opt/ros/*/setup.bash >/dev/null 2>&1 && ros2 node list")
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


NAV_REQUIRED_NODES = {
    "/perception_node": "perception_node.py",
    "/planning_node": "planning_node.py",
    "/map_node": "map_node.py",
    "/cmd_vel_control_node": "cmd_vel_control.py",
}


def _tmux_session_exists(container_name: str, session_name: str) -> bool:
    result = _docker_exec_output(container_name, f"tmux has-session -t {session_name}")
    return result.returncode == 0


def _nav_status(container_name: str) -> tuple[str, list[str]]:
    if not _tmux_session_exists(container_name, NAV_SESSION):
        return "idle", []
    nodes = set(_ros2_node_names(container_name))
    missing = [node for node in NAV_REQUIRED_NODES if node not in nodes]
    if missing:
        return "starting", missing
    return "running", []


def _nav_map_name(container_name: str) -> str | None:
    result = _docker_exec_output(container_name, f"tmux show-environment -t {NAV_SESSION} TINYNAV_MAP_NAME")
    if result.returncode != 0:
        return None
    line = (result.stdout or "").strip()
    prefix = "TINYNAV_MAP_NAME="
    if not line.startswith(prefix):
        return None
    return line[len(prefix):]


def _map_status(container_name: str) -> str:
    nodes = _ros2_node_names(container_name)
    if "/build_map_node" in nodes:
        return "building"
    if "/rosbag2_recorder" in nodes:
        return "recording"
    return "idle"


def _map_build_percent(container_name: str) -> float | None:
    try:
        result = _run([
            "docker",
            "exec",
            container_name,
            "bash",
            "-lc",
            "source /opt/ros/*/setup.bash >/dev/null 2>&1 && ros2 topic echo --once /mapping/percent",
        ], timeout=3.0)
    except subprocess.TimeoutExpired:
        return None
    if result.returncode != 0:
        return None
    for line in result.stdout.splitlines():
        stripped = line.strip()
        if stripped.startswith("data:"):
            try:
                return float(stripped.split(":", 1)[1].strip())
            except ValueError:
                return None
    return None


def _workspace_data_dir() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))) / "tinynav"


def _maps_dir() -> Path:
    return _workspace_data_dir() / "maps"


def _rosbags_dir() -> Path:
    return _workspace_data_dir() / "rosbags"


def _container_maps_dir() -> Path:
    return Path(CONTAINER_WORKSPACE_DIR) / "maps"


def _parse_poi_selection(pois: str) -> list[str]:
    values = [value.strip() for value in pois.split(",") if value.strip()]
    if not values:
        raise ValueError("--pois must be a comma-separated list like 2,1,0")
    return values


def _selected_cmd_pois(map_path: Path, pois: str | None) -> dict[str, object]:
    pois_path = map_path / "pois.json"
    if not pois_path.exists():
        raise FileNotFoundError(f"POI file not found: {pois_path}")
    with pois_path.open() as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("pois.json must be a JSON object")
    if pois is None:
        return data
    selected = {}
    for index, poi_key in enumerate(_parse_poi_selection(pois)):
        if poi_key not in data:
            raise KeyError(f"POI {poi_key} not found in {pois_path}")
        selected[str(index)] = data[poi_key]
    return selected


def _container_rosbags_dir() -> Path:
    return Path(CONTAINER_WORKSPACE_DIR) / "rosbags"


def _tunnel_json_path() -> Path:
    return _workspace_data_dir() / "tunnel.json"


def _request_tunnel(serial: str) -> dict[str, object]:
    payload = json.dumps({"serial": serial}).encode("utf-8")
    request = urllib.request.Request(
        TUNNEL_API_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": TUNNEL_API_AUTH,
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30.0) as response:
        body = response.read().decode("utf-8")
    data = json.loads(body)
    if not isinstance(data, dict):
        raise ValueError("tunnel API response must be a JSON object")
    return data


def _format_size(num_bytes: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(num_bytes)
    for unit in units:
        if size < 1024.0 or unit == units[-1]:
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024.0


def _directory_size(path: Path) -> int:
    total = 0
    for file_path in path.rglob("*"):
        if file_path.is_file():
            total += file_path.stat().st_size
    return total


def _poi_count(map_path: Path) -> int:
    pois_path = map_path / "pois.json"
    if not pois_path.exists():
        return 0
    with pois_path.open() as f:
        data = json.load(f)
    if isinstance(data, dict):
        return len(data)
    if isinstance(data, list):
        return len(data)
    return 0


def _ensure_map_state(name: str, allowed: set[str]) -> str | None:
    state = _map_status(name)
    if state not in allowed:
        allowed_text = ", ".join(sorted(allowed))
        print(f"❌ map command is only allowed in state: {allowed_text}")
        print(f"   👉 current state: {state}")
        return None
    return state


def run_version(command: VersionCommand) -> int:
    print(f"tinynav {__version__}")
    return 0


def run_nav_status(command: NavStatusCommand) -> int:
    if not _ensure_runtime_container(command.container_name):
        return 1
    status, missing = _nav_status(command.container_name)
    print(f"tinynav nav status: {status}")
    if missing:
        print(f"   👉 missing nodes: {', '.join(missing)}")
    return 0


def run_nav_start(command: NavStartCommand) -> int:
    if not _ensure_runtime_container(command.container_name):
        return 1
    status, _ = _nav_status(command.container_name)
    if status != "idle":
        print(f"❌ nav start is only allowed in idle state")
        print(f"   👉 current state: {status}")
        return 1
    container_map_path = _container_maps_dir() / command.map_name
    result = _docker_exec_output(
        command.container_name,
        " && ".join([
            f"test -d {container_map_path}",
            f"tmux kill-session -t {NAV_SESSION} >/dev/null 2>&1 || true",
            f"tmux new-session -d -s {NAV_SESSION}",
            f"tmux set-environment -t {NAV_SESSION} TINYNAV_MAP_NAME {command.map_name}",
            f"tmux split-window -t {NAV_SESSION} -h",
            f"tmux split-window -t {NAV_SESSION}:0.0 -v",
            f"tmux split-window -t {NAV_SESSION}:0.1 -v",
            f"tmux send-keys -t {NAV_SESSION}:0.0 'source /opt/ros/*/setup.bash >/dev/null 2>&1 && uv run python /tinynav/tinynav/core/perception_node.py' C-m",
            f"tmux send-keys -t {NAV_SESSION}:0.1 'source /opt/ros/*/setup.bash >/dev/null 2>&1 && uv run python /tinynav/tinynav/core/planning_node.py' C-m",
            f"tmux send-keys -t {NAV_SESSION}:0.2 'source /opt/ros/*/setup.bash >/dev/null 2>&1 && uv run python /tinynav/tinynav/platforms/cmd_vel_control.py' C-m",
            f"tmux send-keys -t {NAV_SESSION}:0.3 'source /opt/ros/*/setup.bash >/dev/null 2>&1 && uv run python /tinynav/tinynav/core/map_node.py --tinynav_map_path {container_map_path}' C-m",
        ]),
    )
    if result.returncode != 0:
        print("❌ Failed to start navigation inside the container.")
        if result.stderr or result.stdout:
            print(f"   👉 {(result.stderr or result.stdout).strip()}")
        return 1
    print(f"✅ Started navigation inside container {command.container_name}.")
    print(f"   👉 tmux session: {NAV_SESSION}")
    print(f"   👉 map: {command.map_name}")
    return 0


def run_nav_go(command: NavGoCommand) -> int:
    if not _ensure_runtime_container(command.container_name):
        return 1
    status, _ = _nav_status(command.container_name)
    if status != "running":
        print("❌ nav go is only allowed in running state")
        print(f"   👉 current state: {status}")
        return 1
    map_name = _nav_map_name(command.container_name)
    if map_name is None:
        print("❌ Failed to resolve map name from the running nav session.")
        return 1
    map_path = _maps_dir() / map_name
    try:
        payload = _selected_cmd_pois(map_path, command.pois)
    except (FileNotFoundError, ValueError, KeyError) as exc:
        print("❌ Failed to prepare navigation POIs.")
        print(f"   👉 {exc}")
        return 1
    payload_json = json.dumps(payload, separators=(",", ":"))
    ros_msg_yaml = json.dumps({"data": payload_json}, separators=(",", ":"))
    msg_arg = shlex.quote(ros_msg_yaml)
    result = _docker_exec_output(
        command.container_name,
        "source /opt/ros/*/setup.bash >/dev/null 2>&1 && "
        f"ros2 topic pub --once /mapping/cmd_pois std_msgs/msg/String {msg_arg}",
    )
    if result.returncode != 0:
        print("❌ Failed to publish navigation POIs inside the container.")
        if result.stderr or result.stdout:
            print(f"   👉 {(result.stderr or result.stdout).strip()}")
        return 1
    print(f"✅ Published navigation POIs inside container {command.container_name}.")
    print(f"   👉 map: {map_name}")
    if command.pois is None:
        print("   👉 pois: all")
    else:
        print(f"   👉 pois: {command.pois}")
    return 0


def run_nav_stop(command: NavStopCommand) -> int:
    if not _ensure_runtime_container(command.container_name):
        return 1
    if not _tmux_session_exists(command.container_name, NAV_SESSION):
        print("✅ Navigation is not running.")
        return 0
    for pane in ("0.0", "0.1", "0.2", "0.3"):
        _docker_exec_output(command.container_name, f"tmux send-keys -t {NAV_SESSION}:{pane} C-c")
    time.sleep(1.0)
    result = _docker_exec_output(command.container_name, f"tmux kill-session -t {NAV_SESSION}")
    if result.returncode != 0:
        print("❌ Failed to stop navigation inside the container.")
        if result.stderr or result.stdout:
            print(f"   👉 {(result.stderr or result.stdout).strip()}")
        return 1
    print(f"✅ Stopped navigation inside container {command.container_name}.")
    return 0


def run_map_status(command: MapStatusCommand) -> int:
    if not _ensure_runtime_container(command.container_name):
        return 1
    status = _map_status(command.container_name)
    if status != "building":
        print(f"tinynav map status: {status}")
        return 0
    percent = _map_build_percent(command.container_name)
    if percent is None:
        print(f"tinynav map status: {status}")
        return 0
    print(f"tinynav map status: {status} ({percent:.2f}%)")
    return 0


def run_map_start_record(command: MapStartRecordCommand) -> int:
    if not _ensure_runtime_container(command.container_name):
        return 1
    if _ensure_map_state(command.container_name, {"idle"}) is None:
        return 1
    result = _docker_exec_output(
        command.container_name,
        " && ".join([
            f"tmux kill-session -t {MAP_RECORD_SESSION} >/dev/null 2>&1 || true",
            f"tmux new-session -d -s {MAP_RECORD_SESSION}",
            f"tmux split-window -t {MAP_RECORD_SESSION} -v",
            f"tmux send-keys -t {MAP_RECORD_SESSION}:0.0 'bash /tinynav/scripts/run_realsense_sensor.sh' C-m",
            f"tmux send-keys -t {MAP_RECORD_SESSION}:0.1 'bash /tinynav/scripts/run_rosbag_record.sh' C-m",
        ]),
    )
    if result.returncode != 0:
        print("❌ Failed to start map recording inside the container.")
        if result.stderr or result.stdout:
            print(f"   👉 {(result.stderr or result.stdout).strip()}")
        return 1
    print(f"✅ Started map recording inside container {command.container_name}.")
    print(f"   👉 tmux session: {MAP_RECORD_SESSION}")
    return 0


def run_map_stop_record(command: MapStopRecordCommand) -> int:
    if not _ensure_runtime_container(command.container_name):
        return 1
    if _ensure_map_state(command.container_name, {"recording"}) is None:
        return 1

    _docker_exec_output(command.container_name, f"tmux send-keys -t {MAP_RECORD_SESSION}:0.0 C-c")
    _docker_exec_output(command.container_name, f"tmux send-keys -t {MAP_RECORD_SESSION}:0.1 C-c")
    for _ in range(60):
        if _map_status(command.container_name) != "recording":
            _docker_exec_output(command.container_name, f"tmux kill-session -t {MAP_RECORD_SESSION}")
            print(f"✅ Stopped map recording inside container {command.container_name}.")
            return 0
        time.sleep(0.5)
    print("❌ Recorder is still running after stop request.")
    print("   👉 ros2 node list still contains /rosbag2_recorder")
    return 1


def run_map_build(command: MapBuildCommand) -> int:
    if not _ensure_runtime_container(command.container_name):
        return 1
    if _ensure_map_state(command.container_name, {"idle"}) is None:
        return 1
    rosbag_path = _rosbags_dir() / command.rosbag_name
    if not rosbag_path.exists():
        print(f"❌ rosbag not found: {rosbag_path}")
        return 1

    maps_dir = _maps_dir()
    maps_dir.mkdir(parents=True, exist_ok=True)
    map_output = maps_dir / command.rosbag_name
    container_rosbag_path = _container_rosbags_dir() / command.rosbag_name
    container_map_output = _container_maps_dir() / command.rosbag_name
    result = _docker_exec_output(
        command.container_name,
        " && ".join([
            f"tmux kill-session -t {MAP_BUILD_SESSION} >/dev/null 2>&1 || true",
            f"tmux new-session -d -s {MAP_BUILD_SESSION}",
            f"tmux split-window -t {MAP_BUILD_SESSION} -h",
            f"tmux send-keys -t {MAP_BUILD_SESSION}:0.0 'source /opt/ros/*/setup.bash >/dev/null 2>&1 && uv run python /tinynav/tinynav/core/perception_node.py' C-m",
            f"tmux send-keys -t {MAP_BUILD_SESSION}:0.1 'source /opt/ros/*/setup.bash >/dev/null 2>&1 && uv run python /tinynav/tinynav/core/build_map_node.py --map_save_path {container_map_output} --bag_file {container_rosbag_path}' C-m",
        ]),
    )
    if result.returncode != 0:
        print("❌ Failed to start map building inside the container.")
        if result.stderr or result.stdout:
            print(f"   👉 {(result.stderr or result.stdout).strip()}")
        return 1
    print(f"✅ Started map build from rosbag {command.rosbag_name}.")
    print(f"   👉 output directory: {map_output}")
    print(f"   👉 tmux session: {MAP_BUILD_SESSION}")
    return 0


def run_map_edit_pois(command: MapEditPoisCommand) -> int:
    if not _ensure_runtime_container(command.container_name):
        return 1
    if _ensure_map_state(command.container_name, {"idle"}) is None:
        return 1

    map_path = _maps_dir() / command.map_name
    if not map_path.exists():
        print(f"❌ map not found: {map_path}")
        return 1

    container_map_path = _container_maps_dir() / command.map_name
    xhost_result = _run_xhost_local()
    _print_result(xhost_result)
    if not xhost_result.ok:
        return 1

    result = _docker_exec_output(
        command.container_name,
        " && ".join([
            f"tmux kill-session -t {MAP_EDIT_POIS_SESSION} >/dev/null 2>&1 || true",
            f"tmux new-session -d -s {MAP_EDIT_POIS_SESSION}",
            f"tmux send-keys -t {MAP_EDIT_POIS_SESSION}:0.0 'source /opt/ros/*/setup.bash >/dev/null 2>&1 && uv run python /tinynav/tool/poi_editor.py --tinynav-map-path {container_map_path}' C-m",
        ]),
    )
    if result.returncode != 0:
        print("❌ Failed to start POI editor inside the container.")
        if result.stderr or result.stdout:
            print(f"   👉 {(result.stderr or result.stdout).strip()}")
        return 1
    editor_url = "http://localhost:8080/"
    opener = shutil.which("xdg-open")
    if opener is not None:
        subprocess.Popen([opener, editor_url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    print(f"✅ Started POI editor for map {command.map_name}.")
    print(f"   👉 map directory: {map_path}")
    print(f"   👉 tmux session: {MAP_EDIT_POIS_SESSION}")
    print(f"   👉 open in browser: {editor_url}")
    return 0


def run_map_list(command: MapListCommand) -> int:
    if not _ensure_runtime_container(command.container_name):
        return 1
    if _ensure_map_state(command.container_name, {"idle"}) is None:
        return 1

    rosbags_dir = _rosbags_dir()
    maps_dir = _maps_dir()
    if not rosbags_dir.exists():
        print("tinynav maps\n============\n(no rosbags found)")
        return 0

    rosbags = sorted(path for path in rosbags_dir.iterdir() if path.is_dir())
    if not rosbags:
        print("tinynav maps\n============\n(no rosbags found)")
        return 0

    table = Table(title="tinynav maps")
    table.add_column("name", style="cyan")
    table.add_column("size", justify="right")
    table.add_column("built", justify="center")
    table.add_column("pois", justify="right")

    for rosbag_path in rosbags:
        size_text = _format_size(_directory_size(rosbag_path))
        map_path = maps_dir / rosbag_path.name
        built = "[green]yes[/green]" if map_path.is_dir() else "[dim]no[/dim]"
        pois_text = str(_poi_count(map_path)) if map_path.is_dir() else "0"
        table.add_row(rosbag_path.name, size_text, built, pois_text)

    Console().print(table)
    return 0


def run_sensors(command: SensorsCommand) -> int:
    if not _ensure_runtime_container(command.container_name):
        return 1

    if command.preview:
        xhost_result = _run_xhost_local()
        _print_result(xhost_result)
        if not xhost_result.ok:
            return 1

        result = subprocess.run(
            [
                "docker",
                "exec",
                "-it",
                command.container_name,
                "bash",
                "-lc",
                "bash /tinynav/scripts/run_sensors_preview.sh",
            ],
            check=False,
        )
        if result.returncode != 0:
            print("❌ Failed to launch tinynav sensor preview inside the container.")
            print(f"   👉 Make sure the container {command.container_name} is running and initialized.")
            return 1

        print(f"✅ Started sensor preview inside container {command.container_name}.")
        return 0

    results = [
        _list_realsense_sensor(command.container_name),
        _list_looper_sensor(command.container_name),
    ]
    print("tinynav sensors")
    print("===============")
    for result in results:
        _print_result(result)
    return 0


def run_example(command: ExampleCommand) -> int:
    ensure_result = _ensure_example_container_running(command.container_name)
    _print_result(ensure_result)
    if not ensure_result.ok:
        return 1

    xhost_result = _run_xhost_local()
    _print_result(xhost_result)
    if not xhost_result.ok:
        return 1

    result = subprocess.run(
        [
            "docker",
            "exec",
            "-it",
            command.container_name,
            "bash",
            "-lc",
            "bash /tinynav/scripts/run_rosbag_examples.sh",
        ],
        check=False,
    )
    if result.returncode != 0:
        print("❌ Failed to launch tinynav example workflow inside the container.")
        print(f"   👉 Make sure the container {command.container_name} is running and initialized.")
        return 1

    print(f"✅ Started rosbag example workflow inside container {command.container_name}.")
    return 0


def run_tunnel(command: TunnelCommand) -> int:
    tunnel_path = _tunnel_json_path()
    tunnel_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        data = _request_tunnel(command.serial)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError) as exc:
        print("❌ Failed to create TinyNav tunnel config.")
        print(f"   👉 {exc}")
        return 1

    tunnel_path.write_text(json.dumps(data, indent=2) + "\n")
    print(f"✅ Saved TinyNav tunnel config for serial {command.serial}.")
    print(f"   👉 file: {tunnel_path}")
    if isinstance(data.get("hostname"), str):
        print(f"   👉 hostname: {data['hostname']}")
    if isinstance(data.get("ssh_command"), str):
        print(f"   👉 ssh: {data['ssh_command']}")
    return 0


def run_doctor(command: DoctorCommand) -> int:
    results = _collect_prerequisite_results()
    failures = sum(1 for result in results if not result.ok)

    print("tinynav doctor report")
    print("====================")
    print(f"tinynav_cli version: {__version__}")
    print(f"python version: {platform.python_version()}")
    uv_version = shutil.which("uv")
    print(f"uv: {_command_output(['uv', '--version']) if uv_version else 'not found'}")
    print(f"architecture: {platform.machine()}")
    print()
    print("checks:")
    for result in results:
        status = "PASS" if result.ok else "FAIL"
        print(f"- [{status}] {result.name}: {result.message}")
        if result.hint is not None:
            print(f"    hint: {result.hint}")

    print()
    print("/etc/lsb-release:")
    print("-----------------")
    lsb_release = _read_text_file('/etc/lsb-release')
    print(lsb_release if lsb_release is not None else 'not found')

    print()
    print("/etc/nv_tegra_release:")
    print("----------------------")
    nv_tegra_release = _read_text_file('/etc/nv_tegra_release')
    print(nv_tegra_release if nv_tegra_release is not None else 'not found')

    print()
    print("docker info:")
    print("------------")
    docker_info = _docker_info_text()
    if command.verbose:
        print(docker_info)
    else:
        lines = docker_info.splitlines()
        for line in lines[:20]:
            print(line)
        if len(lines) > 20:
            print("... (use --verbose for full docker info)")

    print()
    print(f"summary: {len(results) - failures} passed, {failures} failed")
    return 0 if failures == 0 else 1


def run(command: Command) -> int:
    match command:
        case InitCommand():
            return run_init(command)
        case DoctorCommand():
            return run_doctor(command)
        case NavStatusCommand():
            return run_nav_status(command)
        case NavStartCommand():
            return run_nav_start(command)
        case NavGoCommand():
            return run_nav_go(command)
        case NavStopCommand():
            return run_nav_stop(command)
        case ExampleCommand():
            return run_example(command)
        case TunnelCommand():
            return run_tunnel(command)
        case VersionCommand():
            return run_version(command)
        case MapStatusCommand():
            return run_map_status(command)
        case MapStartRecordCommand():
            return run_map_start_record(command)
        case MapStopRecordCommand():
            return run_map_stop_record(command)
        case MapBuildCommand():
            return run_map_build(command)
        case MapEditPoisCommand():
            return run_map_edit_pois(command)
        case MapListCommand():
            return run_map_list(command)
        case SensorsCommand():
            return run_sensors(command)
        case _:
            raise AssertionError(f"unsupported command: {command!r}")
    return 0


def main() -> None:
    command = tyro.cli(Command, description=f"tinynav CLI v{__version__}")
    raise SystemExit(run(command))
