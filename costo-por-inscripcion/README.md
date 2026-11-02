# Realized energy cost per inscription, rune and stamp, v0

For each item in a sample of 800 (100 per group): the share of its block's energy that matches the vB it used, vs the fee it paid.

| Group | Date | vB (median) | kWh at 13.5 / 17.5 / 29.5 J/TH | Energy at 17.5 J/TH | Fee paid | Fee vs energy |
| --- | --- | --- | --- | --- | --- | --- |
| NodeMonkes inscriptions | Feb 2023 | 358 | 244 / 317 / 534 | $15.19 | $0.88 | 6% |
| Bitcoin Frogs inscriptions | Mar 2023 | 1,119 | 730 / 946 / 1,595 | $45.43 | $0.91 | 2% |
| Classic stamps (#15,900 on) | Apr 2023 | 876 | 635 / 823 / 1,387 | $39.50 | $17.19 | 48% |
| OMB green inscriptions | Jun 2023 | 6,654 | 5,835 / 7,564 / 12,750 | $363.05 | $50.12 | 14% |
| SRC-20 | Dec 2023 | 254 | 304 / 395 / 665 | $18.94 | $8.83 | 46% |
| Bitcoin Puppets inscriptions | Jan 2024 | 993 | 1,203 / 1,559 / 2,628 | $74.83 | $30.28 | 41% |
| Runes, block 840,000 (launch) | Apr 2024 | 181 | 262 / 339 / 572 | $16.29 | $22.18 | 145% |
| Runes, block 967,038 | Sep 2026 | 139 | 303 / 393 / 662 | $18.85 | $0.03 | 0.2% |

Medians of 100 items per group, so the columns don't divide into each other exactly. Power at $0.048/kWh.

## Method

- Energy per block (kWh) = that day's network hashrate (TH/s) x fleet efficiency (J/TH) x 600 / 3,600,000
- Energy per inscription = energy per block x inscription vB / block vB (block weight / 4)
- Inscription vB = reveal transaction plus its share of the commit transaction. Runes and stamps are a single transaction: its vB and its fee
- Fee paid in USD = fee in sats at that day's BTC price

This is an allocation choice: miners spend energy on the block, not on each byte. Splitting it by vB answers "how much of the block's energy did this inscription's space represent".

Three fleets (13.5, 17.5 and 29.5 J/TH), same as the MW index. Each holds efficiency fixed; there is no public network-average series behind them.

## Data

- Sample of inscriptions (height, block time, vB, fee): built in Oct 2026 from ordinals.com, mempool.space and blockstream.info.
- Runes: every transaction with a runestone (an OP_RETURN output starting with OP_13, script `6a5d`) in the full block, then 100 drawn at random with a fixed seed. Blocks are ordered by fee rate, so taking the first 100 would pick the highest payers. Block 840,000 had 2,004 runestones; block 967,038 had 3,365.
- Stamps: the list of transactions comes from the public stampchain.io indexer (100 classic stamps from #15,900 on, and the SRC-20 operations in blocks 820,623 to 820,628). Weight and fee are read from mempool.space. `muestra_runes_stamps.py` builds both samples.
- Block weight per height, daily hashrate and daily BTC price: public mempool.space API, saved in `data/`.

Output: `out/inscripciones.csv` (one row per inscription) and `out/resumen_por_coleccion.csv` (medians).
