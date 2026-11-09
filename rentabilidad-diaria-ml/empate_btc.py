"""
At what Bitcoin price does mining 1 MW pay as much as hosting AI?

For each fleet: mining has to cover the hosting rate plus its own power bill.
Needed hashprice = (hosting + power) / PH/s per MW. Assuming hashrate stays where
it is and fees keep their share, hashprice moves with the Bitcoin price, so
needed BTC = BTC today x needed hashprice / hashprice today. That is a floor:
when the price rises, hashrate follows and the bar moves up.

"Today" is the last full month of mw_bitcoin_diario.csv. Hosting comes from
../out/tabla_mw.csv (TeraWulf / Fluidstack rate). Power at 7 cents, as in the dataset.

Writes out/empate_btc.png and out/empate_btc.csv.
"""
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

AQUI = Path(__file__).resolve().parent
plt.rcParams["text.parse_math"] = False  # los "$" son dólares, no fórmulas
MESES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
LUZ_USD_KWH = 0.07
FLOTAS = [("Older fleet, 29.5 J/TH", 29.5), ("Mid fleet, 17.5 J/TH", 17.5), ("Newest fleet, 13.5 J/TH", 13.5)]

# colores: un solo tono (slot 1 de la paleta de referencia), tinta y superficie claras
SERIE, TINTA, TINTA_2, GUIA, FONDO = "#2a78d6", "#0b0b0b", "#52514e", "#bdbcb6", "#fcfcfb"


def main():
    d = pd.read_csv(AQUI / "mw_bitcoin_diario.csv", index_col=0, parse_dates=True)
    ultimo = d.index.max()
    mes_txt = f"{MESES[ultimo.month - 1]} {ultimo.year}"
    mes = d[(d.index.year == ultimo.year) & (d.index.month == ultimo.month)]
    hp, btc = mes["hashprice_usd_ph_dia"].mean(), mes["btc_usd"].mean()
    hosting = pd.read_csv(AQUI.parent / "out" / "tabla_mw.csv")["hosting"].dropna().iloc[-1]
    luz = 24 * 1000 * LUZ_USD_KWH

    filas = []
    for nombre, jth in FLOTAS:
        ph = 1000 / jth  # PH/s per MW
        for etiqueta, renta in (("hosting", hosting), ("hosting_a_la_mitad", hosting / 2)):
            filas.append({"flota": nombre, "j_th": jth, "caso": etiqueta,
                          "btc_necesario_usd": round(btc * (renta + luz) / ph / hp, -3)})
    t = pd.DataFrame(filas)
    t.to_csv(AQUI / "out" / "empate_btc.csv", index=False)

    full = t[t.caso == "hosting"].reset_index(drop=True)
    fig, ax = plt.subplots(figsize=(9, 4.2), dpi=150)
    fig.patch.set_facecolor(FONDO)
    ax.set_facecolor(FONDO)
    y = range(len(full))[::-1]
    ax.barh(list(y), full.btc_necesario_usd / 1000, height=0.32, color=SERIE, zorder=2)
    for yi, v in zip(y, full.btc_necesario_usd):
        ax.text(v / 1000 + 4, yi, f"${v/1000:,.0f}k", va="center", ha="left", fontsize=12, fontweight="bold", color=TINTA)
    ax.axvline(btc / 1000, color=TINTA_2, lw=1.5, ls=(0, (4, 3)), zorder=3)
    ax.set_ylim(-0.6, len(full) - 0.2)
    ax.text(btc / 1000 + 3, len(full) - 0.45, f"Bitcoin, {mes_txt}: ${btc/1000:,.0f}k", fontsize=10, color=TINTA_2, va="center")
    ax.set_yticks(list(y))
    ax.set_yticklabels(full.flota, fontsize=11, color=TINTA)
    ax.set_xlim(0, full.btc_necesario_usd.max() / 1000 * 1.18)
    ax.xaxis.set_major_formatter(lambda x, _: f"${x:,.0f}k")
    ax.tick_params(axis="x", colors=TINTA_2, labelsize=9, length=0)
    ax.tick_params(axis="y", length=0)
    ax.grid(axis="x", color=GUIA, lw=0.6, alpha=0.6, zorder=0)
    for s in ax.spines.values():
        s.set_visible(False)
    lo, hi = full.btc_necesario_usd.min() / 1000, full.btc_necesario_usd.max() / 1000
    fig.suptitle(f"Bitcoin would need ${lo:,.0f}k to ${hi:,.0f}k for mining 1 MW to match AI hosting",
                 x=0.02, ha="left", fontsize=13, fontweight="bold", color=TINTA)
    fig.text(0.02, 0.855, f"AI hosting pays ${hosting:,.0f} per MW per day (TeraWulf / Fluidstack). Mining pays power at {LUZ_USD_KWH*100:.0f} cents/kWh.\n"
             f"Hashprice {mes_txt}: ${hp:.1f}/PH/day (blockchain.com).", fontsize=9, color=TINTA_2, linespacing=1.4)
    fig.text(0.02, 0.02, "A floor: when the price rises, hashrate follows and the bar moves up. github.com/Hoblayerta/mw-index",
             fontsize=8.5, color=TINTA_2)
    fig.subplots_adjust(left=0.24, right=0.97, top=0.76, bottom=0.14)
    fig.savefig(AQUI / "out" / "empate_btc.png", facecolor=FONDO)
    print(f"{mes_txt}: hashprice {hp:.1f}, BTC {btc:,.0f}, hosting {hosting:,.0f}")
    print(t.to_string(index=False))


if __name__ == "__main__":
    main()
