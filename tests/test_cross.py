import pandas as pd

from navicast import monitor_chile


def test_cross_classifies_dark():
    """Una deteccion SAR cerca de AIS = corroborada; lejos = DARK."""
    ais = pd.DataFrame({"lat": [33.74], "lon": [-118.24]})
    sar = pd.DataFrame({
        "lat": [33.7401, 34.50],     # cerca de AIS / lejos
        "lon": [-118.2401, -119.50],
        "ship_name": ["cerca", "lejos"],
    })
    out = monitor_chile.cross(sar, ais)
    assert "dark" in out.columns
    assert not bool(out.iloc[0]["dark"])   # cerca de AIS -> corroborado
    assert bool(out.iloc[1]["dark"])       # lejos de todo AIS -> dark


def test_cross_empty_ais_not_flagged():
    """Sin AIS de referencia no se puede clasificar -> nada marcado dark."""
    sar = pd.DataFrame({"lat": [33.74], "lon": [-118.24]})
    out = monitor_chile.cross(sar, pd.DataFrame(columns=["lat", "lon"]))
    assert not out["dark"].any()
