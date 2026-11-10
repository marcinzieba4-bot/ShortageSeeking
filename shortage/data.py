"""Data download + on-disk cache (data/raw). Re-run with refresh=True to update."""
import json, os, time, urllib.request, warnings
import numpy as np, pandas as pd
from . import config as C

RAW = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "raw")
os.makedirs(RAW, exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0"}


def _get(url, tries=4):
    for i in range(tries):
        try:
            return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60).read()
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(2 ** (i + 1))


def worldbank(refresh=False):
    p = os.path.join(RAW, "CMO-Historical-Data-Monthly.xlsx")
    if refresh or not os.path.exists(p):
        open(p, "wb").write(_get(C.WB_URL))
    d = pd.read_excel(p, sheet_name="Monthly Prices", header=None)
    names = [str(x).strip() for x in d.iloc[4]]
    body = d.iloc[6:].copy()
    body.columns = ["period"] + names[1:]
    body = body[body["period"].astype(str).str.match(r"^\d{4}M\d{2}$")]
    idx = pd.PeriodIndex(body["period"].str.replace("M", "-"), freq="M")
    out = body.drop(columns="period").apply(pd.to_numeric, errors="coerce")
    out.index = idx
    return out


def dbnomics(provider, path, refresh=False):
    p = os.path.join(RAW, f"{provider}_{path.replace('/', '_')}.json")
    if refresh or not os.path.exists(p):
        url = f"https://api.db.nomics.world/v22/series/{provider}/{path}?observations=1"
        open(p, "wb").write(_get(url))
    doc = json.load(open(p))["series"]["docs"][0]
    s = pd.Series(pd.to_numeric(pd.Series(doc["value"]), errors="coerce").values,
                  index=pd.PeriodIndex(doc["period"], freq="M")).dropna()
    return s


def prices(tickers, refresh=False):
    """Daily adjusted closes, cached to CSV."""
    p = os.path.join(RAW, "prices_daily.csv")
    have = pd.read_csv(p, index_col=0, parse_dates=True) if os.path.exists(p) else pd.DataFrame()
    need = list(tickers) if refresh else [t for t in tickers if t not in have.columns]
    if need:
        import yfinance as yf
        warnings.filterwarnings("ignore")
        for i in range(0, len(need), 20):
            chunk = need[i:i + 20]
            d = yf.download(chunk, start=C.PRICE_START, progress=False, auto_adjust=True, threads=False)["Close"]
            if isinstance(d, pd.Series):
                d = d.to_frame(chunk[0])
            d.index = pd.to_datetime(d.index).tz_localize(None)
            have = have.drop(columns=[c for c in d.columns if c in have.columns]).join(d, how="outer") if len(have) else d
            time.sleep(1)
        have.sort_index().to_csv(p)
    return have.sort_index()[[t for t in tickers if t in have.columns]]


def item_series(refresh=False):
    """Monthly price for every item, PeriodIndex(M). Returns (DataFrame, meta)."""
    wb = worldbank(refresh)
    out = {}
    for key, label, src, sid, theme in C.ITEMS:
        if src == "wb":
            s = wb[sid]
        elif src == "imf":
            s = dbnomics("IMF", "PCPS/" + sid, refresh)
        elif src == "bls":
            s = dbnomics("BLS", sid, refresh)
        elif src == "yahoo":
            # real-time futures: full history for the z-score comes from a long monthly pull
            pl = os.path.join(RAW, f"yahoo_{sid.replace('=', '_')}_monthly.csv")
            if refresh or not os.path.exists(pl):
                import yfinance as yf
                h = yf.download(sid, start="2000-01-01", progress=False, auto_adjust=True)["Close"]
                h = h.iloc[:, 0] if isinstance(h, pd.DataFrame) else h
                h.index = pd.to_datetime(h.index).tz_localize(None)
                h.groupby(h.index.to_period("M")).mean().to_csv(pl)
            s = pd.read_csv(pl, index_col=0).iloc[:, 0]
            s.index = pd.PeriodIndex(s.index, freq="M")
            # drop the current, incomplete month
            s = s[s.index < pd.Timestamp.today().to_period("M")]
        out[key] = s.dropna()
    return pd.DataFrame(out)
