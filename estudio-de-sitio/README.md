# Site study, v0

The one-sheet an operator receives: what each MW of their site earns per day if they keep mining, host AI for a tenant, or run their own GPUs, plus how many of the last 8 months mining would have been at or below zero, the capex of each path, and what happens when the site splits its MW between mining and AI hosting.

Every number comes from `../mw_model.py` and `../data/*.csv`. The script sets the operator's power price and PUE in the model's `SUPUESTOS` and calls the model's own functions. Before it writes anything it checks that the model, with its default assumptions, still reproduces `../out/tabla_mw.csv`, and stops if not.

## Run it

```
pip install pandas matplotlib
python3 estudio_de_sitio.py --mw 20 --tarifa 50 --jth 27 --pue 1.3 --sitio "Fictional site" --ejemplo
```

Optional: `--mw-ia 3` adds the operator's own split (3 MW to AI) to the mix table, marked "your plan". `--capital 10000000` says how many MW that much of the operator's own cash covers.

Inputs: `--mw` site MW, `--tarifa` power price in USD/MWh, `--jth` fleet J/TH, `--pue` PUE for the AI load. `--ejemplo` prints "EXAMPLE, fictional site" at the top. Drop it for a real operator.

Writes `out/<site>.html` (the sheet: the three paths on page 1; the mix, the financing and the payback on page 2; sources run onto page 3), `out/<site>.pdf` (if Chromium is installed) and `out/<site>.csv` (the raw numbers on the sheet).

`out/fictional-site.*` is the example: 20 MW, $50/MWh, 27 J/TH, PUE 1.3. The site is made up.

## Site-specific inputs and financing

`--entradas <file>.json` reads a site's inputs from a file, each tagged `operator`, `public`, `derived` or `assumed` with its source, and prints those tags on the sheet. The file can also carry `deuda`: the site's own financing cases (`nombre`, `anticipo`, `tasa`, `plazo`), a `dscr_min`, a short `texto` and `fuentes`; without it the USD.AI structure applies. `--una-hoja` also writes a one-page summary, `out/<site>-1p.pdf`.

## Who pays for the build (added 5 Nov 2026)

The full study has a table with four ways to pay for the hosting build, each from one public deal, per grid MW: your cash before first rent and what you net per month in the first year at full rent, after debt service or preferred dividend and after the mining income given up. Constants and links: `EMPERY`, `ABERNATHY`, `MACQUARIE`, `FUENTES_OBRA`.

| Structure (fictional 20 MW example) | Your cash per MW | You net per MW per month |
| --- | --- | --- |
| You build it (80% loan, 10 years at 10%) | $1.76M to $2.41M | $21,211 to -$25,872 |
| Tenant pays the build (Empery: triple net, tenant funds build-out and operating costs; $440M over 15 years for 150 MW) | none | $14,826 |
| Joint venture with the tenant (Abernathy: you 50.1%, $1.3B of bonds at 7.25%, ~$260M average NOI for 168 MW of IT) | $0.10M to $0.87M | $30,215 (bond principal not public, treated as interest-only) |
| Preferred equity covers your cash (Macquarie: $2.25M per leased MW at 12.75%, plus 15% of common) | $29,437 to $0.68M | $2,822 to -$44,261 |

Each comes from a large site with a signed or near-signed tenant; none is offered to a 5 to 50 MW site in the sources found.

## The mix (added 4 Nov 2026)

Splits the site 0, 25, 50, 75 and 100% to AI hosting (plus `--mw-ia` if given) and, for each split, over the same 8 months: site net per day, worst month, months at or below zero, share of revenue under the lease, and the AI capex. Only hosting is mixed, because it is the income with a contract, the one a lender can value.

What the example shows (20 MW, $50/MWh, 27 J/TH, PUE 1.3): any split with AI has 0 of 8 months at or below zero, and at 5 MW to AI 47% of revenue is under lease. In the model the split is not a revenue question, since one hosting MW earns about 15x a mining MW in Sep 2026. It is a capex question: 5 MW to AI is $30.8M to $42.3M.

## Financing, construction and ramp (added 4 Nov 2026)

Per grid MW moved to AI hosting, month by month from signing: 12 months of construction with no AI income, the loan drawn evenly and its interest paid monthly, the MW stop mining at signing, a 6-month linear ramp to full rent net of site costs, then equal monthly principal from first rent. Four cases: 5 or 10 years, at 10% or 15%, each at low and high hosting capex. Each case runs favorable (low capex, 85% NOI margin) and unfavorable (high capex, 70% NOI margin). For each: your cash before first rent (20% of capex, 3-month debt-service reserve, interest during construction, mining given up during construction), DSCR in the first year at full rent against 1.15x, and months from signing until your cash is back. The section opens with a one-line answer, and page 1 has a box with the cash per MW and who could put it up instead.

What the example shows: on USD.AI's 5-year term the rent does not cover the payment (DSCR 0.46x to 0.87x). On a 10-year term at 10% it passes only in the favorable case (1.29x; 0.77x unfavorable): $1.76M of your cash per MW before first rent ($1.23M equity, $0.25M reserve, $0.27M interest during construction, $0.02M mining given up), back in 82 months (6.8 years) from signing. At 15% no case passes 1.15x.

Constants and links at the top of the script (`ANTICIPO`, `RESERVA_MESES`, `DSCR_MIN`, `PLAZOS`, `TASAS`, `OBRA_MESES`, `ARRANQUE_MESES`, `FUENTES_DEUDA`), read 4 Nov 2026:

- 80% loan, 20% equity, 3 to 5 years with equal monthly principal, 3-month reserve, 1.15x DSCR: [USD.AI underwriting](https://usd.ai/blog/usdai-underwriting-and-risk-management). USD.AI lends against GPUs in Tier III/IV sites, not against buildings; the sheet uses its structure as a reference for the hosting build.
- 10% to 15%: what USD.AI charged smaller operators, per [American Compute, updated 10 Oct 2026](https://www.amcompute.com/gpu-debt/pricing) (observed public prices; American Compute sells services, so indicative). The same page puts tenant-backed data center debt at 6.00% to 9.875%, and SOFR + 4.00% to 5.50% for GPU loans backed by non-investment-grade customers.
- 10 years: base term of TeraWulf's and Cipher's Fluidstack leases.
- 12 months of construction: Cipher signed Barber Lake on 25 Sep 2025 with rent from Oct 2026 ([business update, 24 Feb 2026](https://www.sec.gov/Archives/edgar/data/1819989/000181998926000007/cipherdigital_businessup.htm)); TeraWulf signed on 14 Aug 2025 and delivered CB-3 in early Jul 2026, and its CB-5 slipped from 2H 2026 to early 2027 ([Q2 2026 results](https://www.sec.gov/Archives/edgar/data/0001083301/000108330126000162/a_wulfearningsreleaseq22026.htm)).
- Site costs, as NOI margin (rent less property operating expenses, property taxes and insurance): 85% at TeraWulf ([14 Aug 2025](https://www.sec.gov/Archives/edgar/data/1083301/000110465925078084/tm2523008d2_ex99-1.htm)), 80% to 85% at Cipher ([25 Sep 2025](https://www.sec.gov/Archives/edgar/data/1819989/000095010325012168/dp234624_ex9901.htm)), ~70% average over lease life at TeraWulf's Abernathy JV ([Oct 2025](https://www.sec.gov/Archives/edgar/data/0001083301/000110465925102858/tm2529509d1_ex99-3.htm)).
- Interest during construction: loan drawn evenly over the 12 months, interest paid monthly. This is a modeling assumption with no source for a small site's draw schedule.
- Mining given up: the AI MW stop mining at signing and lose the average net of the last 8 months.
- Who could put up the cash instead (`QUIEN_PONE`): the tenant as JV partner (Fluidstack 49.9% of TeraWulf's Abernathy JV), a GPU host's capital arm ([Hydra Capital](https://hydrahost.com/financing/), "as little as 5% down"), convertible notes ([Blockfusion and Sona, term sheet for $175M](https://www.theenergymag.com/news/2026-07-01/blockfusion-ai-bitcoin-spac)), the operator's bitcoin ([PowerCompute and Arch](https://www.sec.gov/Archives/edgar/data/0001640384/000119312526408391/lmfa-ex99_1.htm)). Google's backstop supports the rent, not the equity.
- 6-month ramp: TeraWulf's plan of ~40 of 200 MW in 1H 2026 and all by year-end ([14 Aug 2025](https://www.sec.gov/Archives/edgar/data/1083301/000110465925078084/tm2523008d2_ex99-1.htm)).

## Outside the model (read 2 Nov 2026, marked on the sheet)

- Hosting capex: $8M to $11M per MW of critical IT, from TeraWulf (Aug and Oct 2025) and Cipher (Sep 2025) filings on their Fluidstack deals. The sheet divides by PUE to put it per grid MW. Values and links live in `CAPEX_HOSTING_IT` and `FUENTES_HOSTING` at the top of the script.
- Power in hosting: TeraWulf's Abernathy deck says "Power 100% passed-through to tenant", so the hosting path carries no power cost. Cipher's release says "modified gross lease" and does not state power terms.
- Simple payback = capex per MW / (net USD per MW per day x 365). No depreciation, financing, staff, site operating costs or tenant risk.

## Still missing (gaps on the sheet)

- For the financing: a real draw schedule (USD.AI holds funds in escrow until servers are online, so who pays the builder before that is not public), income taxes, depreciation, and the reserve coming back at the end. No source shows anyone putting up the 20% for a 5 to 50 MW site without a signed tenant, or a tenant prepaying rent to fund the build. Construction and ramp come from large public operators; there is no public benchmark for a 20 MW site. A real rate for a small operator with a neocloud tenant (not Google or AWS) is still missing. Moving MW in tranches is not modeled.

- ASIC price per TH for a fleet refresh, so mining has no payback. Hashrate Index's ASIC Price Index chart needs JavaScript and showed no values without it.
- Cooling overhead for mining: all site MW goes to ASICs.
- Whether the US$20M per MW for owned GPUs is per MW of IT or of grid, and what it includes.
