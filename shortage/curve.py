"""Futures-curve and inventory data.

LME base metals (Westmetall mirror of official LME settlements, 2008->): cash, 3-month, warehouse stock.
  spread = cash / 3-month - 1   (>0 backwardation = metal wanted NOW = shortage; <0 contango)
Energy & grains: no free history of individual contract months, so the curve is inferred from
exchange-traded products: a fund that rolls the FRONT contract loses to a fund spread over the next
12 months when the curve is in contango, and beats it in backwardation.
"""
import os, re, time, urllib.request
import numpy as np, pandas as pd

RAW = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "raw", "lme")
os.makedirs(RAW, exist_ok=True)
LME = {"copper": "LME_Cu_cash", "aluminum": "LME_Al_cash", "zinc": "LME_Zn_cash",
       "nickel": "LME_Ni_cash", "tin": "LME_Sn_cash"}
# item -> (front-month fund, 12-month fund): relative 3-month return = curve carry proxy
ETF_PAIRS = {"brent": ("USO", "USL"), "us_gas": ("UNG", "UNL")}


def _year(field, y, refresh):
    p = os.path.join(RAW, f"{field}_{y}.html")
    cur = y >= pd.Timestamp.today().year
    if refresh and cur or not os.path.exists(p):
        url = f"https://www.westmetall.com/en/markdaten.php?action=table&field={field}&year={y}"
        for i in range(4):
            try:
                b = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=60).read()
                break
            except Exception:
                time.sleep(3 * (i + 1))
        open(p, "wb").write(b); time.sleep(0.5)
    h = open(p, encoding="utf-8", errors="ignore").read()
    rows = re.findall(r"<tr>\s*<td >([^<]*)</td>\s*<td >([^<]*)</td>\s*<td >([^<]*)</td>\s*<td class=\"last\">([^<]*)</td>", h)
    f = lambda x: pd.to_numeric(x.replace(",", ""), errors="coerce")
    return pd.DataFrame([(pd.to_datetime(d, format="%d. %B %Y"), f(c), f(m), f(s)) for d, c, m, s in rows],
                        columns=["date", "cash", "m3", "stock"]).set_index("date")


def lme(refresh=False):
    """dict item -> daily DataFrame(cash, m3, stock)."""
    out = {}
    for k, field in LME.items():
        out[k] = pd.concat([_year(field, y, refresh) for y in range(2008, pd.Timestamp.today().year + 1)]).sort_index()
    return out


def lme_monthly(refresh=False):
    """Monthly: spread (mean of daily cash/3m-1) and stock (month-end tonnes). Complete months only."""
    sp, st = {}, {}
    for k, d in lme(refresh).items():
        g = d.index.to_period("M")
        sp[k] = (d.cash / d.m3 - 1).groupby(g).mean()
        st[k] = d.stock.groupby(g).last()
    cur = pd.Timestamp.today().to_period("M")
    sp, st = pd.DataFrame(sp), pd.DataFrame(st)
    return sp[sp.index < cur], st[st.index < cur]
