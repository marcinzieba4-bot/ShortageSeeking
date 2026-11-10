"""v5: one combined shortage universe (price + forum news + earnings-call bottlenecks), then
which overlay adds value: 50-day in/out, 100-day entry gate, rotation. Outputs in outputs/v5/."""
import os, numpy as np, pandas as pd
from shortage import config as C, data as D, backtest as B, v2 as V, bottleneck as BN, filings as F, hn as HN

OUT = "outputs/v5"; os.makedirs(OUT, exist_ok=True)
pd.set_option("display.width", 250, "display.max_rows", 200)
SPLIT = pd.Timestamp(C.V2["split"])

# ---- unified themes: bottleneck inputs and news topics that duplicate a price theme share its basket
SAME = {"Copper": "copper", "Aluminium": "aluminum", "Uranium / enrichment": "uranium", "Lithium / battery materials": "lithium",
        "Natural gas / LNG": "us_gas", "Crude oil / refining": "oil", "Fertiliser": "fertilizer", "Grains / oilseeds": "agri",
        "Lumber / wood": "lumber", "Vehicles (new / used)": "used_cars", "Cattle / beef / eggs / cocoa": "eggs",
        "HBM / DRAM / NAND memory": "memory", "AI accelerators / GPUs": "gpu", "Transformers / switchgear": "power_eq",
        "Ships / containers / freight": "containers", "Mature-node / auto chips": "chips"}
baskets = {k: v["tickers"] for k, v in C.THEMES.items()}
for k, v in BN.SUPPLIERS.items():
    if k not in SAME: baskets[k] = v
tick = sorted({t for v in baskets.values() for t in v} | set(C.BENCH))
px = D.prices(tick); cal = px["SPY"].dropna().index; px = px.reindex(cal)
ret = px.ffill(limit=5).pct_change(fill_method=None)
tr = pd.DataFrame({k: ret[[t for t in v if t in ret]].mean(axis=1, skipna=True) for k, v in baskets.items()}).fillna(0)
spy = ret["SPY"].fillna(0); cash = ret["BIL"].fillna(0); idx = cal[cal >= C.START]

def daily(states, lag, key=lambda k: k):
    """monthly 0/1 states -> daily 'known at this close' matrix; a feed that stopped is switched off."""
    M = pd.DataFrame(0.0, index=cal, columns=tr.columns)
    for k, g in states.items():
        th = key(k)
        if th not in M: continue
        lg = lag(k) if callable(lag) else lag
        for m in g.index[g.state.values > 0]:
            d0, d1 = B.trade_date(m, lg, cal), B.trade_date(m + 1, lg, cal)
            if d0 is None: continue
            M.loc[(cal >= d0) & (cal < (d1 if d1 is not None else cal[-1] + pd.Timedelta(days=1))), th] = 1
    return M

items = D.item_series(); up, _ = V.price_signals(items, C.PARAMS)
src = {k: (s, th) for k, _, s, _, th in C.ITEMS}
ON_P = daily(up, lambda k: C.LAG[src[k][0]], lambda k: src[k][1])
# news: the same rule on every topic the forum data covers (not only the four news-only themes)
sh, gl, tot = HN.counts(); nar = V.narrative(sh, gl, tot)
keep = C.SENT_ONLY; C.SENT_ONLY = list(nar); nu, _ = V.news_only_states(nar); C.SENT_ONLY = keep
ON_N = daily(nu, C.V2["sent_lag"])
# earnings calls: bottleneck when >=3 firms cite it at >=2x norm (calls end May 2025)
H = BN.heat(*BN.breadth(BN.load(F.CALLS))); cu, _ = BN.states(H, min_firms=3)
ON_C = daily(cu, BN.B["lag"], lambda k: SAME.get(k, k))
ON = ((ON_P + ON_N + ON_C) > 0).astype(float); NSRC = ON_P + ON_N + ON_C

level = (1 + tr).cumprod(); ma50, ma100 = level.rolling(50).mean(), level.rolling(100).mean()
mom = level / level.shift(126) - 1

def gate(on, cond):
    """Entry gate: once a shortage is active, wait until cond is true, then stay in until the shortage ends."""
    out = pd.DataFrame(0.0, index=on.index, columns=on.columns)
    for c in on:
        latched = False; o, k = on[c].values, cond[c].values; v = np.zeros(len(o))
        for i in range(len(o)):
            if not o[i]: latched = False
            elif latched or k[i]: latched = True
            v[i] = latched
        out[c] = v
    return out

def run(active, top=None, rank=None, every=63, cap=C.PARAMS["cap"], seed=None):
    a = active.reindex(idx).fillna(0)
    if top:
        rng = np.random.default_rng(seed) if seed is not None else None
        pick = pd.DataFrame(0.0, index=idx, columns=a.columns); cur = []
        for i, d in enumerate(idx):
            cur = [c for c in cur if a.at[d, c] > 0]
            if i % every == 0 or not cur:
                live = a.columns[a.loc[d] > 0]
                if rng is not None: cur = list(rng.permutation(live)[:top])
                else: cur = list(rank.loc[d, live].fillna(-9).sort_values(ascending=False).index[:top])
            pick.loc[d, cur] = 1
        a = pick; cap = 1 / top
    n = a.sum(axis=1); w = a.div(n.where(n > 0, 1), axis=0).clip(upper=cap).shift(1).fillna(0)
    cost = w.diff().abs().sum(axis=1).fillna(0) * C.PARAMS["cost_bps"] / 1e4
    return (w * tr.reindex(idx)).sum(axis=1) + (1 - w.sum(axis=1)) * cash.reindex(idx) - cost, w

def row(nm, r, w=None):
    a, b, t = B.perf(r), B.perf(r[r.index < SPLIT]), B.perf(r[r.index >= SPLIT])
    return dict(rule=nm, cagr=a["cagr"], sharpe=a["sharpe"], maxdd=a["maxdd"], cagr_18_22=b["cagr"], sharpe_18_22=b["sharpe"],
                cagr_23_26=t["cagr"], sharpe_23_26=t["sharpe"], maxdd_23_26=t["maxdd"],
                invested=np.nan if w is None else w.sum(axis=1).mean(), trades_per_yr=np.nan if w is None else w.diff().abs().sum(axis=1).sum() / (len(idx) / 252) / 2)

G100 = gate(ON, level > ma100)
rules = {
 "0. Price signals only (old base)":                   dict(active=ON_P),
 "1. Combined: price + news + call bottlenecks":       dict(active=ON),
 "2. #1 with 50-day in/out (daily)":                   dict(active=ON * (level > ma50)),
 "3. #1 with 100-day entry gate":                      dict(active=G100),
 "4. #1 with 100-day in/out (daily)":                  dict(active=ON * (level > ma100)),
 "5. #1 at 33% cap, no selection":                     dict(active=ON, cap=1 / 3),
 "6. #1 rotate quarterly, top 3 by 6m momentum":       dict(active=ON, top=3, rank=mom),
 "7. #1 rotate monthly, top 3 by 6m momentum":         dict(active=ON, top=3, rank=mom, every=21),
 "8. #1 rotate quarterly, top 3 by sources agreeing":  dict(active=ON, top=3, rank=NSRC + mom.clip(-0.9, 0.9) / 10),
 "9. #3 + rotate quarterly top 3 by momentum":         dict(active=G100, top=3, rank=mom),
 "10. #3 + rotate quarterly top 5 by momentum":        dict(active=G100, top=5, rank=mom),
 "11. #2 + rotate quarterly top 3 by momentum":        dict(active=ON * (level > ma50), top=3, rank=mom),
}
rows = []; curves = {}
for nm, kw in rules.items():
    r, w = run(**kw); rows.append(row(nm, r, w)); curves[nm] = r
# selection value: 300 portfolios that hold 3 RANDOM active shortages, re-drawn quarterly
rnd = pd.DataFrame([row("x", run(ON, top=3, seed=s)[0]) for s in range(300)])
m = rnd.drop(columns="rule").mean().to_dict(); m["rule"] = "   random 3 active shortages (mean of 300)"; rows.append(m)
rnd2 = pd.DataFrame([row("x", run(G100, top=3, seed=s)[0]) for s in range(300)])
m = rnd2.drop(columns="rule").mean().to_dict(); m["rule"] = "   random 3 from 100-day-gated set (mean of 300)"; rows.append(m)
rows.append(row("SPY", spy.reindex(idx)))
T = pd.DataFrame(rows); T.to_csv(f"{OUT}/rules.csv", index=False); print(T.round(3).to_string(index=False))
for a, b, lab in (("6. #1 rotate quarterly, top 3 by 6m momentum", rnd, "momentum top-3 vs random-3"), ("9. #3 + rotate quarterly top 3 by momentum", rnd2, "gated momentum top-3 vs gated random-3")):
    x = T[T.rule == a].iloc[0]
    print(f"{lab}: sharpe percentile {(rnd.sharpe < x.sharpe).mean() if b is rnd else (rnd2.sharpe < x.sharpe).mean():.0%}, post-2023 sharpe percentile {(b.sharpe_23_26 < x.sharpe_23_26).mean():.0%}")
pd.DataFrame(curves).assign(SPY=spy.reindex(idx)).to_csv(f"{OUT}/daily_returns.csv")

# what each source added, held alone, and yearly results of the main candidates
S = pd.DataFrame([row(n, *run(a)) for n, a in (("price only", ON_P), ("news only", ON_N), ("calls only (to mid-2025)", ON_C))]); S.to_csv(f"{OUT}/by_source.csv", index=False)
print(); print(S.round(3).to_string(index=False))
Y = pd.DataFrame(curves)[[k for k in curves if k[:2] in ("1.", "2.", "3.", "6.", "9.")]].assign(SPY=spy.reindex(idx))
Y = Y.groupby(Y.index.year).apply(lambda d: (1 + d).prod() - 1); Y.to_csv(f"{OUT}/yearly.csv"); print(); print(Y.round(2).to_string())
# post-2023 detail: what was held
r, w = run(G100, top=3, rank=mom); h = w[w.index >= SPLIT]
print("\npost-2023 average weight, rule 9:"); print(h.mean()[h.mean() > 0.01].sort_values(ascending=False).round(3).to_string())
now = idx[-1]; print("\nactive today:", list(ON.columns[ON.loc[now] > 0]), "| passing 100-day gate:", list(G100.columns[G100.loc[now] > 0]), "| above 50-day:", list(ON.columns[(ON.loc[now] > 0) & (level.loc[now] > ma50.loc[now])]))
