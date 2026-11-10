"""Bottleneck detector built on company text.

Every company is a sensor. Each month we look at the calls (or filings) of the last 3 months and count
how many DISTINCT companies used shortage language about a given input (HBM, transformers, labour...)
and how many used glut language about it. That share is compared with the same share over the prior
24 months. An input is a live bottleneck when unusually many companies complain about it at once.
Trade: buy the companies that SELL the constrained input."""
import json, numpy as np, pandas as pd
from . import config as C, filings as F

# input -> candidate assets that sell it (first = purest play)
SUPPLIERS = {
    "HBM / DRAM / NAND memory": ["MU", "SNDK", "WDC", "000660.KS", "005930.KS"],
    "Advanced packaging (CoWoS, substrates)": ["AMKR", "ONTO", "KLIC", "CAMT", "TSM"],
    "Leading-edge wafers / foundry": ["TSM", "ASML", "AMAT", "LRCX", "KLAC"],
    "AI accelerators / GPUs": ["NVDA", "AVGO", "AMD", "TSM"],
    "Mature-node / auto chips": ["TXN", "ADI", "MCHP", "ON", "NXPI", "GFS"],
    "Optical components": ["COHR", "LITE", "CIEN", "FN", "AAOI"],
    "Hard drives / storage": ["STX", "WDC"],
    "Electric power / grid connection": ["VST", "CEG", "TLN", "NRG"],
    "Gas turbines": ["GEV", "BE", "CMI", "CAT"],
    "Transformers / switchgear": ["ETN", "HUBB", "POWL", "GEV", "VRT"],
    "Data-centre cooling": ["VRT", "TT", "CARR", "JCI", "MOD"],
    "Data-centre space": ["EQIX", "DLR", "IRM"],
    "Skilled labour": ["PWR", "EME", "FIX", "RHI"],
    "Copper": ["FCX", "SCCO", "TECK", "COPX"],
    "Aluminium": ["AA", "CENX", "NHY.OL"],
    "Steel": ["NUE", "STLD", "CLF", "SLX"],
    "Uranium / enrichment": ["CCJ", "LEU", "UEC", "URA"],
    "Lithium / battery materials": ["ALB", "SQM", "PLS.AX", "LIT"],
    "Rare earths / magnets": ["MP", "LYC.AX", "REMX"],
    "Critical minerals (Ga, Ge, Sb, W)": ["REMX", "MP", "LYC.AX"],
    "Natural gas / LNG": ["EQT", "AR", "LNG", "KMI", "WMB"],
    "Crude oil / refining": ["XOP", "VLO", "MPC", "XOM"],
    "Oilfield services / rigs": ["SLB", "HAL", "OIH"],
    "Aero engines / castings / titanium": ["HWM", "ATI", "CRS", "GE", "TDG"],
    "Aircraft": ["AER", "FTAI", "WLFC"],
    "Ships / containers / freight": ["MATX", "DAC", "ZIM", "GSL", "SBLK"],
    "Trucking capacity": ["JBHT", "ODFL", "KNX", "SAIA"],
    "Housing / lots": ["DHI", "LEN", "BLDR", "ITB"],
    "Fertiliser": ["CF", "NTR", "MOS"],
    "Grains / oilseeds": ["ADM", "BG", "DE", "MOO"],
    "Cattle / beef / eggs / cocoa": ["CALM", "TSN", "PPC"],
    "Lumber / wood": ["WY", "WFG.TO", "LPX"],
    "Vehicles (new / used)": ["AN", "LAD", "PAG", "KMX", "GM"],
    "Solar modules / polysilicon": ["FSLR", "ENPH", "TAN"],
    "Chemicals / plastics": ["DOW", "LYB", "OLN", "WLK"],
    "GLP-1 drugs / fill-finish": ["LLY", "NVO", "WST"],
    "Semiconductor equipment": ["AMAT", "LRCX", "KLAC", "ASML"],
    "Water": ["AWK", "XYL", "PHO"],
}
B = dict(window=24, on=2.0, off=1.0, min_firms=5, k=2.0, lag=2)   # same shape as the v2 news rule


def load(path):
    """Scores as a DataFrame. For calls, the 2005-May 2025 set is extended with the Feb 2024-May 2026 set
    (same S&P 500 tickers), using the newer set only for dates after the older one ends."""
    import os
    if path.endswith("call_scores.json"):
        d = pd.DataFrame(json.load(open(path)))
        p2 = path.replace("call_scores.json", "call_scores_2.json")
        if os.path.exists(p2):
            n = pd.DataFrame(json.load(open(p2)))
            d = pd.concat([d, n[n.date > d.date.max()]], ignore_index=True)
    else:
        d = pd.DataFrame(list(json.load(open(path)).values()))
    d["month"] = pd.PeriodIndex(d["date"].str[:7], freq="M")
    return d[d.words > 500]


def breadth(d):
    """Monthly panels: firms reporting in the trailing 3 months, and firms citing each input (short / glut)."""
    months = pd.period_range(d.month.min(), d.month.max(), freq="M")
    S = pd.DataFrame(0.0, index=months, columns=list(F.INPUTS)); G = S.copy(); N = pd.Series(0.0, index=months)
    by = {m: g for m, g in d.groupby("month")}
    for m in months:
        w = pd.concat([by[x] for x in (m - 2, m - 1, m) if x in by]) if any(x in by for x in (m - 2, m - 1, m)) else None
        if w is None: continue
        N[m] = w.ticker.nunique()
        for col, tgt in (("inputs_s", S), ("inputs_g", G)):
            seen = {}
            for tk, dd in zip(w.ticker, w[col]):
                for k in (dd or {}): seen.setdefault(k, set()).add(tk)
            for k, v in seen.items():
                if k in tgt.columns: tgt.at[m, k] = len(v)
    return S, G, N


def heat(S, G, N):
    """heat_s, heat_g, net per input: firms citing now vs expected from the prior-24-month share."""
    out = {}
    for k in S.columns:
        f = {}
        for nm, X in (("s", S[k]), ("g", G[k])):
            share = (X / N.where(N > 0)).shift(3).rolling(B["window"], min_periods=B["window"]).mean()
            f["heat_" + nm] = (X + B["k"]) / (share * N + B["k"]); f["n_" + nm] = X
        d = pd.DataFrame(f); d["net"] = np.log(d.heat_s) - np.log(d.heat_g); d["firms"] = N
        out[k] = d.dropna()
    return out


def states(H, min_firms=None):
    mf = B["min_firms"] if min_firms is None else min_firms
    up, dn = {}, {}
    for k, n in H.items():
        for side, sign, store in (("s", 1, up), ("g", -1, dn)):
            st, on, held = [], False, 0
            for t in n.index:
                if on:
                    held += 1
                    if n.at[t, "heat_" + side] < B["off"] or held >= C.PARAMS["max_hold"]: on = False
                elif n.at[t, "heat_" + side] >= B["on"] and sign * n.at[t, "net"] > 0 and n.at[t, "n_" + side] >= mf:
                    on, held = True, 0
                st.append(int(on))
            store[k] = pd.DataFrame({"state": st, "z": n["heat_" + side], "price": n["n_" + side]}, index=n.index)
    return up, dn
