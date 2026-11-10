"""Company text, scored for shortage / glut language.

Two sources, both time-stamped:
  calls    earnings-call transcripts, S&P 500, 2005 to May 2025 (Hugging Face dataset
           kurry/sp500_earnings_transcripts, MIT licence). Not stored in this repo; only scores are.
  filings  SEC EDGAR 10-Q / 10-K reports for ~115 companies, mid-2017 to today. Sentences that are
           hypothetical risk language ("could", "may", "might") are ignored.

Per filing we keep only derived numbers and a few short quotes:
  s, g        sentences with shortage-type / glut-type language
  words       document length
  inputs_s/g  which named inputs (HBM, transformers, copper ...) appear inside those sentences
Cached in data/raw/edgar_scores.json."""
import html, json, os, re, threading, time, urllib.request
from concurrent.futures import ThreadPoolExecutor

RAW = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "raw")
CACHE = os.path.join(RAW, "edgar_scores.json")
UA = {"User-Agent": "research-client admin@example.com", "Accept-Encoding": "identity"}
_lock, _last = threading.Lock(), [0.0]

SHORT_RE = re.compile(r"shortage|short supply|supply[- ]constrain|capacity[- ]constrain|constrained|constraints? (?:on|in) (?:supply|capacity)|"
                      r"tight(?:ness|er|ening)? (?:supply|market|capacity|inventor)|supply (?:remains? |is |was )?tight|sold[- ]out|on allocation|"
                      r"bottleneck|lead[- ]times? (?:have |has |are |remain )?(?:extend|lengthen|increas|stretch|long)|undersuppl|scarcit|"
                      r"unable to (?:meet|fulfill|satisfy)(?: all)?(?: customer)? demand|demand (?:continues to |significantly |far )?(?:exceed|outstrip|outpac)|"
                      r"exceed(?:s|ed|ing)? (?:our |available )?supply|supply deficit|structural deficit", re.I)
GLUT_RE = re.compile(r"oversuppl|glut|excess (?:inventor|suppl|capacit)|overcapacit|inventory (?:correction|digestion|destocking|adjustment|reduction)|"
                     r"destock|pricing pressure|price (?:erosion|declines?)|lower (?:average )?(?:selling )?prices|underutiliz|under-utiliz|"
                     r"(?:weak|soft)(?:er|ening|ness)? (?:end[- ])?(?:market )?demand|demand (?:weakness|softness)|curtail|idl(?:e|ed|ing) (?:capacity|production|plant|mill|smelter)", re.I)
SKIP_RE = re.compile(r"forward[- ]looking|risks and uncertainties|factors that (?:could|may)|undue reliance|safe harbor", re.I)

# named inputs that can be the bottleneck (or the glut): label -> pattern
INPUTS = {
    "HBM / DRAM / NAND memory": r"\bHBM\b|high[- ]bandwidth memory|\bDRAM\b|\bNAND\b|memory (?:chips?|supply|pricing|market)",
    "Advanced packaging (CoWoS, substrates)": r"CoWoS|advanced packaging|substrates?\b|\bABF\b",
    "Leading-edge wafers / foundry": r"wafer (?:supply|capacity|starts)|foundry capacity|leading[- ]edge|\b[23] ?nm\b|\bEUV\b",
    "AI accelerators / GPUs": r"\bGPUs?\b|accelerators?\b|Blackwell|\bAI (?:chips?|compute|capacity)\b|compute capacity",
    "Mature-node / auto chips": r"semiconductor (?:shortage|supply)|chip (?:shortage|supply)|microcontrollers?|analog (?:chips|products)",
    "Optical components": r"optical|transceivers?|lasers?\b|indium phosphide|\bInP\b|photonic",
    "Hard drives / storage": r"hard (?:disk )?drives?|\bHDDs?\b|exabytes?|nearline",
    "Electric power / grid connection": r"power (?:availability|supply|capacity|constraints?)|grid|interconnection|megawatts?|gigawatts?|electricity (?:supply|demand)|utility power",
    "Gas turbines": r"gas turbines?|turbine (?:slots|capacity|supply)|aeroderivative",
    "Transformers / switchgear": r"transformers?\b|switchgear|electrical equipment|circuit breakers?",
    "Data-centre cooling": r"liquid cooling|chillers?|thermal management|cooling (?:capacity|systems)",
    "Data-centre space": r"data[- ]cent(?:er|re) (?:capacity|space|supply)|colocation|powered shells?|leasing capacity",
    "Skilled labour": r"labor|labour|workforce|skilled (?:trades|workers)|craft (?:labor|workers)|electricians|drivers|pilots|technicians",
    "Copper": r"\bcopper\b",
    "Aluminium": r"\balumin(?:um|ium)\b|alumina",
    "Steel": r"\bsteel\b|hot[- ]rolled|scrap",
    "Uranium / enrichment": r"uranium|enrichment|\bSWU\b|HALEU|conversion (?:capacity|services)",
    "Lithium / battery materials": r"lithium|spodumene|battery (?:materials|cells)|cathode",
    "Rare earths / magnets": r"rare earths?|magnets?\b|\bNdPr\b|neodymium|dysprosium",
    "Critical minerals (Ga, Ge, Sb, W)": r"gallium|germanium|antimony|tungsten|critical minerals",
    "Natural gas / LNG": r"natural gas|\bLNG\b|pipeline (?:capacity|takeaway)|takeaway capacity",
    "Crude oil / refining": r"crude|refining capacity|\bOPEC\b|diesel|distillate|jet fuel",
    "Oilfield services / rigs": r"\brigs?\b|frac(?:turing)? (?:crews|fleets|capacity)|pressure pumping|drilling capacity",
    "Aero engines / castings / titanium": r"engines?\b|castings?|forgings?|titanium|\bLEAP\b|\bGTF\b",
    "Aircraft": r"aircraft (?:deliveries|availability|supply|shortage)|narrowbody|widebody|\bOEM deliver",
    "Ships / containers / freight": r"vessels?\b|containers?\b|freight (?:rates|capacity)|port congestion|tanker|charter rates",
    "Trucking capacity": r"truck(?:ing|load)? capacity|truckload|\bLTL\b|carrier capacity",
    "Housing / lots": r"housing (?:supply|shortage|inventory)|existing home|\blots?\b|new homes",
    "Fertiliser": r"fertili[sz]er|nitrogen|\burea\b|potash|phosphate|ammonia",
    "Grains / oilseeds": r"\bcorn\b|wheat|soybeans?|crush margins?|grain",
    "Cattle / beef / eggs / cocoa": r"cattle|\bbeef\b|\beggs?\b|layer flock|avian influenza|cocoa",
    "Lumber / wood": r"lumber|\bOSB\b|timber|wood products",
    "Vehicles (new / used)": r"used (?:vehicles?|cars?)|new vehicle (?:inventory|supply)|vehicle (?:inventory|supply|availability)|days.? supply",
    "Solar modules / polysilicon": r"polysilicon|solar (?:modules?|panels?)|module (?:supply|pricing|oversupply)",
    "Chemicals / plastics": r"polyethylene|petrochemical|olefins?|chlor-?alkali|caustic|\bPVC\b|operating rates",
    "GLP-1 drugs / fill-finish": r"GLP-1|tirzepatide|semaglutide|Zepbound|Mounjaro|Wegovy|fill[- ]finish|incretin",
    "Semiconductor equipment": r"wafer fab equipment|\bWFE\b|lithography|etch|deposition|semiconductor equipment",
    "Water": r"\bwater (?:supply|availability|scarcity|rights)",
}
INPUT_RE = {k: re.compile(v, re.I) for k, v in INPUTS.items()}

# who reports: ticker -> theme label (what the company sells / is exposed to)
COMPANIES = {
    # semis & AI chain
    "MU": "Memory", "WDC": "Memory", "STX": "Storage", "SNDK": "Memory", "NVDA": "AI accelerators", "AMD": "AI accelerators", "AVGO": "AI accelerators",
    "INTC": "Chips", "TXN": "Mature chips", "ADI": "Mature chips", "MCHP": "Mature chips", "ON": "Mature chips", "NXPI": "Mature chips", "GFS": "Foundry",
    "AMAT": "Chip equipment", "LRCX": "Chip equipment", "KLAC": "Chip equipment", "AMKR": "Packaging", "ONTO": "Packaging", "KLIC": "Packaging",
    "COHR": "Optical", "LITE": "Optical", "CIEN": "Optical", "FN": "Optical", "AAOI": "Optical", "ANET": "Networking", "CSCO": "Networking",
    "DELL": "Servers", "SMCI": "Servers", "HPE": "Servers", "MSFT": "Hyperscaler", "GOOGL": "Hyperscaler", "AMZN": "Hyperscaler", "META": "Hyperscaler",
    "ORCL": "Hyperscaler", "CRWV": "Hyperscaler", "AAPL": "Devices", "EQIX": "Data centres", "DLR": "Data centres",
    # power & electrical
    "VST": "Power producers", "CEG": "Power producers", "TLN": "Power producers", "NRG": "Power producers", "NEE": "Utilities", "SO": "Utilities", "DUK": "Utilities",
    "GEV": "Gas turbines & grid", "ETN": "Electrical equipment", "HUBB": "Electrical equipment", "POWL": "Electrical equipment", "VRT": "DC power & cooling",
    "PWR": "Grid contractors", "EME": "Grid contractors", "MTZ": "Grid contractors", "FIX": "Grid contractors", "CARR": "HVAC", "TT": "HVAC", "JCI": "HVAC",
    "BE": "On-site power", "CMI": "Engines & gensets", "CAT": "Engines & gensets",
    # metals & mining & energy
    "FCX": "Copper", "SCCO": "Copper", "AA": "Aluminium", "CENX": "Aluminium", "NUE": "Steel", "STLD": "Steel", "CLF": "Steel", "MP": "Rare earths",
    "ALB": "Lithium", "CCJ": "Uranium", "LEU": "Uranium", "UEC": "Uranium", "NEM": "Gold", "BTU": "Coal", "ARLP": "Coal",
    "XOM": "Oil", "CVX": "Oil", "OXY": "Oil", "SLB": "Oil services", "HAL": "Oil services", "VLO": "Refining", "MPC": "Refining",
    "EQT": "US gas", "AR": "US gas", "LNG": "LNG", "KMI": "Pipelines", "WMB": "Pipelines",
    # industrial, aero, transport
    "BA": "Aircraft", "GE": "Aero engines", "RTX": "Aero engines", "HWM": "Aero parts", "ATI": "Aero materials", "CRS": "Aero materials", "TDG": "Aero parts",
    "AL": "Aircraft lessors", "DAL": "Airlines", "UAL": "Airlines", "MATX": "Shipping", "JBHT": "Trucking", "ODFL": "Trucking", "UNP": "Rail",
    "DE": "Farm equipment", "PCAR": "Trucks",
    # autos, housing, consumer, ag, chem, health
    "F": "Autos", "GM": "Autos", "TSLA": "Autos", "KMX": "Used cars", "AN": "Auto dealers", "DHI": "Homebuilders", "LEN": "Homebuilders", "BLDR": "Building products",
    "WY": "Timber", "CF": "Fertiliser", "MOS": "Fertiliser", "ADM": "Agribusiness", "BG": "Agribusiness", "TSN": "Protein", "CALM": "Eggs", "HSY": "Cocoa user",
    "DOW": "Chemicals", "LYB": "Chemicals", "OLN": "Chemicals", "FSLR": "Solar", "ENPH": "Solar", "LLY": "GLP-1", "AWK": "Water",
}


def _get(url, tries=5):
    for i in range(tries):
        with _lock:                                   # stay well under SEC's 10 requests/second
            w = _last[0] + 0.14 - time.time()
            if w > 0: time.sleep(w)
            _last[0] = time.time()
        try:
            return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60).read()
        except Exception as e:
            if getattr(e, "code", 0) == 404: return None
            time.sleep(2 * (i + 1))
    return None


def text_of(b):
    t = b.decode("utf-8", "ignore")
    t = re.sub(r"(?is)<(script|style|ix:header).*?</\1>", " ", t)
    t = re.sub(r"(?s)<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", html.unescape(t))


HYPO_RE = re.compile(r"\b(?:could|may|might|would|if we|if our|there can be no assurance|no assurance)\b", re.I)


def score(text, drop_hypothetical=False, quotes=3):
    sents = re.split(r"(?<=[.!?])\s+(?=[A-Z])", text)
    out = dict(words=len(text.split()), s=0, g=0, inputs_s={}, inputs_g={}, quotes=[])
    for x in sents:
        if len(x) > 700 or SKIP_RE.search(x) or (drop_hypothetical and HYPO_RE.search(x)): continue
        hs, hg = bool(SHORT_RE.search(x)), bool(GLUT_RE.search(x))
        if not (hs or hg): continue
        out["s"] += hs; out["g"] += hg
        for k, rx in INPUT_RE.items():
            if rx.search(x):
                if hs: out["inputs_s"][k] = out["inputs_s"].get(k, 0) + 1
                if hg: out["inputs_g"][k] = out["inputs_g"].get(k, 0) + 1
        if hs and len(out["quotes"]) < quotes and 60 < len(x) < 320:
            out["quotes"].append(x.strip())
    return out


def _filings(cik):
    j = json.loads(_get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json"))
    blocks = [j["filings"]["recent"]] + [json.loads(_get("https://data.sec.gov/submissions/" + f["name"])) for f in j["filings"].get("files", [])]
    rows = []
    for b in blocks:
        for form, date, acc, items, prim, accd in zip(b["form"], b["filingDate"], b["accessionNumber"], b["items"], b["primaryDocument"], b["acceptanceDateTime"]):
            if form in ("10-Q", "10-K") and date >= "2017-07-01":
                rows.append((date, acc, prim, accd))
    return rows


def _one(tk, cik, date, acc, prim, accd):
    b = _get(f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-', '')}/{prim}")
    if b is None: return None
    r = score(text_of(b), drop_hypothetical=True); r.update(ticker=tk, date=date, accepted=accd, acc=acc)
    return r


def build(tickers=None, workers=6):
    cache = json.load(open(CACHE)) if os.path.exists(CACHE) else {}
    ciks = {v["ticker"]: v["cik_str"] for v in json.loads(_get("https://www.sec.gov/files/company_tickers.json")).values()}
    jobs = []
    for tk in tickers or COMPANIES:
        if tk not in ciks: print("no CIK", tk); continue
        for date, acc, prim, accd in _filings(ciks[tk]):
            if acc not in cache: jobs.append((tk, ciks[tk], date, acc, prim, accd))
    jobs.sort(key=lambda j: j[2], reverse=True)          # newest first: live readings arrive early
    print("filings to fetch:", len(jobs), flush=True)
    with ThreadPoolExecutor(workers) as ex:
        for i, r in enumerate(ex.map(lambda j: _one(*j), jobs)):
            if r: cache[r["acc"]] = r
            if i % 300 == 299:
                json.dump(cache, open(CACHE, "w")); print(i + 1, flush=True)
    json.dump(cache, open(CACHE, "w"))
    return len(cache)


CALLS = os.path.join(RAW, "call_scores.json")


def _score_call(row):
    sym, date, text = row
    r = score(text or "", quotes=2 if date >= "2024-06" else 0); r.update(ticker=sym, date=date[:10])
    return r


def build_calls(parquet_path):
    """Score every transcript in the dataset; writes data/raw/call_scores.json (scores only)."""
    import pyarrow.parquet as pq
    from multiprocessing import Pool
    f = pq.ParquetFile(parquet_path); out = []
    with Pool() as pool:
        for i in range(f.num_row_groups):
            t = f.read_row_group(i, columns=["symbol", "date", "content"]).to_pandas()
            out += pool.map(_score_call, list(zip(t.symbol, t.date, t.content)), chunksize=50)
            print(i + 1, "/", f.num_row_groups, len(out), flush=True)
    json.dump(out, open(CALLS, "w"))
    return len(out)


if __name__ == "__main__":
    import sys
    print(build_calls(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[1] == "calls" else build())
