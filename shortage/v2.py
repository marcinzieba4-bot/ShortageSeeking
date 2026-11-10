"""v2: oversupply side, news sentiment, futures curve, stops / targets / re-entry, long-short baskets."""
import numpy as np, pandas as pd
from . import config as C, backtest as B
from .signals import detect, episodes

P2 = C.V2


# ------------------------------------------------------------------ signals
def price_signals(items, params):
    """Shortage = unusual rise to a 24m high.  Oversupply = exact mirror (detector run on 1/price)."""
    up = {k: detect(items[k], **params) for k in items.columns}
    dn = {k: detect(1.0 / items[k], **params) for k in items.columns}
    return up, dn


def narrative(short, glut, total, w=P2["sent_window"], k=3.0):
    """Monthly news features per theme, causal, from raw mention counts.
    Counts are small, so every ratio is smoothed by adding k pseudo-mentions to both sides.
    heat_s / heat_g : mentions in the last 3 months / mentions expected from the prior-24-month rate
    net             : log(heat_s) - log(heat_g)  (>0: shortage talk is the unusual one)
    spike           : the same ratio for the latest single month
    n3              : raw shortage mentions in the last 3 months"""
    out = {}
    N3, NW = total.rolling(3).sum(), total.shift(1).rolling(w, min_periods=w).sum()
    for th in short.columns:
        f = {}
        for nm, c in (("s", short[th].fillna(0)), ("g", glut[th].fillna(0))):
            rate = c.shift(1).rolling(w, min_periods=w).sum() / NW
            f["heat_" + nm] = (c.rolling(3).sum() + k) / (rate * N3 + k)
            f["n3_" + nm] = c.rolling(3).sum()
            if nm == "s":
                f["spike"] = (c + 1) / (rate * total + 1)
        d = pd.DataFrame(f); d["net"] = np.log(d.heat_s) - np.log(d.heat_g)
        out[th] = d.dropna()
    return out


def news_only_states(nar):
    """States for themes with no price series: ON while coverage is abnormally high and one-sided."""
    up, dn = {}, {}
    for th in C.SENT_ONLY:
        if th not in nar:
            continue
        n = nar[th].dropna()
        for side, heat, sign, store in (("s", "heat_s", 1, up), ("g", "heat_g", -1, dn)):
            cnt = "n3_" + side
            st, on, held = [], False, 0
            for t in n.index:
                if on:
                    held += 1
                    if n.at[t, heat] < P2["sent_off"] or held >= C.PARAMS["max_hold"]:
                        on = False
                elif n.at[t, heat] >= P2["sent_on"] and sign * n.at[t, "net"] > 0 and n.at[t, cnt] >= P2["sent_min"]:
                    on, held = True, 0
                st.append(int(on))
            store[th] = pd.DataFrame({"state": st, "z": n[heat], "price": n[heat]}, index=n.index)
    return up, dn


def curve_features(lme_spread, lme_stock, px):
    """Monthly curve state per item: carry (>0 backwardation) and, for LME metals, stock change."""
    out = {}
    for k in lme_spread.columns:
        out[k] = pd.DataFrame({"carry": lme_spread[k].rolling(3).mean(),
                               "stock_yoy": lme_stock[k] / lme_stock[k].shift(12) - 1})
    for k, (front, far) in C.CURVE_PAIRS.items():
        m = px[[front, far]].dropna().groupby(lambda d: d.to_period("M")).last()
        rel = (m[front] / m[front].shift(3)) / (m[far] / m[far].shift(3)) - 1   # front fund beats 12m fund => backwardation
        rel = rel[rel.index < px.index[-1].to_period("M")]
        out[k] = pd.DataFrame({"carry": rel, "stock_yoy": np.nan})
    return out


# ------------------------------------------------------------------ events
def make_events(up, dn, cal, news_up=None, news_dn=None):
    src = {k: (s, th, lab) for k, lab, s, _, th in C.ITEMS}
    rows = []

    def add(sigs, side, kind):
        for k, sig in sigs.items():
            if kind == "price":
                s, th, lab = src[k]; lag = C.LAG[s]
            else:
                th, lab, lag = k, C.THEMES[k]["name"] + " (news)", P2["sent_lag"]
            last = sig.index[-1]
            stale = last < cal[-1].to_period("M") - 2
            for a, e in episodes(sig):
                if e is None and stale:
                    e = last
                    if a >= e:
                        continue
                d0 = B.trade_date(a, lag, cal)
                if d0 is None or d0 < pd.Timestamp(C.START):
                    continue
                d1 = B.trade_date(e, lag, cal) if e is not None else None
                rows.append(dict(item=k, label=lab, theme=th, side=side, kind=kind, signal_month=a, exit_month=e,
                                 entry=d0, exit=d1 if d1 is not None else cal[-1], open=d1 is None, z=sig.z[a]))
    add(up, 1, "price"); add(dn, -1, "price")
    if news_up: add(news_up, 1, "news")
    if news_dn: add(news_dn, -1, "news")
    return pd.DataFrame(rows).sort_values("entry").reset_index(drop=True)


# ------------------------------------------------------------------ trade management
def simulate(r, entry, exit, stop=None, target=None, reentry=False):
    """Daily 0/1 holding of one trade between entry and exit (signal exit always wins).
    r: side-adjusted daily returns.  stop: trailing loss from the trade's peak.  target: take profit.
    reentry: after a stop, buy back when the theme makes a new high since the original entry."""
    idx = r.index[(r.index > entry) & (r.index <= exit)]
    pos = np.zeros(len(idx)); inpos, done = True, False
    eq = peak = shadow = shadow_peak = 1.0
    for i, d in enumerate(idx):
        pos[i] = 1.0 if inpos else 0.0
        x = r.at[d]; shadow *= 1 + x
        if inpos:
            eq *= 1 + x; peak = max(peak, eq)
            if target is not None and eq - 1 >= target:
                inpos, done = False, True
            elif stop is not None and eq / peak - 1 <= -stop:
                inpos = False
        elif reentry and not done and shadow > shadow_peak:
            inpos, eq, peak = True, 1.0, 1.0
        shadow_peak = max(shadow_peak, shadow)
    return pd.Series(pos, index=idx)


def trade_return(r, pos, cost_bps=10):
    """Compounded return of a managed trade, net of costs on every in/out."""
    turns = np.abs(np.diff(np.r_[0, pos.values, 0])).sum()
    return float((1 + r.reindex(pos.index) * pos).prod() * (1 - cost_bps / 1e4) ** turns - 1)


def evaluate(ev, expr_r, spy, col="theme", **mgmt):
    """Per-event side-adjusted return under a management rule; expr_r holds daily returns per expression."""
    out = []
    for e in ev.itertuples():
        c = getattr(e, col)
        if c is None or c not in expr_r.columns or pd.isna(e.entry):
            out.append((np.nan, np.nan, 0)); continue
        r = expr_r[c] * e.side
        pos = simulate(r, e.entry, e.exit, **mgmt)
        ret = trade_return(r, pos)
        mkt = B.cum(spy, e.entry, e.exit) * e.side
        out.append((ret, ret - mkt, int(pos.sum())))
    return pd.DataFrame(out, columns=["ret", "excess", "days"], index=ev.index)


# ------------------------------------------------------------------ baskets
def baskets(ev, expr_r, cash, spy, col="theme", cap=None, **mgmt):
    """Daily returns of: long-shortage, short-oversupply, long-short, and shortage-vs-SPY."""
    cap = cap or C.PARAMS["cap"]
    idx = expr_r.index[expr_r.index >= C.START]
    cols = sorted(set(ev[col].dropna()))
    L = pd.DataFrame(0.0, index=idx, columns=cols); S = L.copy()
    for e in ev.itertuples():
        c = getattr(e, col)
        if c is None or c not in expr_r.columns:
            continue
        pos = simulate(expr_r[c] * e.side, e.entry, e.exit, **mgmt).reindex(idx).fillna(0)
        tgt = L if e.side > 0 else S
        tgt[c] = np.maximum(tgt[c], pos)
    both = (L > 0) & (S > 0)                     # same theme flagged both ways -> stand aside
    L[both] = 0; S[both] = 0

    def weights(A):
        n = A.sum(axis=1)
        return A.div(n.where(n > 0, 1), axis=0).clip(upper=cap)
    wl, ws = weights(L), weights(S)
    r = expr_r.reindex(idx)[cols].fillna(0)
    cst = lambda w: w.diff().abs().sum(axis=1).fillna(0) * C.PARAMS["cost_bps"] / 1e4
    cs, sp = cash.reindex(idx).fillna(0), spy.reindex(idx).fillna(0)
    gl, gs = wl.sum(axis=1), ws.sum(axis=1)
    long_leg = (wl * r).sum(axis=1) - cst(wl)
    short_leg = -(ws * r).sum(axis=1) - cst(ws) - gs * P2["borrow"] / 252
    res = pd.DataFrame({
        "Long shortage":            long_leg + (1 - gl) * cs,
        "Short oversupply":         short_leg + cs,
        "Shortage vs oversupply":   long_leg + short_leg + (1 - gl) * cs,
        "Shortage vs SPY":          long_leg - gl * sp - gl * P2["borrow"] / 252 + cs,
        "SPY": sp})
    return res, wl, ws
