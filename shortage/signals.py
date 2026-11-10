"""Shortage detector. Strictly causal: the state for month t uses data <= t only."""
import numpy as np, pandas as pd


def detect(p: pd.Series, lookback=6, z_window=120, z_min_obs=60, z_entry=1.5,
           high_window=24, exit_ma=6, max_hold=24, **_):
    """Return DataFrame(index=month) with z, entry flag and position state (0/1)."""
    p = p.dropna()
    r = np.log(p / p.shift(lookback))
    hist = r.shift(1)                                   # history excludes the current month
    mu = hist.rolling(z_window, min_periods=z_min_obs).mean()
    sd = hist.rolling(z_window, min_periods=z_min_obs).std()
    z = (r - mu) / sd
    new_high = p >= p.shift(1).rolling(high_window).max()
    ma = p.rolling(exit_ma).mean()
    entry = (z >= z_entry) & new_high
    below = p < ma
    state, held, on = [], 0, False
    for t in p.index:
        if on:
            held += 1
            if below[t] or held >= max_hold:
                on = False
        elif entry[t]:
            on, held = True, 0
        state.append(int(on))
    return pd.DataFrame({"price": p, "z": z, "new_high": new_high, "entry": entry,
                         "state": state}, index=p.index)


def episodes(sig: pd.DataFrame):
    """List of (entry_month, exit_month or None) from a state column."""
    s = sig["state"]
    d = s.diff().fillna(s)
    starts = list(s.index[d == 1]); ends = list(s.index[d == -1])
    out = []
    for a in starts:
        e = next((x for x in ends if x > a), None)
        out.append((a, e))
    return out
