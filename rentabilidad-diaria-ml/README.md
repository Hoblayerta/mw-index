# What 1 MW earns mining Bitcoin, day by day (2016 to 2026), and what machine learning can and can't tell an operator

A daily dataset and a machine-learning project built on the mw-index formulas, done as the final project of a machine-learning course (Nov 2026). The question behind it: when does an old fleet stop paying for itself, so the operator has to decide whether to move its MW to AI?

## Files

- `mw_bitcoin_diario.csv`: one row per day, 1 Jan 2016 to 28 Sep 2026, 3,921 rows. Network data plus what 1 MW nets per day with three fleets, and targets measured 30 days later.
- `construir_dataset.py`: builds the CSV from blockchain.com daily series.
- `proyecto_mw.ipynb`: the notebook, executed (EDA, logistic regression, linear regression, SVR, baselines). Reads `mw_bitcoin_diario.csv` and `../out/tabla_mw.csv`.
- `informe_proyecto_mw.pdf`: the two-page report (in Spanish).
- `h100_semanal_getdeploying.csv` and `h100_mensual_pulse.csv`: H100 hourly prices, for the mining vs AI chart only (one year of history, too short to train on).

Column names are in Spanish, like the rest of the repo.

## How the dataset is built

- **Source:** blockchain.com daily charts (`api.blockchain.info/charts/<name>?timespan=all&format=csv`), downloaded 5 Nov 2026: `market-price`, `hash-rate`, `difficulty`, `transaction-fees-usd`, `miners-revenue`, `n-transactions`, `avg-block-size`, `cost-per-transaction`. Put them in one folder and run `python3 construir_dataset.py <folder> mw_bitcoin_diario.csv`.
- **Hashprice** = miner revenue of the day / hashrate in PH/s. Checked against `../out/tabla_mw.csv`: it runs $2 to $4 above Luxor's (blockchain.com estimates hashrate differently), and the months where the old fleet goes negative match (Feb, Mar, Jun and Jul 2026).
- **Net per MW** = hashprice x PH/s per MW − 24 MWh x power price, the same formula as `mw_model.py`, for the 29.5, 17.5 and 13.5 J/TH fleets. **Power at $0.07/kWh**, not the model's $0.048: at $0.048 almost no day is unprofitable and a classifier has nothing to learn.
- **Targets (`*_30d`) are measured 30 days after each row** and are never used as inputs. The last 30 days are dropped.
- **From 2016:** before that the network was so small that hashprice was in the thousands of dollars per PH.

## Main columns

| Column | What it is |
| --- | --- |
| `fecha`, `anio`, `mes`, `dia_semana` | Date, year, month, weekday (1 = Monday) |
| `ciclo_halving`, `dias_desde_halving` | Which halving was last (1 = 2012 ... 4 = 2024) and days since it |
| `btc_usd`, `hashrate_eh_s`, `dificultad_t` | Price, hashrate (EH/s), difficulty (trillions) |
| `fees_usd_dia`, `fees_pct_ingreso`, `ingreso_minero_usd_dia` | Fees, fees as % of miner revenue, subsidy plus fees |
| `n_transacciones`, `tam_bloque_mb`, `costo_por_tx_usd` | Transactions, average block size, miner revenue per transaction |
| `hashprice_usd_ph_dia` | USD per PH/s per day |
| `mw_vieja/media/nueva_neto_usd_dia` | USD net per MW per day, 29.5 / 17.5 / 13.5 J/TH |
| `hashprice_30d_despues` | Hashprice 30 days later |
| `mw_vieja/media/nueva_margen_30d_usd` | USD net per MW over the next 30 days (today + 29) |
| `mw_vieja_rentable_30d` | 1 if the old fleet is still net positive 30 days later: 3,369 of 3,921 days (85.9%). The 552 that aren't fall in 2024 (34% of its days), 2025 (43%) and 2026 (100%) |

## Results

Every model is tested two ways: a random split (`train_test_split`, 15% test) and a split by date (train through Nov 2024, test on 2025 and 2026), because neighboring days look alike and a random split inflates the scores. Each model is also compared to a simple baseline.

| Model | Random split | Split by date (test 2025 and 2026) |
| --- | --- | --- |
| Logistic regression: old fleet profitable in 30 days | Accuracy 96.8%, precision 87.4%, recall 90.5% | Accuracy 67.8%, recall 100%, because it calls 632 of 633 days unprofitable |
| Baseline: in 30 days it stays as today | n/a | Accuracy 85.2%, precision 92.0%, recall 85.5% |
| Linear regression: hashrate from price and days since halving | R² 83.8% | R² negative |
| SVR (rbf, C=100): hashrate | R² 95.0% | R² negative |
| 30-day margin per MW, old fleet: baseline "today x 30" vs linear / SVR | n/a | MAE $2,757 (baseline, right sign 92.9% of the time) vs $33,308 / $152,423 |

**What it says:**

- **None of the class models beats the simple rule.** What an operator sees on today's power bill, times 30, forecasts next month better than any of them. A classifier with 100% recall can still be useless for deciding when to act.
- **The data alone answers the useful question.** In 2026 the old fleet at 7 cents loses money in all 271 thirty-day windows (median −$14,493 per MW per month). It only breaks even with power under 5.17 cents/kWh. The 17.5 and 13.5 J/TH fleets never lose over 30 days.
- **Fees are not what saves a miner.** They were 4.5% of miner revenue on average (median 2%). Only one day since 2016 went above 50% (20 Apr 2024, Runes).
- **Mining only catches up with AI hosting at much higher Bitcoin prices.** With Sep 2026 hashprice and power at 7 cents, matching AI hosting (~$3,899 per MW per day) takes Bitcoin at about $305k for the old fleet, $181k for the 17.5 J/TH fleet and $139k for the 13.5 one. That is a floor: when price rises, hashrate follows and the bar moves up.
- **There is no public data to model AI against Bitcoin.** With 13 months of H100 prices, the correlation with hashprice is −0.44 and flips sign depending on the period.

## Sources and licenses

- blockchain.com daily charts (network series).
- mw-index formulas and parameters (this repo: Luxor, CoinShares, TeraWulf / Fluidstack).
- [GetDeploying GPU prices](https://getdeploying.com/dataset/gpu-prices) and [Pulse Intelligence](https://pulse-intelligence-exa.pages.dev/data/), CC BY 4.0.
- Earlier ML work on mining ROI: [MineROI-Net, arXiv 2512.05402](https://arxiv.org/abs/2512.05402) (Dec 2025), whose data scripts pull the same blockchain.com series.

## Not in this dataset

Each operator's real power price (7 cents is used for all), inference token prices (Pulse's public index is empty) and a long history of GPU prices (only from 2025).
