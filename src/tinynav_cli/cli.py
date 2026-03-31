from __future__ import annotations

import getpass
import grp
import os
import platform
import random
import shutil
import subprocess
import sys
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Union

import tyro
from rich.live import Live
from rich.panel import Panel
from rich.text import Text
from typing_extensions import Annotated

from .version import __version__

DEFAULT_IMAGE = "uniflexai/tinynav:latest"
CN_MIRROR_IMAGE = "docker.1ms.run/uniflexai/tinynav:latest"
CN_HF_ENDPOINT = "https://hf-mirror.com"
CN_PIP_INDEX_URL = "https://mirrors.aliyun.com/pypi/simple/"
CN_PIP_TRUSTED_HOST = "mirrors.aliyun.com"
DEFAULT_CONTAINER_NAME = "tinynav_cli"


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
class NavCommand:
    """Run a navigation task."""


@dataclass
class ExampleCommand:
    """Run the rosbag example workflow inside the tinynav container."""

    container_name: str = DEFAULT_CONTAINER_NAME


@dataclass
class VersionCommand:
    """Print the tinynav CLI version."""


@dataclass
class MapBuildCommand:
    """Build a map."""


@dataclass
class MapListCommand:
    """List known maps."""


MapBuild = Annotated[MapBuildCommand, tyro.conf.subcommand(name="build")]
MapList = Annotated[MapListCommand, tyro.conf.subcommand(name="list")]
MapCommand = Union[MapBuild, MapList]

Init = Annotated[InitCommand, tyro.conf.subcommand(name="init")]
Doctor = Annotated[DoctorCommand, tyro.conf.subcommand(name="doctor")]
Nav = Annotated[NavCommand, tyro.conf.subcommand(name="nav")]
Example = Annotated[ExampleCommand, tyro.conf.subcommand(name="example")]
Version = Annotated[VersionCommand, tyro.conf.subcommand(name="version")]
Map = Annotated[MapCommand, tyro.conf.subcommand(name="map")]
Command = Union[Init, Doctor, Nav, Example, Version, Map]


@dataclass
class CheckResult:
    name: str
    ok: bool
    message: str
    hint: str | None = None


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, check=False)


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


def _choose_ros_domain_id(current_value: int | None) -> int:
    if current_value is not None:
        return current_value
    default_value = random.randint(1, 101)
    if not sys.stdin.isatty():
        return default_value
    print("If you do not care about ROS_DOMAIN_ID, just press Enter to use the suggested random value.")
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
    return ["-v", f"{Path(workspace_dir).expanduser()}:{workspace_dir}"]


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
        "-e",
        f"ROS_DOMAIN_ID={command.ros_domain_id}",
        *_cn_env_args(command.cn_mode),
        "-w",
        command.workspace_dir,
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


def run_version(command: VersionCommand) -> int:
    print(f"tinynav {__version__}")
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
        case NavCommand():
            print("tinynav nav: not implemented yet")
        case ExampleCommand():
            return run_example(command)
        case VersionCommand():
            return run_version(command)
        case MapBuildCommand():
            print("tinynav map build: not implemented yet")
        case MapListCommand():
            print("tinynav map list: not implemented yet")
        case _:
            raise AssertionError(f"unsupported command: {command!r}")
    return 0


def main() -> None:
    command = tyro.cli(Command, description=f"tinynav CLI v{__version__}")
    raise SystemExit(run(command))
