import pandas as pd, numpy as np, re, collections
tw=pd.read_pickle("disposal_raw.pkl"); tw=tw[tw["mkt"]=="TWSE"].copy()
tp=pd.read_pickle("disposal_tpex.pkl").copy()
raw=pd.concat([tw[["mkt","code","period","announce"]],tp[["mkt","code","period","announce"]]],ignore_index=True)
print("announcements:",len(raw),raw["mkt"].value_counts().to_dict())
pat=re.compile(r"(\d{2,3})\s*/\s*(\d{1,2})\s*/\s*(\d{1,2})")
def parse(s):
    ms=pat.findall(str(s))
    if len(ms)<2: return None
    def mk(a,b,c):
        a=int(a); y=a+1911 if a<200 else a
        return pd.Timestamp(y,int(b),int(c))
    s=mk(*ms[0]); e=mk(*ms[1])
    if e<s: return None
    return s,e
ok=[]; n=0
for r in raw.itertuples():
    c=str(r.code).strip()
    if not re.fullmatch(r"\d{4,5}",c): n+=1; continue
    p=parse(r.period)
    if p is None: n+=1; continue
    ok.append((c,p[0],p[1]))
print("parsed intervals:",len(ok),"skipped:",n)
iv=pd.DataFrame(ok,columns=["stock","start","end"])
# trading calendar from universe
u=pd.read_pickle("universe3_raw.pkl"); u["stock"]=u["stock"].astype(str)
cal=pd.DatetimeIndex(sorted(pd.to_datetime(u["date"]).unique()))
print("trading days:",len(cal))
# expand: for each interval mark all trading days in range
rows=[]
for st,s,e in iv.itertuples(index=False):
    days=cal[(cal>=s)&(cal<=e)]
    if len(days)==0: continue
    rows.append((st,len(days),days[0],days[-1]))
tot=sum(r[1] for r in rows)
print("stock-day disposal marks (before dedup):",tot)
# build set via numpy for speed
calmap={d:i for i,d in enumerate(cal)}
marks=collections.defaultdict(set)
for st,s,e in iv.itertuples(index=False):
    idx=np.searchsorted(cal,s,"left"); jdx=np.searchsorted(cal,e,"right")
    if jdx<=idx: continue
    marks[st].update(range(idx,jdx))
recs=[]
for st,idxs in marks.items():
    a=np.array(sorted(idxs))
    recs.append(pd.DataFrame({"stock":st,"di":a}))
panel=pd.concat(recs,ignore_index=True)
panel["date"]=cal[panel["di"].values]
panel=panel[["date","stock"]].drop_duplicates()
panel["is_disposed"]=True
print("DISPOSAL PANEL:",len(panel),"rows,",panel['stock'].nunique(),"stocks")
panel.to_pickle("disposal_panel_full.pkl")
# yearly rate over universe
m=u.merge(panel,on=["date","stock"],how="left")
m["dis"]=m["is_disposed"].fillna(False).astype(bool)
print()
print("處置股佔 universe 比例（逐年）")
g=m.groupby(pd.to_datetime(m["date"]).dt.year)["dis"].agg(["sum","count","mean"])
for y,r in g.iterrows(): print(f"  {y}  {int(r['sum']):6d} / {int(r['count']):6d}  = {r['mean']*100:5.2f}%")
print()
print("TOTAL disposal share of 3%+ universe:", f"{m['dis'].mean()*100:.2f}%")
# coverage check vs old flags
old=pd.read_pickle("disposal_flags.pkl"); old["stock"]=old["stock"].astype(str)
j=old.merge(panel,on=["date","stock"],how="left"); j["new"]=j["is_disposed"].fillna(False).astype(bool)
print("old flags n=",len(j),"old True=",int(old['is_disposed'].sum()),"new True on same rows=",int(j['new'].sum()))
agree=(j["is_disposed"].astype(bool)==j["new"]).mean()
print("agreement:",f"{agree*100:.1f}%")
