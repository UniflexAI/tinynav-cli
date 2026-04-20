import json

import pytest

from tinynav_cli.cli import _parse_poi_selection, _selected_cmd_pois
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
