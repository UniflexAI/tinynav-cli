import json

import pytest

from tinynav_cli import cli
from tinynav_cli.cli import _parse_poi_selection, _selected_cmd_pois, NavGoCommand
from tinynav_cli.version import __version__


def test_version() -> None:
    assert __version__ == "0.0.13"


def test_parse_poi_selection() -> None:
    assert _parse_poi_selection("2,1,0") == ["2", "1", "0"]


def test_parse_poi_selection_rejects_empty() -> None:
    with pytest.raises(ValueError):
        _parse_poi_selection("")


def test_selected_cmd_pois_preserves_inner_ids(tmp_path) -> None:
    map_path = tmp_path / "maps" / "demo"
    map_path.mkdir(parents=True)
    pois = {
        "0": {"id": 0, "name": "POI_0", "position": [0, 0, 0]},
        "1": {"id": 1, "name": "POI_1", "position": [1, 1, 1]},
        "2": {"id": 2, "name": "POI_2", "position": [2, 2, 2]},
    }
    (map_path / "pois.json").write_text(json.dumps(pois))

    selected = _selected_cmd_pois(map_path, "2,1,0")

    assert list(selected.keys()) == ["0", "1", "2"]
    assert selected["0"]["id"] == 2
    assert selected["1"]["id"] == 1
    assert selected["2"]["id"] == 0


def test_selected_cmd_pois_without_filter_returns_all(tmp_path) -> None:
    map_path = tmp_path / "maps" / "demo"
    map_path.mkdir(parents=True)
    pois = {"0": {"id": 0}}
    (map_path / "pois.json").write_text(json.dumps(pois))

    assert _selected_cmd_pois(map_path, None) == pois



def test_nav_go_requires_running_state(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "_ensure_runtime_container", lambda name: True)
    monkeypatch.setattr(cli, "_nav_status", lambda name: ("starting", []))

    result = cli.run_nav_go(NavGoCommand())

    assert result == 1
    assert "running state" in capsys.readouterr().out


def test_nav_go_uses_running_session_map_name(monkeypatch, tmp_path, capsys) -> None:
    map_name = "demo_map"
    map_path = tmp_path / "maps" / map_name
    map_path.mkdir(parents=True)
    pois = {"0": {"id": 0, "name": "POI_0", "position": [0, 0, 0]}}
    (map_path / "pois.json").write_text(json.dumps(pois))

    monkeypatch.setattr(cli, "_ensure_runtime_container", lambda name: True)
    monkeypatch.setattr(cli, "_nav_status", lambda name: ("running", []))
    monkeypatch.setattr(cli, "_nav_map_name", lambda name: map_name)
    monkeypatch.setattr(cli, "_maps_dir", lambda: tmp_path / "maps")

    published = {}

    class Result:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_exec(container_name: str, shell_command: str):
        published["container"] = container_name
        published["command"] = shell_command
        return Result()

    monkeypatch.setattr(cli, "_docker_exec_output", fake_exec)

    result = cli.run_nav_go(NavGoCommand(pois="0"))

    assert result == 0
    assert published["container"] == cli.DEFAULT_CONTAINER_NAME
    assert "/mapping/cmd_pois" in published["command"]
    out = capsys.readouterr().out
    assert f"map: {map_name}" in out
