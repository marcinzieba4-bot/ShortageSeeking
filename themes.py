"""Builds the full theme list (outputs/v3/themes.csv and THEMES.md) from every lens:
price signal, forum news, earnings calls, SEC filings, and a manual column of what analyst reports say."""
import json, numpy as np, pandas as pd
from shortage import config as C, data as D, backtest as B, v2 as V, bottleneck as BN, filings as F, hn as HN

# Analyst-report column, researched 10 Nov 2026 (sources in README). view: S shortage, G glut, M mixed, - not researched
A = {
 "HBM / DRAM / NAND memory": ("S", "HBM lines crowd out ordinary DRAM; wafer and cleanroom capacity", "DRAM contracts at a record in Oct 2026, Q4 seen +10-15%; NAND flat for the first time in 21 months"),
 "Advanced packaging (CoWoS, substrates)": ("S", "CoWoS packaging lines and substrates", "Most CoWoS capacity reported pre-booked"),
 "AI accelerators / GPUs": ("S", "Shifts down the chain: memory, packaging, optics, then power", "Compute still short; constraint keeps migrating"),
 "Optical components": ("S", "Indium-phosphide laser chips and substrates (China export licences)", "TrendForce (Aug 2026): InP shortage is the optical bottleneck; NVIDIA pre-paid suppliers"),
 "Electric power / grid connection": ("S", "Grid interconnection queues of 5+ years; firm generation", "Power is the most-cited limit on data-centre build-out"),
 "Gas turbines": ("S", "Turbine manufacturing slots", "Leading supplier reported sold out through 2029"),
 "Transformers / switchgear": ("S", "Large power transformers, switchgear, electrical steel", "Lead times reported at up to five years"),
 "Copper": ("M", "Mine output and concentrate (smelters have excess capacity)", "Concentrate deficit, treatment charges near zero; refined balance disputed (surplus 2026, deficit possible 2027)"),
 "Uranium / enrichment": ("S", "Conversion and enrichment; HALEU", "Commentary cites a 20-30 Mlb primary deficit; sources weak"),
 "Lithium / battery materials": ("G", "None: supply exceeds demand", "Banks see oversupply into 2027"),
 "Natural gas / LNG": ("M", "Reports dated: forecast LNG glut 2027-30, but Europe gas is up 85% in six months", "BNEF and Goldman forecast LNG supply above demand 2027-30; the price has since moved the other way"),
 "Crude oil / refining": ("M", "Reports dated: early-2026 glut calls, but Brent averaged about $125 in Oct 2026", "World Bank (Mar 2026) saw a 1.2 mb/d surplus; Brent has since risen above $100"),
 "Aero engines / castings / titanium": ("S", "Castings, forgings, titanium and nickel superalloys", "94% of executives surveyed expect the shortage to last another year; GE buying a castings maker"),
 "Aircraft": ("S", "Engines (see above)", "Aircraft deliveries capped by engine supply"),
 "Rare earths / magnets": ("S", "Chinese export licences for heavy rare earths and magnets", "S&P: bottlenecks persist through 2026; NdPr spiked then eased"),
 "Critical minerals (Ga, Ge, Sb, W)": ("S", "Chinese export controls", "Gallium shipments to Japan at zero in mid-2026"),
 "Cattle / beef / eggs / cocoa": ("M", "US cattle herd at a cyclical low; cocoa easing", "Beef tight until the herd rebuilds; cocoa and coffee moving to surplus"),
 "Solar modules / polysilicon": ("G", "None: capacity far above demand", "Module prices at record lows in mid-2026"),
 "Steel": ("G", "None: Chinese exports at record", "China output above domestic demand"),
 "Ships / containers / freight": ("M", "Port congestion (episodic)", "Fleet overcapacity, but rates spiked on congestion in 2026"),
 "Nickel": ("G", "None: Indonesian supply", "Range-bound at low prices on oversupply"),
 "Coffee": ("G", "None: record crop expected", "Brazil 2026-27 crop raised; prices sliding"),
}
MAP = {  # input -> (price items, news theme)
 "HBM / DRAM / NAND memory": ([], "memory"), "AI accelerators / GPUs": ([], "gpu"), "Mature-node / auto chips": (["chips"], "chips"),
 "Transformers / switchgear": ([], "power_eq"), "Copper": (["copper"], "copper"), "Aluminium": (["aluminum"], "aluminum"),
 "Uranium / enrichment": (["uranium"], "uranium"), "Lithium / battery materials": (["lithium"], "lithium"),
 "Natural gas / LNG": (["us_gas", "eu_gas"], "us_gas"), "Crude oil / refining": (["brent"], "oil"), "Ships / containers / freight": ([], "containers"),
 "Fertiliser": (["urea", "dap", "potash"], "fertilizer"), "Grains / oilseeds": (["wheat", "maize", "soybeans"], "agri"),
 "Cattle / beef / eggs / cocoa": (["eggs", "cocoa"], "eggs"), "Lumber / wood": (["lumber"], "lumber"), "Vehicles (new / used)": (["used_cars"], "used_cars"),
}
EXTRA = {  # price-only themes from v1
 "Gold": (["gold"], ["GDX"]), "Silver": (["silver"], ["SIL"]), "Platinum / palladium": (["platinum", "palladium"], ["SBSW", "IMPUY"]),
 "Thermal coal": (["coal"], ["BTU", "ARLP", "WHC.AX", "YAL.AX"]), "Tin": (["tin"], ["MLX.AX", "AFM.V"]), "Nickel": (["nickel"], ["VALE", "IGO.AX", "NIC.AX"]),
 "Zinc": (["zinc"], ["TECK", "BOL.ST", "HBM"]), "Iron ore": (["iron_ore"], ["RIO", "BHP", "VALE", "FMG.AX"]),
 "Coffee": (["coffee"], ["KC=F"]), "Sugar": (["sugar"], ["CANE"]), "Cotton": (["cotton"], ["CT=F"]),
}

items = D.item_series(); up, dn = V.price_signals(items, C.PARAMS)
sh, gl, tot = HN.counts(); nar = V.narrative(sh, gl, tot)
calls = BN.load(F.CALLS); H = BN.heat(*BN.breadth(calls))
fil = BN.load(F.CACHE); S2, G2, N2 = BN.breadth(fil)
tick = sorted({t for v in BN.SUPPLIERS.values() for t in v} | {t for _, v in EXTRA.values() for t in v} | {"SPY"})
px = D.prices(tick); cal = px["SPY"].dropna().index; px = px.reindex(cal).ffill(limit=5)
now = cal[-1].to_period("M")

def price_state(keys):
    out = []
    for k in keys:
        g = up[k]
        if g.index[-1] < now - 3: out.append(f"{k}: no data since {g.index[-1]}"); continue
        out.append(f"{k}: " + ("SHORTAGE on" if up[k].state.iloc[-1] else "GLUT on" if dn[k].state.iloc[-1] else f"off (z {g.z.iloc[-1]:+.1f})"))
    return "; ".join(out) if out else "no price series"
def news_state(th):
    if th not in nar: return "-"
    x = nar[th].iloc[-1]
    return f"shortage talk {x.heat_s:.1f}x, glut talk {x.heat_g:.1f}x"
def filing_state(k):
    m = S2.index[-1] if N2.iloc[-1] > 0.6 * N2.max() else S2.index[-2]
    a, b = S2.loc[m - 2:m, k].max(), G2.loc[m - 2:m, k].max()        # firms citing, latest 3-month window
    return f"{int(a)} short / {int(b)} glut", a - b
def calls_state(k):
    h = H[k].iloc[-1]
    return f"{int(h.n_s)} short / {int(h.n_g)} glut"
def asset_stats(tks):
    t = [x for x in tks if x in px and px[x].notna().sum() > 260]
    if not t: return np.nan, np.nan, None
    r = px[t].iloc[-1] / px[t].iloc[-253] - 1
    idx = (1 + px[t].pct_change(fill_method=None).mean(axis=1).fillna(0)).cumprod()
    return r.mean(), idx.iloc[-1] / idx.iloc[-200:].mean() - 1, r.idxmax()

rows = []
for k, tks in list(BN.SUPPLIERS.items()) + [(k, v[1]) for k, v in EXTRA.items()]:
    pk, nt = MAP.get(k, ([], None)) if k in BN.SUPPLIERS else (EXTRA[k][0], None)
    view, neck, note = A.get(k, ("-", "", ""))
    r12, vs200, lead = asset_stats(tks)
    fs, fnet = filing_state(k) if k in BN.SUPPLIERS else ("-", 0)
    quant = sum([any("SHORTAGE on" in x for x in [price_state(pk)]), -1 * ("GLUT on" in price_state(pk)),
                 (nt in nar and nar[nt].iloc[-1].heat_s >= 2 and nar[nt].iloc[-1].net > 0), fnet >= 2, -1 * (fnet <= -2)])
    status = {"S": "SHORTAGE", "G": "GLUT", "M": "MIXED", "-": "not researched"}[view]
    rows.append(dict(theme=k, analysts=status, bottleneck=neck, analyst_note=note, price_signal=price_state(pk), forum_news=news_state(nt) if nt else "-",
                     calls_to_may25=calls_state(k) if k in BN.SUPPLIERS else "-", filings_now=fs, quant_score=int(quant),
                     assets=", ".join(tks), basket_12m=r12, basket_vs_200d=vs200, leader_12m=lead))
T = pd.DataFrame(rows)
order = {"SHORTAGE": 0, "MIXED": 1, "GLUT": 2, "not researched": 3}
T = T.sort_values(["analysts", "basket_12m"], key=lambda s: s.map(order) if s.name == "analysts" else -s.fillna(-9)).reset_index(drop=True)
T.to_csv("outputs/v3/themes.csv", index=False)

pct = lambda x: "n/a" if pd.isna(x) else f"{x:+.0%}"
md = ["# All themes, as of 10 November 2026", "",
      "Status comes from analyst and trade reports found by web search today (see README for sources); the other columns are the model's own readings.",
      "Company counts = number of companies using shortage / glut language about the input in their latest quarterly reports (112 companies tracked).", "",
      "| # | Theme | Analysts say | Where the bottleneck is | Price signal | Companies (short / glut) | Assets (purest first) | Basket 12m | Strongest name |",
      "|---|---|---|---|---|---|---|---|---|"]
for i, r in T.iterrows():
    md.append(f"| {i + 1} | {r.theme} | {r.analysts} | {r.bottleneck or '-'} | {r.price_signal} | {r.filings_now} | {r.assets} | {pct(r.basket_12m)} | {r.leader_12m or '-'} |")
open("THEMES.md", "w").write("\n".join(md) + "\n")
pd.set_option("display.width", 250, "display.max_rows", 100, "display.max_colwidth", 45)
print(T[["theme", "analysts", "price_signal", "forum_news", "calls_to_may25", "filings_now", "quant_score", "basket_12m", "basket_vs_200d", "leader_12m"]].round(2).to_string())
