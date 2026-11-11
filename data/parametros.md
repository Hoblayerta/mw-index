# Parámetros del modelo por MW (con fuente)

## Minería
- Eficiencia de flota: S19j Pro 29.5 J/TH; S21 17.5 J/TH; última generación <15 J/TH (CoinShares Q1 2026, Luxor mar 2026)
- Costo de electricidad típico: US$0.048/kWh promedio; mitad del hashrate entre 0.038 y 0.058 (Luxor jul 2026)
- Capex: ~US$0.7 a 1 M por MW (CoinShares Q4 2025)
- Precio de máquinas, USD por TH (Hashrate Index ASIC Price Index, promedio de sep 2026; último dato público 27 sep 2026): <14 J/TH 18.38; 14-19 J/TH 3.84; 19-25 J/TH 3.04; 25-38 J/TH 1.06. Hashrate Index lo cobra (Platinum); The Block lo publica gratis con Luxor como fuente (https://www.theblock.co/data/on-chain-metrics/bitcoin/bitcoin-asic-price-index), leído el 11 nov 2026 a las 06:21 UTC. Serie mensual desde ago 2024 en asic_precio.csv, diaria en asic_precio_diario.csv, con leer_asic_precio.py
- Verificación: Luxor "Energy Hashprice" jun 2026: <14 J/TH ~US$105/MWh; 14-19 J/TH ~US$77/MWh; 19-25 ~US$58; 25-38 ~US$40

## GPU
- H100 SXM: 700 W TDP; DGX H100 (8 GPU + CPU + red): 10.2 kW máximo (hoja NVIDIA)
- PUE: aire 1.3-1.6; líquida directa 1.1-1.2
- H100 por MW IT: 690 a 785 (derivado)
- Utilización típica en modelos públicos: ~71% (Epoch, modelo de 1 GW)
- Capex: ~US$20 M por MW (CoinShares Q4 2025)

## Hosting (lo que cobra un minero convertido, sin GPU propia)
- TeraWulf-Fluidstack: ~US$1.85 M por MW IT al año (~US$154/kW/mes)
- Cipher-Fluidstack: ~US$1.79 M por MW IT al año; ampliación ~US$2.13 M
- Colocation wholesale EE.UU. H2 2025: ~US$196/kW/mes (CBRE vía secundario)
