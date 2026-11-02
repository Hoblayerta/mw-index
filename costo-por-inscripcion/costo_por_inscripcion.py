"""
Costo energético realizado por inscripción, rune y stamp, v0.
Para cada inscripción de la muestra: qué parte de la energía de su bloque le toca según los vB que ocupó
(reveal más la parte del commit), contra el fee que pagó.

Entrada: la muestra de 400 inscripciones (100 por colección) de 03-producto/tabla-colecciones/datos/costo-inscripcion-muestra.csv,
que ya trae altura, hora del bloque, vB y fee pagado (ver tabla-colecciones/fuente-de-datos.md).
Si existe data/muestra_runes_stamps.csv (sale de muestra_runes_stamps.py), se suman sus grupos de runes y stamps.
Datos nuevos, de la API pública de mempool.space (se guardan en data/):
  - peso de cada bloque:      /api/block-height/<h> y /api/block/<hash>
  - hashrate diario:          /api/v1/mining/hashrate/all
  - precio BTC de ese día:    /api/v1/historical-price?currency=USD&timestamp=<t>

Energía del bloque (kWh) = hashrate del día (TH/s) x J/TH x 600 / 3,600,000
Energía de la inscripción = energía del bloque x vB de la inscripción / vB del bloque (peso / 4)

Uso: python3 costo_por_inscripcion.py
"""
import csv
import json
import statistics
import time
import urllib.request
from pathlib import Path

AQUI = Path(__file__).parent
DATA = AQUI / "data"
OUT = AQUI / "out"
DATA.mkdir(exist_ok=True)
OUT.mkdir(exist_ok=True)
MUESTRA = AQUI.parents[1] / "tabla-colecciones" / "datos" / "costo-inscripcion-muestra.csv"
MUESTRA_RUNES_STAMPS = DATA / "muestra_runes_stamps.csv"  # sale de muestra_runes_stamps.py
API = "https://mempool.space/api"

SUPUESTOS = {
    "j_por_th": {"nueva": 13.5, "media": 17.5, "vieja": 29.5},  # mismas flotas que el índice de 1 MW
    "usd_kwh": 0.048,
    "segundos_por_bloque": 600,
}


def get(url, texto=False):
    req = urllib.request.Request(url, headers={"User-Agent": "costo-por-inscripcion/0"})
    for intento in range(4):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                b = r.read().decode()
                return b if texto else json.loads(b)
        except Exception:
            time.sleep(2 * (intento + 1))
    raise RuntimeError(f"no contestó: {url}")


def cache(nombre, fn):
    p = DATA / nombre
    if p.exists():
        return json.loads(p.read_text())
    v = fn()
    p.write_text(json.dumps(v))
    return v


def cache_por_llave(nombre, llaves, fn):
    """Como cache, pero baja solo las llaves que faltan."""
    p = DATA / nombre
    v = json.loads(p.read_text()) if p.exists() else {}
    faltan = [k for k in llaves if str(k) not in v]
    for k in faltan:
        v[str(k)] = fn(k)
        time.sleep(0.3)
    if faltan:
        p.write_text(json.dumps(v))
    return v


def main():
    filas = list(csv.DictReader(open(MUESTRA)))
    if MUESTRA_RUNES_STAMPS.exists():
        filas += list(csv.DictReader(open(MUESTRA_RUNES_STAMPS)))
    alturas = sorted({int(f["altura"]) for f in filas})

    def bajar_bloque(h):
        bh = get(f"{API}/block-height/{h}", texto=True).strip()
        b = get(f"{API}/block/{bh}")
        return {"hash": bh, "weight": b["weight"], "timestamp": b["timestamp"], "tx_count": b["tx_count"]}

    bloques = cache_por_llave("bloques.json", alturas, bajar_bloque)
    hashrate = cache("hashrate_all.json", lambda: get(f"{API}/v1/mining/hashrate/all"))["hashrates"]
    hr_por_dia = {h["timestamp"] // 86400: h["avgHashrate"] for h in hashrate}

    dias = sorted({int(f["hora_bloque"]) // 86400 for f in filas})

    def bajar_precio(d):
        return get(f"{API}/v1/historical-price?currency=USD&timestamp={d * 86400 + 43200}")["prices"][0]["USD"]

    precios = cache_por_llave("precios.json", dias, bajar_precio)

    s = SUPUESTOS
    salida = []
    for f in filas:
        b = bloques[f["altura"]]
        dia = int(f["hora_bloque"]) // 86400
        th_s = hr_por_dia.get(dia) or hr_por_dia[min(hr_por_dia, key=lambda k: abs(k - dia))]
        th_s = th_s / 1e12
        vb_bloque = b["weight"] / 4
        parte = float(f["vb"]) / vb_bloque
        precio = precios[str(dia)]
        fila = {"grupo": f["grupo"], "id": f["id"], "altura": f["altura"], "hora_bloque": f["hora_bloque"],
                "vb": round(float(f["vb"]), 2), "vb_bloque": vb_bloque, "eh_s": round(th_s / 1e6, 1),
                "fee_sats": float(f["costo"]), "btc_usd": precio,
                "fee_usd": float(f["costo"]) / 1e8 * precio}
        for flota, j in s["j_por_th"].items():
            kwh_bloque = th_s * j * s["segundos_por_bloque"] / 3.6e6
            fila[f"kwh_{flota}"] = kwh_bloque * parte
            fila[f"energia_usd_{flota}"] = fila[f"kwh_{flota}"] * s["usd_kwh"]
        fila["fee_pct_energia_media"] = 100 * fila["fee_usd"] / fila["energia_usd_media"]
        salida.append(fila)

    with open(OUT / "inscripciones.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(salida[0]))
        w.writeheader()
        w.writerows(salida)

    med = statistics.median
    resumen = []
    for g in dict.fromkeys(x["grupo"] for x in salida):
        fs = [x for x in salida if x["grupo"] == g]
        r = {"grupo": g, "n": len(fs), "desde": time.strftime("%Y-%m-%d", time.gmtime(min(int(x["hora_bloque"]) for x in fs))),
             "hasta": time.strftime("%Y-%m-%d", time.gmtime(max(int(x["hora_bloque"]) for x in fs))),
             "eh_s": med(x["eh_s"] for x in fs), "vb_mediana": med(x["vb"] for x in fs),
             "fee_usd_mediana": med(x["fee_usd"] for x in fs)}
        for flota in s["j_por_th"]:
            r[f"kwh_{flota}_mediana"] = med(x[f"kwh_{flota}"] for x in fs)
            r[f"energia_usd_{flota}_mediana"] = med(x[f"energia_usd_{flota}"] for x in fs)
        r["fee_pct_energia_media_mediana"] = med(x["fee_pct_energia_media"] for x in fs)
        resumen.append(r)
    with open(OUT / "resumen_por_coleccion.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(resumen[0]))
        w.writeheader()
        w.writerows(resumen)
    for r in resumen:
        print(f"{r['grupo']:18} {r['desde']}..{r['hasta']}  n={r['n']}  {r['eh_s']:.0f} EH/s  vB={r['vb_mediana']:.0f}  "
              f"kWh 13.5/17.5/29.5 = {r['kwh_nueva_mediana']:.0f}/{r['kwh_media_mediana']:.0f}/{r['kwh_vieja_mediana']:.0f}  "
              f"energia 17.5 = US${r['energia_usd_media_mediana']:.2f}  fee = US${r['fee_usd_mediana']:.2f}  "
              f"fee/energia = {r['fee_pct_energia_media_mediana']:.0f}%")


if __name__ == "__main__":
    main()
