"""Combined shortage universe (price + forum news + earnings-call bottlenecks) as daily matrices."""
import numpy as np, pandas as pd
from . import config as C, data as D, backtest as B, v2 as V, bottleneck as BN, filings as F, hn as HN

SAME = {"Copper": "copper", "Aluminium": "aluminum", "Uranium / enrichment": "uranium", "Lithium / battery materials": "lithium",
        "Natural gas / LNG": "us_gas", "Crude oil / refining": "oil", "Fertiliser": "fertilizer", "Grains / oilseeds": "agri",
        "Lumber / wood": "lumber", "Vehicles (new / used)": "used_cars", "Cattle / beef / eggs / cocoa": "eggs",
        "HBM / DRAM / NAND memory": "memory", "AI accelerators / GPUs": "gpu", "Transformers / switchgear": "power_eq",
        "Ships / containers / freight": "containers", "Mature-node / auto chips": "chips"}


def build():
    baskets = {k: v["tickers"] for k, v in C.THEMES.items()}
    names = {k: v["name"] for k, v in C.THEMES.items()}
    for k, v in BN.SUPPLIERS.items():
        if k not in SAME: baskets[k] = v; names[k] = k
    tick = sorted({t for v in baskets.values() for t in v} | set(C.BENCH))
    px = D.prices(tick); cal = px["SPY"].dropna().index; px = px.reindex(cal)
    ret = px.ffill(limit=5).pct_change(fill_method=None)
    tr = pd.DataFrame({k: ret[[t for t in v if t in ret]].mean(axis=1, skipna=True) for k, v in baskets.items()}).fillna(0)

    def daily(states, lag, key=lambda k: k):
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
    P = daily(up, lambda k: C.LAG[src[k][0]], lambda k: src[k][1])
    sh, gl, tot = HN.counts(); nar = V.narrative(sh, gl, tot)
    keep = C.SENT_ONLY; C.SENT_ONLY = list(nar); nu, _ = V.news_only_states(nar); C.SENT_ONLY = keep
    N = daily(nu, C.V2["sent_lag"])
    H = BN.heat(*BN.breadth(BN.load(F.CALLS))); cu, _ = BN.states(H, min_firms=3)
    Cc = daily(cu, BN.B["lag"], lambda k: SAME.get(k, k))
    level = (1 + tr).cumprod()
    return dict(tr=tr, P=P, N=N, C=Cc, ON=((P + N + Cc) > 0).astype(float), level=level, cal=cal, idx=cal[cal >= C.START],
                spy=ret["SPY"].fillna(0), cash=ret["BIL"].fillna(0), baskets=baskets, names=names, px=px)


def rotate(U, active, rank=None, top=3, every=21, seed=None, absmom=None, weights="eq", idle="cash", spy_gate=False, cost_bps=10):
    """Hold `top` active shortages, re-picked every `every` trading days (a pick whose shortage ends is dropped at once).
    rank=None with seed -> random picks. Returns (daily returns, weight matrix)."""
    idx = U["idx"]; A = active.reindex(idx).fillna(0).values; T, n = A.shape
    R = None if rank is None else rank.reindex(idx).fillna(-9).values
    if absmom is not None: A = A * (absmom.reindex(idx).fillna(-1).values > 0)
    rng = np.random.default_rng(seed) if rank is None else None
    W = np.zeros((T, n)); cur = np.array([], dtype=int)
    for i in range(T):
        cur = cur[A[i, cur] > 0]
        if i % every == 0 or len(cur) == 0:
            live = np.flatnonzero(A[i] > 0)
            cur = (rng.permutation(live)[:top] if rng is not None else live[np.argsort(-R[i, live], kind="stable")[:top]]) if len(live) else live
        W[i, cur] = 1.0 / top
    w = pd.DataFrame(W, index=idx, columns=active.columns)
    if weights == "invvol":
        vol = U["tr"].rolling(63).std().reindex(idx); iv = (1 / vol).where(w > 0)
        w = iv.div(iv.sum(axis=1), axis=0).fillna(0).mul(w.sum(axis=1), axis=0)
    if spy_gate:
        s = (1 + U["spy"]).cumprod(); ok = (s > s.rolling(200).mean()).reindex(idx)
        w = w.mul(ok.astype(float), axis=0)
    w = w.shift(1).fillna(0)
    cost = w.diff().abs().sum(axis=1).fillna(0) * cost_bps / 1e4
    rest = U["spy"] if idle == "spy" else U["cash"]
    r = (w * U["tr"].reindex(idx)).sum(axis=1) + (1 - w.sum(axis=1)) * rest.reindex(idx) - cost
    return r, w
