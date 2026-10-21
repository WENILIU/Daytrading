import pandas as pd, numpy as np

df = pd.read_csv('volume_features.csv', parse_dates=['date'])
df['vol5_vs_prev'] = df['vol_first5'] / df['vol_prev']

flat_short = df[(df['direction']=='SHORT') & (df['mkt_cond']=='flat')].copy()
print(f"FLAT SHORT: {len(flat_short)} signals, WR={flat_short['win'].mean()*100:.1f}%")
print()

bins = [-1,-0.03,-0.02,-0.01,-0.005,0,0.005,0.01,0.03,1]
labels = ['<-3%','-3~-2%','-2~-1%','-1~-0.5%','-0.5~0%','0~0.5%','0.5~1%','1~3%','>3%']
flat_short['pc5'] = pd.cut(flat_short['price_chg_5min'], bins=bins, labels=labels)

print('=== [REAL-TIME] price_chg_5min ===')
for b in labels:
    sub = flat_short[flat_short['pc5']==b]
    if len(sub)>0:
        wr = sub['win'].mean()*100
        pnl = sub['pnl'].mean()*100
        print(f"  {b:10s}: {len(sub):4d} | WR={wr:5.1f}% | PnL={pnl:+.2f}%")
print()

print('=== [REAL-TIME] vol_first5 / vol_prev_day ===')
bins_v = [0,0.01,0.03,0.05,0.1,0.2,0.5,100]
labels_v = ['<1%','1-3%','3-5%','5-10%','10-20%','20-50%','>50%']
flat_short['v5r'] = pd.cut(flat_short['vol5_vs_prev'], bins=bins_v, labels=labels_v)
for b in labels_v:
    sub = flat_short[flat_short['v5r']==b]
    if len(sub)>0:
        wr = sub['win'].mean()*100
        pnl = sub['pnl'].mean()*100
        print(f"  {b:8s}: {len(sub):4d} | WR={wr:5.1f}% | PnL={pnl:+.2f}%")
print()

print('=== OPTIMAL: price drop threshold ===')
for thresh in [-0.003, -0.005, -0.008, -0.01, -0.015, -0.02]:
    take = flat_short[flat_short['price_chg_5min'] < thresh]
    skip = flat_short[flat_short['price_chg_5min'] >= thresh]
    if len(take) >= 50:
        wr_t = take['win'].mean()*100
        pnl_t = take['pnl'].mean()*100
        wr_s = skip['win'].mean()*100
        pnl_s = skip['pnl'].mean()*100
        t_s = f"{thresh*100:.1f}%"
        print(f"  drop>{t_s:6s}: TAKE {len(take):4d} (WR={wr_t:.1f}%, PnL={pnl_t:+.2f}%) | SKIP {len(skip):4d} (WR={wr_s:.1f}%, PnL={pnl_s:+.2f}%)")
print()

print('=== COMBO: price drop + vol5/prev cap ===')
for pc in [-0.005, -0.01, -0.015]:
    for vr in [0.05, 0.1, 0.2, 0.5]:
        cond = (flat_short['price_chg_5min'] < pc) & (flat_short['vol5_vs_prev'] < vr)
        sub = flat_short[cond]
        if len(sub) >= 50:
            wr = sub['win'].mean()*100
            pnl = sub['pnl'].mean()*100
            pc_s = f"{pc*100:.1f}%"
            vr_s = f"{vr*100:.0f}%"
            print(f"  drop>{pc_s} + vol5/prev<{vr_s}: {len(sub):4d} | WR={wr:5.1f}% | PnL={pnl:+.2f}%")
print()

print('=== REJECT: gap-and-go (price up + high vol) ===')
for pc in [0.005, 0.01, 0.02]:
    for vr in [0.1, 0.2, 0.3]:
        cond = (flat_short['price_chg_5min'] > pc) & (flat_short['vol5_vs_prev'] > vr)
        sub = flat_short[cond]
        if len(sub) >= 30:
            wr = sub['win'].mean()*100
            pnl = sub['pnl'].mean()*100
            pc_s = f"{pc*100:.1f}%"
            vr_s = f"{vr*100:.0f}%"
            print(f"  rise>{pc_s} + vol5/prev>{vr_s}: {len(sub):4d} | WR={wr:5.1f}% | PnL={pnl:+.2f}%")
print()

print('=== LONG signals ===')
long_df = df[df['direction']=='LONG'].copy()
print(f"Total LONG: {len(long_df)}, WR={long_df['win'].mean()*100:.1f}%")
for cond in ['up2','flat','down2']:
    sub = long_df[long_df['mkt_cond']==cond]
    if len(sub)>0:
        wr = sub['win'].mean()*100
        pnl = sub['pnl'].mean()*100
        print(f"  {cond}: {len(sub)}, WR={wr:.1f}%, PnL={pnl:+.2f}%")
print()

long_flat = long_df[long_df['mkt_cond']=='flat'].copy()
print(f"FLAT LONG: {len(long_flat)}, WR={long_flat['win'].mean()*100:.1f}%")
print('--- price_chg_5min (LONG: rising = reversal confirmed) ---')
long_flat['pc5'] = pd.cut(long_flat['price_chg_5min'], bins=bins, labels=labels)
for b in labels:
    sub = long_flat[long_flat['pc5']==b]
    if len(sub)>0:
        wr = sub['win'].mean()*100
        pnl = sub['pnl'].mean()*100
        print(f"  {b:10s}: {len(sub):4d} | WR={wr:5.1f}% | PnL={pnl:+.2f}%")
