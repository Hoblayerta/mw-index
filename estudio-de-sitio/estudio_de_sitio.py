"""
Estudio de sitio, v0: la hoja que recibe un operador.

Entradas (las 4 que cambian por operador):
  --mw      MW del sitio
  --tarifa  tarifa de luz, USD/MWh
  --jth     eficiencia de la flota, J/TH
  --pue     PUE de la carga de IA
  --mw-ia   (opcional) MW que el operador piensa pasar a IA; sale marcado en la mezcla
  --capital (opcional) USD que el operador puede poner; dice cuántos MW alcanza a pasar
  --entradas sitios/<sitio>.json: las entradas de un operador real con la fuente de cada una
            (tipo public, derived o assumed); reemplaza --mw, --tarifa, --jth, --pue y --sitio,
            y puede traer "renta" (USD por MW de red al año) si el sitio tiene una renta pública

Los números salen de ../mw_model.py y de ../data/*.csv: el script cambia
usd_kwh y pue en SUPUESTOS y llama las funciones del modelo. Lo único que no
viene del modelo es el capex de hosting y que la luz la paga el inquilino
(CAPEX_HOSTING_IT y FUENTES_HOSTING, de documentos de SEC leídos el 2 nov 2026). Antes de calcular, comprueba que el modelo con sus supuestos de fábrica
reproduce ../out/tabla_mw.csv; si no, se detiene.

Escribe en out/: <slug>.html (la hoja), <slug>.pdf (si hay chromium) y
<slug>.csv (los números crudos de la hoja).

Mezcla: el sitio parte sus MW entre minar y alojar IA (0, 25, 50, 75 y 100% a IA,
más --mw-ia si viene). Por cada mezcla, el neto del sitio en cada uno de los
últimos 8 meses, cuántos quedan en cero o abajo, qué parte del ingreso viene del
contrato del inquilino y el capex de la parte de IA. Solo hosting: es el ingreso
con contrato, el que un prestamista puede valuar.

Ejemplo:
  python3 estudio_de_sitio.py --mw 20 --tarifa 50 --jth 27 --pue 1.3 \
      --sitio "Fictional site" --ejemplo
"""
import argparse
import json
import datetime as dt
import html
import re
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent
sys.path.insert(0, str(RAIZ))
import mw_model  # noqa: E402

N_MESES = 8
SEGMENTOS = {"marketplace": "marketplace median", "indice_mixto": "mixed index",
             "contrato_1y": "1-year contract", "compuesto": "composite"}
REPO = "github.com/Hoblayerta/mw-index"

# ---------- fuera del modelo: capex de hosting y quién paga la luz ----------
# Leído el 2 nov 2026 en documentos públicos de SEC. USD por MW de IT crítico.
CAPEX_HOSTING_IT = (8_000_000, 11_000_000)
FUENTES_HOSTING = [
    ("TeraWulf, Fluidstack deal, 14 Aug 2025: $8-10M per MW of critical IT load, modified gross lease",
     "https://www.sec.gov/Archives/edgar/data/1083301/000110465925078084/tm2523008d2_ex99-1.htm"),
    ("TeraWulf, Abernathy JV deck, Oct 2025: $8-10M per critical MW, \"Power 100% passed-through to tenant\"",
     "https://www.sec.gov/Archives/edgar/data/0001083301/000110465925102858/tm2529509d1_ex99-3.htm"),
    ("Cipher, Fluidstack deal, 25 Sep 2025: $9-11M per MW of critical IT load, modified gross lease, power terms not stated",
     "https://www.sec.gov/Archives/edgar/data/1819989/000095010325012168/dp234624_ex9901.htm"),
]


# ---------- fuera del modelo: deuda, obra y arranque del inquilino ----------
# Leído el 4 nov 2026. La estructura es la de USD.AI (presta contra GPUs, no contra
# edificios; aquí se usa como referencia para la parte de IA).
ANTICIPO = 0.80          # USD.AI: "covers up to 80% of the deployment cost"
RESERVA_MESES = 3        # USD.AI: "a three-month debt-service reserve is funded at closing"
DSCR_MIN = 1.15          # USD.AI: DSCR mínimo, trimestral
PLAZOS = (5, 10)         # USD.AI: 3 a 5 años; 10 = base del contrato de TeraWulf y de Cipher con Fluidstack
TASAS = (0.10, 0.15)     # American Compute, 10 oct 2026: préstamos on-chain a operadores chicos (USD.AI)
OBRA_MESES = 12          # de la firma a la primera renta: Cipher 25 sep 2025 -> oct 2026; TeraWulf 14 ago 2025 -> CB-3 jul 2026
ARRANQUE_MESES = 6       # TeraWulf: fase 1 (~40 de 200 MW) en 1S 2026 y todo a fin de 2026
# Costos del sitio: lo que queda de la renta después de operación, predial y seguro (margen NOI).
MARGEN_NOI = (0.85, 0.70)  # TeraWulf ago 2025 y Cipher sep 2025: 85%; TeraWulf Abernathy oct 2025: ~70% promedio
FUENTES_DEUDA = [
    ("USD.AI underwriting: 80% of deployment cost, 20% equity, 3 to 5 years with equal monthly principal, 3-month debt-service reserve, 1.15x DSCR; finances GPUs in Tier III/IV sites",
     "https://usd.ai/blog/usdai-underwriting-and-risk-management"),
    ("American Compute, GPU loan spreads and interest rates, updated 10 Oct 2026: onchain loans to smaller operators 10.00-15.00% (observed public prices, not quotes)",
     "https://www.amcompute.com/gpu-debt/pricing"),
    ("TeraWulf, 14 Aug 2025: 10-year Fluidstack leases, phase one ~40 MW online 1H 2026, full 200+ MW by year-end 2026",
     "https://www.sec.gov/Archives/edgar/data/1083301/000110465925078084/tm2523008d2_ex99-1.htm"),
    ("TeraWulf Q2 2026 results, 5 Aug 2026: CB-3 delivered early July 2026; CB-4 phased rent in 2H 2026; CB-5 slipped to early 2027",
     "https://www.sec.gov/Archives/edgar/data/0001083301/000108330126000162/a_wulfearningsreleaseq22026.htm"),
    ("Cipher business update, 24 Feb 2026: Barber Lake (Fluidstack, signed 25 Sep 2025) 10-year lease, start Oct 2026",
     "https://www.sec.gov/Archives/edgar/data/1819989/000181998926000007/cipherdigital_businessup.htm"),
    ("Site costs as NOI margin (rent less property operating expenses, property taxes and insurance): TeraWulf 14 Aug 2025, 85%; Cipher 25 Sep 2025, 80-85%; TeraWulf Abernathy JV deck Oct 2025, ~70% average over lease life",
     "https://www.sec.gov/Archives/edgar/data/0001083301/000110465925102858/tm2529509d1_ex99-3.htm"),
]

# Quién paga la obra: tres estructuras públicas además de "la pagas tú" (leído 5 nov 2026).
EMPERY = {"pagos": 440e6, "anios": 15, "mw": 150}          # pagos de renta triple neto al dueño del sitio
ABERNATHY = {"mw_it": 168, "bonos": 1.3e9, "tasa_bonos": 0.0725, "noi_anual": 260e6,
             "capex_it": (8e6, 10e6), "parte_dueno": 0.501}
MACQUARIE = {"por_mw": 2.25e6, "tasa": 0.1275}             # capital preferente por MW rentado
FUENTES_OBRA = [
    ("Empery Digital proxy, Sep 2026: $65M for 25% of a 150 MW Midwest site; detailed LOI for a triple net lease, tenant funds all build-out and operating costs; payments of more than $440M over 15 years from early 2027",
     "https://www.sec.gov/Archives/edgar/data/0001829794/000168316826007266/empery_defa14a.htm"),
    ("TeraWulf, Abernathy JV, Oct 2025: TeraWulf 50.1%, Fluidstack 49.9%; 168 MW of critical IT; ~$9.5B of rent over 25 years; ~$260M average annual site NOI; build cost $8-10M per critical MW; $1.3B of bonds at 7.25%",
     "https://www.sec.gov/Archives/edgar/data/1083301/000110465925102858/tm2529509d1_8k.htm"),
    ("Applied Digital 8-K, Jan 2025: Macquarie invests $2.25M per MW of leased capacity in perpetual preferred units at 12.75%, minimum 1.80x multiple, plus 15% of the HPC business's common equity; requires an executed lease",
     "https://www.sec.gov/Archives/edgar/data/1144879/000149315225002040/form8-k.htm"),
]

# Quién puede poner la caja en lugar del operador (leído 2 y 4 nov 2026).
QUIEN_PONE = [
    ("The tenant, as a JV partner", "TeraWulf's Abernathy JV: TeraWulf 50.1% (can rise to 51%), Fluidstack 49.9% (Oct 2025). The deck does not say how much equity each puts in.",
     "https://www.sec.gov/Archives/edgar/data/0001083301/000110465925102858/tm2529509d1_ex99-3.htm"),
    ("A GPU host's capital arm", "Hydra Capital: $15M to $250M+, JV \"from as little as 5% down\"; no published offtake or tier rules.",
     "https://hydrahost.com/financing/"),
    ("Convertible-note investors", "Blockfusion (50 MW): term sheet for $175M of convertible notes with Sona Asset Management, on a non-binding LOI (TheEnergyMag, 1 Jul 2026).",
     "https://www.theenergymag.com/news/2026-07-01/blockfusion-ai-bitcoin-spac"),
    ("The operator's own bitcoin", "PowerCompute (26 MW) borrowed from Arch against 307 BTC, closed by selling 267.3 BTC (8-K, 30 Sep 2026).",
     "https://www.sec.gov/Archives/edgar/data/0001640384/000119312526408391/lmfa-ex99_1.htm"),
]
NO_REEMPLAZA = ("A backstop like Google's on TeraWulf's and Cipher's Fluidstack leases supports the tenant's rent, "
                "which helps the debt, but it is not equity.")
FALTA_QUIEN = ("No source shows anyone putting up the 20% for a 5 to 50 MW site without a signed tenant, "
               "or a tenant prepaying rent to fund the build.")



# ---------- comprobación: el modelo reproduce su CSV ----------
def comprobar_modelo():
    df, _ = mw_model.cargar()
    df = mw_model.construir(df)
    tabla = pd.read_csv(RAIZ / "out" / "tabla_mw.csv")
    cols = ["mina_vieja_neto", "mina_media_neto", "mina_nueva_neto", "hosting", "gpu_neto"]
    calc = df[["mes"] + cols].copy()
    calc["mes"] = calc["mes"].astype(str)
    m = tabla.merge(calc, on="mes", suffixes=("_csv", "_calc"))
    for c in cols:
        a, b = m[f"{c}_csv"], m[f"{c}_calc"].round(0)
        ok = (a.isna() & b.isna()) | (a == b)
        if not ok.all():
            raise SystemExit(f"El modelo ya no reproduce tabla_mw.csv en {c}: {m.loc[~ok, 'mes'].tolist()}")
    return len(m)


# ---------- cálculo del sitio ----------
def calcular(mw, tarifa, jth, pue, renta=None):
    s = mw_model.SUPUESTOS
    s["usd_kwh"] = tarifa / 1000
    s["pue"] = pue

    hp = pd.read_csv(RAIZ / "data" / "hashprice.csv").dropna(subset=["hashprice_usd_ph_dia"])
    hp = hp.sort_values("mes").tail(N_MESES).reset_index(drop=True)
    meses = []
    for _, r in hp.iterrows():
        bruto, neto = mw_model.ingreso_mina_usd_mw_dia(r["hashprice_usd_ph_dia"], jth)
        meses.append({"mes": r["mes"], "hashprice": r["hashprice_usd_ph_dia"],
                      "bruto_mw_dia": bruto, "neto_mw_dia": neto, "tipo": r["tipo"], "fuente": r["fuente"]})
    ultimo = meses[-1]

    h100 = pd.read_csv(RAIZ / "data" / "h100.csv").sort_values("mes")
    h100_mes = h100["mes"].iloc[-1]
    h100_filas = h100[h100["mes"] == h100_mes]
    h100_precio = h100_filas["h100_usd_hora"].mean()  # mismo promedio por mes que el modelo
    _, gpu_neto = mw_model.ingreso_gpu_usd_mw_dia(h100_precio)

    hosting = mw_model.ingreso_hosting_usd_mw_dia() if renta is None else renta / 365

    ph_por_mw = (1e6 / jth) / 1000
    luz_mw_dia = 1000 * 24 * s["usd_kwh"]
    equilibrio = luz_mw_dia / ph_por_mw  # hashprice donde el neto es 0

    return {
        "meses": meses,
        "mina": ultimo["neto_mw_dia"],
        "mina_mes": ultimo["mes"],
        "mina_hp": ultimo["hashprice"],
        "mina_min": min(m["neto_mw_dia"] for m in meses),
        "mina_max": max(m["neto_mw_dia"] for m in meses),
        "meses_en_cero": sum(1 for m in meses if m["neto_mw_dia"] <= 0),
        "equilibrio": equilibrio,
        "hosting": hosting,
        "gpu": gpu_neto,
        "h100_mes": h100_mes,
        "h100_precio": h100_precio,
        "h100_fuente": "; ".join(h100_filas["fuente"]),
        "h100_segmento": "; ".join(SEGMENTOS.get(x, x) for x in h100_filas["segmento"]),
        "gpus_por_mw": s["h100_por_mw_it"] / pue,
        "capex_mina": s["capex_mina_usd_mw"],
        "capex_gpu": s["capex_ia_usd_mw"],
        "capex_hosting": tuple(x / pue for x in CAPEX_HOSTING_IT),  # por MW de red, como el resto
        "s": dict(s),
    }


def mezclas(mw, r, mw_ia=None):
    """Parte los MW del sitio entre minar y alojar IA y mide cada mezcla en los mismos meses."""
    partes = sorted({mw * f for f in (0, .25, .5, .75, 1)} | ({min(max(mw_ia, 0), mw)} if mw_ia is not None else set()))
    hl, hh = r["capex_hosting"]
    filas = []
    for ia in partes:
        mina = mw - ia
        contrato = ia * r["hosting"]
        netos = [mina * m["neto_mw_dia"] + contrato for m in r["meses"]]
        bruto_ult = mina * r["meses"][-1]["bruto_mw_dia"] + contrato
        filas.append({
            "mw_ia": ia, "mw_mina": mina,
            "neto_ult": netos[-1], "peor": min(netos),
            "en_cero": sum(1 for x in netos if x <= 0),
            "contrato": contrato / bruto_ult if bruto_ult > 0 else None,
            "capex": (hl * ia, hh * ia),
            "caja": (r["caja_mw"][0] * ia, r["caja_mw"][1] * ia),
            "plan": mw_ia is not None and abs(ia - min(max(mw_ia, 0), mw)) < 1e-9,
        })
    return filas


def financiar(hosting_dia, capex_mw, margen, mina_dia, tasa, plazo, horizonte=240, anticipo=None, dscr_min=None):
    """Un MW de red que pasa a hosting, mes por mes desde la firma.

    Obra: el préstamo se desembolsa parejo y sus intereses se pagan cada mes, sin renta.
    El MW deja de minar desde la firma (pierde mina_dia). Desde la primera renta: arranque
    lineal del inquilino, renta neta de costos del sitio (margen NOI) y principal mensual igual."""
    anticipo = ANTICIPO if anticipo is None else anticipo
    dscr_min = DSCR_MIN if dscr_min is None else dscr_min
    prestamo = anticipo * capex_mw
    principal = prestamo / (12 * plazo)
    renta_llena = hosting_dia * 365 / 12 * margen
    mina_mes = mina_dia * 365 / 12
    saldo, flujos, servicio, renta = prestamo, [], [], []
    intereses_obra = 0.0
    for m in range(horizonte):
        if m < OBRA_MESES:
            interes = prestamo * (m + 1) / OBRA_MESES * tasa / 12
            intereses_obra += interes
            flujos.append(-interes - mina_mes); servicio.append(0.0); renta.append(0.0)
            continue
        ingreso = renta_llena * min(1, (m - OBRA_MESES + 1) / ARRANQUE_MESES)
        pago = principal + saldo * tasa / 12 if saldo > 1e-6 else 0.0
        saldo = max(0.0, saldo - principal)
        flujos.append(ingreso - pago - mina_mes); servicio.append(pago); renta.append(ingreso)
    reserva = sum(servicio[OBRA_MESES:OBRA_MESES + RESERVA_MESES])
    capital = (1 - anticipo) * capex_mw
    mina_obra = mina_mes * OBRA_MESES
    caja = capital + reserva + intereses_obra + mina_obra
    lleno = OBRA_MESES + ARRANQUE_MESES
    dscr = sum(renta[lleno:lleno + 12]) / sum(servicio[lleno:lleno + 12])
    acumulado, payback = -(capital + reserva), None
    for m, f in enumerate(flujos):
        acumulado += f
        if acumulado >= 0 and m >= OBRA_MESES:
            payback = m + 1
            break
    neto_mes = (sum(renta[lleno:lleno + 12]) - sum(servicio[lleno:lleno + 12])) / 12 - mina_mes
    return {"caja_inicial": caja, "capital": capital, "reserva": reserva, "neto_mes_lleno": neto_mes,
            "intereses_obra": intereses_obra, "mina_obra": mina_obra,
            "dscr": dscr, "payback_meses": payback, "pasa": dscr >= dscr_min}


def escenarios_deuda(r, casos=None, dscr_min=None):
    """Cada caso en dos lados: favorable (capex bajo, margen alto) y desfavorable (capex alto, margen bajo).

    Sin `casos`, la estructura de USD.AI (PLAZOS x TASAS, ANTICIPO). Con `casos` (del JSON del sitio,
    "deuda"), cada uno trae nombre, anticipo, tasa y plazo propios, y dscr_min aplica a todos."""
    mina_dia = float(np.mean([m["neto_mw_dia"] for m in r["meses"]]))
    if not casos:
        casos = [{"nombre": None, "anticipo": ANTICIPO, "tasa": t, "plazo": p} for p in PLAZOS for t in TASAS]
    filas = []
    for c in casos:
        args = dict(anticipo=c["anticipo"], dscr_min=dscr_min)
        bajo = financiar(r["hosting"], r["capex_hosting"][0], MARGEN_NOI[0], mina_dia, c["tasa"], c["plazo"], **args)
        alto = financiar(r["hosting"], r["capex_hosting"][1], MARGEN_NOI[1], mina_dia, c["tasa"], c["plazo"], **args)
        corta = f"{c['plazo']:g}-year loan at {c['tasa']:.1%}" if c["nombre"] else f"{c['plazo']}-year loan at {c['tasa']:.0%}"
        etiqueta = (f"{c['nombre']}: {c['anticipo']:.0%} loan, {c['plazo']:g} yr at {c['tasa']:.1%}" if c["nombre"]
                    else f"{c['plazo']} years at {c['tasa']:.0%}")
        filas.append({"plazo": c["plazo"], "tasa": c["tasa"], "anticipo": c["anticipo"], "nombre": c["nombre"],
                      "etiqueta": etiqueta, "corta": (f"{c['nombre']} ({corta})" if c["nombre"] else corta),
                      "bajo": bajo, "alto": alto})
    return filas, mina_dia


def escenarios_obra(r, pue):
    """Cuatro formas de pagar la obra de hosting, por MW de red: caja propia y neto al mes (primer año a renta llena).

    Todas restan la minería que esos MW dejan (promedio de los últimos meses). Los MW de Abernathy y Macquarie
    son de IT; se pasan a MW de red con el PUE del sitio."""
    mina_mes = r["mina_dia_media"] * 365 / 12
    base = r["caso_base"]
    filas = [{"nombre": f"You build it ({base['corta']})",
              "caja": (base["bajo"]["caja_inicial"], base["alto"]["caja_inicial"]),
              "neto": (base["bajo"]["neto_mes_lleno"], base["alto"]["neto_mes_lleno"]),
              "nota": "Current scenario: you put the equity, the reserve and the interest during construction; you keep all the rent net of site costs."}]
    renta_empery = EMPERY["pagos"] / EMPERY["anios"] / EMPERY["mw"] / 12
    filas.append({"nombre": "Tenant pays the build (Empery-type triple net lease)",
                  "caja": (0.0, 0.0), "neto": (renta_empery - mina_mes,) * 2,
                  "nota": f"You bring the site and its power; the tenant pays the build-out and operating costs. Rent = $440M / 15 years / 150 MW = {usd(renta_empery)} per MW per month (Empery does not say if MW are gross or IT)."})
    a = ABERNATHY
    deuda_it = a["bonos"] / a["mw_it"]
    caja_it = tuple(a["parte_dueno"] * max(0.0, c - deuda_it) for c in a["capex_it"])
    neto_it = a["parte_dueno"] * (a["noi_anual"] / a["mw_it"] - deuda_it * a["tasa_bonos"]) / 12
    filas.append({"nombre": f"Joint venture with the tenant (Abernathy-type, you {a['parte_dueno']:.1%})",
                  "caja": tuple(c / pue for c in caja_it), "neto": (neto_it / pue - mina_mes,) * 2,
                  "nota": f"Bonds of {usd_m(deuda_it)} per MW of IT at {a['tasa_bonos']:.2%} cover most of the {usd_m(a['capex_it'][0])} to {usd_m(a['capex_it'][1])} build; you put {a['parte_dueno']:.1%} of the rest and get {a['parte_dueno']:.1%} of NOI after interest. Bond principal payments not public: treated as interest-only (assumed)."})
    pref = MACQUARIE["por_mw"] / pue
    filas.append({"nombre": "Preferred equity covers your cash (Macquarie-type)",
                  "caja": tuple(max(0.0, base[k]["caja_inicial"] - pref) for k in ("bajo", "alto")),
                  "neto": tuple(base[k]["neto_mes_lleno"] - MACQUARIE["tasa"] * pref / 12 for k in ("bajo", "alto")),
                  "nota": f"{usd_m(MACQUARIE['por_mw'])} per leased MW (taken as MW of IT) at {MACQUARIE['tasa']:.2%} a year replaces your cash; Macquarie also took 15% of the common equity and required a signed lease."})
    return filas


def armar_obra(r):
    filas = []
    for f in r["obra"]:
        caja = "none" if f["caja"][1] == 0 else (usd_m(f["caja"][0]) if abs(f["caja"][0] - f["caja"][1]) < 1 else f"{usd_m(f['caja'][0])} to {usd_m(f['caja'][1])}")
        neto = usd(f["neto"][0]) if abs(f["neto"][0] - f["neto"][1]) < 1 else f"{usd(f['neto'][0])} to {usd(f['neto'][1])}"
        filas.append(f"<tr><th>{html.escape(f['nombre'])}<div class='basis'>{html.escape(f['nota'])}</div></th>"
                     f"<td class='capex'>{caja}</td><td class='num s'>{neto}</td></tr>")
    return "".join(filas)


# ---------- formato ----------
def usd(x, dec=0):
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "n/a"
    signo = "-" if x < 0 else ""
    return f"{signo}${abs(x):,.{dec}f}"


def usd_m(x):
    if x is None:
        return None
    if abs(x) >= 1e9:
        return f"${x/1e9:,.2f}B"
    if abs(x) < 1e5:
        return usd(x)
    return f"${x/1e6:,.2f}M"


def mes_txt(p):
    return dt.datetime.strptime(p, "%Y-%m").strftime("%b %Y")


def anios(capex, neto):
    if neto is None or neto <= 0:
        return None
    return capex / (neto * 365)


def hueco(txt):
    return f'<span class="gap">Not in model: {html.escape(txt)}</span>'


def meses_txt(m):
    return "not within 20 years" if m is None else f"{m} months ({m / 12:.1f} yr)"


def armar_deuda(r, solo_plazo=None):
    filas = []
    for f in r["deuda"]:
        if solo_plazo and f["plazo"] != solo_plazo:
            continue
        b, a = f["bajo"], f["alto"]
        pasa = "yes" if b["pasa"] and a["pasa"] else ("only favorable" if b["pasa"] else "no")
        filas.append(
            f"<tr><th>{html.escape(f['etiqueta'])}</th>"
            f"<td class='capex'>{usd_m(b['caja_inicial'])} to {usd_m(a['caja_inicial'])}</td>"
            f"<td class='num s'>{b['dscr']:.2f}x to {a['dscr']:.2f}x</td>"
            f"<td class='capex'>{pasa}</td>"
            f"<td class='capex'>{meses_txt(b['payback_meses'])} to {meses_txt(a['payback_meses'])}</td></tr>")
    return "".join(filas)


def respuesta(r, mw):
    """La respuesta en una frase: qué estructura pasa el DSCR, cuánta caja por MW y en cuánto regresa."""
    pasan = [f for f in r["deuda"] if f["bajo"]["pasa"]]
    if not pasan:
        return f"<b>Answer for this site:</b> none of these loans meets {r['dscr_min']}x coverage, so on this structure the AI part does not get financed."
    f = min(pasan, key=lambda x: x["bajo"]["payback_meses"] or 10**9)
    b = f["bajo"]
    alto = "also in the unfavorable case" if f["alto"]["pasa"] else "only in the favorable case (low capex, 85% margin)"
    cortos = [x for x in r["deuda"] if x["plazo"] == min(PLAZOS) and not x["nombre"]]
    corto = "" if not cortos or any(x["bajo"]["pasa"] for x in cortos) else f" On a {min(PLAZOS)}-year loan the rent does not cover the payment."
    return (f"<b>Answer for this site:</b> each MW moved to AI needs about {usd_m(b['caja_inicial'])} of your cash before first rent and gives it back "
            f"in {meses_txt(b['payback_meses'])} from signing, on {html.escape(f['corta'])}, {alto}.{corto} "
            f"How many of the {mw:g} MW go to AI is set by your cash: MW = your cash / {usd_m(b['caja_inicial'])} or more.")


def armar_caja(r, corto=False):
    """La caja de la página 1: cuánta caja propia por MW y quién podría ponerla."""
    f = r["caso_base"]
    b, a = f["bajo"], f["alto"]
    partes = (f"{1 - f['anticipo']:.0%} of capex {usd_m(b['capital'])} to {usd_m(a['capital'])}, "
              f"{RESERVA_MESES}-month reserve {usd_m(b['reserva'])} to {usd_m(a['reserva'])}, "
              f"interest during construction {usd_m(b['intereses_obra'])} to {usd_m(a['intereses_obra'])}, "
              f"mining given up {usd_m(b['mina_obra'])} to {usd_m(a['mina_obra'])}")
    quien = "".join(f"<li><b>{html.escape(n)}.</b> {html.escape(d)}</li>" for n, d, _ in QUIEN_PONE)
    if corto:
        nombres = ", ".join(n.lower() for n, _, _ in QUIEN_PONE)
        return (f"<div class='box'><p style='margin:0'><b>Own cash per MW moved to AI: {usd_m(b['caja_inicial'])} to {usd_m(a['caja_inicial'])}</b> "
                f"before first rent ({html.escape(f['corta'])}). For {r['mw']:g} MW all to AI: {usd_m(b['caja_inicial'] * r['mw'])} to {usd_m(a['caja_inicial'] * r['mw'])}. "
                f"Who has put up that cash instead, with public examples: {html.escape(nombres)}. "
                f"<span class='gap'>Missing:</span> {html.escape(FALTA_QUIEN)}</p></div>")
    return (f"<div class='box'><p style='margin:0 0 4px'><b>Own cash per MW moved to AI: {usd_m(b['caja_inicial'])} to {usd_m(a['caja_inicial'])}</b> "
            f"before first rent ({partes}; {html.escape(f['corta'])}, favorable to unfavorable case, page 2). "
            f"For {r['mw']:g} MW all to AI: {usd_m(b['caja_inicial'] * r['mw'])} to {usd_m(a['caja_inicial'] * r['mw'])}.</p>"
            f"<p style='margin:0 0 2px'><b>Who could put up that cash instead, with public examples:</b></p><ul class='small'>{quien}"
            f"<li>{html.escape(NO_REEMPLAZA)}</li></ul>"
            f"<p style='margin:4px 0 0' class='small'><span class='gap'>Missing:</span> {html.escape(FALTA_QUIEN)}</p></div>")


def armar_mezcla(r):
    filas = []
    for f in r["mezcla"]:
        nota = " <span class='plan'>your plan</span>" if f["plan"] else ""
        capex = "none" if f["mw_ia"] == 0 else f"{usd_m(f['capex'][0])} to {usd_m(f['capex'][1])}"
        filas.append(
            f"<tr{' class="mine"' if f['plan'] else ''}><th>{f['mw_mina']:g} mining / {f['mw_ia']:g} AI{nota}</th>"
            f"<td class='num s'>{usd(f['neto_ult'])}</td><td class='num s'>{usd(f['peor'])}</td>"
            f"<td class='num s'>{f['en_cero']} of {N_MESES}</td>"
            f"<td class='num s'>{'n/a' if f['contrato'] is None else f'{f['contrato']:.0%}'}</td>"
            f"<td class='capex'>{capex}</td>"
            f"<td class='capex'>{'none' if f['mw_ia'] == 0 else usd_m(f['caja'][0]) + ' to ' + usd_m(f['caja'][1])}</td></tr>")
    return "".join(filas)


def armar_html(sitio, mw, tarifa, jth, pue, r, ejemplo, generado, una_hoja=False, completo=""):
    s = r["s"]
    e = html.escape
    banner = '<div class="example">EXAMPLE, fictional site</div>' if ejemplo else ""
    if r.get("entradas") and not ejemplo:
        if any(d["tipo"] == "operator" for d in r["entradas"].values()):
            banner = '<div class="example public operador">Inputs from the operator, marked below. Model and market data are public.</div>'
        else:
            banner = '<div class="example public">Built from public data only. Not reviewed by the operator.</div>'
    origen = ""
    if r.get("entradas"):
        etiqueta = {"operator": "From the operator", "public": "Public", "derived": "Derived", "assumed": "ASSUMED"}
        nombres = {"mw": "Site power", "tarifa": "Power price", "jth": "Fleet efficiency", "pue": "PUE for AI load", "renta": "Hosting rent"}
        filas_o = []
        for k in ("mw", "tarifa", "jth", "pue", "renta"):
            d = r["entradas"].get(k)
            if not d:
                continue
            tag = etiqueta[d["tipo"]]
            tag = f"<span class='gap'>{tag}</span>" if d["tipo"] == "assumed" else f"<b>{tag}</b>"
            link = f" ({e(d['url'])})" if d.get("url") and not una_hoja else ""
            filas_o.append(f"<li>{nombres[k]}: {tag}. {e(d['fuente'])}{link}</li>")
        origen = f"<ul class='small origen'>{''.join(filas_o)}</ul>"

    hl, hh = r["capex_hosting"]
    pb_h = (anios(hl, r["hosting"]), anios(hh, r["hosting"]))
    pb_g = anios(r["capex_gpu"], r["gpu"])
    filas = [
        ("Keep mining",
         f"Hashprice {mes_txt(r['mina_mes'])}: {usd(r['mina_hp'], 2)}/PH/day. Net of power.",
         r["mina"],
         f"{usd_m(r['capex_mina'])} to build a mine (model reference), already spent on an existing site. Fleet refresh: {hueco('ASIC price per TH')}",
         usd_m(r["capex_mina"] * mw) + " (reference)",
         '<span class="gap">Not found: needs ASIC price per TH</span>'),
        ("Host AI for a tenant",
         (f"{usd(s['hosting_usd_mw_it_anio'] / 1e6, 2)}M per MW of IT per year (TeraWulf / Fluidstack)." if not r.get("renta")
          else f"{usd_m(r['renta']['valor'])} per grid MW per year: " + ("the site's own LOI figure, see inputs." if una_hoja else f"{e(r['renta']['fuente'])}."))
         + " Power is passed through to the tenant, so no power cost is subtracted.",
         r["hosting"],
         f"{usd_m(hl)} to {usd_m(hh)}: $8M to $11M per MW of critical IT (TeraWulf, Cipher filings) divided by PUE",
         f"{usd_m(hl * mw)} to {usd_m(hh * mw)}",
         f"{pb_h[0]:.1f} to {pb_h[1]:.1f} years"),
        ("Own GPUs (H100)",
         f"{r['gpus_por_mw']:,.0f} H100 per grid MW at {usd(r['h100_precio'], 2)}/h ({mes_txt(r['h100_mes'])}), {s['utilizacion']:.0%} utilization. Net of power.",
         r["gpu"],
         f"{usd_m(r['capex_gpu'])} (CoinShares Q4 2025, in the model; source does not say per MW of IT or grid)",
         usd_m(r["capex_gpu"] * mw),
         f"{pb_g:.1f} years" if pb_g else "n/a"),
    ]
    tabla = "".join(
        f"<tr><th>{e(n)}<div class='basis'>{b}</div></th>"
        f"<td class='num'>{usd(v)}</td><td class='num'>{usd(v * mw)}</td>"
        f"<td class='capex'>{c1}</td><td class='capex'>{c2}</td><td class='capex pb'>{c3}</td></tr>"
        for n, b, v, c1, c2, c3 in filas)
    r["payback"] = {"hosting": pb_h, "gpu": pb_g}

    celdas = "".join(
        f"<div class='m{' neg' if m['neto_mw_dia'] <= 0 else ''}'>"
        f"<div class='mm'>{mes_txt(m['mes'])}</div>"
        f"<div class='mv'>{usd(m['neto_mw_dia'])}</div>"
        f"<div class='mh'>hp {usd(m['hashprice'], 2)}</div></div>"
        for m in r["meses"])

    fuentes_hp = sorted({m["fuente"] for m in r["meses"]})
    secundario = [mes_txt(m["mes"]) for m in r["meses"] if "secundario" in str(m["tipo"])]

    supuestos = (
        f"Mining puts all {mw:g} MW on ASICs at {jth:g} J/TH ({1000/jth:.1f} PH/s per MW, no cooling overhead), "
        f"revenue = hashprice x PH/s, minus 24 MWh/day at your tariff. "
        f"AI paths use IT load = 1/PUE of each grid MW; {s['h100_por_mw_it']} H100 per MW of IT "
        f"(from NVIDIA DGX H100 specs); {s['utilizacion']:.0%} utilization (Epoch); "
        + (f"hosting rate {usd(s['hosting_usd_mw_it_anio'] / 1e6, 2)}M per MW of IT per year (TeraWulf / Fluidstack). " if not r.get("renta")
           else f"hosting rate {usd_m(r['renta']['valor'])} per grid MW per year from the site's own public figure (see inputs). ")
        + f"Mine and GPU capex per MW from CoinShares Q4 2025 (in the model); hosting capex from TeraWulf and Cipher filings (not in the model). Fees are inside hashprice."
    )

    nota_tabla = "" if una_hoja else f"""<p class="small">Mining and owned GPUs are net of power. Hosting carries no power cost because the tenant pays it in TeraWulf's Fluidstack lease (Cipher's release does not say). Simple payback = capex per MW / (net USD per MW per day x 365). It does not include depreciation, financing, staff, site operating costs or tenant risk.</p>"""
    resto = f"""<h2>Mining, last {N_MESES} months with data (net USD per MW per day)</h2>
<div class="months">{celdas}</div>
<p class="lead"><b>{r['meses_en_cero']} of {N_MESES} months at or below zero</b> for this fleet and power price. Break-even hashprice: <b>{usd(r['equilibrio'], 2)}/PH/day</b>. Range over the {N_MESES} months: {usd(r['mina_min'])} to {usd(r['mina_max'])} per MW per day.</p>

<div class="mixblock">
<h2>Mixing mining and AI hosting on this site, USD per day, whole site</h2>
<table class="mix">
<thead><tr><th>MW split</th><th class="num">Net, {mes_txt(r['mina_mes'])}</th><th class="num">Worst of {N_MESES} months</th><th class="num">Months at or below 0</th><th class="num">Under lease</th><th>AI capex (hosting)</th><th>Your cash</th></tr></thead>
<tbody>{armar_mezcla(r)}</tbody>
</table>
<p class="small">Each split uses the same {N_MESES} months as above: mining MW earn that month's net, AI MW earn the hosting rate. Revenue under lease = hosting revenue / (hosting revenue + mining revenue before power), {mes_txt(r['mina_mes'])}. Your cash before first rent: as in the financing table below, 10-year term at 10%. Assumes the grid connection splits freely between the two loads; interconnection and finding the tenant are not in the model.{r['capital_txt']}</p>
</div>

<div class="mixblock">
<h2>Financing the AI part and when it pays back, per grid MW moved to AI</h2>
<p class="lead" style="margin:0 0 6px">{r['respuesta']}</p>
<p class="lead" style="margin:0 0 4px">Months with no AI income: <b>{OBRA_MESES} of construction</b> from signing to first rent, then the tenant ramps over <b>{ARRANQUE_MESES} months</b> to full rent ({usd(r['hosting'] * 365 / 12)} per MW per month).</p>
<table class="mix">
<thead><tr><th>Loan term and rate</th><th>Your cash before first rent</th><th class="num">DSCR, first year at full rent</th><th>Meets {r['dscr_min']}x?</th><th>Your cash back, from signing</th></tr></thead>
<tbody>{armar_deuda(r)}</tbody>
</table>
<p class="small">{r['deuda_texto'] + ' ' if r.get('deuda_texto') else ''}Default structure from USD.AI: loan = {ANTICIPO:.0%} of capex, you put {1 - ANTICIPO:.0%} plus a {RESERVA_MESES}-month debt-service reserve, equal monthly principal from first rent, {DSCR_MIN}x minimum coverage. USD.AI lends 3 to 5 years against GPUs, not buildings; 10 years is the base term of the TeraWulf and Cipher hosting leases. Rates 10% to 15%: what USD.AI charged smaller operators (American Compute, Oct 2026). Ranges run from favorable (low capex, 85% NOI margin) to unfavorable (high capex, 70% NOI margin). Your cash before first rent = 20% of capex + {RESERVA_MESES}-month reserve + interest during construction + mining given up during construction. Below 1.0x the rent does not cover the payment and you add cash every month until the loan is paid; the payback counts that. Construction {OBRA_MESES} months: Cipher signed Barber Lake on 25 Sep 2025 with rent from Oct 2026; TeraWulf signed on 14 Aug 2025 and delivered CB-3 in early Jul 2026, and its CB-5 slipped from 2H 2026 to early 2027. Ramp {ARRANQUE_MESES} months: TeraWulf's plan, 40 of 200 MW in 1H 2026 and all by year-end. These are large public operators; a 20 MW site has no public benchmark. Interest during construction assumes the loan is drawn evenly over the {OBRA_MESES} months and interest is paid monthly (no source for a small site's draw schedule). The AI MW stop mining at signing and give up {usd(r['mina_dia_media'])} per MW per day, the average of the last {N_MESES} months. Rent is net of site costs: NOI margin 85% (TeraWulf, Cipher) to ~70% (TeraWulf Abernathy, average over lease life); NOI = rent less property operating expenses, property taxes and insurance. Not included: income taxes, depreciation, and the reserve coming back at the end.</p>
</div>

<div class="mixblock">
<h2>Who pays for the build, per grid MW moved to AI</h2>
<table class="obra">
<thead><tr><th>Structure</th><th>Your cash before first rent</th><th class="num">You net per month, first year at full rent</th></tr></thead>
<tbody>{armar_obra(r)}</tbody>
</table>
<p class="small">Net per month is after debt service or preferred dividend and after the mining income those MW give up ({usd(r['mina_dia_media'] * 365 / 12)} per MW per month, last {N_MESES} months). Ranges: favorable to unfavorable case. Each structure comes from one public deal at a large site; none is offered to a 5 to 50 MW site in the sources found.</p>
</div>

<div class="foot small">
<p style="margin:0 0 4px"><b>Assumptions.</b> {e(supuestos)}</p>
<p style="margin:0 0 4px"><b>Sources.</b> Hashprice: Luxor Hashrate Index monthly lookbacks ({len(fuentes_hp)} pages){', ' + ', '.join(secundario) + ' from a secondary summary (asic.tools)' if secundario else ''}. H100: {e(r['h100_fuente'])} ({e(r['h100_segmento'])}; H100 points mix marketplace, contract and index prices). Each row's URL is in {REPO}/data. Series compiled 19 Oct 2026. Hosting capex and power terms, read 2 Nov 2026: {' '.join(f'{e(t)} ({u}).' for t, u in FUENTES_HOSTING)} Debt, construction, ramp and site costs, read 4 Nov 2026: {' '.join(f'{e(t)} ({u}).' for t, u in FUENTES_DEUDA)} {'This site\'s financing cases: ' + ' '.join(f'{e(t)} ({u}).' for t, u in r['deuda_fuentes']) if r['deuda_fuentes'] else ''} Who could put up the cash: {' '.join(f'{e(n)} ({u}).' for n, _, u in QUIEN_PONE)} Who pays for the build, read 5 Nov 2026: {' '.join(f'{e(t)} ({u}).' for t, u in FUENTES_OBRA)}</p>
<p style="margin:0">Generated {generado} with estudio-de-sitio/estudio_de_sitio.py. Model check: reproduces out/tabla_mw.csv.</p>
</div>
"""
    if una_hoja:
        resto = f"""<div class="mixblock">
<h2>Financing the AI part, per grid MW moved to AI</h2>
<p class="lead" style="margin:0 0 4px">{r['respuesta']}{r['capital_txt']}</p>
<table class="mix">
<thead><tr><th>Loan term and rate</th><th>Your cash before first rent</th><th class="num">DSCR, first year at full rent</th><th>Meets {r['dscr_min']}x?</th><th>Your cash back, from signing</th></tr></thead>
<tbody>{armar_deuda(r, solo_plazo=None if r.get('deuda_texto') else max(PLAZOS))}</tbody>
</table>
<p class="small">{OBRA_MESES} months of construction with no AI income, then {ARRANQUE_MESES} months of tenant ramp. {r.get('deuda_texto') or f'Loan of {ANTICIPO:.0%} of capex with a {RESERVA_MESES}-month reserve (USD.AI structure), rates of 10% and 15% (what USD.AI charged smaller operators, American Compute, Oct 2026).'} Ranges: low capex and 85% NOI margin to high capex and 70%. Mining for the last {N_MESES} months at this fleet and power price: {r['meses_en_cero']} of {N_MESES} at or below zero.</p>
</div>
<div class="foot small"><p style="margin:0">One-page summary. The full study ({e(completo)}) has the month-by-month mining, the MW mix, every assumption and every source link. Model: {REPO}. Generated {generado}.</p></div>
"""
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Site study: {e(sitio)}</title>
<style>
@page {{ size: Letter; margin: 0.45in 0.5in; }}
:root {{ --ink:#1a1a1a; --mute:#5c5c5c; --line:#d9d6cf; --bg:#ffffff; --soft:#f5f3ee; --neg:#a3291d; --negbg:#fbeae7; --gap:#7a5a00; --gapbg:#fff4cc; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--bg); color:var(--ink); font:10.5pt/1.35 "Helvetica Neue", Arial, sans-serif; }}
.page {{ max-width:7.5in; margin:0 auto; padding:16px; }}
@media print {{ .page {{ padding:0; }} }}
.example {{ border:3px solid var(--neg); color:var(--neg); text-align:center; font-weight:800; font-size:22pt; letter-spacing:.04em; padding:6px; margin-bottom:10px; }}
h1 {{ font-size:17pt; margin:0 0 2px; }}
.sub {{ color:var(--mute); margin:0 0 10px; }}
.inputs {{ display:grid; grid-template-columns:repeat(4,1fr); gap:6px; margin-bottom:12px; }}
.inputs div {{ background:var(--soft); padding:6px 8px; border-radius:4px; }}
.inputs b {{ display:block; font-size:14pt; }}
.inputs span {{ color:var(--mute); font-size:8.5pt; }}
h2 {{ font-size:11pt; margin:12px 0 4px; text-transform:uppercase; letter-spacing:.05em; color:var(--mute); }}
table {{ width:100%; border-collapse:collapse; }}
th, td {{ text-align:left; vertical-align:top; padding:6px 5px; border-bottom:1px solid var(--line); }}
thead th, thead th.num {{ font-size:8.5pt; color:var(--mute); font-weight:600; border-bottom:1.5px solid var(--ink); }}
tbody th {{ width:30%; font-size:11pt; }}
.pb {{ font-weight:700; font-size:9.5pt; }}
.basis {{ font-weight:400; font-size:8.5pt; color:var(--mute); margin-top:2px; }}
.num {{ text-align:right; font-variant-numeric:tabular-nums; font-size:12pt; font-weight:700; white-space:nowrap; }}
.capex {{ font-size:8.5pt; }}
.gap {{ background:var(--gapbg); color:var(--gap); padding:0 3px; border-radius:2px; font-weight:600; }}
.months {{ display:grid; grid-template-columns:repeat({N_MESES},1fr); gap:4px; }}
.m {{ background:var(--soft); padding:5px 4px; border-radius:4px; text-align:center; }}
.m.neg {{ background:var(--negbg); color:var(--neg); }}
.mm {{ font-size:8pt; color:inherit; opacity:.8; }}
.mv {{ font-weight:700; font-size:10.5pt; font-variant-numeric:tabular-nums; }}
.mh {{ font-size:7.5pt; opacity:.75; }}
.lead {{ font-size:11pt; margin:6px 0 0; }}
.small {{ font-size:8pt; color:var(--mute); }}
ul.small {{ margin:4px 0 0; padding-left:16px; }}
.mixblock {{ break-inside:avoid; page-break-inside:avoid; }}
table.obra tbody th {{ width:58%; font-size:9.5pt; white-space:normal; }}
table.obra td, table.obra th {{ padding:4px 5px; }}
table.mix th {{ width:auto; font-size:9pt; }}
table.mix tbody th {{ white-space:nowrap; }}
table.mix {{ table-layout:auto; }}
table.mix .capex {{ white-space:normal; min-width:1.1in; }}
table.mix td, table.mix th {{ padding:4px 5px; }}
.num.s {{ font-size:10pt; }}
tr.mine {{ background:var(--soft); }}
.plan {{ font-size:7.5pt; font-weight:700; color:var(--mute); text-transform:uppercase; }}
.example.public {{ font-size:12pt; border-width:2px; }}
.example.operador {{ color:var(--ink); border-color:var(--ink); }}
ul.origen {{ margin:-6px 0 8px; padding-left:16px; }}
.box {{ border:1.5px solid var(--ink); border-radius:4px; padding:5px 8px; margin:0 0 4px; font-size:8.8pt; line-height:1.28; }}
.box ul.small {{ font-size:8pt; color:var(--ink); margin:2px 0 0; }}
.box li {{ margin:0; }}
.una {{ font-size:9.5pt; }}
.una h1 {{ font-size:15pt; }}
.una .sub {{ font-size:8.5pt; margin-bottom:6px; }}
.una .inputs b {{ font-size:12pt; }}
.una .inputs {{ margin-bottom:8px; }}
.una tbody th {{ font-size:10pt; }}
.una .num {{ font-size:11pt; }}
.una th, .una td {{ padding:4px 5px; }}
.una h2 {{ margin:8px 0 3px; }}
.una table.mix tbody th {{ white-space:normal; width:30%; font-size:8.5pt; }}
.una .small {{ font-size:7.5pt; }}
.una .basis {{ display:none; }}
.una .lead {{ font-size:9.5pt; }}
.una ul.origen {{ font-size:7.5pt; }}
.foot {{ margin-top:10px; border-top:1px solid var(--line); padding-top:6px; }}
</style></head>
<body class="{'una' if una_hoja else ''}"><div class="page">
{banner}
<h1>Site study: {e(sitio)}</h1>
<p class="sub">What each MW of this site earns per day in three paths, from the public model at {REPO}, plus public filings where marked. Model output from public averages, not a forecast and not an offer.</p>

<div class="inputs">
<div><b>{mw:g} MW</b><span>Site power</span></div>
<div><b>${tarifa:g}/MWh</b><span>Power price</span></div>
<div><b>{jth:g} J/TH</b><span>Fleet efficiency</span></div>
<div><b>{pue:g}</b><span>PUE for AI load</span></div>
</div>
{origen}

{armar_caja(r, corto=una_hoja)}

<h2>Three paths, USD per day</h2>
<table>
<thead><tr><th>Path and basis</th><th class="num">Per MW</th><th class="num">Whole site</th><th>Capex per grid MW</th><th>Capex, whole site</th><th>Simple payback</th></tr></thead>
<tbody>{tabla}</tbody>
</table>
{nota_tabla}

{resto}
</div></body></html>
"""


def guardar_csv(path, mw, tarifa, jth, pue, r):
    filas = [
        ("input", "mw", mw), ("input", "usd_mwh", tarifa), ("input", "j_th", jth), ("input", "pue", pue),
        ("mining", f"neto_usd_mw_dia_{r['mina_mes']}", round(r["mina"], 2)),
        ("mining", "meses_en_cero_o_negativo", r["meses_en_cero"]),
        ("mining", "hashprice_equilibrio_usd_ph_dia", round(r["equilibrio"], 2)),
        ("hosting", "usd_mw_dia", round(r["hosting"], 2)),
        ("gpu", f"neto_usd_mw_dia_{r['h100_mes']}", round(r["gpu"], 2)),
        ("capex", "mina_usd_mw_referencia", r["capex_mina"]),
        ("capex", "hosting_usd_mw_red_bajo", round(r["capex_hosting"][0])),
        ("capex", "hosting_usd_mw_red_alto", round(r["capex_hosting"][1])),
        ("payback", "hosting_anios_bajo", round(r["payback"]["hosting"][0], 2)),
        ("payback", "hosting_anios_alto", round(r["payback"]["hosting"][1], 2)),
        ("payback", "gpu_anios", round(r["payback"]["gpu"], 2) if r["payback"]["gpu"] else "n/a"),
        ("payback", "mina_anios", "NO ENCONTRADO: precio de ASIC por TH"),
        ("capex", "gpu_usd_mw", r["capex_gpu"]),
    ] + [("mining_mes", m["mes"], round(m["neto_mw_dia"], 2)) for m in r["meses"]]
    for f in r["deuda"]:
        k = (f"deuda_{re.sub(r'[^a-z0-9]+', '_', f['nombre'].lower()).strip('_')}" if f["nombre"]
             else f"deuda_{f['plazo']}a_{f['tasa']:.0%}")
        for lado in ("bajo", "alto"):
            d = f[lado]
            filas += [(k, f"caja_antes_de_renta_usd_mw_{lado}", round(d["caja_inicial"])),
                      (k, f"intereses_obra_usd_mw_{lado}", round(d["intereses_obra"])),
                      (k, f"mineria_dejada_obra_usd_mw_{lado}", round(d["mina_obra"])),
                      (k, f"dscr_renta_llena_{lado}", round(d["dscr"], 3)),
                      (k, f"payback_meses_desde_firma_{lado}", d["payback_meses"] if d["payback_meses"] else "mas de 240")]
    for i, f in enumerate(r["obra"]):
        k = f"obra_{['tu_construyes', 'inquilino_paga', 'sociedad_inquilino', 'preferente'][i]}"
        filas += [(k, "caja_propia_usd_mw_bajo", round(f["caja"][0])), (k, "caja_propia_usd_mw_alto", round(f["caja"][1])),
                  (k, "neto_usd_mw_mes_bajo", round(f["neto"][0])), (k, "neto_usd_mw_mes_alto", round(f["neto"][1]))]
    for f in r["mezcla"]:
        k = f"mezcla_{f['mw_mina']:g}_mina_{f['mw_ia']:g}_ia"
        filas += [(k, "neto_sitio_usd_dia_ultimo_mes", round(f["neto_ult"], 2)),
                  (k, "peor_mes_neto_sitio_usd_dia", round(f["peor"], 2)),
                  (k, "meses_en_cero_o_negativo", f["en_cero"]),
                  (k, "parte_del_ingreso_con_contrato", round(f["contrato"], 4) if f["contrato"] is not None else "n/a"),
                  (k, "capex_ia_usd_bajo", round(f["capex"][0])),
                  (k, "capex_ia_usd_alto", round(f["capex"][1])),
                  (k, "caja_propia_usd_bajo", round(f["caja"][0])),
                  (k, "caja_propia_usd_alto", round(f["caja"][1]))]
    pd.DataFrame(filas, columns=["camino", "dato", "valor"]).to_csv(path, index=False)


def a_pdf(html_path, pdf_path):
    nav = shutil.which("chromium") or shutil.which("google-chrome")
    if not nav:
        return False
    subprocess.run([nav, "--headless", "--disable-gpu", "--no-pdf-header-footer",
                    f"--print-to-pdf={pdf_path}", html_path.as_uri()],
                   check=True, capture_output=True, timeout=120)
    return True


def main():
    p = argparse.ArgumentParser(description="Site study one-sheet from the mw-index model")
    p.add_argument("--mw", type=float, help="site power, MW")
    p.add_argument("--tarifa", type=float, help="power price, USD/MWh")
    p.add_argument("--jth", type=float, help="fleet efficiency, J/TH")
    p.add_argument("--pue", type=float, help="PUE for the AI load")
    p.add_argument("--mw-ia", type=float, help="MW the operator plans to move to AI (marked in the mix)")
    p.add_argument("--capital", type=float, help="USD the operator can put in (shows how many MW it covers)")
    p.add_argument("--sitio", default="Operator site", help="name shown on the sheet")
    p.add_argument("--ejemplo", action="store_true", help="mark as EXAMPLE, fictional site")
    p.add_argument("--entradas", help="JSON with a real site's inputs and the source of each")
    p.add_argument("--una-hoja", action="store_true", help="also write <site>-1p.html/.pdf, a one-page summary")
    p.add_argument("--out", default=str(AQUI / "out"))
    a = p.parse_args()

    entradas, deuda = None, None
    if a.entradas:
        datos = json.loads(Path(a.entradas).read_text(encoding="utf-8"))
        deuda = datos.get("deuda")
        entradas = datos["entradas"]
        for k in ("mw", "tarifa", "jth", "pue"):
            d = entradas[k]
            if d.get("tipo") not in ("operator", "public", "derived", "assumed") or not d.get("fuente"):
                raise SystemExit(f"{a.entradas}: '{k}' needs tipo (operator, public, derived or assumed) and fuente")
            setattr(a, k, float(d["valor"]))
        a.sitio = datos["sitio"]
    if None in (a.mw, a.tarifa, a.jth, a.pue):
        raise SystemExit("Faltan entradas: --mw, --tarifa, --jth y --pue, o --entradas sitios/<sitio>.json")

    n = comprobar_modelo()
    renta = entradas.get("renta") if entradas else None
    r = calcular(a.mw, a.tarifa, a.jth, a.pue, renta["valor"] if renta else None)
    r["entradas"], r["renta"] = entradas, renta
    r["dscr_min"] = deuda.get("dscr_min", DSCR_MIN) if deuda else DSCR_MIN
    r["deuda_texto"] = deuda.get("texto") if deuda else None
    r["deuda_fuentes"] = [tuple(x) for x in deuda.get("fuentes", [])] if deuda else []
    r["deuda"], r["mina_dia_media"] = escenarios_deuda(r, deuda["casos"] if deuda else None, r["dscr_min"])
    r["caso_base"] = (r["deuda"][0] if deuda else
                      next(f for f in r["deuda"] if f["plazo"] == max(PLAZOS) and f["tasa"] == min(TASAS)))
    caso = r["caso_base"]
    r["caja_mw"] = (caso["bajo"]["caja_inicial"], caso["alto"]["caja_inicial"])
    r["capital_txt"] = ""
    if a.capital:
        r["capital_txt"] = (f" With {usd_m(a.capital)} of your own cash: {min(a.mw, a.capital / r['caja_mw'][1]):.1f} to "
                            f"{min(a.mw, a.capital / r['caja_mw'][0]):.1f} MW to AI on that structure.")
    r["mw"] = a.mw
    r["obra"] = escenarios_obra(r, a.pue)
    r["mezcla"] = mezclas(a.mw, r, a.mw_ia)
    r["respuesta"] = respuesta(r, a.mw)
    generado = dt.datetime.now().astimezone().strftime("%d %b %Y %H:%M %Z")

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "-", a.sitio.lower()).strip("-") or "sitio"
    h = out / f"{slug}.html"
    h.write_text(armar_html(a.sitio, a.mw, a.tarifa, a.jth, a.pue, r, a.ejemplo, generado), encoding="utf-8")
    guardar_csv(out / f"{slug}.csv", a.mw, a.tarifa, a.jth, a.pue, r)
    pdf = a_pdf(h, out / f"{slug}.pdf")
    if a.una_hoja:
        h1 = out / f"{slug}-1p.html"
        h1.write_text(armar_html(a.sitio, a.mw, a.tarifa, a.jth, a.pue, r, a.ejemplo, generado,
                                 una_hoja=True, completo=f"{slug}.pdf"), encoding="utf-8")
        a_pdf(h1, out / f"{slug}-1p.pdf")
        print(f"Una hoja: {h1}")

    print(f"Modelo comprobado contra tabla_mw.csv ({n} meses).")
    print(f"Minar ({r['mina_mes']}): {usd(r['mina'])}/MW/día | hosting {usd(r['hosting'])} | GPU propia {usd(r['gpu'])}")
    print(f"Meses en cero o negativo: {r['meses_en_cero']} de {N_MESES} | equilibrio {usd(r['equilibrio'], 2)}/PH/día")
    for f in r["mezcla"]:
        print(f"Mezcla {f['mw_mina']:g} minar / {f['mw_ia']:g} IA: {usd(f['neto_ult'])}/día, peor mes {usd(f['peor'])}, "
              f"{f['en_cero']} de {N_MESES} en cero, contrato {'n/a' if f['contrato'] is None else format(f['contrato'], '.0%')}")
    for f in r["deuda"]:
        b, al = f["bajo"], f["alto"]
        print(f"Deuda {f['etiqueta']}: caja {usd_m(b['caja_inicial'])} a {usd_m(al['caja_inicial'])} por MW, "
              f"DSCR {b['dscr']:.2f} a {al['dscr']:.2f}, payback {b['payback_meses']} a {al['payback_meses']} meses")
    for f in r["obra"]:
        print(f"Obra, {f['nombre']}: caja {usd_m(f['caja'][0])} a {usd_m(f['caja'][1])} por MW, neto {usd(f['neto'][0])} a {usd(f['neto'][1])} al mes")
    print(f"Escrito: {h}" + (f" y {out / (slug + '.pdf')}" if pdf else " (sin PDF: no hay chromium)"))


if __name__ == "__main__":
    main()
