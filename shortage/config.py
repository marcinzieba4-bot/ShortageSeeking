"""Universe definition and pre-registered parameters.

Every "item" is a physical good whose scarcity is tracked with ONE external
price variable, mapped to ONE tradable theme (the natural producers of the
scarce good).  Parameters below were fixed before any backtest was run; the
sensitivity grid in run.py shows neighbours, it is not used to pick them.
"""

START = "2018-01-01"          # first date a position may be opened
PRICE_START = "2017-01-01"    # equity history download start

PARAMS = dict(
    lookback=6,      # months: log price change horizon
    z_window=120,    # months: trailing window for mean/std of that change
    z_min_obs=60,    # need >=5y of history before any signal is allowed
    z_entry=1.5,     # entry: change is >=1.5 sigma above its own history
    high_window=24,  # entry: AND price is at a new 24-month high
    exit_ma=6,       # exit: price falls below its 6-month average
    max_hold=24,     # exit: time stop, months
    cost_bps=10,     # per side, on traded notional
    cap=0.20,        # max portfolio weight per theme
)

# Publication lag = trading day of month M+1 on which month-M data is treated
# as known and traded (at that day's close).
#   World Bank Pink Sheet: published 2nd-3rd business day  -> trade day 5
#   IMF PCPS / BLS CPI & PPI: published ~mid-month        -> trade day 15
#   Yahoo futures: real time, month average is known at month end -> day 1
LAG = {"wb": 5, "imf": 15, "bls": 15, "yahoo": 1}

THEMES = {
    "oil":        dict(name="Oil & gas E&P",          tickers=["XOP"]),
    "us_gas":     dict(name="US gas producers",       tickers=["EQT", "AR", "RRC", "CNX"]),
    "eu_gas":     dict(name="LNG / Europe gas",       tickers=["LNG", "EQNR"]),
    "coal":       dict(name="Thermal coal miners",    tickers=["BTU", "ARLP", "WHC.AX", "YAL.AX"]),
    "copper":     dict(name="Copper miners",          tickers=["COPX"]),
    "aluminum":   dict(name="Aluminium smelters",     tickers=["AA", "CENX", "NHY.OL"]),
    "iron_ore":   dict(name="Iron ore majors",        tickers=["RIO", "BHP", "VALE", "FMG.AX"]),
    "nickel":     dict(name="Nickel miners",          tickers=["VALE", "IGO.AX", "NIC.AX"]),
    "zinc":       dict(name="Zinc miners",            tickers=["TECK", "BOL.ST", "HBM"]),
    "tin":        dict(name="Tin miners",             tickers=["MLX.AX", "AFM.V"]),
    "gold":       dict(name="Gold miners",            tickers=["GDX"]),
    "silver":     dict(name="Silver miners",          tickers=["SIL"]),
    "pgm":        dict(name="PGM miners",             tickers=["SBSW", "IMPUY"]),
    "uranium":    dict(name="Uranium miners",         tickers=["URA"]),
    "lithium":    dict(name="Lithium producers",      tickers=["ALB", "SQM", "PLS.AX", "MIN.AX"]),
    "fertilizer": dict(name="Fertiliser producers",   tickers=["CF", "NTR", "MOS", "YAR.OL"]),
    "agri":       dict(name="Agribusiness",           tickers=["MOO"]),
    "lumber":     dict(name="Timber & sawmills",      tickers=["WY", "PCH", "WFG.TO", "CFP.TO"]),
    "used_cars":  dict(name="Auto dealers / rental",  tickers=["AN", "LAD", "PAG", "KMX", "CAR"]),
    "eggs":       dict(name="Egg producers",          tickers=["CALM"]),
    "chips":      dict(name="Semiconductors",         tickers=["SMH"]),
    # direct commodity expression (no natural listed producer): front futures
    "cocoa_f":    dict(name="Cocoa (futures)",        tickers=["CC=F"], futures=True),
    "coffee_f":   dict(name="Coffee (futures)",       tickers=["KC=F"], futures=True),
    "sugar_f":    dict(name="Sugar (futures)",        tickers=["SB=F"], futures=True),
    "cotton_f":   dict(name="Cotton (futures)",       tickers=["CT=F"], futures=True),
}

# key, label, source, series id, theme
ITEMS = [
    ("brent",     "Crude oil, Brent",      "wb",  "Crude oil, Brent",       "oil"),
    ("us_gas",    "Natural gas, US",       "wb",  "Natural gas, US",        "us_gas"),
    ("eu_gas",    "Natural gas, Europe",   "wb",  "Natural gas, Europe",    "eu_gas"),
    ("coal",      "Coal, Australian",      "wb",  "Coal, Australian",       "coal"),
    ("copper",    "Copper",                "wb",  "Copper",                 "copper"),
    ("aluminum",  "Aluminium",             "wb",  "Aluminum",               "aluminum"),
    ("iron_ore",  "Iron ore",              "wb",  "Iron ore, cfr spot",     "iron_ore"),
    ("nickel",    "Nickel",                "wb",  "Nickel",                 "nickel"),
    ("zinc",      "Zinc",                  "wb",  "Zinc",                   "zinc"),
    ("tin",       "Tin",                   "wb",  "Tin",                    "tin"),
    ("gold",      "Gold",                  "wb",  "Gold",                   "gold"),
    ("silver",    "Silver",                "wb",  "Silver",                 "silver"),
    ("platinum",  "Platinum",              "wb",  "Platinum",               "pgm"),
    ("palladium", "Palladium",             "yahoo", "PA=F",                 "pgm"),
    ("uranium",   "Uranium",               "imf", "M.W00.PURAN.USD",        "uranium"),
    ("lithium",   "Lithium",               "imf", "M.W00.PLITH.USD",        "lithium"),
    ("urea",      "Urea",                  "wb",  "Urea",                   "fertilizer"),
    ("dap",       "DAP phosphate",         "wb",  "DAP",                    "fertilizer"),
    ("potash",    "Potash",                "wb",  "Potassium chloride **",  "fertilizer"),
    ("wheat",     "Wheat, US HRW",         "wb",  "Wheat, US HRW",          "agri"),
    ("maize",     "Maize",                 "wb",  "Maize",                  "agri"),
    ("soybeans",  "Soybeans",              "wb",  "Soybeans",               "agri"),
    ("lumber",    "Softwood lumber PPI",   "bls", "pc/PCU3211133211133",    "lumber"),
    ("used_cars", "Used cars CPI",         "bls", "cu/CUUR0000SETA02",      "used_cars"),
    ("eggs",      "Eggs, retail price",    "bls", "ap/APU0000708111",       "eggs"),
    ("chips",     "Semiconductor PPI",     "bls", "pc/PCU334413334413",     "chips"),
    ("cocoa",     "Cocoa",                 "wb",  "Cocoa",                  "cocoa_f"),
    ("coffee",    "Coffee, Arabica",       "wb",  "Coffee, Arabica",        "coffee_f"),
    ("sugar",     "Sugar, world",          "wb",  "Sugar, world",           "sugar_f"),
    ("cotton",    "Cotton, A Index",       "wb",  "Cotton, A Index",        "cotton_f"),
]

BENCH = ["SPY", "ACWI", "BIL"]
WB_URL = ("https://thedocs.worldbank.org/en/doc/74e8be41ceb20fa0da750cda2f6b9e4e-0050012026/"
          "related/CMO-Historical-Data-Monthly.xlsx")
