from navicast.common import schema


def test_sentinels():
    assert schema.SENTINELS == {"SOG": 102.3, "COG": 360.0}


def test_columns():
    assert len(schema.AIS_COLUMNS) == 17
    assert schema.AIS_COLUMNS[0] == "MMSI"
    assert "BaseDateTime" in schema.BRONZE_COLUMN_TYPES


def test_identity_keys():
    assert schema.IDENTITY_KEYS == ["MMSI", "IMO", "CallSign"]
