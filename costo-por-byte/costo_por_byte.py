"""
Costo realizado por byte de block space, v0.
Por mes de ene 2024 a sep 2026: cuánta energía (kWh y USD) cuesta producir un vB de block space contra el fee que paga el usuario por ese vB.
La diferencia la cubre el subsidio.

Fuente única de datos: API pública de mempool.space (se guarda el crudo en data/).
Supuestos en SUPUESTOS, los mismos del índice de 1 MW.

Uso: python3 costo_por_byte.py           (usa el crudo de data/ si existe)
     python3 costo_por_byte.py --bajar   (vuelve a bajar el crudo)
"""
import json
import sys
import urllib.request
from pathlib import Path

import matplotlib
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt

AQUI = Path(__file__).parent
DATA = AQUI / "data"
OUT = AQUI / "out"
OUT.mkdir(exist_ok=True)

# ---------- SUPUESTOS (editar aquí) ----------
SUPUESTOS = {
    "j_por_th": {"vieja": 29.5, "media": 17.5, "nueva": 13.5},  # misma flota que el índice de 1 MW
    "usd_kwh": 0.048,  # Luxor jul 2026
    "segundos_por_bloque": 600,
}

FUENTES = {
    "hashrate": "https://mempool.space/api/v1/mining/hashrate/3y",
    "tamanos": "https://mempool.space/api/v1/mining/blocks/sizes-weights/3y",
    "fees": "https://mempool.space/api/v1/mining/blocks/fees/3y",
}

HALVING_2024 = pd.Timestamp("2024-04-20", tz="UTC")  # bloque 840,000
DESDE = "2024-01"
HASTA = "2026-09"  # último mes completo al bajar el crudo (21 oct 2026)


def bajar():
    for nombre, url in FUENTES.items():
        req = urllib.request.Request(url, headers={"User-Agent": "costo-por-byte/0"})
        with urllib.request.urlopen(req, timeout=60) as r:
            (DATA / f"{nombre}.json").write_bytes(r.read())
        print(f"bajado {nombre} <- {url}")


def cargar():
    hr = json.loads((DATA / "hashrate.json").read_text())["hashrates"]
    tw = json.loads((DATA / "tamanos.json").read_text())
    fe = json.loads((DATA / "fees.json").read_text())

    hr = pd.DataFrame(hr)
    hr["fecha"] = pd.to_datetime(hr["timestamp"], unit="s", utc=True)
    hr["th_s"] = hr["avgHashrate"] / 1e12

    sz = pd.DataFrame(tw["sizes"])
    wt = pd.DataFrame(tw["weights"])
    bl = sz.merge(wt[["avgHeight", "avgWeight"]], on="avgHeight")
    bl = bl.merge(pd.DataFrame(fe)[["avgHeight", "avgFees", "USD"]], on="avgHeight")
    bl["fecha"] = pd.to_datetime(bl["timestamp"], unit="s", utc=True)
    bl["vbytes"] = bl["avgWeight"] / 4
    bl["subsidio_btc"] = (bl["fecha"] < HALVING_2024).map({True: 6.25, False: 3.125})
    return hr, bl


def construir(hr, bl):
    hr_m = hr.set_index("fecha")["th_s"].resample("MS").mean()
    bl_m = bl.set_index("fecha")[["avgSize", "vbytes", "avgFees", "USD", "subsidio_btc"]].resample("MS").mean()
    df = bl_m.join(hr_m, how="inner").dropna().astype(float)

    s = SUPUESTOS
    for flota, j in s["j_por_th"].items():
        # energía de un bloque = hashrate (TH/s) x J/TH x 600 s, pasada a kWh
        kwh_bloque = df["th_s"] * j * s["segundos_por_bloque"] / 3.6e6
        df[f"kwh_por_vb_{flota}"] = kwh_bloque / df["vbytes"]
        df[f"costo_usd_por_vb_{flota}"] = df[f"kwh_por_vb_{flota}"] * s["usd_kwh"]

    df["fees_usd_bloque"] = df["avgFees"] / 1e8 * df["USD"]
    df["ingreso_usd_bloque"] = (df["avgFees"] / 1e8 + df["subsidio_btc"]) * df["USD"]
    df["fees_usd_por_vb"] = df["fees_usd_bloque"] / df["vbytes"]
    df["ingreso_usd_por_vb"] = df["ingreso_usd_bloque"] / df["vbytes"]
    df["fee_rate_sat_vb"] = df["avgFees"] / df["vbytes"]
    # qué parte de la energía de su vB paga el usuario (flota media)
    df["usuario_paga_pct_energia"] = 100 * df["fees_usd_por_vb"] / df["costo_usd_por_vb_media"]
    df.index = df.index.tz_localize(None).to_period("M")
    df.index.name = "mes"
    return df[(df.index >= pd.Period(DESDE, "M")) & (df.index <= pd.Period(HASTA, "M"))]


def graficar(df):
    x = df.index.to_timestamp()
    halving = HALVING_2024.tz_localize(None)
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(11, 8), sharex=True, gridspec_kw={"height_ratios": [1, 2]})

    for flota, c in [("nueva", "C2"), ("media", "C1"), ("vieja", "C4")]:
        j = SUPUESTOS["j_por_th"][flota]
        a1.plot(x, df[f"kwh_por_vb_{flota}"], color=c, lw=2, label=f"{j} J/TH fleet")
    a1.set_ylabel("kWh per vB")
    a1.set_title("Bitcoin block space: energy per vB vs the fee users pay per vB")
    a1.grid(alpha=.3)
    a1.legend(fontsize=8, loc="upper left")
    a1.axvline(halving, color="k", ls=":", lw=1)

    for flota, c in [("nueva", "C2"), ("media", "C1"), ("vieja", "C4")]:
        j = SUPUESTOS["j_por_th"][flota]
        a2.plot(x, df[f"costo_usd_por_vb_{flota}"] * 100, color=c, lw=2,
                label=f"Energy cost per vB, {j} J/TH at {SUPUESTOS['usd_kwh'] * 100:.1f}c/kWh")
    a2.plot(x, df["fees_usd_por_vb"] * 100, color="C3", lw=2.5, label="Fee paid per vB")
    a2.axvline(halving, color="k", ls=":", lw=1, label="Halving, Apr 2024")
    a2.set_yscale("log")
    a2.set_ylabel("US cents per vB (log)")
    a2.grid(alpha=.3, which="both")
    a2.legend(fontsize=8, loc="center right")
    fig.tight_layout()
    fig.savefig(OUT / "costo_por_vb.png", dpi=150)


if __name__ == "__main__":
    if "--bajar" in sys.argv or not (DATA / "fees.json").exists():
        bajar()
    hr, bl = cargar()
    df = construir(hr, bl)
    graficar(df)
    cols = ["th_s", "vbytes", "fee_rate_sat_vb", "USD",
            "kwh_por_vb_nueva", "kwh_por_vb_media", "kwh_por_vb_vieja",
            "costo_usd_por_vb_nueva", "costo_usd_por_vb_media", "costo_usd_por_vb_vieja",
            "fees_usd_por_vb", "ingreso_usd_por_vb", "usuario_paga_pct_energia"]
    tabla = df[cols].copy()
    tabla.to_csv(OUT / "tabla_costo_por_vb.csv", float_format="%.6g")
    vista = tabla.copy()
    vista["th_s"] = (vista["th_s"] / 1e6).round(0)  # EH/s
    for c in cols[7:12]:
        vista[c] = (vista[c] * 100).round(3)  # centavos
    vista = vista.rename(columns={"th_s": "EH_s"})
    print(vista.round(2).to_string())
