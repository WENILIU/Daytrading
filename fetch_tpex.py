import os,json,time,urllib.request
import pandas as pd
CACHE=r"C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\disposal_cache"
def getb(fn,url):
    p=os.path.join(CACHE,fn+".bin")
    if os.path.exists(p) and os.path.getsize(p)>50: return open(p,"rb").read()
    for a in range(4):
        try:
            req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0"})
            b=urllib.request.urlopen(req,timeout=40).read()
            open(p,"wb").write(b); time.sleep(0.25); return b
        except Exception: time.sleep(1.5+a)
    return None
def dec(b):
    for enc in ("utf-8","big5","big5hkscs","cp950","latin-1"):
        try: return b.decode(enc)
        except Exception: continue
    return b.decode("utf-8","ignore")
months=pd.period_range("2010-01","2026-06",freq="M")
rows=[]; bad=[]
for i,per in enumerate(months):
    y,m=per.year,per.month; ry=y-1911
    u=f"https://www.tpex.org.tw/www/zh-tw/bulletin/disposal?type=all&startDate={ry}/{m:02d}/01&endDate={ry}/{m:02d}/28"
    b=getb(f"tpexb_{y}{m:02d}",u)
    if b is None: bad.append((y,m,"fetch")); continue
    try: j=json.loads(dec(b))
    except Exception as e: bad.append((y,m,"parse "+str(e)[:30])); continue
    for t in j.get("tables",[]) or []:
        f=t.get("fields",[])
        if "證券代號" not in f: bad.append((y,m,"fields "+str(f)[:40])); continue
        for r in t.get("data",[]) or []:
            d=dict(zip(f,r))
            rows.append({"mkt":"TPEx","code":str(d.get("證券代號","")).strip(),
                         "period":str(d.get("處置起訖時間",d.get("處置起迄時間",""))),
                         "announce":str(d.get("公布日期",""))})
    if i%24==0: print(f"  {i+1}/198 {y}-{m:02d} rows={len(rows)}",flush=True)
print("TPEx rows:",len(rows),"bad:",len(bad),bad[:5])
pd.DataFrame(rows).to_pickle("disposal_tpex.pkl")
