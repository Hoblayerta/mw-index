"""
Muestra de transacciones de runes y de stamps, leída directo de los bloques con la API pública de mempool.space.

- Runes: transacciones con runestone, es decir una salida OP_RETURN que empieza con OP_13 (script 6a5d).
  Cubre etchings y mints.
  Por grupo se leen bloques completos desde una altura de inicio hasta tener al menos 100 runestones, y de ahí se
  sortean 100 (semilla fija). No se toman las primeras: el bloque va ordenado por fee, y saldrían las que más pagaron.
- Stamps: la API no las distingue por tipo de salida, así que la lista de transacciones sale del indexador
  público stampchain.io (stamps clásicos y SRC-20, con su bloque), y el peso y el fee se leen de mempool.space.

Cada transacción es una sola: vB = peso / 4 y fee = fee de la transacción (no hay commit aparte).

Salida: data/muestra_runes_stamps.csv con las columnas que usa costo_por_inscripcion.py
(grupo, id, altura, hora_bloque, vb, costo).

Uso: python3 muestra_runes_stamps.py
"""
import csv
import json
import random
import time
import urllib.request
from pathlib import Path

AQUI = Path(__file__).parent
DATA = AQUI / "data"
DATA.mkdir(exist_ok=True)
API = "https://mempool.space/api"
POR_GRUPO = 100

GRUPOS = {
    # grupo: (altura de inicio, función que decide si la tx entra)
    "runes-lanzamiento": (840000, "runes"),      # bloque del halving, 20 abr 2024, cuando arrancó Runes
    "runes-sep-2026": (None, "runes"),           # la altura sale de la fecha 15 sep 2026
    "stamps-abr-2023": (None, "stamps"),         # stamps clásicos #15,900 en adelante, abril 2023
    "src20-dic-2023": (820623, "src20"),         # ola de SRC-20, diciembre 2023
}
STAMPCHAIN = "https://stampchain.io/api/v2"
FECHA_SEP_2026 = 1789430400  # 2026-09-15 00:00 UTC


def get(url, texto=False):
    req = urllib.request.Request(url, headers={"User-Agent": "muestra-runes-stamps/0"})
    for intento in range(5):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                b = r.read().decode()
                return b if texto else json.loads(b)
        except Exception:
            time.sleep(3 * (intento + 1))
    raise RuntimeError(f"no contestó: {url}")


def es_runes(tx):
    return any(o["scriptpubkey_type"] == "op_return" and o["scriptpubkey"].startswith("6a5d") for o in tx["vout"])


FILTROS = {"runes": es_runes}


def txids_stamps(grupo, altura, tipo):
    """Lista de transacciones de stampchain.io: 100 stamps clásicos, o los SRC-20 bloque por bloque."""
    if tipo == "stamps":
        return [d["tx_hash"] for d in get(f"{STAMPCHAIN}/stamps?limit={POR_GRUPO}&sort=ASC&page=160")["data"]]
    ids = []
    while len(ids) < POR_GRUPO:
        ids += [d["tx_hash"] for d in get(f"{STAMPCHAIN}/src20/block/{altura}?limit=100")["data"]]
        print(f"{grupo}: bloque {altura}, llevo {len(ids)}")
        altura += 1
    return ids[:POR_GRUPO]


def leer_txs(grupo, ids):
    filas = []
    for txid in ids:
        tx = get(f"{API}/tx/{txid}")
        filas.append({"grupo": grupo, "id": txid, "altura": tx["status"]["block_height"],
                      "hora_bloque": tx["status"]["block_time"], "vb": tx["weight"] / 4, "costo": tx["fee"]})
        time.sleep(0.2)
    return filas


def muestrear(grupo, altura, filtro):
    filas = []
    while len(filas) < POR_GRUPO:
        bh = get(f"{API}/block-height/{altura}", texto=True).strip()
        b = get(f"{API}/block/{bh}")
        for inicio in range(0, b["tx_count"], 25):
            for tx in get(f"{API}/block/{bh}/txs/{inicio}"):
                if tx["fee"] and FILTROS[filtro](tx):
                    filas.append({"grupo": grupo, "id": tx["txid"], "altura": altura,
                                  "hora_bloque": b["timestamp"], "vb": tx["weight"] / 4, "costo": tx["fee"]})
            time.sleep(0.2)
        print(f"{grupo}: bloque {altura}, llevo {len(filas)}")
        altura += 1
    random.seed(0)
    return sorted(random.sample(filas, POR_GRUPO), key=lambda f: (f["altura"], f["id"]))


def main():
    salida = DATA / "muestra_runes_stamps.csv"
    hechas = {}
    if salida.exists():
        for f in csv.DictReader(open(salida)):
            hechas.setdefault(f["grupo"], []).append(f)
    todas = []
    for grupo, (altura, filtro) in GRUPOS.items():
        if len(hechas.get(grupo, [])) == POR_GRUPO:
            todas += hechas[grupo]
        elif filtro in ("stamps", "src20"):
            todas += leer_txs(grupo, txids_stamps(grupo, altura, filtro))
        else:
            if altura is None:
                altura = get(f"{API}/v1/mining/blocks/timestamp/{FECHA_SEP_2026}")["height"]
            todas += muestrear(grupo, altura, filtro)
        # se guarda lo hecho más lo que ya estaba, para no perder grupos si se corta
        pendientes = [f for g in list(GRUPOS)[len({x["grupo"] for x in todas}):] for f in hechas.get(g, [])]
        with open(salida, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=["grupo", "id", "altura", "hora_bloque", "vb", "costo"])
            w.writeheader()
            w.writerows(todas + pendientes)


if __name__ == "__main__":
    main()
