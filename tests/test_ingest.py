from navicast import ingest


def test_noaa_url():
    assert (ingest.noaa_url("2024-01-15")
            == "https://coast.noaa.gov/htdata/CMSP/AISDataHandler/2024/AIS_2024_01_15.zip")


def test_bronze_key():
    assert (ingest._bronze_key("snap_x", "noaa", "AIS_2024_01_15.parquet")
            == "bronze/source=noaa/snapshot=snap_x/region=national/AIS_2024_01_15.parquet")
