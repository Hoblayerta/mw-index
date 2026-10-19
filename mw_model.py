"""
Índice de un MW, v0.
Compara cuánto rinde un megavatio por día en tres usos:
  1. Minar Bitcoin (hashprice x eficiencia)
  2. Alojar GPUs de un tercero (hosting, sin capex de GPU)
  3. Alquilar H100 propias (índice H100 x densidad x utilización)
Más: fee rate y precio por token, para ver si hay algo que correlacionar.

Todo supuesto está en SUPUESTOS. Cambiarlos cambia el número; no hay magia.
"""
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path

DATA = Path(__file__).parent / "data"
OUT = Path(__file__).parent / "out"
OUT.mkdir(exist_ok=True)

# ---------- SUPUESTOS (editar aquí) ----------
SUPUESTOS = {
    # minería
    "j_por_th_flota_vieja": 29.5,   # S19j Pro
    "j_por_th_flota_media": 17.5,   # S21
    "j_por_th_flota_nueva": 13.5,   # S21 XP
    "usd_kwh": 0.048,               # Luxor jul 2026
    # GPU propia
    "h100_por_mw_it": 740,          # medio del rango 690-785
    "pue": 1.3,                     # aire eficiente / líquida mediocre
    "utilizacion": 0.71,            # Epoch
    # hosting
    "hosting_usd_mw_it_anio": 1_850_000,  # TeraWulf-Fluidstack
    # capex (para la columna de payback, solo referencia)
    "capex_mina_usd_mw": 850_000,
    "capex_ia_usd_mw": 20_000_000,
}


def ingreso_mina_usd_mw_dia(hashprice_usd_ph_dia, j_por_th):
    """1 MW alimentando ASICs de j_por_th J/TH durante un día.
    TH/s que caben en 1 MW = 1e6 W / (j_por_th W/TH) ; en PH/s = /1000.
    Ingreso bruto = PH/s x hashprice (USD/PH/día)."""
    ph_s = (1e6 / j_por_th) / 1000
    bruto = ph_s * hashprice_usd_ph_dia
    electricidad = 1000 * 24 * SUPUESTOS["usd_kwh"]  # 1 MW x 24 h
    return bruto, bruto - electricidad


def ingreso_gpu_usd_mw_dia(h100_usd_hora):
    """1 MW de capacidad IT llena de H100 propias.
    Con PUE, el MW de red alimenta 1/PUE MW IT."""
    mw_it = 1 / SUPUESTOS["pue"]
    gpus = SUPUESTOS["h100_por_mw_it"] * mw_it
    bruto = gpus * h100_usd_hora * 24 * SUPUESTOS["utilizacion"]
    electricidad = 1000 * 24 * SUPUESTOS["usd_kwh"]
    return bruto, bruto - electricidad


def ingreso_hosting_usd_mw_dia():
    mw_it = 1 / SUPUESTOS["pue"]
    return SUPUESTOS["hosting_usd_mw_it_anio"] * mw_it / 365


def cargar():
    hp = pd.read_csv(DATA / "hashprice.csv")
    btc = pd.read_csv(DATA / "btc.csv")
    h100 = pd.read_csv(DATA / "h100.csv")
    fees = pd.read_csv(DATA / "fees.csv")
    tok = pd.read_csv(DATA / "tokens.csv")
    for d in (hp, btc, h100, fees, tok):
        d["mes"] = pd.PeriodIndex(d["mes"], freq="M")
    # H100: si hay varios puntos en un mes, promedio
    h100m = h100.groupby("mes", as_index=False)["h100_usd_hora"].mean()
    df = (hp[["mes", "hashprice_usd_ph_dia", "tipo"]]
          .merge(btc[["mes", "btc_cierre_usd"]], on="mes", how="outer")
          .merge(h100m, on="mes", how="outer")
          .merge(fees[["mes", "fees_pct_ingreso_minero"]], on="mes", how="outer")
          .sort_values("mes").reset_index(drop=True))
    return df, tok


def construir(df):
    for nombre, j in [("vieja", SUPUESTOS["j_por_th_flota_vieja"]),
                      ("media", SUPUESTOS["j_por_th_flota_media"]),
                      ("nueva", SUPUESTOS["j_por_th_flota_nueva"])]:
        b, n = zip(*[ingreso_mina_usd_mw_dia(h, j) if pd.notna(h) else (np.nan, np.nan)
                     for h in df["hashprice_usd_ph_dia"]])
        df[f"mina_{nombre}_bruto"] = b
        df[f"mina_{nombre}_neto"] = n
    b, n = zip(*[ingreso_gpu_usd_mw_dia(h) if pd.notna(h) else (np.nan, np.nan)
                 for h in df["h100_usd_hora"]])
    df["gpu_bruto"] = b
    df["gpu_neto"] = n
    df["hosting"] = ingreso_hosting_usd_mw_dia()
    # la brecha que importa: cuántas veces rinde el MW en GPU vs minando con flota media
    df["brecha_gpu_vs_mina_media"] = df["gpu_neto"] / df["mina_media_neto"]
    df["brecha_hosting_vs_mina_media"] = df["hosting"] / df["mina_media_neto"]
    return df


def graficar(df, tok):
    # reindexar a todos los meses para que los huecos rompan la línea en vez de interpolarse
    full = pd.period_range(df["mes"].min(), df["mes"].max(), freq="M")
    d = df.set_index("mes").reindex(full).reset_index().rename(columns={"index": "mes"})
    x = d["mes"].dt.to_timestamp()

    fig, ax = plt.subplots(figsize=(11, 6))
    ax.plot(x, d["mina_nueva_neto"], label="Mining, 13.5 J/TH fleet (net of power)", lw=2)
    ax.plot(x, d["mina_media_neto"], label="Mining, 17.5 J/TH fleet (net of power)", lw=2)
    ax.plot(x, d["mina_vieja_neto"], label="Mining, 29.5 J/TH fleet (net of power)", lw=2)
    ax.axhline(d["hosting"].iloc[-1], color="C3", ls="--", lw=2, label="AI hosting (TeraWulf/Fluidstack-type, no GPU capex)")
    g = d.dropna(subset=["gpu_neto"])
    ax.scatter(g["mes"].dt.to_timestamp(), g["gpu_neto"], label="Owned H100s (months with data)", zorder=5, s=40)
    ax.axhline(0, color="k", lw=.8)
    ax.set_yscale("symlog", linthresh=500)
    ax.set_ylabel("USD per MW per day (symlog scale)")
    ax.set_title("What 1 MW earns per day: mining BTC vs hosting AI vs renting H100s")
    ax.grid(alpha=.3, which="both")
    ax.legend(fontsize=8, loc="upper left")
    fig.tight_layout()
    fig.savefig(OUT / "mw_minar_vs_ia.png", dpi=150)

    # fee share y token price: la "correlación" que no existe
    fig, ax1 = plt.subplots(figsize=(11, 5))
    f = df.dropna(subset=["fees_pct_ingreso_minero"])
    ax1.bar(f["mes"].dt.to_timestamp(), f["fees_pct_ingreso_minero"], width=20, label="Fees as % of miner revenue")
    ax1.set_yscale("log")
    ax1.set_ylabel("% of miner revenue (log)")
    ax2 = ax1.twinx()
    t4 = tok[tok["nivel"].str.startswith("GPT-4")]
    t35 = tok[tok["nivel"].str.startswith("GPT-3.5")]
    ax2.plot(t4["mes"].dt.to_timestamp(), t4["usd_por_millon"], "o-", color="C3", label="USD per 1M tokens, GPT-4 level")
    ax2.plot(t35["mes"].dt.to_timestamp(), t35["usd_por_millon"], "s-", color="C2", label="USD per 1M tokens, GPT-3.5 level")
    ax2.set_yscale("log")
    ax2.set_ylabel("USD per 1M tokens (log)")
    ax1.set_title("Bitcoin fee share vs inference token price")
    h1, l1 = ax1.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax1.legend(h1 + h2, l1 + l2, fontsize=8, loc="upper right")
    fig.tight_layout()
    fig.savefig(OUT / "fees_vs_tokens.png", dpi=150)


def correlaciones(df):
    """Pearson sobre meses donde ambos existen. Pocos puntos: no es prueba, es rastro."""
    out = {}
    pares = [("hashprice_usd_ph_dia", "h100_usd_hora"),
             ("btc_cierre_usd", "h100_usd_hora"),
             ("hashprice_usd_ph_dia", "fees_pct_ingreso_minero"),
             ("btc_cierre_usd", "hashprice_usd_ph_dia")]
    for a, b in pares:
        s = df[[a, b]].dropna()
        out[f"{a} ~ {b}"] = (round(s[a].corr(s[b]), 2) if len(s) > 2 else np.nan, len(s))
    return out


if __name__ == "__main__":
    df, tok = cargar()
    df = construir(df)
    graficar(df, tok)
    cols = ["mes", "hashprice_usd_ph_dia", "btc_cierre_usd", "h100_usd_hora",
            "mina_vieja_neto", "mina_media_neto", "mina_nueva_neto",
            "hosting", "gpu_neto", "brecha_gpu_vs_mina_media", "brecha_hosting_vs_mina_media"]
    tabla = df[cols].copy()
    for c in cols[1:]:
        tabla[c] = tabla[c].round(0)
    tabla.to_csv(OUT / "tabla_mw.csv", index=False)
    print(tabla.dropna(subset=["mina_media_neto"]).to_string(index=False))
    print("\nCorrelaciones (pearson, n):")
    for k, v in correlaciones(df).items():
        print(f"  {k}: r={v[0]}  n={v[1]}")
