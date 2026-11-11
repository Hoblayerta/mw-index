"""
ASIC prices in USD per TH, by efficiency tier, from Hashrate Index's ASIC Price Index (Luxor).

Hashrate Index puts the index behind its paid tiers. The Block publishes the same series,
with Luxor as the source, on a free public chart:
  https://www.theblock.co/data/on-chain-metrics/bitcoin/bitcoin-asic-price-index
This script reads the data file behind that chart, no login, and writes:
  asic_precio_diario.csv   raw daily values since 2024-08-01 (the index updates weekly,
                           so values repeat between updates)
  asic_precio.csv          monthly average per tier, one source URL per row

Run: python3 leer_asic_precio.py   (standard library only)
"""
import csv
import json
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

AQUI = Path(__file__).resolve().parent
PAGINA = "https://www.theblock.co/data/on-chain-metrics/bitcoin/bitcoin-asic-price-index"
DATOS = "https://data.tbstat.com/dashboard/onchainmetrics_bitcoin_asicpriceindex_daily_other.json"
DESDE = "2024-08-01"
# nombre de la serie en la fuente -> columna
TIERS = {
    "Under 14 J/TH": "usd_th_menos_14",
    "14-19 J/TH": "usd_th_14_19",
    "19-25 J/TH": "usd_th_19_25",
    "25-38 J/TH": "usd_th_25_38",
}


def main():
    req = urllib.request.Request(DATOS, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        crudo = json.load(r)
    leido = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    dias = defaultdict(dict)
    for serie, col in TIERS.items():
        for p in crudo["Series"][serie]["Data"]:
            if p["Result"] is None:
                continue
            dia = datetime.fromtimestamp(p["Timestamp"], timezone.utc).strftime("%Y-%m-%d")
            if dia >= DESDE:
                dias[dia][col] = p["Result"]

    cols = list(TIERS.values())
    with open(AQUI / "asic_precio_diario.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["dia"] + cols + ["fuente", "leido"])
        for dia in sorted(dias):
            w.writerow([dia] + [dias[dia].get(c, "") for c in cols] + [DATOS, leido])

    meses = defaultdict(lambda: defaultdict(list))
    for dia, vals in dias.items():
        for c, v in vals.items():
            meses[dia[:7]][c].append(v)
    with open(AQUI / "asic_precio.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["mes"] + cols + ["ultimo_dia_con_dato", "tipo", "fuente", "leido"])
        for mes in sorted(meses):
            ultimo = max(d for d in dias if d.startswith(mes))
            fila = [round(sum(meses[mes][c]) / len(meses[mes][c]), 2) if meses[mes][c] else ""
                    for c in cols]
            w.writerow([mes] + fila + [ultimo, "prom_mensual_de_diario", PAGINA, leido])

    print(f"leido {leido}; ultimo dia con dato {max(dias)}")


if __name__ == "__main__":
    main()
