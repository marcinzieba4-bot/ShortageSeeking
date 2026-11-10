"""News-flow measure #2: Hacker News full-text search (Algolia API).
Monthly count of stories + comments that contain an industry keyword together with "shortage",
and the same with "glut", divided by all HN items that month. Posts are time-stamped when written,
so a past month's count never changes: the series is point-in-time. Bias: an English-speaking
technology audience, so coverage is best for chips/energy and thin for farm goods."""
import json, os, time, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor
import pandas as pd

RAW = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "raw", "hn_counts.csv")
KEYWORDS = {
    "memory": "DRAM", "gpu": "GPU", "power_eq": "transformer", "containers": "container", "chips": "chip",
    "copper": "copper", "lithium": "lithium", "uranium": "uranium", "eu_gas": "LNG", "us_gas": "natural gas",
    "coal": "coal", "fertilizer": "fertilizer", "oil": "oil", "used_cars": "used car", "eggs": "egg",
    "lumber": "lumber", "agri": "wheat", "aluminum": "aluminum", "nickel": "nickel", "cocoa_f": "cocoa",
}
SIDES = {"short": "shortage", "glut": "glut"}


def _count(query, a, b):
    p = dict(hitsPerPage=0, typoTolerance="false", numericFilters=f"created_at_i>={a},created_at_i<{b}")
    if query:
        p["query"] = query
    url = "https://hn.algolia.com/api/v1/search?" + urllib.parse.urlencode(p)
    for i in range(6):
        try:
            return json.load(urllib.request.urlopen(url, timeout=40))["nbHits"]
        except Exception:
            time.sleep(2 * (i + 1))
    return None


def download(start="2015-01", refresh=False):
    have = pd.read_csv(RAW) if os.path.exists(RAW) and not refresh else pd.DataFrame(columns=["month", "series", "n"])
    done = set(zip(have.month, have.series))
    months = pd.period_range(start, pd.Timestamp.today().to_period("M") - 1, freq="M")
    jobs = []
    for m in months:
        a, b = int(m.start_time.timestamp()), int((m + 1).start_time.timestamp())
        for name, q in [("_all", "")] + [(f"{t}_{s}", f"{k} {w}") for t, k in KEYWORDS.items() for s, w in SIDES.items()]:
            if (str(m), name) not in done:
                jobs.append((str(m), name, q, a, b))
    with ThreadPoolExecutor(5) as ex:
        res = list(ex.map(lambda j: (j[0], j[1], _count(j[2], j[3], j[4])), jobs))
    new = pd.DataFrame([r for r in res if r[2] is not None], columns=["month", "series", "n"])
    pd.concat([have, new]).sort_values(["series", "month"]).to_csv(RAW, index=False)
    return len(new), len(jobs)


def monthly():
    """(short, glut): per-theme share of all HN items, in mentions per million, PeriodIndex(M)."""
    d = pd.read_csv(RAW).pivot(index="month", columns="series", values="n")
    d.index = pd.PeriodIndex(d.index, freq="M")
    share = d.drop(columns="_all").div(d["_all"], axis=0) * 1e6
    pick = lambda s: share[[c for c in share if c.endswith("_" + s)]].rename(columns=lambda c: c[: -len(s) - 1])
    return pick("short"), pick("glut")


def counts():
    """(short counts, glut counts, total HN items) per month - raw integers for smoothed ratios."""
    d = pd.read_csv(RAW).pivot(index="month", columns="series", values="n")
    d.index = pd.PeriodIndex(d.index, freq="M")
    pick = lambda s: d[[c for c in d if c.endswith("_" + s)]].rename(columns=lambda c: c[: -len(s) - 1])
    return pick("short"), pick("glut"), d["_all"]


if __name__ == "__main__":
    print(download())
