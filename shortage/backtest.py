"""Point-in-time backtest: monthly shortage states -> daily theme portfolio."""
import numpy as np, pandas as pd
from . import config as C
from .signals import detect, episodes


def trade_date(month: pd.Period, lag: int, cal: pd.DatetimeIndex):
    """Close of the `lag`-th trading day of the month AFTER the data month."""
    nxt = month + 1
    days = cal[(cal >= nxt.start_time) & (cal <= nxt.end_time)]
    return days[lag - 1] if len(days) >= lag else None


def theme_returns(px: pd.DataFrame):
    """Daily equal-weight return of each theme, using only tickers already listed."""
    ret = px.ffill(limit=5).pct_change(fill_method=None)
    out = {}
    for k, t in C.THEMES.items():
        cols = [c for c in t["tickers"] if c in ret.columns]
        out[k] = ret[cols].mean(axis=1, skipna=True)
    return pd.DataFrame(out).fillna(0.0)


def run_signals(items: pd.DataFrame, params):
    return {k: detect(items[k], **params) for k in items.columns}


def build_events(sigs, cal, start=C.START):
    rows = []
    src = {k: (s, th, lab) for k, lab, s, _, th in C.ITEMS}
    for k, sig in sigs.items():
        s, th, lab = src[k]
        last = sig.index[-1]
        stale = last < cal[-1].to_period("M") - 2        # feed stopped updating
        for a, e in episodes(sig):
            if e is None and stale:
                e = last                                 # no data -> no position: close it
                if a >= e:
                    continue                             # fired on the feed's last print: untradable
            d0 = trade_date(a, C.LAG[s], cal)
            if d0 is None or d0 < pd.Timestamp(start):
                # signal not yet tradable, or it fired before the study window
                if d0 is None and a >= cal[-1].to_period("M") - 1:
                    rows.append(dict(item=k, label=lab, theme=th, signal_month=a, entry=None,
                                     exit_month=e, exit=None, z=sig.z[a], px_entry=sig.price[a]))
                continue
            d1 = trade_date(e, C.LAG[s], cal) if e is not None else None
            rows.append(dict(item=k, label=lab, theme=th, signal_month=a, entry=d0,
                             exit_month=e, exit=d1, z=sig.z[a], px_entry=sig.price[a],
                             px_peak=sig.price[a:(e if e is not None else sig.index[-1])].max()))
    return pd.DataFrame(rows).sort_values("signal_month").reset_index(drop=True)


def cum(r, a, b):
    """Total return from close of a to close of b."""
    x = r[(r.index > a) & (r.index <= b)]
    return float((1 + x).prod() - 1)


def event_stats(ev, tr, bench, horizons=(21, 63, 126, 252)):
    """Per-event theme return (entry->exit and fixed horizons), raw and vs benchmark."""
    out = []
    last = tr.index[-1]
    for _, e in ev.iterrows():
        if e.entry is None or pd.isna(e.entry):
            continue
        r = tr[e.theme]
        end = e.exit if e.exit is not None and not pd.isna(e.exit) else last
        row = dict(e)
        row["open"] = e.exit is None or pd.isna(e.exit)
        row["days"] = int(((r.index > e.entry) & (r.index <= end)).sum())
        row["ret"] = cum(r, e.entry, end)
        row["spy"] = cum(bench, e.entry, end)
        row["excess"] = row["ret"] - row["spy"]
        i0 = r.index.get_loc(e.entry)
        for h in horizons:
            if i0 + h < len(r):
                b = r.index[i0 + h]
                row[f"fwd{h}"] = cum(r, e.entry, b)
                row[f"xs{h}"] = row[f"fwd{h}"] - cum(bench, e.entry, b)
        out.append(row)
    return pd.DataFrame(out)


def placebo(es, tr, bench, h=126, n=5000, seed=7, start=C.START):
    """Is the signal better than a random entry date INTO THE SAME THEME?
    Draw random entry days per event (same theme, same horizon) and compare means."""
    rng = np.random.default_rng(seed)
    col = f"fwd{h}"
    e = es.dropna(subset=[col])
    idx = tr.index[tr.index >= start]
    fwd = {}
    for th in e.theme.unique():
        c = (1 + tr[th]).cumprod()
        fwd[th] = (c.shift(-h) / c - 1).reindex(idx).dropna().values
    actual = e[col].mean()
    sims = np.array([np.mean([rng.choice(fwd[t]) for t in e.theme]) for _ in range(n)])
    return dict(h=h, n_events=len(e), actual=actual, random_mean=sims.mean(),
                pctile=float((sims < actual).mean()))


def portfolio(ev, tr, cash, spy, params, start=C.START):
    """Daily portfolio: equal weight across active themes (cap per theme), rest in cash."""
    idx = tr.index[tr.index >= start]
    active = pd.DataFrame(0, index=idx, columns=tr.columns)
    for _, e in ev.iterrows():
        if e.entry is None or pd.isna(e.entry):
            continue
        end = e.exit if e.exit is not None and not pd.isna(e.exit) else idx[-1]
        active.loc[(idx > e.entry) & (idx <= end), e.theme] = 1   # earn returns from day after entry close
    n = active.sum(axis=1)
    w = active.div(n.where(n > 0, 1), axis=0).clip(upper=params["cap"])
    gross = w.sum(axis=1)
    turn = w.diff().abs().sum(axis=1).fillna(w.abs().sum(axis=1))
    cost = turn * params["cost_bps"] / 1e4
    themes_r = (w * tr.reindex(idx)).sum(axis=1)
    res = pd.DataFrame({
        "shortage_cash": themes_r + (1 - gross) * cash.reindex(idx).fillna(0) - cost,
        "shortage_spy":  themes_r + (1 - gross) * spy.reindex(idx).fillna(0) - cost,
        "invested": gross, "n_themes": n})
    return res, w


def perf(r: pd.Series):
    r = r.dropna()
    yrs = len(r) / 252
    c = (1 + r).cumprod()
    return dict(cagr=c.iloc[-1] ** (1 / yrs) - 1, vol=r.std() * 252 ** .5,
                sharpe=r.mean() / r.std() * 252 ** .5 if r.std() > 0 else np.nan,
                maxdd=(c / c.cummax() - 1).min(), total=c.iloc[-1] - 1)
