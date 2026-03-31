from __future__ import annotations

import grp
import os
import platform
import shutil
import subprocess
from dataclasses import dataclass
from typing import Union

import tyro
from typing_extensions import Annotated

from .version import __version__

DEFAULT_IMAGE = "uniflexai/tinynav:latest"


@dataclass
class InitCommand:
    """Initialize the local TinyNav CLI workspace."""

    docker_image: str = DEFAULT_IMAGE
    skip_docker_pull: bool = False
    yes: bool = False


@dataclass
class DoctorCommand:
    """Inspect the local environment and report common setup issues."""


@dataclass
class NavCommand:
    """Run a navigation task."""


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
Map = Annotated[MapCommand, tyro.conf.subcommand(name="map")]
Command = Union[Init, Doctor, Nav, Map]


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

    current_user = __import__("getpass").getuser()
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
    if not __import__("sys").stdin.isatty():
        print(f"Docker image {image} is not present locally. Re-run with --yes to download it automatically.")
        return False
    answer = input(f"Docker image {image} is not present locally. Download it now? [y/N]: ").strip().lower()
    return answer in {"y", "yes"}


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


def run_init(command: InitCommand) -> int:
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
    results.append(_check_docker_access())
    if all(result.ok for result in results):
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

    failures = 0
    for result in results:
        _print_result(result)
        if not result.ok:
            failures += 1

    if failures > 0:
        print(f"\ninit failed: {failures} prerequisite check(s) failed.")
        return 1

    if command.skip_docker_pull:
        print("⏭️  Skipping docker pull as requested.")
        return 0

    if _docker_image_exists(command.docker_image):
        print(f"✅ Docker image already present: {command.docker_image}")
        return 0

    if not _confirm_pull(command.docker_image, command.yes):
        print("⏭️  Docker pull skipped.")
        return 0

    pull_result = _docker_pull(command.docker_image)
    _print_result(pull_result)
    return 0 if pull_result.ok else 1


def run(command: Command) -> int:
    match command:
        case InitCommand():
            return run_init(command)
        case DoctorCommand():
            print("tinynav doctor: not implemented yet")
        case NavCommand():
            print("tinynav nav: not implemented yet")
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
