"""v4 checks: rotation among active shortage themes, moving-average filters, 'still accelerating' holding rule."""
import os, numpy as np, pandas as pd
from shortage import config as C, data as D, backtest as B, v2 as V

OUT = "outputs/v4"; os.makedirs(OUT, exist_ok=True)
SPLIT = pd.Timestamp(C.V2["split"])
items = D.item_series()
themes = {k: v for k, v in C.THEMES.items() if k not in C.SENT_ONLY}
tick = sorted({t for th in themes.values() for t in th["tickers"]} | set(C.BENCH))
px = D.prices(tick); cal = px["SPY"].dropna().index; px = px.reindex(cal)
tr = B.theme_returns(px)[list(themes)]
spy = px["SPY"].pct_change().fillna(0); cash = px["BIL"].pct_change().fillna(0)
idx = cal[cal >= C.START]
up, _ = V.price_signals(items, C.PARAMS)
src = {k: (s, th) for k, _, s, _, th in C.ITEMS}

# daily, point-in-time: is the theme in shortage, and how strong (z of its strongest item)
on = pd.DataFrame(0.0, index=cal, columns=list(themes)); zz = pd.DataFrame(np.nan, index=cal, columns=list(themes))
for k, g in up.items():
    s, th = src[k]
    stale_from = B.trade_date(g.index[-1] + 2, C.LAG[s], cal)
    for m in g.index:
        d0 = B.trade_date(m, C.LAG[s], cal); d1 = B.trade_date(m + 1, C.LAG[s], cal)
        if d0 is None: continue
        sl = (cal > d0) & (cal <= (d1 if d1 is not None else cal[-1]))
        if stale_from is not None: sl &= cal <= stale_from
        if g.state[m]:
            on.loc[sl, th] = 1
            zz.loc[sl, th] = np.fmax(zz.loc[sl, th].values, g.z[m])
level = (1 + tr).cumprod()
ma = {n: level.rolling(n).mean() for n in (50, 100, 200)}
mom = level / level.shift(126) - 1

def run(active, top=None, rank=None, every=None, cap=C.PARAMS["cap"]):
    """active: daily 0/1 known at that day's close. Optional rotation: keep top-N by `rank`, re-picked every `every` days."""
    a = active.reindex(idx).fillna(0)
    if top:
        pick = pd.DataFrame(0.0, index=idx, columns=a.columns); cur = []
        for i, d in enumerate(idx):
            if i % every == 0:
                r = rank.loc[d].where(a.loc[d] > 0).dropna().sort_values(ascending=False)
                cur = list(r.index[:top])
            cur = [c for c in cur if a.at[d, c] > 0]          # a theme whose shortage ended is dropped at once
            pick.loc[d, cur] = 1
        a = pick; cap = 1 / top
    n = a.sum(axis=1); w = a.div(n.where(n > 0, 1), axis=0).clip(upper=cap)
    w = w.shift(1).fillna(0)                                   # decided at close, earns from the next day
    cost = w.diff().abs().sum(axis=1).fillna(0) * C.PARAMS["cost_bps"] / 1e4
    r = (w * tr.reindex(idx)).sum(axis=1) + (1 - w.sum(axis=1)) * cash.reindex(idx) - cost
    return r, w.sum(axis=1).mean(), w.diff().abs().sum(axis=1).sum() / (len(idx) / 252)

onl = on.shift(1).fillna(0)       # 'on' was built as position-day; shift back so it is 'known at close'
onl = on.copy()
V4 = {
 "Base: hold every active shortage": dict(active=on),
 "Only while theme above 50-day average": dict(active=on * (level > ma[50])),
 "Only while theme above 100-day average": dict(active=on * (level > ma[100])),
 "Only while theme above 200-day average": dict(active=on * (level > ma[200])),
 "Only while still accelerating (z >= 0.5)": dict(active=on * (zz >= 0.5)),
 "Only while still accelerating (z >= 1.0)": dict(active=on * (zz >= 1.0)),
 "Rotate monthly: top 3 by shortage strength": dict(active=on, top=3, rank=zz, every=21),
 "Rotate quarterly: top 3 by shortage strength": dict(active=on, top=3, rank=zz, every=63),
 "Rotate monthly: top 3 by theme 6m momentum": dict(active=on, top=3, rank=mom, every=21),
 "Rotate quarterly: top 3 by theme 6m momentum": dict(active=on, top=3, rank=mom, every=63),
 "Rotate monthly: top 1 by shortage strength": dict(active=on, top=1, rank=zz, every=21),
 "Above 100-day avg + rotate monthly top 3 by strength": dict(active=on * (level > ma[100]), top=3, rank=zz, every=21),
}
rows = []; curves = {}
for nm, kw in V4.items():
    r, inv, turn = run(**kw); a, b, t = B.perf(r), B.perf(r[r.index < SPLIT]), B.perf(r[r.index >= SPLIT])
    rows.append(dict(rule=nm, cagr=a["cagr"], vol=a["vol"], sharpe=a["sharpe"], maxdd=a["maxdd"], sharpe_2018_22=b["sharpe"],
                     sharpe_2023_26=t["sharpe"], cagr_2023_26=t["cagr"], invested=inv, turnover_x=turn)); curves[nm] = r
a = B.perf(spy.reindex(idx)); b = B.perf(spy.reindex(idx)[idx < SPLIT]); t = B.perf(spy.reindex(idx)[idx >= SPLIT])
rows.append(dict(rule="SPY", cagr=a["cagr"], vol=a["vol"], sharpe=a["sharpe"], maxdd=a["maxdd"], sharpe_2018_22=b["sharpe"], sharpe_2023_26=t["sharpe"], cagr_2023_26=t["cagr"], invested=1, turnover_x=0))
T = pd.DataFrame(rows); T.to_csv(f"{OUT}/rules.csv", index=False)
pd.set_option("display.width", 250); print(T.round(3).to_string(index=False))
pd.DataFrame(curves).to_csv(f"{OUT}/daily_returns.csv")

# event level: where was the theme vs its averages on the entry day?
ev = pd.read_csv("outputs/events.csv", parse_dates=["entry", "exit"])
for n in (100, 200):
    ev[f"above{n}"] = [bool(level.at[d, t] > ma[n].at[d, t]) for d, t in zip(ev.entry, ev.theme)]
R = []
for n in (100, 200):
    for flag in (True, False):
        d = ev[ev[f"above{n}"] == flag]
        R.append(dict(at_entry=f"theme {'above' if flag else 'below'} {n}-day average", n=len(d), won=(d.ret > 0).mean(), mean=d.ret.mean(), median=d.ret.median(), vs_spy=d.excess.mean()))
E = pd.DataFrame(R); E.to_csv(f"{OUT}/entry_filter.csv", index=False); print(); print(E.round(3).to_string(index=False))
