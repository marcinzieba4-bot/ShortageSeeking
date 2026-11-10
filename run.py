"""End-to-end: download -> detect shortages -> backtest -> tables + charts in outputs/."""
import itertools, os, sys
import numpy as np, pandas as pd
from shortage import config as C, data as D, backtest as B

OUT = "outputs"; os.makedirs(OUT, exist_ok=True)
refresh = "--refresh" in sys.argv
pd.set_option("display.width", 220, "display.max_columns", 40, "display.max_rows", 200)

items = D.item_series(refresh)
tick = sorted({t for th in C.THEMES.values() for t in th["tickers"]} | set(C.BENCH))
px = D.prices(tick, refresh)
missing = [t for t in tick if t not in px.columns or px[t].dropna().empty]
print("missing tickers:", missing)
cal = px["SPY"].dropna().index
px = px.reindex(cal)
tr = B.theme_returns(px)
spy = px["SPY"].pct_change().fillna(0); cash = px["BIL"].pct_change().fillna(0)
acwi = px["ACWI"].pct_change().fillna(0)

sigs = B.run_signals(items, C.PARAMS)
ev = B.build_events(sigs, cal)
es = B.event_stats(ev, tr, spy)
# ex-ante features known at entry (used only for the exploratory split in section 2b)
state = pd.DataFrame({k: v.state for k, v in sigs.items()})
es["breadth"] = [int(state.loc[m].sum()) for m in es.signal_month]
cumth = (1 + tr).cumprod()
ma200 = cumth.rolling(200).mean()
es["theme_uptrend"] = [bool(cumth.at[d, t] > ma200.at[d, t]) for d, t in zip(es.entry, es.theme)]
es["peak_vs_entry"] = es.px_peak / es.px_entry - 1
es.to_csv(f"{OUT}/events.csv", index=False)

# ---- 1. event table
show = es[["label", "theme", "signal_month", "entry", "exit", "z", "days", "ret", "spy", "excess", "fwd63", "fwd126", "fwd252", "open"]].copy()
for c in ["entry", "exit"]:
    show[c] = pd.to_datetime(show[c]).dt.date
print("\n=== EVENTS (theme return entry->exit) ===")
print(show.round(2).to_string(index=False))

# ---- 2. event-study summary
def summ(d, name):
    r = dict(set=name, n=len(d), hit=(d.ret > 0).mean(), beat_spy=(d.excess > 0).mean(),
             mean_ret=d.ret.mean(), median_ret=d.ret.median(), mean_excess=d.excess.mean(),
             avg_days=d.days.mean())
    for h in (63, 126, 252):
        r[f"fwd{h}"] = d[f"fwd{h}"].mean(); r[f"xs{h}"] = d[f"xs{h}"].mean()
    return r
fut = es.theme.map(lambda t: C.THEMES[t].get("futures", False))
S = pd.DataFrame([summ(es, "all"), summ(es[~fut], "equity themes"), summ(es[fut], "direct futures"),
                  summ(es[es.entry < "2022-01-01"], "entries 2018-21"), summ(es[es.entry >= "2022-01-01"], "entries 2022-26")])
S.to_csv(f"{OUT}/event_summary.csv", index=False)
print("\n=== EVENT SUMMARY ==="); print(S.round(3).to_string(index=False))

X = pd.DataFrame([summ(es[es.z >= 2], "z>=2"), summ(es[es.z < 2], "z<2"),
                  summ(es[es.breadth >= 4], "breadth>=4 items ON"), summ(es[es.breadth < 4], "breadth<4"),
                  summ(es[es.theme_uptrend], "theme above 200d avg"), summ(es[~es.theme_uptrend], "theme below 200d avg")])
X.to_csv(f"{OUT}/exploratory_splits.csv", index=False)
print("\n=== EXPLORATORY SPLITS (in-sample, hypotheses only) ==="); print(X.round(3).to_string(index=False))

bytheme = es.groupby("theme").agg(n=("ret", "size"), mean_ret=("ret", "mean"), mean_excess=("excess", "mean"),
                                  hit=("ret", lambda x: (x > 0).mean())).sort_values("mean_excess", ascending=False)
bytheme.to_csv(f"{OUT}/by_theme.csv")
print("\n=== BY THEME ==="); print(bytheme.round(3).to_string())

# ---- 3. placebo: signal date vs random date in the same theme
P = pd.DataFrame([B.placebo(es, tr, spy, h) for h in (63, 126, 252)])
P.to_csv(f"{OUT}/placebo.csv", index=False)
print("\n=== PLACEBO (random entry, same theme) ==="); print(P.round(3).to_string(index=False))

# ---- 4. portfolio
port, w = B.portfolio(ev, tr, cash, spy, C.PARAMS)
idx = port.index
always = tr.reindex(idx).mean(axis=1)
curves = pd.DataFrame({"Shortage (rest cash)": port.shortage_cash, "Shortage (rest SPY)": port.shortage_spy,
                       "SPY": spy.reindex(idx), "ACWI": acwi.reindex(idx), "All themes always-on": always})
PF = pd.DataFrame({k: B.perf(v) for k, v in curves.items()}).T
PF["avg_invested"] = [port.invested.mean(), 1, 1, 1, 1]
PF.to_csv(f"{OUT}/performance.csv")
print("\n=== PORTFOLIO 2018-> ==="); print(PF.round(3).to_string())
yr = curves.groupby(curves.index.year).apply(lambda d: (1 + d).prod() - 1)
yr.to_csv(f"{OUT}/yearly.csv"); print("\n=== BY YEAR ==="); print(yr.round(3).to_string())
(1 + curves).cumprod().to_csv(f"{OUT}/equity_curves.csv")

# ---- 5. sensitivity (neighbouring parameters; base case is NOT chosen from this)
rows = []
for lb, z, ma in itertools.product((3, 6, 12), (1.0, 1.5, 2.0), (3, 6, 10)):
    p = dict(C.PARAMS, lookback=lb, z_entry=z, exit_ma=ma)
    e2 = B.build_events(B.run_signals(items, p), cal)
    s2 = B.event_stats(e2, tr, spy)
    pf, _ = B.portfolio(e2, tr, cash, spy, p)
    a, b = B.perf(pf.shortage_cash), B.perf(pf.shortage_spy)
    rows.append(dict(lookback=lb, z=z, exit_ma=ma, n=len(s2), hit=(s2.ret > 0).mean(), mean_excess=s2.excess.mean(),
                     cagr_cash=a["cagr"], sharpe_cash=a["sharpe"], cagr_spy=b["cagr"], sharpe_spy=b["sharpe"]))
G = pd.DataFrame(rows); G.to_csv(f"{OUT}/sensitivity.csv", index=False)
print("\n=== SENSITIVITY ==="); print(G.round(3).to_string(index=False))

# ---- 6. live dashboard
src = {k: s for k, _, s, _, _ in C.ITEMS}
live = []
for k, lab, s, sid, th in C.ITEMS:
    g = sigs[k]; t = g.index[-1]
    live.append(dict(item=lab, theme=C.THEMES[th]["name"], tickers=",".join(C.THEMES[th]["tickers"]),
                     data_through=str(t), z=g.z[t], new_24m_high=bool(g.new_high[t]),
                     chg_6m=g.price[t] / g.price.iloc[-7] - 1, stale=t < cal[-1].to_period("M") - 2,
                     state="no data" if t < cal[-1].to_period("M") - 2 else ("ON" if g.state[t] else "off")))
L = pd.DataFrame(live).sort_values("z", ascending=False)
L.to_csv(f"{OUT}/live_signals.csv", index=False)
print("\n=== LIVE ==="); print(L.round(2).to_string(index=False))
os.makedirs("outputs", exist_ok=True); pd.to_pickle(dict(items=items, sigs=sigs, es=es, curves=curves, port=port, w=w, tr=tr), f"{OUT}/_state.pkl")
