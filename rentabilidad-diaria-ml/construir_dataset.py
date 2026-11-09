# Construye mw_bitcoin_diario.csv a partir de los CSV de blockchain.com
# Uso: python3 construir_dataset.py <carpeta_con_csv_blockchain> <salida.csv>
import pandas as pd, numpy as np, sys
src, out = sys.argv[1], sys.argv[2]
names={'market-price':'btc_usd','hash-rate':'hashrate_eh_s','difficulty':'dificultad_t','transaction-fees-usd':'fees_usd_dia',
       'miners-revenue':'ingreso_minero_usd_dia','n-transactions':'n_transacciones','avg-block-size':'tam_bloque_mb','cost-per-transaction':'costo_por_tx_usd'}
dfs=[]
for f,c in names.items():
    d=pd.read_csv(f'{src}/{f}.csv',header=None,names=['fecha',c]); d['fecha']=pd.to_datetime(d.fecha).dt.normalize()
    dfs.append(d.groupby('fecha')[c].mean())
df=pd.concat(dfs,axis=1).dropna()
df=df[df.index>='2016-01-01']   # desde 2016 el mercado es el que conocemos (ASIC, pools, hashrate estable)
df['hashrate_eh_s']=df.hashrate_eh_s/1e6          # TH/s -> EH/s
df['dificultad_t']=df.dificultad_t/1e12           # -> billones (T)
df['fees_pct_ingreso']=df.fees_usd_dia/df.ingreso_minero_usd_dia*100
# hashprice: USD que gana 1 PH/s en un dia = ingreso minero del dia / hashrate en PH/s
df['hashprice_usd_ph_dia']=df.ingreso_minero_usd_dia/(df.hashrate_eh_s*1000)
# lo que gana 1 MW neto por dia con cada flota (formula de mw_model.py), luz 0.07 USD/kWh
LUZ=0.07
for nombre,jth in [('vieja',29.5),('media',17.5),('nueva',13.5)]:
    ph_por_mw=1_000_000/jth/1000
    df[f'mw_{nombre}_neto_usd_dia']=df.hashprice_usd_ph_dia*ph_por_mw-24*1000*LUZ
# objetivos: lo que pasa 30 dias despues
df['hashprice_30d_despues']=df.hashprice_usd_ph_dia.shift(-30)
df['mw_vieja_rentable_30d']=(df.mw_vieja_neto_usd_dia.shift(-30)>0).astype(int)
# margen acumulado de los proximos 30 dias (hoy + 29 dias) por flota: lo que gana o pierde 1 MW si sigue encendido un mes
for nombre in ['vieja','media','nueva']:
    df[f'mw_{nombre}_margen_30d_usd']=df[f'mw_{nombre}_neto_usd_dia'][::-1].rolling(30).sum()[::-1]
df=df.iloc[:-30]
# ciclo de Bitcoin: dias desde el ultimo halving (28 nov 2012, 9 jul 2016, 11 may 2020, 20 abr 2024)
halvings=pd.to_datetime(['2012-11-28','2016-07-09','2020-05-11','2024-04-20'])
df['dias_desde_halving']=[ (f - halvings[halvings<=f].max()).days for f in df.index ]
df['ciclo_halving']=[ int((halvings<=f).sum()) for f in df.index ]   # 1 = 2012, 2 = 2016, 3 = 2020, 4 = 2024
df['dia_semana']=df.index.dayofweek+1
df['anio']=df.index.year
df['mes']=df.index.month
cols=['anio','mes','dia_semana','ciclo_halving','dias_desde_halving','btc_usd','hashrate_eh_s','dificultad_t','fees_usd_dia','fees_pct_ingreso','ingreso_minero_usd_dia','n_transacciones','tam_bloque_mb','costo_por_tx_usd','hashprice_usd_ph_dia','mw_vieja_neto_usd_dia','mw_media_neto_usd_dia','mw_nueva_neto_usd_dia','hashprice_30d_despues','mw_vieja_rentable_30d','mw_vieja_margen_30d_usd','mw_media_margen_30d_usd','mw_nueva_margen_30d_usd']
df=df[cols].round(4); df.index.name='fecha'
df.to_csv(out)
print(df.shape, df.index.min().date(), df.index.max().date())
print('no rentable 30d:', (df.mw_vieja_rentable_30d==0).sum(), f'({(1-df.mw_vieja_rentable_30d.mean())*100:.1f}%)')
print(df.groupby('anio').mw_vieja_rentable_30d.apply(lambda s:(1-s.mean())*100).round(1))
print(df.describe().T[['mean','min','max']].round(1))
