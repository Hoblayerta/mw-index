# Site study, v0

The one-sheet an operator receives: what each MW of their site earns per day if they keep mining, host AI for a tenant, or run their own GPUs, plus how many of the last 8 months mining would have been at or below zero, and the capex of each path.

Every number comes from `../mw_model.py` and `../data/*.csv`. The script sets the operator's power price and PUE in the model's `SUPUESTOS` and calls the model's own functions. Before it writes anything it checks that the model, with its default assumptions, still reproduces `../out/tabla_mw.csv`, and stops if not.

## Run it

```
pip install pandas matplotlib
python3 estudio_de_sitio.py --mw 20 --tarifa 50 --jth 27 --pue 1.3 --sitio "Fictional site" --ejemplo
```

Inputs: `--mw` site MW, `--tarifa` power price in USD/MWh, `--jth` fleet J/TH, `--pue` PUE for the AI load. `--ejemplo` prints "EXAMPLE, fictional site" at the top. Drop it for a real operator.

Writes `out/<site>.html` (the sheet, prints to one Letter page), `out/<site>.pdf` (if Chromium is installed) and `out/<site>.csv` (the raw numbers on the sheet).

`out/fictional-site.*` is the example: 20 MW, $50/MWh, 27 J/TH, PUE 1.3. The site is made up.

## Outside the model (read 2 Nov 2026, marked on the sheet)

- Hosting capex: $8M to $11M per MW of critical IT, from TeraWulf (Aug and Oct 2025) and Cipher (Sep 2025) filings on their Fluidstack deals. The sheet divides by PUE to put it per grid MW. Values and links live in `CAPEX_HOSTING_IT` and `FUENTES_HOSTING` at the top of the script.
- Power in hosting: TeraWulf's Abernathy deck says "Power 100% passed-through to tenant", so the hosting path carries no power cost. Cipher's release says "modified gross lease" and does not state power terms.
- Simple payback = capex per MW / (net USD per MW per day x 365). No depreciation, financing, staff, site operating costs or tenant risk.

## Still missing (gaps on the sheet)

- ASIC price per TH for a fleet refresh, so mining has no payback. Hashrate Index's ASIC Price Index chart needs JavaScript and showed no values without it.
- Cooling overhead for mining: all site MW goes to ASICs.
- Whether the US$20M per MW for owned GPUs is per MW of IT or of grid, and what it includes.
