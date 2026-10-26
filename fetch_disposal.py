import os,json,re,time,urllib.request,urllib.error
import pandas as pd, numpy as np
CACHE=r"C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\disposal_cache"
os.makedirs(CACHE,exist_ok=True)
def get(url,fn):
    p=os.path.join(CACHE,fn)
    if os.path.exists(p) and os.path.getsize(p)>50:
        return open(p,encoding="utf-8",errors="ignore").read()
    for attempt in range(4):
        try:
            req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0"})
            c=urllib.request.urlopen(req,timeout=40).read().decode("utf-8","ignore")
            open(p,"w",encoding="utf-8").write(c); time.sleep(0.25); return c
        except Exception as e:
            time.sleep(1.5+attempt)
    return None
months=pd.period_range("2010-01","2026-06",freq="M")
rows=[]; fail=[]
for i,per in enumerate(months):
    y,m=per.year,per.month
    # TWSE (西元)
    u1=f"https://www.twse.com.tw/announcement/punish?response=json&startDate={y}{m:02d}01&endDate={y}{m:02d}28"
    c=get(u1,f"twse_{y}{m:02d}.json")
    if c is None: fail.append(("TWSE",y,m))
    else:
        try:
            j=json.loads(c)
            for r in j.get("data",[]) or []:
                d=dict(zip(j["fields"],r))
                rows.append({"mkt":"TWSE","code":str(d.get("證券代號","")).strip(),"period":str(d.get("處置起迄時間","")),"announce":str(d.get("公布日期",""))})
        except Exception as e: fail.append(("TWSEparse",y,m,str(e)[:40]))
    # TPEx (民國)
    ry=y-1911
    u2=f"https://www.tpex.org.tw/www/zh-tw/bulletin/disposal?type=all&startDate={ry}/{m:02d}/01&endDate={ry}/{m:02d}/28"
    c=get(u2,f"tpex_{y}{m:02d}.json")
    if c is None: fail.append(("TPEx",y,m))
    else:
        try:
            j=json.loads(c)
            for t in j.get("tables",[]) or []:
                f=t.get("fields",[])
                for r in t.get("data",[]) or []:
                    d=dict(zip(f,r))
                    rows.append({"mkt":"TPEx","code":str(d.get("證券代號","")).strip(),"period":str(d.get("處置起訖時間",d.get("處置起迄時間",""))),"announce":str(d.get("公布日期",""))})
        except Exception as e: fail.append(("TPExparse",y,m,str(e)[:40]))
    if i%12==0: print(f"  {i+1}/{len(months)} {y}-{m:02d}  rows={len(rows)}",flush=True)
print("raw announcements:",len(rows))
print("failures:",fail[:10],len(fail))
pd.DataFrame(rows).to_pickle("disposal_raw.pkl")
print("saved disposal_raw.pkl")
