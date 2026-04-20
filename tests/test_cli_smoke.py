import subprocess
import sys
from pathlib import Path


TINYNAV_BIN = Path(sys.executable).with_name("tinynav")


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(TINYNAV_BIN), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def output_text(result: subprocess.CompletedProcess[str]) -> str:
    return (result.stdout or "") + (result.stderr or "")


def test_version_command_runs() -> None:
    result = run_cli("version")
    assert result.returncode == 0
    assert "tinynav" in output_text(result)


def test_root_help_runs() -> None:
    result = run_cli("--help")
    assert result.returncode == 0
    assert "init" in output_text(result)
    assert "doctor" in output_text(result)
    assert "example" in output_text(result)


def test_init_help_runs() -> None:
    result = run_cli("init", "--help")
    assert result.returncode == 0
    assert "Initialize the local TinyNav CLI workspace." in output_text(result)
    assert "INIT OPTIONS" in output_text(result)


def test_doctor_help_runs() -> None:
    result = run_cli("doctor", "--help")
    assert result.returncode == 0
    assert "verbose" in output_text(result)


def test_example_help_runs() -> None:
    result = run_cli("example", "--help")
    assert result.returncode == 0
    assert "container" in output_text(result).lower()


def test_map_help_runs() -> None:
    result = run_cli("map", "--help")
    assert result.returncode == 0
    text = output_text(result)
    assert "status" in text
    assert "start_record" in text
    assert "stop_record" in text
    assert "build" in text
    assert "list" in text


def test_sensors_help_runs() -> None:
    result = run_cli("sensors", "--help")
    assert result.returncode == 0
    text = output_text(result).lower()
    assert "container" in text
    assert "preview" in text



def test_nav_help_runs() -> None:
    result = run_cli("nav", "--help")
    assert result.returncode == 0
    text = output_text(result)
    assert "status" in text
    assert "start" in text
    assert "go" in text
    assert "stop" in text
