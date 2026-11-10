"""v3: bottlenecks from earnings calls / filings / Beige Book -> supplier baskets -> best asset. Outputs in outputs/v3/."""
import json, os, sys
import numpy as np, pandas as pd
from shortage import config as C, data as D, backtest as B, v2 as V, bottleneck as BN, filings as F

OUT = "outputs/v3"; os.makedirs(OUT, exist_ok=True)
pd.set_option("display.width", 250, "display.max_columns", 40, "display.max_rows", 400, "display.max_colwidth", 60)
SPLIT = pd.Timestamp(C.V2["split"])

tick = sorted({t for v in BN.SUPPLIERS.values() for t in v} | set(C.BENCH))
px = D.prices(tick)
cal = px["SPY"].dropna().index; px = px.reindex(cal)
ret = px.ffill(limit=5).pct_change(fill_method=None)
spy = ret["SPY"].fillna(0); cash = ret["BIL"].fillna(0)
basket = pd.DataFrame({k: ret[[t for t in v if t in ret]].mean(axis=1, skipna=True) for k, v in BN.SUPPLIERS.items()}).fillna(0)
expr = pd.concat([basket, ret[[t for t in tick if t in ret]].fillna(0)], axis=1)
print("missing:", [t for t in tick if t not in px or px[t].dropna().empty])

def events(up, dn, src):
    rows = []
    for sigs, side in ((up, 1), (dn, -1)):
        for k, sig in sigs.items():
            from shortage.signals import episodes
            last = sig.index[-1]
            for a, e in episodes(sig):
                d0 = B.trade_date(a, BN.B["lag"], cal)
                if d0 is None or d0 < pd.Timestamp(C.START): continue
                if e is None: e = last if last < cal[-1].to_period("M") - 2 else None
                d1 = B.trade_date(e, BN.B["lag"], cal) if e is not None else None
                if d1 is not None and d1 <= d0: continue
                rows.append(dict(label=k, theme=k, side=side, src=src, signal_month=a, exit_month=e, entry=d0,
                                 exit=d1 if d1 is not None else cal[-1], open=d1 is None, heat=sig.z[a], firms=sig.price[a]))
    return pd.DataFrame(rows).sort_values("entry").reset_index(drop=True)

def summ(d, name):
    d = d.dropna(subset=["ret"])
    return dict(set=name, n=len(d), win=(d.ret > 0).mean(), beat_spy=(d.excess > 0).mean(), mean=d.ret.mean(),
                median=d.ret.median(), mean_vs_spy=d.excess.mean(), median_vs_spy=d.excess.median(), days=d.days.mean())
def table(rows, title, f):
    T = pd.DataFrame(rows); T.to_csv(f"{OUT}/{f}.csv", index=False)
    print(f"\n=== {title} ==="); print(T.round(3).to_string(index=False)); return T

# ---------------- calls (2005 -> May 2025)
calls = BN.load(F.CALLS)
S, G, N = BN.breadth(calls); H = BN.heat(S, G, N)
up, dn = BN.states(H)
ev = events(up, dn, "calls")
ev[["ret", "excess", "days"]] = V.evaluate(ev, expr, spy)
ev["train"] = ev.entry < SPLIT
ev.to_csv(f"{OUT}/call_events.csv", index=False)
L, Sh = ev[ev.side > 0], ev[ev.side < 0]
table([summ(L, "bottleneck: long suppliers"), summ(L[L.train], "  entries 2018-22"), summ(L[~L.train], "  entries 2023-25"),
       summ(Sh, "glut: short suppliers"), summ(Sh[Sh.train], "  entries 2018-22"), summ(Sh[~Sh.train], "  entries 2023-25")],
      "1. EARNINGS-CALL SIGNALS (S&P 500 calls, to May 2025)", "1_call_signals")
show = lambda d: print(d.assign(entry=d.entry.dt.date, exit=d.exit.dt.date)[["label", "entry", "exit", "heat", "firms", "days", "ret", "excess"]].round(2).to_string(index=False))
print("-- bottleneck longs"); show(L); print("-- glut shorts"); show(Sh)

# ---------------- 2. which asset inside the theme: leader vs basket vs laggard (picked at entry, no hindsight)
def pick(e, best=True):
    c = [t for t in BN.SUPPLIERS[e.theme] if t in px]
    i = cal.get_loc(e.entry)
    r = {t: px[t].iloc[i] / px[t].iloc[i - 126] - 1 for t in c if i >= 126 and pd.notna(px[t].iloc[i]) and pd.notna(px[t].iloc[i - 126])}
    if len(r) < 2: return None
    return (max if best else min)(r, key=r.get)
rows = []
for nm, d in (("bottleneck longs", L),):
    d = d.copy(); d["leader"] = [pick(e) for e in d.itertuples()]; d["laggard"] = [pick(e, False) for e in d.itertuples()]; d["first"] = [BN.SUPPLIERS[t][0] for t in d.theme]
    d = d[d.leader.notna()]
    for col, lab in (("theme", "equal-weight supplier basket"), ("leader", "6-month leader at entry"), ("laggard", "6-month laggard at entry"), ("first", "designated pure play")):
        e = V.evaluate(d, expr, spy, col=col); x = d.assign(ret=e.ret, excess=e.excess, days=e.days)
        r = summ(x, lab); r["tr_mean"] = x[x.train].ret.mean(); r["te_mean"] = x[~x.train].ret.mean(); rows.append(r)
    L = L.join(d[["leader", "laggard"]])
table(rows, "2. WHICH ASSET (same bottleneck signals)", "2_asset_choice")

# ---------------- 3. leaderboard through time: top bottlenecks / gluts as they stood each year-end
rows = []
for y in range(2017, 2026):
    m = pd.Period(f"{y}-12" if y < 2025 else "2025-05", "M")
    hs = pd.Series({k: H[k].at[m, "heat_s"] for k in H if m in H[k].index and H[k].at[m, "n_s"] >= 5}).sort_values(ascending=False)
    hg = pd.Series({k: H[k].at[m, "heat_g"] for k in H if m in H[k].index and H[k].at[m, "n_g"] >= 5}).sort_values(ascending=False)
    rows.append(dict(as_of=str(m), top_bottlenecks="; ".join(f"{k.split(' (')[0]} {v:.1f}x" for k, v in hs.head(4).items()),
                     top_gluts="; ".join(f"{k.split(' (')[0]} {v:.1f}x" for k, v in hg.head(3).items())))
table(rows, "3. LEADERBOARD AT EACH YEAR-END (firms citing vs 2-year norm)", "3_leaderboard")

# ---------------- 4. portfolio of bottleneck longs
pf, wl, ws = V.baskets(ev, expr, cash, spy)
pf = pf[pf.index <= "2025-08-31"]
rows = []
for c in ["Long shortage", "Short oversupply", "Shortage vs SPY", "SPY"]:
    a, b, t = B.perf(pf[c]), B.perf(pf[c][pf.index < SPLIT]), B.perf(pf[c][pf.index >= SPLIT])
    rows.append(dict(basket=c.replace("shortage", "bottleneck suppliers").replace("Shortage", "Bottleneck suppliers").replace("oversupply", "glut suppliers"),
                     cagr=a["cagr"], vol=a["vol"], sharpe=a["sharpe"], maxdd=a["maxdd"], sharpe_2018_22=b["sharpe"], sharpe_2023_25=t["sharpe"]))
table(rows, "4. BASKETS FROM CALL SIGNALS (Jan 2018 - Aug 2025)", "4_baskets")
(1 + pf).cumprod().to_csv(f"{OUT}/4_basket_curves.csv")

# ---------------- 5. live: SEC filings (same companies every quarter, to today) + Beige Book
live = None
if os.path.exists(F.CACHE):
    fil = BN.load(F.CACHE)
    S2, G2, N2 = BN.breadth(fil); H2 = BN.heat(S2, G2, N2)
    m = max(h.index[-1] for h in H2.values() if len(h))
    m = m - 1 if N2.get(m, 0) < 0.6 * N2.max() else m
    live = pd.DataFrame([dict(input=k, firms_short=h.at[m, "n_s"], heat_short=h.at[m, "heat_s"], firms_glut=h.at[m, "n_g"], heat_glut=h.at[m, "heat_g"], net=h.at[m, "net"])
                         for k, h in H2.items() if m in h.index]).sort_values("net", ascending=False)
    live.to_csv(f"{OUT}/5_live_filings.csv", index=False)
    print(f"\n=== 5. LIVE FROM SEC FILINGS, 3 months to {m} ({int(N2[m])} companies; {len(fil)} filings scored) ==="); print(live.round(2).to_string(index=False))
    up2, dn2 = BN.states(H2, min_firms=3)
    ev2 = events(up2, dn2, "filings"); ev2[["ret", "excess", "days"]] = V.evaluate(ev2, expr, spy); ev2.to_csv(f"{OUT}/5_filing_events.csv", index=False)
    x = ev2[ev2.entry >= "2025-06-01"]
    print("-- filing-based signals entered since June 2025 (after the call data ends)"); print(x.assign(entry=x.entry.dt.date, exit=x.exit.dt.date)[["label", "side", "entry", "exit", "heat", "firms", "ret", "excess", "open"]].round(2).to_string(index=False))
    table([summ(ev2[ev2.side > 0], "filings: bottleneck longs, all"), summ(ev2[(ev2.side > 0) & (ev2.entry >= "2025-06-01")], "  entered since Jun 2025"),
           summ(ev2[ev2.side < 0], "filings: glut shorts, all")], "5b. FILING-BASED SIGNALS", "5b_filing_signals")
bb = pd.DataFrame(list(json.load(open(os.path.join(F.RAW, "beige_scores.json"))).values())).sort_values("ym")
bb["net"] = (bb.s - bb.g) / bb.words * 1e4
bb[["ym", "words", "s", "g", "net"]].to_csv(f"{OUT}/6_beige_book.csv", index=False)
print("\n=== 6. BEIGE BOOK: shortage minus glut sentences per 10k words ==="); print(bb.assign(y=bb.ym.str[:4]).groupby("y")[["s", "g", "net"]].mean().round(1).T.to_string())
last = bb.iloc[-1]; print("latest", last.ym, "top shortage inputs:", sorted(last.inputs_s.items(), key=lambda x: -x[1])[:5], "| glut:", sorted(last.inputs_g.items(), key=lambda x: -x[1])[:5])
pd.to_pickle(dict(ev=ev, L=L, H=H, pf=pf, px=px, live=live, bb=bb, expr=expr, spy=spy, cal=cal, H2=H2 if live is not None else None), f"{OUT}/_state.pkl")
