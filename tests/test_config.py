import pytest

from navicast.common import config


def test_load_has_sections():
    cfg = config.load()
    assert "aws" in cfg and "snapshots" in cfg


def test_snapshot_known():
    _, snap = config.snapshot("snap_2024-01-w3_laxlb_v1")
    assert snap["from_bronze"] == "snap_2024-01-w3_noaa_national_v1"
    assert snap["bbox"]["lon_min"] == -118.6


def test_snapshot_unknown_raises():
    with pytest.raises(KeyError):
        config.snapshot("no_existe_este_snapshot")
