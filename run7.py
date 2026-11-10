"""v7: the monthly top-3 rotation without technology themes. Outputs in outputs/v7/."""
import os, numpy as np, pandas as pd
from shortage import config as C, backtest as B, universe as UN
OUT = "outputs/v7"; os.makedirs(OUT, exist_ok=True); pd.set_option("display.width", 250)
SPLIT = pd.Timestamp(C.V2["split"])
U = UN.build(); ON, level, idx, tr = U["ON"], U["level"], U["idx"], U["tr"]; spy = U["spy"].reindex(idx); mom6 = level / level.shift(126) - 1
TECH = ["chips", "memory", "gpu", "Advanced packaging (CoWoS, substrates)", "Leading-edge wafers / foundry", "Optical components", "Hard drives / storage", "Semiconductor equipment"]
AI_CHAIN = TECH + ["power_eq", "Electric power / grid connection", "Gas turbines", "Data-centre cooling", "Data-centre space"]
def stats(r):
    a, b, t = B.perf(r), B.perf(r[r.index < SPLIT]), B.perf(r[r.index >= SPLIT])
    return dict(cagr=a["cagr"], vol=a["vol"], sharpe=a["sharpe"], maxdd=a["maxdd"], cagr_18_22=b["cagr"], sharpe_18_22=b["sharpe"], cagr_23_26=t["cagr"], sharpe_23_26=t["sharpe"])
rows = []; yearly = {}; W = {}
for nm, drop in (("All themes", []), ("Without technology (chips, memory, AI chips, optics, equipment)", TECH), ("Without technology and AI power chain", AI_CHAIN)):
    A = ON.drop(columns=[c for c in drop if c in ON])
    r, w = UN.rotate(U, A, rank=mom6.reindex(columns=A.columns), top=3, every=21)
    rnd = pd.DataFrame([stats(UN.rotate(U, A, top=3, every=21, seed=s)[0]) for s in range(200)])
    s = stats(r); s.update(universe=nm, themes=A.shape[1], random_median_cagr=rnd.cagr.median(), beats_random_on_sharpe=(rnd.sharpe < s["sharpe"]).mean(), invested=w.sum(axis=1).mean())
    rows.append(s); yearly[nm.split(" (")[0]] = r.groupby(r.index.year).apply(lambda d: (1 + d).prod() - 1); W[nm] = w
s = stats(spy); s.update(universe="SPY"); rows.append(s)
T = pd.DataFrame(rows).set_index("universe"); T.to_csv(f"{OUT}/ex_tech.csv"); print(T.round(3).T.to_string())
Y = pd.DataFrame(yearly); Y["SPY"] = spy.groupby(spy.index.year).apply(lambda d: (1 + d).prod() - 1); Y.to_csv(f"{OUT}/yearly.csv"); print(); print(Y.round(2).to_string())
w0 = W["All themes"]; contrib = (w0 * tr.reindex(idx)).sum()
print("\nshare of days holding a tech theme:", round((w0[[c for c in TECH if c in w0]].sum(axis=1) > 0).mean(), 2), "| tech share of summed contribution:", round(contrib[[c for c in TECH if c in contrib]].sum() / contrib.sum(), 2),
      "| AI-chain share:", round(contrib[[c for c in AI_CHAIN if c in contrib]].sum() / contrib.sum(), 2))
w1 = list(W.values())[1]; h = w1[w1.index >= "2025-06-01"].mean(); print("held instead since mid-2025:", h[h > 0.02].sort_values(ascending=False).round(2).to_dict())
