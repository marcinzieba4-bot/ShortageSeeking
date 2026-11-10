"""Builds report/shortage-rotation-report.html from outputs/v6/_state.pkl (run run6.py first)."""
import json, html, numpy as np, pandas as pd
from shortage import backtest as B
S = pd.read_pickle("outputs/v6/_state.pkl")
r0, spy, rnd, TR, A, RND, yr = S["r0"], S["spy"], S["rnd"], S["TR"], S["A"], S["RND"], S["yr"]
eq, sp = (1 + r0).cumprod(), (1 + spy).cumprod()
wk = eq.resample("W-FRI").last().index.intersection(eq.index) if False else eq.resample("W-FRI").last().dropna().index
g = lambda s: [round(float(x), 4) for x in s.resample("W-FRI").last().dropna().values]
dd = eq / eq.cummax() - 1; dds = sp / sp.cummax() - 1
curve = dict(d=[d.strftime("%Y-%m-%d") for d in wk], rot=g(eq), spy=g(sp), p5=g(rnd.quantile(.05, axis=1)), p50=g(rnd.median(axis=1)), p95=g(rnd.quantile(.95, axis=1)),
             dd=g(dd), dds=g(dds))
P, PS = B.perf(r0), B.perf(spy)
m = pd.DataFrame({"a": r0, "b": spy}).resample("ME").apply(lambda d: (1 + d).prod() - 1)
trades = [dict(n=int(i), theme=x.theme, assets=x.assets, signal=x.signal, buy=str(x.buy), sell="open" if x.open else str(x.sell), days=int(x.days), ret=round(x.ret, 4),
               spy=round(x.spy, 4), contrib=round(x.contribution, 4), why=x.why_bought, sold=x.why_sold) for i, x in TR.iterrows()]
bysig = TR.groupby("signal").agg(n=("ret", "size"), won=("ret", lambda x: (x > 0).mean()), mean=("ret", "mean"), contrib=("contribution", "sum")).sort_values("contrib", ascending=False)
byth = TR.groupby("theme").agg(n=("ret", "size"), contrib=("contribution", "sum")).sort_values("contrib", ascending=False)
top10 = TR.contribution.sort_values(ascending=False).head(10).sum() / TR.contribution.sum()
pc = lambda x, d=1: f"{x * 100:+.{d}f}%"; pp = lambda x, d=1: f"{x * 100:.{d}f}%"
me = {k: (RND[k] < v).mean() for k, v in dict(cagr=P["cagr"], sharpe=P["sharpe"]).items()}
DATA = dict(curve=curve, years=[dict(y=int(y), rot=round(v.rotation, 4), spy=round(v.SPY, 4)) for y, v in yr.iterrows()], trades=trades)
def rows(df, cols): return "".join("<tr>" + "".join(f"<td>{c(r)}</td>" for c in cols) + "</tr>" for _, r in df.iterrows())
add = A.reset_index()
add_rows = rows(add, [lambda r: html.escape(r.rule), lambda r: pp(r.cagr), lambda r: f"{r.sharpe:.2f}", lambda r: pp(r.maxdd, 0), lambda r: f"{r.sharpe_18_22:.2f}", lambda r: f"{r.sharpe_23_26:.2f}"])
sig_rows = rows(bysig.reset_index(), [lambda r: r.signal, lambda r: int(r.n), lambda r: pp(r.won, 0), lambda r: pc(r["mean"]), lambda r: pc(r.contrib, 0)])
th_rows = rows(byth.reset_index(), [lambda r: html.escape(r.theme), lambda r: int(r.n), lambda r: pc(r.contrib, 0)])
yr_rows = "".join(f"<tr><td>{int(y)}{' to date' if y == yr.index[-1] else ''}</td><td>{pc(v.rotation, 0)}</td><td>{pc(v.SPY, 0)}</td><td>{(v.rotation - v.SPY) * 100:+.0f}</td></tr>" for y, v in yr.iterrows())
op = TR[TR.open]
T = open("report/template.html").read()
rep = {"{{DATA}}": json.dumps(DATA, separators=(",", ":")), "{{CAGR}}": pp(P["cagr"]), "{{CAGR_SPY}}": pp(PS["cagr"]), "{{SHARPE}}": f"{P['sharpe']:.2f}", "{{SHARPE_SPY}}": f"{PS['sharpe']:.2f}",
       "{{VOL}}": pp(P["vol"], 0), "{{VOL_SPY}}": pp(PS["vol"], 0), "{{DD}}": pp(P["maxdd"], 0), "{{DD_SPY}}": pp(PS["maxdd"], 0), "{{MULT}}": f"{eq.iloc[-1]:.0f}x", "{{MULT_SPY}}": f"{sp.iloc[-1]:.1f}x",
       "{{NTR}}": str(len(TR)), "{{WON}}": pp((TR.ret > 0).mean(), 0), "{{BEAT}}": pp((TR.vs_spy > 0).mean(), 0), "{{MEAN}}": pc(TR.ret.mean()), "{{MEDIAN}}": pc(TR.ret.median()),
       "{{DAYS}}": f"{TR.days.mean():.0f}", "{{TOP10}}": pp(top10, 0), "{{MONTHS}}": pp((m.a > m.b).mean(), 0), "{{CORR}}": f"{r0.corr(spy):.2f}",
       "{{RND_CAGR}}": pp(RND.cagr.median()), "{{RND_SHARPE}}": f"{RND.sharpe.median():.2f}", "{{RND95_CAGR}}": pp(RND.cagr.quantile(.95)), "{{RND95_SHARPE}}": f"{RND.sharpe.quantile(.95):.2f}",
       "{{PCT_CAGR}}": "all 500" if me["cagr"] >= 1 else pp(me["cagr"], 1) + " of the 500", "{{RANK_CAGR}}": f"{int(round(me['cagr'] * 500))} of 500", "{{RANK_SHARPE}}": f"{int(round(me['sharpe'] * 500))} of 500", "{{RND_DD}}": pp(RND.maxdd.median(), 0),
       "{{ADD_ROWS}}": add_rows, "{{SIG_ROWS}}": sig_rows, "{{TH_ROWS}}": th_rows, "{{YR_ROWS}}": yr_rows,
       "{{OPEN}}": "; ".join(f"{x.theme} ({x.assets}), bought {x.buy}, {pc(x.ret)} so far" for _, x in op.iterrows()) or "none",
       "{{ASOF}}": eq.index[-1].strftime("%-d %B %Y")}
for k, v in rep.items(): T = T.replace(k, v)
open("report/shortage-rotation-report.html", "w").write(T); print(len(T) // 1024, "KB", {k: v for k, v in rep.items() if len(v) < 12})
