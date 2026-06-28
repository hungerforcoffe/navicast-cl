"""Modelo de ETA (Sprint 4). LSTM: secuencia de pings -> minutos a puerto.

Pipeline (todo reproducible, semilla fija):
  1. Carga Gold etiquetado y construye secuencias (ventana K por buque).
  2. Split POR BUQUE (sin fuga) 70/15/15 con hash estable del MMSI.
  3. Estandariza features continuas (media/desv calculadas SOLO en train).
  4. Baselines: fisico ingenuo (dist/SOG) + HistGradientBoosting (ultimo ping).
  5. LSTM (PyTorch CPU): target log1p(eta_min), perdida Huber; mejor epoca por val.
  6. Evalua en test (MAE en minutos) y compara; guarda modelo + scaler en S3.

Decisiones validadas: K=16, split por buque, target log + Huber, ambos baselines.
El LSTM es EXCLUSIVO del ETA (la deteccion de buques oscuros es otra cosa, Sprint 5).
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view

from navicast.common import config, io_s3

K = 16
HIDDEN = 64
EPOCHS = 20
BATCH = 256
SEED = 42

CONT = ["SOG", "dist_to_port_km", "dt_s", "dist_km"]   # se estandarizan (indices 0..3)
ANG = ["COG", "Heading", "bearing_to_port"]            # -> cos/sin
FEAT = CONT + [f"{fn}_{a}" for a in ANG for fn in ("cos", "sin")]
FDIM = len(FEAT)


def _split(mmsi: int) -> str:
    h = int(hashlib.md5(str(int(mmsi)).encode()).hexdigest(), 16) % 100
    return "train" if h < 70 else ("val" if h < 85 else "test")


def _prep(glob: str) -> pd.DataFrame:
    df = duckdb.connect().execute(f"""
        SELECT MMSI, BaseDateTime, SOG, COG, Heading,
               dist_to_port_km, dt_s, dist_km, bearing_to_port, eta_min, has_eta
        FROM read_parquet('{glob}', hive_partitioning=true)
    """).df().sort_values(["MMSI", "BaseDateTime"]).reset_index(drop=True)
    for c in CONT:
        df[c] = df[c].fillna(0).astype("float32")
    for a in ANG:
        rad = np.radians(df[a].fillna(0).to_numpy())
        df[f"cos_{a}"] = np.cos(rad).astype("float32")
        df[f"sin_{a}"] = np.sin(rad).astype("float32")
    return df


def _build_sequences(df: pd.DataFrame):
    """Devuelve X (N,K,FDIM) crudo, y_log (N,), splits (N,) por buque."""
    Xs, ys, sp = [], [], []
    skipped = 0
    for mmsi, g in df.groupby("MMSI", sort=False):
        if len(g) < K:
            skipped += int(g["has_eta"].sum())
            continue
        F = g[FEAT].to_numpy(dtype=np.float32)
        win = sliding_window_view(F, window_shape=K, axis=0).transpose(0, 2, 1)  # (T-K+1,K,FDIM)
        last = np.arange(K - 1, len(g))
        has = g["has_eta"].to_numpy()[last]
        eta = g["eta_min"].to_numpy()[last].astype("float32")
        keep = has
        if keep.any():
            Xs.append(win[keep])
            ys.append(eta[keep])
            sp.extend([_split(mmsi)] * int(keep.sum()))
    X = np.concatenate(Xs).astype("float32")
    y = np.log1p(np.concatenate(ys)).astype("float32")
    return X, y, np.array(sp), skipped


def _mae_min(pred_log, true_log) -> float:
    return float(np.mean(np.abs(np.expm1(pred_log) - np.expm1(true_log))))


def _train_lstm(Xtr, ytr, Xva, yva, epochs):
    import torch
    import torch.nn as nn
    from torch.utils.data import DataLoader, TensorDataset

    torch.manual_seed(SEED)

    class LSTMReg(nn.Module):
        def __init__(self, fdim, hidden=HIDDEN):
            super().__init__()
            self.lstm = nn.LSTM(fdim, hidden, batch_first=True)
            self.head = nn.Sequential(nn.Linear(hidden, hidden // 2), nn.ReLU(),
                                      nn.Linear(hidden // 2, 1))

        def forward(self, x):
            _, (h, _) = self.lstm(x)
            return self.head(h[-1]).squeeze(-1)

    model = LSTMReg(Xtr.shape[2])
    opt = torch.optim.Adam(model.parameters(), lr=1e-3)
    lossf = nn.HuberLoss()
    dl = DataLoader(TensorDataset(torch.from_numpy(Xtr), torch.from_numpy(ytr)),
                    batch_size=BATCH, shuffle=True)
    Xva_t, yva_t = torch.from_numpy(Xva), yva
    best_mae, best_state = 1e9, None
    for ep in range(epochs):
        model.train()
        for xb, yb in dl:
            opt.zero_grad()
            loss = lossf(model(xb), yb)
            loss.backward()
            opt.step()
        model.eval()
        with torch.no_grad():
            pv = model(Xva_t).numpy()
        mae = _mae_min(pv, yva_t)
        if mae < best_mae:
            best_mae = mae
            best_state = {k: v.clone() for k, v in model.state_dict().items()}
        print(f"  epoca {ep + 1:2d}/{epochs}  val MAE = {mae:6.1f} min", flush=True)
    model.load_state_dict(best_state)
    return model, best_mae


def run(snapshot_id: str, config_path: str | Path | None = None, upload: bool = True,
        epochs: int = EPOCHS) -> dict[str, Any]:
    cfg, _ = config.snapshot(snapshot_id, config_path)
    gold = (config.REPO_ROOT / "data" / "gold" / snapshot_id).as_posix()
    glob = f"{gold}/**/*.parquet"

    np.random.seed(SEED)
    df = _prep(glob)
    X, y, sp, skipped = _build_sequences(df)
    tr, va, te = sp == "train", sp == "val", sp == "test"
    print(f"secuencias: {len(y):,} (train {tr.sum():,} | val {va.sum():,} | test {te.sum():,})"
          f"  [descartadas por <K pings: {skipped:,}]")

    # estandarizar features continuas (0..3) con stats de TRAIN
    mu = X[tr][:, :, :4].reshape(-1, 4).mean(0)
    sd = X[tr][:, :, :4].reshape(-1, 4).std(0) + 1e-6
    Xs = X.copy()
    Xs[:, :, :4] = (X[:, :, :4] - mu) / sd

    yte_min = np.expm1(y[te])

    # --- baseline 1: fisico ingenuo (ultimo ping, datos crudos) ---
    dist = X[te][:, -1, 1]              # dist_to_port_km
    sog = np.maximum(X[te][:, -1, 0], 0.5)
    eta_naive = dist / (sog * 1.852) * 60.0
    mae_naive = float(np.mean(np.abs(eta_naive - yte_min)))

    # --- baseline 2: HistGradientBoosting sobre el ultimo ping ---
    from sklearn.ensemble import HistGradientBoostingRegressor
    gbm = HistGradientBoostingRegressor(random_state=SEED)
    gbm.fit(X[tr][:, -1, :], y[tr])
    mae_gbm = _mae_min(gbm.predict(X[te][:, -1, :]), y[te])

    # --- LSTM ---
    model, val_mae = _train_lstm(Xs[tr], y[tr], Xs[va], y[va], epochs)
    import torch
    with torch.no_grad():
        pred_te = model(torch.from_numpy(Xs[te])).numpy()
    mae_lstm = _mae_min(pred_te, y[te])

    results = {"naive_fisico": round(mae_naive, 1),
               "hist_gbm": round(mae_gbm, 1),
               "lstm": round(mae_lstm, 1)}
    _report(snapshot_id, results, yte_min, np.expm1(pred_te), epochs)

    # --- guardar artefactos (modelo + scaler) ---
    mdir = config.REPO_ROOT / "data" / "models" / snapshot_id
    mdir.mkdir(parents=True, exist_ok=True)
    torch.save(model.state_dict(), mdir / "eta_lstm.pt")
    meta = {"feat": FEAT, "K": K, "hidden": HIDDEN,
            "scaler_mean": mu.tolist(), "scaler_std": sd.tolist(),
            "cont_idx": [0, 1, 2, 3], "target": "log1p(eta_min)",
            "test_mae_min": results, "trained_at": dt.datetime.now(dt.timezone.utc).isoformat()}
    (mdir / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    if upload:
        aws = cfg["aws"]
        client = io_s3.get_client(aws["region"], aws.get("profile"))
        for f in (mdir / "eta_lstm.pt", mdir / "meta.json"):
            io_s3.upload_file(client, f, aws["bucket"], f"models/snapshot={snapshot_id}/{f.name}")
        print(f"modelo -> {io_s3.s3_uri(aws['bucket'], f'models/snapshot={snapshot_id}/')}")

    return meta


def _report(snapshot_id, results, yte_min, pred_lstm_min, epochs) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    base = results["naive_fisico"]
    print("\n" + "=" * 58)
    print(f"ETA - MAE en test (minutos)  |  {snapshot_id}")
    print("=" * 58)
    print(f"{'modelo':<22}{'MAE (min)':>12}{'vs naive':>12}")
    print("-" * 58)
    for name, mae in results.items():
        print(f"{name:<22}{mae:>12.1f}{base / mae:>11.2f}x")
    print("=" * 58)

    n = min(6000, len(yte_min))
    idx = np.random.choice(len(yte_min), n, replace=False)
    fig, ax = plt.subplots(figsize=(6, 6))
    ax.scatter(yte_min[idx], pred_lstm_min[idx], s=4, alpha=0.2, color="#48c")
    lim = np.percentile(yte_min, 99)
    ax.plot([0, lim], [0, lim], "r--", linewidth=1)
    ax.set_xlim(0, lim); ax.set_ylim(0, lim)
    ax.set_xlabel("ETA real (min)"); ax.set_ylabel("ETA predicho LSTM (min)")
    ax.set_title(f"LSTM ETA: predicho vs real (test) — MAE {results['lstm']:.0f} min")
    fig.tight_layout()
    fig.savefig(config.REPO_ROOT / "docs" / "eta_model_eval.png", dpi=120)

    md = ["# Modelo ETA — resultados (Sprint 4)", "",
          f"Snapshot: `{snapshot_id}` · ventana K={K} · {epochs} epocas · split por buque · "
          "target log1p + Huber.", "",
          "MAE en **test** (buques nunca vistos), en minutos:", "",
          "| Modelo | MAE (min) | Mejora vs naive |", "|---|---:|---:|"]
    for name, mae in results.items():
        md.append(f"| {name} | {mae:.1f} | {base / mae:.2f}x |")
    md += ["", "Scatter predicho vs real: `docs/eta_model_eval.png`.", "",
           "## Limitaciones y mejoras", "",
           "El scatter muestra **bandas horizontales**: el modelo predice casi una constante "
           "para entradas casi identicas cuyo ETA real varia mucho. Causa principal: **buques "
           "fondeados esperando turno** -- su cinematica (quieto, SOG~0) es identica ping tras "
           "ping mientras el ETA real cuenta atras. Ese tiempo de cola NO esta en los datos AIS "
           "de posicion, asi que cualquier modelo choca con ese techo (no es un bug).", "",
           "Mejoras (features que distingan los casos hoy indistinguibles):",
           "1. **Tiempo esperando**: minutos desde que el buque bajo de ~1 nudo (la ventana K=16 "
           "solo ve ~16 min; barato y probablemente el de mayor impacto).",
           "2. **Congestion del puerto**: nº de buques en darsena/cola en ese instante.",
           "3. **Campo destino/ETA reportado en AIS** (mensajes estaticos; ruidoso pero util).",
           "4. **Mas datos (1 mes)** y **distancia al borde** del poligono (no al centroide)."]
    (config.REPO_ROOT / "docs" / "eta_model_report.md").write_text("\n".join(md), encoding="utf-8")


def _cli() -> None:
    ap = argparse.ArgumentParser(description="Entrena el LSTM de ETA (+ baselines).")
    ap.add_argument("--snapshot", required=True)
    ap.add_argument("--config", default=None)
    ap.add_argument("--no-upload", action="store_true")
    ap.add_argument("--epochs", type=int, default=EPOCHS)
    args = ap.parse_args()
    run(args.snapshot, config_path=args.config, upload=not args.no_upload, epochs=args.epochs)


if __name__ == "__main__":
    _cli()
