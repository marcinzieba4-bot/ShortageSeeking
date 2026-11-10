"""Analytical report source: the Federal Reserve Beige Book (8 a year, public, dated at release).
The full report (all twelve districts) is scored with the same shortage / glut sentence rules."""
import json, os, re, urllib.request
from . import filings as F

CACHE = os.path.join(F.RAW, "beige_scores.json")


def _get(u):
    try:
        return urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=60).read()
    except Exception:
        return None


def build(start=2015):
    cache = json.load(open(CACHE)) if os.path.exists(CACHE) else {}
    import datetime
    for y in range(start, datetime.date.today().year + 1):
        idx = _get(f"https://www.federalreserve.gov/monetarypolicy/beigebook{y}.htm")
        if not idx: continue
        for ym in sorted(set(re.findall(r"beigebook(\d{6})", idx.decode("utf-8", "ignore")))):
            if ym in cache: continue
            b = _get(f"https://www.federalreserve.gov/monetarypolicy/beigebook{ym}.htm")
            if not b: continue
            h = b.decode("utf-8", "ignore")
            m = re.search(r"Last Update:\s*</?[^>]*>?\s*([A-Z][a-z]+ \d{1,2}, \d{4})", h) or re.search(r"([A-Z][a-z]+ \d{1,2}, \d{4})", h)
            r = F.score(F.text_of(b), quotes=3); r.update(ym=ym, released=m.group(1) if m else None)
            cache[ym] = r
    json.dump(cache, open(CACHE, "w"))
    return len(cache)


if __name__ == "__main__":
    print(build())
