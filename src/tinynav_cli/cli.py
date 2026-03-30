from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

import tyro

from .version import __version__


@dataclass
class InitCommand:
    """Initialize the local TinyNav CLI workspace."""


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


MapCommand = Annotated[MapBuildCommand | MapListCommand, tyro.conf.subcommand(name="build") | tyro.conf.subcommand(name="list")]
Command = Annotated[
    InitCommand | DoctorCommand | NavCommand | MapCommand,
    tyro.conf.subcommand(name="init")
    | tyro.conf.subcommand(name="doctor")
    | tyro.conf.subcommand(name="nav")
    | tyro.conf.subcommand(name="map"),
]


def run(command: Command) -> int:
    match command:
        case InitCommand():
            print("tinynav init: not implemented yet")
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
