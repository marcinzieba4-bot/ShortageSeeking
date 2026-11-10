"""v6: monthly top-3 rotation: random benchmark, full trade list, candidate additions. Outputs in outputs/v6/."""
import os, numpy as np, pandas as pd
from shortage import config as C, backtest as B, universe as UN

OUT = "outputs/v6"; os.makedirs(OUT, exist_ok=True)
pd.set_option("display.width", 250, "display.max_rows", 400)
SPLIT = pd.Timestamp(C.V2["split"])
U = UN.build(); idx, tr, ON, level, spy = U["idx"], U["tr"], U["ON"], U["level"], U["spy"].reindex(U["idx"])
mom6 = level / level.shift(126) - 1; mom3 = level / level.shift(63) - 1; mom12 = level / level.shift(252) - 1; mom1 = level / level.shift(21) - 1
ma100 = level.rolling(100).mean()

def stats(r):
    a, b, t = B.perf(r), B.perf(r[r.index < SPLIT]), B.perf(r[r.index >= SPLIT])
    return dict(cagr=a["cagr"], vol=a["vol"], sharpe=a["sharpe"], maxdd=a["maxdd"], cagr_18_22=b["cagr"], sharpe_18_22=b["sharpe"], cagr_23_26=t["cagr"], sharpe_23_26=t["sharpe"])

# ---- 1. the strategy and its random benchmark
r0, w0 = UN.rotate(U, ON, rank=mom6, top=3, every=21)
RND = pd.DataFrame([stats(UN.rotate(U, ON, top=3, every=21, seed=s)[0]) for s in range(500)])
rnd_curves = pd.DataFrame({s: (1 + UN.rotate(U, ON, top=3, every=21, seed=s)[0]).cumprod() for s in range(200)})
me = stats(r0)
bench = pd.DataFrame({"monthly top 3 by 6m momentum": me, "random 3, median": RND.median(), "random 3, 5th pct": RND.quantile(.05), "random 3, 95th pct": RND.quantile(.95),
                      "percentile of strategy": {k: (RND[k] < me[k]).mean() for k in me}, "SPY": stats(spy)}).T
bench.to_csv(f"{OUT}/1_random_benchmark.csv"); print("=== 1. MONTHLY ROTATION vs 500 RANDOM MONTHLY PORTFOLIOS ==="); print(bench.round(3).to_string())
yr = pd.DataFrame({"rotation": r0, "SPY": spy}); yr = yr.groupby(yr.index.year).apply(lambda d: (1 + d).prod() - 1); yr["diff"] = yr.rotation - yr.SPY
yr.to_csv(f"{OUT}/1_yearly.csv"); print(); print(yr.round(3).to_string())
c = pd.DataFrame({"rotation": r0, "SPY": spy}); print("correlation with SPY", round(c.corr().iloc[0, 1], 2), "| months beating SPY", round((c.resample("ME").apply(lambda d: (1 + d).prod() - 1).pipe(lambda m: m.rotation > m.SPY)).mean(), 2))

# ---- 2. every trade (a continuous holding of one theme)
src = lambda d, t: "+".join(n for n, M in (("price", U["P"]), ("news", U["N"]), ("calls", U["C"])) if M.at[d, t] > 0)
rows = []
for t in w0.columns:
    h = (w0[t] > 0).astype(int); d = h.diff().fillna(h.iloc[0])
    for s in h.index[d == 1]:
        after = h.index[(h.index > s) & (h == 0)]
        e = after[0] if len(after) else None
        held = h.index[(h.index >= s) & (h.index < (e if e is not None else h.index[-1] + pd.Timedelta(days=1)))]
        i0 = idx.get_loc(s) - 1; dec = idx[max(i0, 0)]                    # decision day = close before first held day
        rr = float((1 + tr.loc[held, t]).prod() - 1); sp = float((1 + spy.loc[held]).prod() - 1)
        rows.append(dict(theme=U["names"].get(t, t), signal=src(dec, t) or "price", buy=dec.date(), sell=held[-1].date(), days=len(held), open=e is None,
                         ret=rr, spy=sp, vs_spy=rr - sp, contribution=float((w0.loc[held, t] * tr.loc[held, t]).sum())))
TR = pd.DataFrame(rows).sort_values("buy").reset_index(drop=True); TR.index += 1
TR.to_csv(f"{OUT}/2_trades.csv")
print(f"\n=== 2. TRADES: {len(TR)}, won {(TR.ret > 0).mean():.0%}, beat SPY {(TR.vs_spy > 0).mean():.0%}, mean {TR.ret.mean():+.1%}, median {TR.ret.median():+.1%}, avg days {TR.days.mean():.0f} ===")
print(TR.assign(ret=TR.ret.round(3), spy=TR.spy.round(3), vs_spy=TR.vs_spy.round(3), contribution=TR.contribution.round(3)).to_string())
g = TR.groupby("signal").agg(n=("ret", "size"), won=("ret", lambda x: (x > 0).mean()), mean=("ret", "mean"), contribution=("contribution", "sum")); print(); print(g.round(3).to_string())
g2 = TR.groupby("theme").agg(n=("ret", "size"), contribution=("contribution", "sum")).sort_values("contribution", ascending=False); g2.to_csv(f"{OUT}/2_by_theme.csv"); print(); print(g2.round(3).to_string())
md = ["# Every trade of the monthly top-3 shortage rotation, Jan 2018 to Nov 2026", "",
      "Return is the theme basket over the holding period; each position is one third of the portfolio.", "",
      "| # | Theme | Signal | Buy | Sell | Days | Return | SPY | vs SPY |", "|---|---|---|---|---|---|---|---|---|"]
for i, x in TR.iterrows():
    md.append(f"| {i} | {x.theme} | {x.signal} | {x.buy} | {'open' if x.open else x.sell} | {x.days} | {x.ret:+.1%} | {x.spy:+.1%} | {x.vs_spy:+.1%} |")
open("TRADES.md", "w").write("\n".join(md) + "\n")

# ---- 3. what can be added (each is one change to the monthly top-3 rotation)
G100 = pd.DataFrame(0.0, index=ON.index, columns=ON.columns)
for col in ON:
    o, k = ON[col].values, (level[col] > ma100[col]).values; v = np.zeros(len(o)); L = False
    for i in range(len(o)):
        L = bool(o[i]) and (L or bool(k[i])); v[i] = L
    G100[col] = v
blend = (mom3.rank(axis=1, pct=True) + mom6.rank(axis=1, pct=True) + mom12.rank(axis=1, pct=True)) / 3
add = {
 "baseline: monthly top 3 by 6m momentum": dict(active=ON, rank=mom6),
 "idle money in SPY instead of cash": dict(active=ON, rank=mom6, idle="spy"),
 "only themes with positive 6m return": dict(active=ON, rank=mom6, absmom=mom6),
 "100-day entry gate": dict(active=G100, rank=mom6),
 "rank by 3m momentum": dict(active=ON, rank=mom3),
 "rank by 12m momentum": dict(active=ON, rank=mom12),
 "rank by blend of 3/6/12m": dict(active=ON, rank=blend),
 "rank by 6m momentum skipping last month": dict(active=ON, rank=level.shift(21) / level.shift(126) - 1),
 "weight by inverse volatility": dict(active=ON, rank=mom6, weights="invvol"),
 "top 2": dict(active=ON, rank=mom6, top=2),
 "top 4": dict(active=ON, rank=mom6, top=4),
 "top 5": dict(active=ON, rank=mom6, top=5),
 "to cash when SPY is below its 200-day average": dict(active=ON, rank=mom6, spy_gate=True),
 "rebalance every 2 weeks": dict(active=ON, rank=mom6, every=10),
 "20 bp cost per trade instead of 10": dict(active=ON, rank=mom6, cost_bps=20),
}
rows = []; keep = {}
for nm, kw in add.items():
    r, w = UN.rotate(U, **kw); s = stats(r); s.update(rule=nm, invested=w.sum(axis=1).mean()); rows.append(s); keep[nm] = r
A = pd.DataFrame(rows).set_index("rule"); A.to_csv(f"{OUT}/3_additions.csv"); print("\n=== 3. ADDITIONS ==="); print(A.round(3).to_string())
both = [k for k in A.index[1:] if A.at[k, "sharpe_18_22"] > A.iloc[0].sharpe_18_22 and A.at[k, "sharpe_23_26"] > A.iloc[0].sharpe_23_26]
print("better than baseline in BOTH periods:", both)
# combine the additions that helped in both halves
r2, w2 = UN.rotate(U, ON, rank=mom6, idle="spy", absmom=mom6)
print("combo (positive momentum + idle in SPY):", {k: round(v, 3) for k, v in stats(r2).items()})
pd.to_pickle(dict(r0=r0, spy=spy, rnd=rnd_curves, w0=w0, keep=keep, r2=r2), f"{OUT}/_state.pkl")
