"""v2 research run: oversupply, curve, news, trade management, baskets. Outputs in outputs/v2/."""
import itertools, os, sys
import numpy as np, pandas as pd
from shortage import config as C, data as D, backtest as B, v2 as V, curve as CV, hn as HN

OUT = "outputs/v2"; os.makedirs(OUT, exist_ok=True)
pd.set_option("display.width", 250, "display.max_columns", 40, "display.max_rows", 300)
SPLIT = pd.Timestamp(C.V2["split"])

items = D.item_series()
tick = sorted({t for th in C.THEMES.values() for t in th["tickers"]} | set(C.BENCH) | set(C.COMMODITY_ETF.values())
              | {x for p in C.CURVE_PAIRS.values() for x in p})
px = D.prices(tick)
cal = px["SPY"].dropna().index; px = px.reindex(cal)
tr = B.theme_returns(px)
etf_r = px[sorted(set(C.COMMODITY_ETF.values()))].pct_change(fill_method=None).fillna(0).add_prefix("etf:")
expr = pd.concat([tr, etf_r], axis=1)
spy = px["SPY"].pct_change().fillna(0); cash = px["BIL"].pct_change().fillna(0)

# ---------------- signals
up, dn = V.price_signals(items, C.PARAMS)
sh, gl, tot = HN.counts()
nar = V.narrative(sh, gl, tot)
nu, nd = V.news_only_states(nar)
ev = V.make_events(up, dn, cal, nu, nd)
ev["etf"] = ev.item.map(lambda k: "etf:" + C.COMMODITY_ETF[k] if k in C.COMMODITY_ETF else None)
ev["train"] = ev.entry < SPLIT
sp_m, st_m = CV.lme_monthly()
cur = V.curve_features(sp_m, st_m, px)

# features known at the signal month
def feat(e, name):
    d = cur.get(e.item)
    if d is None or e.signal_month not in d.index: return np.nan
    return d.at[e.signal_month, name]
ev["carry"] = [feat(e, "carry") for e in ev.itertuples()]
ev["stock_yoy"] = [feat(e, "stock_yoy") for e in ev.itertuples()]
def nfeat(e, name):
    d = nar.get(e.theme)
    m = e.signal_month - (0 if e.kind == "news" else 0)
    if d is None or m not in d.index: return np.nan
    return d.at[m, name]
for f in ("net", "heat_s", "heat_g", "spike"):
    ev[f] = [nfeat(e, f) for e in ev.itertuples()]
base = V.evaluate(ev, expr, spy)
ev[["ret", "excess", "days"]] = base
ev.to_csv(f"{OUT}/events.csv", index=False)

def summ(d, name):
    d = d.dropna(subset=["ret"])
    return dict(set=name, n=len(d), win=(d.ret > 0).mean(), beat_spy=(d.excess > 0).mean(), mean=d.ret.mean(),
                median=d.ret.median(), mean_vs_spy=d.excess.mean(), days=d.days.mean())
def table(rows, title, f):
    T = pd.DataFrame(rows); T.to_csv(f"{OUT}/{f}.csv", index=False)
    print(f"\n=== {title} ==="); print(T.round(3).to_string(index=False)); return T

P = ev[ev.kind == "price"]; LONG, SHORT = P[P.side > 0], P[P.side < 0]
# ---------------- 1. oversupply side (returns are for the SHORT, i.e. positive = theme fell)
table([summ(LONG, "shortage: long theme"), summ(SHORT, "oversupply: short theme"),
       summ(SHORT[SHORT.train], "  oversupply, entries <2023"), summ(SHORT[~SHORT.train], "  oversupply, entries >=2023")],
      "1. SHORTAGE vs OVERSUPPLY (price signals)", "1_sides")
print(SHORT.assign(entry=SHORT.entry.dt.date, exit=SHORT.exit.dt.date)[["label", "theme", "entry", "exit", "z", "days", "ret", "excess"]].round(2).to_string(index=False))

# ---------------- 2. expression: producers vs roll-inclusive commodity fund
E2 = P[P.etf.notna()].copy()
e_etf = V.evaluate(E2, expr, spy, col="etf")
rows = []
for side, nm in ((1, "shortage long"), (-1, "oversupply short")):
    a = E2[E2.side == side]; b = e_etf.loc[a.index]
    rows.append(dict(summ(a, f"{nm}: producers")));  rows.append(dict(summ(a.assign(ret=b.ret, excess=b.excess, days=b.days), f"{nm}: commodity fund")))
table(rows, "2. EXPRESSION (same signals, 13 items with a commodity fund)", "2_expression")
E2["etf_ret"] = e_etf.ret

# ---------------- 3. curve
K = P[P.carry.notna()].copy(); K["etf_ret"] = V.evaluate(K, expr, spy, col="etf").ret
rows = []
for side, nm in ((1, "shortage"), (-1, "oversupply")):
    a = K[K.side == side]
    for lab, m in (("backwardation", a.carry > 0), ("contango", a.carry <= 0)):
        r = summ(a[m], f"{nm} + {lab}"); r["fund_mean"] = a[m].etf_ret.mean(); rows.append(r)
a = K[(K.side == 1) & K.stock_yoy.notna()]
rows += [summ(a[a.stock_yoy < 0], "shortage + LME stocks falling"), summ(a[a.stock_yoy >= 0], "shortage + LME stocks rising")]
table(rows, "3. CURVE AT ENTRY (LME metals, oil, US gas)", "3_curve")

# ---------------- 4. news narrative
N = P[P.net.notna()].copy()
rows = []
for side, nm in ((1, "shortage"), (-1, "oversupply")):
    a = N[N.side == side]
    rows += [summ(a[a.net * side > 0], f"{nm}: news agrees"), summ(a[a.net * side <= 0], f"{nm}: news disagrees"),
             summ(a[(a.heat_s if side > 0 else a.heat_g) >= 2], f"{nm}: coverage already >=2x normal"),
             summ(a[(a.heat_s if side > 0 else a.heat_g) < 2], f"{nm}: coverage <2x normal")]
if len(N): table(rows, "4. NEWS AT ENTRY (price signals with news history)", "4_news")
NO = ev[ev.kind == "news"]
if len(NO):
    table([summ(NO[NO.side > 0], "news-only shortage: long"), summ(NO[NO.side < 0], "news-only glut: short")], "4b. NEWS-ONLY THEMES", "4b_news_only")
    print(NO.assign(entry=NO.entry.dt.date, exit=NO.exit.dt.date)[["label", "side", "entry", "exit", "z", "days", "ret", "excess", "open"]].round(2).to_string(index=False))

# ---------------- 5. trade management grid (chosen on train, judged on test)
rows = []
grid = [dict(stop=s, target=t, reentry=r) for s in (None, .15, .25) for t in (None, .5, 1.0) for r in ((False, True) if s else (False,))]
for g in grid:
    e = V.evaluate(LONG, expr, spy, **g); d = LONG.assign(ret=e.ret, excess=e.excess, days=e.days)
    pf, _, _ = V.baskets(LONG, expr, cash, spy, **g)
    r = pf["Long shortage"]
    rows.append(dict(**{k: (v if v is not None else "-") for k, v in g.items()},
                     tr_mean=d[d.train].ret.mean(), tr_win=(d[d.train].ret > 0).mean(), tr_sharpe=B.perf(r[r.index < SPLIT])["sharpe"],
                     tr_maxdd=B.perf(r[r.index < SPLIT])["maxdd"],
                     te_mean=d[~d.train].ret.mean(), te_win=(d[~d.train].ret > 0).mean(), te_sharpe=B.perf(r[r.index >= SPLIT])["sharpe"],
                     te_maxdd=B.perf(r[r.index >= SPLIT])["maxdd"], all_cagr=B.perf(r)["cagr"]))
G = table(rows, "5. STOPS / TARGETS / RE-ENTRY on shortage longs (tr = entries<2023, te = after)", "5_management")

# ---------------- 6. baskets
pf, wl, ws = V.baskets(ev[ev.kind == "price"], expr, cash, spy)
rows = []
for c in pf.columns:
    a, b, t = B.perf(pf[c]), B.perf(pf[c][pf.index < SPLIT]), B.perf(pf[c][pf.index >= SPLIT])
    rows.append(dict(basket=c, cagr=a["cagr"], vol=a["vol"], sharpe=a["sharpe"], maxdd=a["maxdd"],
                     sharpe_2018_22=b["sharpe"], sharpe_2023_26=t["sharpe"], corr_spy=pf[c].corr(pf["SPY"])))
table(rows, "6. BASKETS (price signals, producers, base exits)", "6_baskets")
yr = pf.groupby(pf.index.year).apply(lambda d: (1 + d).prod() - 1); yr.to_csv(f"{OUT}/6_baskets_yearly.csv")
print(yr.round(3).to_string())
print("avg long gross", wl.sum(axis=1).mean().round(2), "avg short gross", ws.sum(axis=1).mean().round(2))
# ---------------- 7. news as a holding rule (shortage longs whose theme has news history)
def with_exit(d, months):
    d = d.copy()
    x = [B.trade_date(m, 5, cal) if m is not None else None for m in months]
    d["exit"] = [v if v is not None else cal[-1] for v in x]
    return d
NL = LONG[LONG.net.notna()].copy()
def cont_month(e):          # keep holding after the price exit while shortage talk is still above normal
    n = nar[e.theme]; m = e.exit_month
    if m is None or pd.isna(m): return None
    k = 0
    while m in n.index and n.at[m, "heat_s"] >= 1 and n.at[m, "net"] > 0 and k < 12:
        m += 1; k += 1
    return m if m in n.index or m <= n.index[-1] else None
def frenzy_month(e):        # leave early once a single month of coverage is >=4x normal
    n = nar[e.theme]; end = e.exit_month if e.exit_month is not None and not pd.isna(e.exit_month) else n.index[-1]
    hit = n.loc[e.signal_month + 1:end]; hit = hit[hit.spike >= 4]
    return hit.index[0] if len(hit) else (None if pd.isna(e.exit_month) else e.exit_month)
def fade_month(e):          # leave early once glut talk overtakes shortage talk
    n = nar[e.theme]; end = e.exit_month if e.exit_month is not None and not pd.isna(e.exit_month) else n.index[-1]
    hit = n.loc[e.signal_month + 1:end]; hit = hit[hit.net < 0]
    return hit.index[0] if len(hit) else (None if pd.isna(e.exit_month) else e.exit_month)
rows = []
if len(NL):
    variants = {"base (price exit only)": NL,
                "entry filter: only if news agrees": NL[NL.net > 0],
                "entry filter: only if news NOT yet hot (<2x)": NL[NL.heat_s < 2],
                "hold on while shortage talk stays high": with_exit(NL, [cont_month(e) for e in NL.itertuples()]),
                "leave on news frenzy (month >=4x)": with_exit(NL, [frenzy_month(e) for e in NL.itertuples()]),
                "leave when glut talk overtakes": with_exit(NL, [fade_month(e) for e in NL.itertuples()])}
    for nm, d in variants.items():
        e = V.evaluate(d, expr, spy); d = d.assign(ret=e.ret, excess=e.excess, days=e.days)
        rows.append(dict(rule=nm, n=len(d), tr_n=int(d.train.sum()), tr_mean=d[d.train].ret.mean(), tr_vs_spy=d[d.train].excess.mean(),
                         tr_win=(d[d.train].ret > 0).mean(), te_n=int((~d.train).sum()), te_mean=d[~d.train].ret.mean(),
                         te_vs_spy=d[~d.train].excess.mean(), te_win=(d[~d.train].ret > 0).mean(), days=d.days.mean()))
    table(rows, "7. NEWS AS A HOLDING RULE (shortage longs)", "7_news_rules")

# ---------------- 8. capital cycle: buy the theme when a glut ENDS (price back above its 6m average), hold 12 months
rec = SHORT[~SHORT.open].copy()
rec["side"] = 1; rec["entry"] = rec["exit"]
rec["exit"] = [cal[min(cal.get_loc(d) + 252, len(cal) - 1)] for d in rec.entry]
rec["train"] = rec.entry < SPLIT; rec["kind"] = "recovery"
e = V.evaluate(rec, expr, spy); rec[["ret", "excess", "days"]] = e
table([summ(rec, "buy at end of glut, hold 12m"), summ(rec[rec.train], "  entries <2023"), summ(rec[~rec.train], "  entries >=2023")],
      "8. GLUT-RECOVERY LONGS", "8_recovery")
print(rec.assign(entry=rec.entry.dt.date, exit=rec.exit.dt.date)[["label", "theme", "entry", "exit", "days", "ret", "excess"]].round(2).to_string(index=False))

# ---------------- 9. candidate strategies
combo = pd.concat([LONG, rec, ev[(ev.kind == "news") & (ev.side > 0)]])
LF = LONG.copy()
if len(NL):
    LF.loc[NL.index, "exit"] = with_exit(NL, [cont_month(e) for e in NL.itertuples()])["exit"]
cands = {"A. Shortage longs (v1 rule)": (LONG, {}),
         "F. B + hold while shortage talk stays high": (LF, dict(target=1.0)),
         "B. A + take profit at +100%": (LONG, dict(target=1.0)),
         "C. A + 15% trailing stop": (LONG, dict(stop=.15)),
         "D. A + glut-recovery longs": (pd.concat([LONG, rec]), {}),
         "E. D + news-only shortage themes": (combo, {})}
rows = []; curves = {}
for nm, (d, g) in cands.items():
    pfc, w1, _ = V.baskets(d, expr, cash, spy, **g)
    for leg, lab in (("Long shortage", nm), ("Shortage vs SPY", nm + " | hedged with SPY")):
        r = pfc[leg]; a, b, t = B.perf(r), B.perf(r[r.index < SPLIT]), B.perf(r[r.index >= SPLIT])
        rows.append(dict(strategy=lab, cagr=a["cagr"], vol=a["vol"], sharpe=a["sharpe"], maxdd=a["maxdd"],
                         sharpe_tr=b["sharpe"], sharpe_te=t["sharpe"], cagr_te=t["cagr"], invested=w1.sum(axis=1).mean()))
        curves[lab] = r
a = B.perf(spy[spy.index >= C.START]); t = B.perf(spy[spy.index >= SPLIT]); b = B.perf(spy[(spy.index >= C.START) & (spy.index < SPLIT)])
rows.append(dict(strategy="SPY", cagr=a["cagr"], vol=a["vol"], sharpe=a["sharpe"], maxdd=a["maxdd"], sharpe_tr=b["sharpe"], sharpe_te=t["sharpe"], cagr_te=t["cagr"], invested=1))
table(rows, "9. CANDIDATE STRATEGIES (tr 2018-22, te 2023-26)", "9_candidates")
curves["SPY"] = spy[spy.index >= C.START]
pd.DataFrame(curves).to_csv(f"{OUT}/9_candidate_daily_returns.csv")

# ---------------- 10. live
live = []
for nm, sig, side in [("shortage", up, 1), ("oversupply", dn, -1)]:
    for k, g in sig.items():
        if g.state.iloc[-1] and g.index[-1] >= cal[-1].to_period("M") - 2:
            live.append(dict(state=nm, item=k, since=str([a for a, _ in __import__("shortage.signals", fromlist=["episodes"]).episodes(g)][-1]), z=g.z.iloc[-1]))
for th, n in nar.items():
    x = n.iloc[-1]; live.append(dict(state="news", item=th, since=str(n.index[-1]), z=np.nan, heat_short=x.heat_s, heat_glut=x.heat_g, net=x.net))
Lv = pd.DataFrame(live); Lv.to_csv(f"{OUT}/10_live.csv", index=False)
print("\n=== 10. LIVE ==="); print(Lv.round(2).to_string(index=False))
rl = rec[rec.exit >= cal[-1]]; print("open recovery longs:", list(zip(rl.label, rl.entry.dt.date)))
pd.to_pickle(dict(rec=rec, curves=curves, ev=ev, pf=pf, nar=nar, cur=cur, expr=expr, spy=spy, cash=cash, up=up, dn=dn, items=items, wl=wl, ws=ws), f"{OUT}/_state.pkl")
