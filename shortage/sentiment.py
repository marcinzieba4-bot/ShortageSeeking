"""News-flow sentiment from GDELT: share of world news that pairs an industry keyword with
shortage words vs glut words. Counts for a past month are fixed once that month ends, so the
series is point-in-time. Cached in data/raw/gdelt/."""
import io, os, time, urllib.parse, urllib.request
import numpy as np, pandas as pd

RAW = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "raw", "gdelt")
os.makedirs(RAW, exist_ok=True)

SHORT = '(shortage OR shortages OR scarcity OR "supply crunch" OR "tight supply" OR "supply deficit")'
GLUT = '(glut OR oversupply OR oversupplied OR surplus OR "excess supply")'

# theme -> industry keyword expression
KEYWORDS = {
    "oil": '"crude oil"', "us_gas": '"natural gas"', "eu_gas": 'LNG', "coal": 'coal',
    "copper": 'copper', "aluminum": '(aluminum OR aluminium)', "iron_ore": '"iron ore"',
    "nickel": 'nickel', "zinc": 'zinc', "tin": '("tin prices" OR "tin market" OR "tin supply" OR "tin miners")',
    "silver": '"silver prices"', "pgm": '(platinum OR palladium)', "uranium": 'uranium',
    "lithium": 'lithium', "fertilizer": '(fertilizer OR fertiliser OR urea OR potash)',
    "agri": '(wheat OR corn OR soybean)', "lumber": 'lumber', "used_cars": '"used car"',
    "eggs": '"egg prices"', "chips": '(semiconductor OR semiconductors OR chipmakers)',
    "cocoa_f": 'cocoa', "coffee_f": '"coffee prices"', "sugar_f": '"sugar prices"', "cotton_f": 'cotton',
    # sentiment-only themes (no free price series exists)
    "memory": '("memory chip" OR "memory chips" OR DRAM OR NAND OR HBM)',
    "containers": '("shipping container" OR "container shipping" OR "freight rates")',
    "power_eq": '(transformer OR transformers OR "power grid" OR "gas turbine" OR "gas turbines")',
    "gpu": '(GPU OR GPUs OR "AI chips")',
}


def _fetch(query):
    url = "https://api.gdeltproject.org/api/v2/doc/doc?" + urllib.parse.urlencode(dict(
        query=query + " sourcelang:english", mode="timelinevol", format="csv",
        startdatetime="20170101000000", enddatetime=time.strftime("%Y%m%d000000")))
    for i in range(40):
        try:
            b = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=90).read()
            t = b.decode("utf-8-sig", "ignore")
            if t.lower().startswith("date"):
                return t
        except Exception:
            pass
        time.sleep(min(20 + 10 * i, 90))
    raise RuntimeError("gdelt failed: " + query)


PRIORITY = ["memory", "gpu", "power_eq", "containers", "chips", "copper", "lithium", "uranium", "eu_gas", "coal",
            "fertilizer", "oil", "us_gas", "used_cars", "eggs", "lumber", "agri", "aluminum", "nickel", "tin",
            "cocoa_f", "pgm", "iron_ore", "zinc", "silver", "coffee_f", "sugar_f", "cotton_f"]


def download(refresh=False):
    for th in PRIORITY:
        kw = KEYWORDS[th]
        for side, words in (("short", SHORT), ("glut", GLUT)):
            p = os.path.join(RAW, f"{th}_{side}.csv")
            if refresh or not os.path.exists(p):
                txt = _fetch(f"{kw} {words}")
                open(p, "w").write(txt)
                print("fetched", th, side, flush=True)
                time.sleep(7)


def monthly():
    """DataFrames (short, glut): monthly mean share of coverage, PeriodIndex(M), complete months only."""
    out = {"short": {}, "glut": {}}
    for th in KEYWORDS:
        for side in out:
            p = os.path.join(RAW, f"{th}_{side}.csv")
            if not os.path.exists(p):
                continue
            d = pd.read_csv(p)
            s = pd.Series(pd.to_numeric(d.iloc[:, -1], errors="coerce").values,
                          index=pd.to_datetime(d.iloc[:, 0], utc=True).dt.tz_localize(None))
            m = s.groupby(s.index.to_period("M")).mean()
            out[side][th] = m[m.index < pd.Timestamp.today().to_period("M")]
    return pd.DataFrame(out["short"]), pd.DataFrame(out["glut"])


if __name__ == "__main__":
    download()
