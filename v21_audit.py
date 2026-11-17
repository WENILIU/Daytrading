import sys, io, argparse
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
ap=argparse.ArgumentParser()
ap.add_argument("--trades", default=r"v21_trades_2023-05-23_2026-12-31.csv")
ap.add_argument("--daily", default=r"v21_daily_2023-05-23_2026-12-31.csv")
ap.add_argument("--cap", type=float, default=4_500_000.0)
a=ap.parse_args()
CAP=a.cap
tr=pd.read_csv(a.trades, encoding="utf-8-sig")
for c in ["跳空pct","衰竭pct","距限制pct","張數","名義額","淨pct","淨額元","pred_q"]:
    tr[c]=pd.to_numeric(tr[c],errors="coerce")
n=len(tr); win=(tr["淨pct"]>0).mean()*100
lines=[]; P=lines.append
P("# v21 風險 / 可執行性稽核")
P("來源：%s ｜ 標記帳戶 %.0f 萬"%(a.trades,CAP/1e4)); P("")
P("## 樣本")
P("- 筆數 %d ｜ 交易日 %d ｜ 期間 %s ~ %s"%(n,tr["日期"].nunique(),tr["日期"].min(),tr["日期"].max()))
P("- 淨勝率 %.1f%% ｜ 平均淨 %.3f%% ｜ 合計淨額 %s"%(win,tr["淨pct"].mean(),"{:,.0f}".format(tr["淨額元"].sum())))
P("")
P("## 出場原因占比")
P("| 出場原因 | 筆數 | 占比 | 平均淨% | 最差淨% |")
g=tr.groupby("出場原因").agg(cnt=("淨pct","size"),avg=("淨pct","mean"),worst=("淨pct","min"))
for reason,row in g.iterrows():
    P("| %s | %d | %.1f%% | %+.2f%% | %+.2f%% |"%(reason,int(row.cnt),100*row.cnt/n,row.avg,row.worst))
P("")
P("## 單筆尾部（淨%分位）")
qs=[1,5,10,25,50,75,90,95,99]
P("- " + "  ".join("p%d %+.2f%%"%(q,np.percentile(tr["淨pct"],q)) for q in qs))
loss=tr[tr["淨pct"]<0]
P("- 虧損筆 %d（%.1f%%）平均 %+.2f%% 最差 %+.2f%%；虧損>5%% 的 %d 筆"%(len(loss),100*len(loss)/n,loss["淨pct"].mean(),loss["淨pct"].min(),(loss["淨pct"]<-5).sum()))
P("")
P("## 最差 10 筆")
P("| 日期 | 股票 | 方向 | 淨% | 淨額元 | 名義額 | 對帳戶% | 出場原因 |")
for _,x in tr.nsmallest(10,"淨額元").iterrows():
    P("| %s | %s | %s | %+.2f%% | %s | %s | %.2f%% | %s |"%(
        x["日期"],x["股票"],x["方向"],x["淨pct"],"{:,.0f}".format(x["淨額元"]),
        "{:,.0f}".format(x["名義額"]),x["淨額元"]/CAP*100,x["出場原因"]))
P("")
P("## 對帳戶衝擊（淨額元/450萬）")
imp=tr["淨額元"]/CAP*100
P("- 單筆衝擊 p1 %+.3f%% p5 %+.3f%% 中位 %+.3f%% p95 %+.3f%% ｜ 最差單筆 %+.3f%%(=%s)"%(
    np.percentile(imp,1),np.percentile(imp,5),np.median(imp),np.percentile(imp,95),
    imp.min(),"{:,.0f}".format(tr["淨額元"].min())))
P("- 單筆名義額 最大 %s(=%.1f%%帳戶) p99 %s ｜ 張數最大 %d"%(
    "{:,.0f}".format(tr["名義額"].max()),tr["名義額"].max()/CAP*100,
    "{:,.0f}".format(tr["名義額"].quantile(.99)),tr["張數"].max()))
P("")
# 逐日
d=tr.groupby("日期").agg(net=("淨額元","sum"),cnt=("淨pct","size"),notional=("名義額","sum")).reset_index().sort_values("日期")
d["netpct"]=d["net"]/CAP*100
P("## 逐日風險（450萬固定、每日平倉視角）")
P("- 最差交易日 %s: %s 元 (%+.2f%%) ｜ 最佳 %s: %s 元"%(
    d.loc[d["net"].idxmin(),"日期"] if len(d) else "-", "{:,.0f}".format(d["net"].min()) if len(d) else "-",
    d["netpct"].min() if len(d) else 0, d.loc[d["net"].idxmax(),"日期"] if len(d) else "-",
    "{:,.0f}".format(d["net"].max()) if len(d) else "-"))
P("- 單日名義額合計/450萬 最大 %.1f%% p99 %.1f%%（引擎已設≤100%%、單筆≤25%%）"%(d["notional"].max()/CAP*100, d["notional"].quantile(.99)/CAP*100))
eq=d["net"].cumsum(); peak=eq.cummax(); dd=(eq-peak); mdd=dd.min()
P("- 不復利固定450萬的累計最大回撤 = %s 元 (%.2f%% 帳戶)"%("{:,.0f}".format(mdd), mdd/CAP*100))
sign=np.sign(d["net"]); # longest losing streak
run=0; worst=0
for s in sign:
    run=run+1 if s<0 else 0; worst=max(worst,run)
P("- 連續虧損日數 最長 %d 天 ｜ 獲利日占比 %.1f%%"%(worst,(d["net"]>0).mean()*100))
P("")
P("## 可執行性/尾險 指標")
zr=tr[(tr["距限制pct"]>=1.4)&(tr["距限制pct"]<2.5)]
gr=tr[tr["跳空pct"].abs()>=7]
P("- 距漲跌幅限制 1.4~2.5%%（緩衝薄、釘死風險）%d 筆（%.1f%%）→ 實盤優先限價/避免貼限制"%(len(zr),100*len(zr)/n))
P("- 跳空|gap|≥7%%（進場滑價尾）%d 筆（%.1f%%）；引擎已 ≤8%% 上限"%(len(gr),100*len(gr)/n))
P("- 全部為當日平倉（停利/停損/13:25），0 隔夜。")
rep="\n".join(lines)
out="v21_audit_%s.md"%(a.trades.replace("v21_trades_","").replace(".csv",""))
open(out,"w",encoding="utf-8").write(rep+"\n")
print(rep)
print("\nWROTE",out)
