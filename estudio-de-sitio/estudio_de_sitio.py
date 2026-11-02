"""
Estudio de sitio, v0: la hoja que recibe un operador.

Entradas (las 4 que cambian por operador):
  --mw      MW del sitio
  --tarifa  tarifa de luz, USD/MWh
  --jth     eficiencia de la flota, J/TH
  --pue     PUE de la carga de IA

Los números salen de ../mw_model.py y de ../data/*.csv: el script cambia
usd_kwh y pue en SUPUESTOS y llama las funciones del modelo. Lo único que no
viene del modelo es el capex de hosting y que la luz la paga el inquilino
(CAPEX_HOSTING_IT y FUENTES_HOSTING, de documentos de SEC leídos el 2 nov 2026). Antes de calcular, comprueba que el modelo con sus supuestos de fábrica
reproduce ../out/tabla_mw.csv; si no, se detiene.

Escribe en out/: <slug>.html (la hoja), <slug>.pdf (si hay chromium) y
<slug>.csv (los números crudos de la hoja).

Ejemplo:
  python3 estudio_de_sitio.py --mw 20 --tarifa 50 --jth 27 --pue 1.3 \
      --sitio "Fictional site" --ejemplo
"""
import argparse
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
def calcular(mw, tarifa, jth, pue):
    s = mw_model.SUPUESTOS
    s["usd_kwh"] = tarifa / 1000
    s["pue"] = pue

    hp = pd.read_csv(RAIZ / "data" / "hashprice.csv").dropna(subset=["hashprice_usd_ph_dia"])
    hp = hp.sort_values("mes").tail(N_MESES).reset_index(drop=True)
    meses = []
    for _, r in hp.iterrows():
        _, neto = mw_model.ingreso_mina_usd_mw_dia(r["hashprice_usd_ph_dia"], jth)
        meses.append({"mes": r["mes"], "hashprice": r["hashprice_usd_ph_dia"],
                      "neto_mw_dia": neto, "tipo": r["tipo"], "fuente": r["fuente"]})
    ultimo = meses[-1]

    h100 = pd.read_csv(RAIZ / "data" / "h100.csv").sort_values("mes")
    h100_mes = h100["mes"].iloc[-1]
    h100_filas = h100[h100["mes"] == h100_mes]
    h100_precio = h100_filas["h100_usd_hora"].mean()  # mismo promedio por mes que el modelo
    _, gpu_neto = mw_model.ingreso_gpu_usd_mw_dia(h100_precio)

    hosting = mw_model.ingreso_hosting_usd_mw_dia()

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
    return f"${x/1e6:,.2f}M"


def mes_txt(p):
    return dt.datetime.strptime(p, "%Y-%m").strftime("%b %Y")


def anios(capex, neto):
    if neto is None or neto <= 0:
        return None
    return capex / (neto * 365)


def hueco(txt):
    return f'<span class="gap">Not in model: {html.escape(txt)}</span>'


def armar_html(sitio, mw, tarifa, jth, pue, r, ejemplo, generado):
    s = r["s"]
    e = html.escape
    banner = '<div class="example">EXAMPLE, fictional site</div>' if ejemplo else ""

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
         f"{usd(s['hosting_usd_mw_it_anio'] / 1e6, 2)}M per MW of IT per year (TeraWulf / Fluidstack). Power is passed through to the tenant, so no power cost is subtracted.",
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
        f"hosting rate {usd(s['hosting_usd_mw_it_anio'] / 1e6, 2)}M per MW of IT per year (TeraWulf / Fluidstack). "
        f"Mine and GPU capex per MW from CoinShares Q4 2025 (in the model); hosting capex from TeraWulf and Cipher filings (not in the model). Fees are inside hashprice."
    )

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
.foot {{ margin-top:10px; border-top:1px solid var(--line); padding-top:6px; }}
</style></head>
<body><div class="page">
{banner}
<h1>Site study: {e(sitio)}</h1>
<p class="sub">What each MW of this site earns per day in three paths, from the public model at {REPO}, plus public filings where marked. Model output from public averages, not a forecast and not an offer.</p>

<div class="inputs">
<div><b>{mw:g} MW</b><span>Site power</span></div>
<div><b>${tarifa:g}/MWh</b><span>Power price</span></div>
<div><b>{jth:g} J/TH</b><span>Fleet efficiency</span></div>
<div><b>{pue:g}</b><span>PUE for AI load</span></div>
</div>

<h2>Three paths, USD per day</h2>
<table>
<thead><tr><th>Path and basis</th><th class="num">Per MW</th><th class="num">Whole site</th><th>Capex per grid MW</th><th>Capex, whole site</th><th>Simple payback</th></tr></thead>
<tbody>{tabla}</tbody>
</table>
<p class="small">Mining and owned GPUs are net of power. Hosting carries no power cost because the tenant pays it in TeraWulf's Fluidstack lease (Cipher's release does not say). Simple payback = capex per MW / (net USD per MW per day x 365). It does not include depreciation, financing, staff, site operating costs or tenant risk.</p>

<h2>Mining, last {N_MESES} months with data (net USD per MW per day)</h2>
<div class="months">{celdas}</div>
<p class="lead"><b>{r['meses_en_cero']} of {N_MESES} months at or below zero</b> for this fleet and power price. Break-even hashprice: <b>{usd(r['equilibrio'], 2)}/PH/day</b>. Range over the {N_MESES} months: {usd(r['mina_min'])} to {usd(r['mina_max'])} per MW per day.</p>

<div class="foot small">
<p style="margin:0 0 4px"><b>Assumptions.</b> {e(supuestos)}</p>
<p style="margin:0 0 4px"><b>Sources.</b> Hashprice: Luxor Hashrate Index monthly lookbacks ({len(fuentes_hp)} pages){', ' + ', '.join(secundario) + ' from a secondary summary (asic.tools)' if secundario else ''}. H100: {e(r['h100_fuente'])} ({e(r['h100_segmento'])}; H100 points mix marketplace, contract and index prices). Each row's URL is in {REPO}/data. Series compiled 19 Oct 2026. Hosting capex and power terms, read 2 Nov 2026: {' '.join(f'{e(t)} ({u}).' for t, u in FUENTES_HOSTING)}</p>
<p style="margin:0">Generated {generado} with estudio-de-sitio/estudio_de_sitio.py. Model check: reproduces out/tabla_mw.csv.</p>
</div>
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
    p.add_argument("--mw", type=float, required=True, help="site power, MW")
    p.add_argument("--tarifa", type=float, required=True, help="power price, USD/MWh")
    p.add_argument("--jth", type=float, required=True, help="fleet efficiency, J/TH")
    p.add_argument("--pue", type=float, required=True, help="PUE for the AI load")
    p.add_argument("--sitio", default="Operator site", help="name shown on the sheet")
    p.add_argument("--ejemplo", action="store_true", help="mark as EXAMPLE, fictional site")
    p.add_argument("--out", default=str(AQUI / "out"))
    a = p.parse_args()

    n = comprobar_modelo()
    r = calcular(a.mw, a.tarifa, a.jth, a.pue)
    generado = dt.datetime.now().astimezone().strftime("%d %b %Y %H:%M %Z")

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "-", a.sitio.lower()).strip("-") or "sitio"
    h = out / f"{slug}.html"
    h.write_text(armar_html(a.sitio, a.mw, a.tarifa, a.jth, a.pue, r, a.ejemplo, generado), encoding="utf-8")
    guardar_csv(out / f"{slug}.csv", a.mw, a.tarifa, a.jth, a.pue, r)
    pdf = a_pdf(h, out / f"{slug}.pdf")

    print(f"Modelo comprobado contra tabla_mw.csv ({n} meses).")
    print(f"Minar ({r['mina_mes']}): {usd(r['mina'])}/MW/día | hosting {usd(r['hosting'])} | GPU propia {usd(r['gpu'])}")
    print(f"Meses en cero o negativo: {r['meses_en_cero']} de {N_MESES} | equilibrio {usd(r['equilibrio'], 2)}/PH/día")
    print(f"Escrito: {h}" + (f" y {out / (slug + '.pdf')}" if pdf else " (sin PDF: no hay chromium)"))


if __name__ == "__main__":
    main()
