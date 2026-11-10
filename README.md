# ShortageSeeking

A rule-based strategy that looks for the most statistically unusual **physical shortages**, and goes long
the listed producers of whatever is scarce. Back-tested from January 2018 to November 2026 using only
information that was published before each trade.

**Headline:** 71 shortage signals since 2018. The portfolio returned 19.0% a year (Sharpe 0.99) while being
invested only 56% of the time, against 14.2% (Sharpe 0.79) for SPY. The edge is real but lumpy: ten trades
produced about three quarters of the total gain, and only 56% of signals made money.

![equity curves](outputs/equity_curves.png)

## The idea

A shortage shows up in one place before it shows up in producers' earnings: the price of the scarce
good. So each "item" is one good, tracked by **one external price series**, mapped to **one tradable theme**.

| Shortage tracked by | Theme bought |
|---|---|
| Brent, US gas, Europe gas, Australian coal | E&Ps, US gas producers, LNG/Equinor, coal miners |
| Copper, aluminium, iron ore, nickel, zinc, tin | the respective miners / smelters |
| Gold, silver, platinum, palladium | GDX, SIL, PGM miners |
| Uranium, lithium (IMF) | URA, lithium producers |
| Urea, DAP, potash | fertiliser producers |
| Wheat, maize, soybeans | agribusiness (MOO) |
| Softwood lumber PPI, used-car CPI, egg retail price, semiconductor PPI (BLS) | timber, auto dealers, Cal-Maine, SMH |
| Cocoa, coffee, sugar, cotton | front futures (no natural listed producer) |

30 items, 25 themes; the full mapping is in `shortage/config.py`.

## The rules (fixed before the first backtest run)

For each item, every month, using only data up to that month:

1. **Unusual move:** the 6-month log price change is at least **1.5 standard deviations** above that item's
   own trailing 10-year history of 6-month changes (minimum 5 years of history).
2. **Breakout:** the price is at a new **24-month high**.
3. Both true → shortage is ON. Buy the theme, equal-weight across its tickers.
4. **Exit** when the price falls below its own 6-month average, or after 24 months.

Portfolio: equal weight across active themes, 20% cap per theme, the rest in T-bills (or SPY in the
overlay variant). 10 bp cost per side.

### Look-ahead discipline

- The z-score for month *t* excludes month *t* from its own mean and standard deviation.
- Trades happen at the close of a fixed trading day in the **following** month, after the data is public:
  day 5 for the World Bank Pink Sheet, day 15 for IMF and BLS series, day 1 for real-time futures.
- A ticker joins its theme basket only from the day it has a price; nothing is bought before it listed.
- If a data feed stops updating, the position is closed. No data means no position.
- Parameters were not tuned. The 27-combination grid below is reported in full rather than used to pick.

## Results, January 2018 to November 2026

| | CAGR | Vol | Sharpe | Max drawdown | Avg invested |
|---|---|---|---|---|---|
| Shortage, rest in cash | 19.0% | 19.4% | 0.99 | -28.7% | 56% |
| Shortage, rest in SPY | 25.9% | 24.0% | 1.08 | -37.9% | 100% |
| SPY | 14.2% | 19.0% | 0.79 | -33.7% | 100% |
| ACWI | 11.1% | 18.0% | 0.67 | -33.5% | 100% |
| All 25 themes held permanently | 18.7% | 20.7% | 0.93 | -42.8% | 100% |

Per signal (71 events, average holding period about 6.5 months):

| | Value |
|---|---|
| Made money | 56% |
| Beat SPY over the holding period | 56% |
| Mean theme return / median | +20.0% / +8.8% |
| Mean return above SPY | +13.1 points |
| Mean 6-month forward return vs random entry into the same theme | 16.9% vs 10.9% (94th percentile) |
| Same at 3 months / 12 months | 74th / 91st percentile |

![all events](outputs/events.png)

### Where it was early

| Shortage | Bought | Signal strength (z) | Price still to rise to peak | Theme return | vs SPY |
|---|---|---|---|---|---|
| Used cars | Sep 2020 | 2.3 | +3% | +51% | +33 |
| Copper | Oct 2020 | 2.2 | +52% | +75% | +41 |
| Europe gas | Feb 2021 | 4.3 | +423% | +103% | +93 |
| Tin | Feb 2021 | 1.6 | +101% | +180% | +171 |
| Fertiliser (DAP, urea, potash) | Feb to Apr 2021 | 1.7 to 2.1 | +126% to +275% | +63% to +74% | +60 to +70 |
| Thermal coal | Apr 2021 | 2.8 | +137% | +91% | +75 |
| Lithium | Sep 2021 | 1.7 | +371% | +83% | +97 |
| Cocoa | May 2023 | 1.7 | +238% | +176% | +148 |
| Gold | May 2024 | 2.1 | +115% | +174% | +129 |

The Europe gas signal fired in February 2021, about seven months before the energy crisis made headlines.

### Where it failed

- **Short whipsaws.** The 16 trades that lasted 45 trading days or less averaged -5 points against SPY;
  the longer ones averaged +18. Losses are small and frequent, wins are large and rare.
- **Price spike without producer leverage.** Silver 2020 (-46 vs SPY), gold 2020 and 2023, aluminium 2022
  and 2026, US gas (six signals, four losers). Miners' costs rose with the metal, or the spike was weather.
- **Late-cycle signals.** Spring 2022 (nickel squeeze, zinc, aluminium, grains after the invasion) fired
  near the top.
- **Regime dependence.** Entries from 2018 to 2021 averaged +15.8 points over SPY; entries from 2022 to
  2026 averaged +9.7 with a negative median. 2026 to date is -3% against +11% for SPY.
- **Theme beta explains much of it.** Simply holding all 25 themes permanently returned 18.7% a year.
  The signal's contribution is similar return with roughly half the exposure and a shallower drawdown.

### Sensitivity

All 27 combinations of lookback (3, 6, 12 months), entry threshold (1.0, 1.5, 2.0) and exit average
(3, 6, 10 months) are in `outputs/sensitivity.csv`. Sharpe ranges from 0.90 to 1.26 (median 1.01) and
CAGR from 14.5% to 26.6%; none is worse than SPY on Sharpe. The pre-set base case sits in the middle.

### Hypotheses for the next out-of-sample test (not adopted)

These splits were found after the fact, so they are ideas to test going forward, not results:

| Condition at entry | Signals | Made money | Mean vs SPY |
|---|---|---|---|
| z ≥ 2 | 24 | 67% | +19.9 |
| z < 2 | 47 | 51% | +9.7 |
| 4 or more items in shortage at once | 48 | 63% | +15.7 |
| Fewer than 4 | 23 | 43% | +7.8 |
| Theme already above its 200-day average | 66 | 59% | +14.6 |
| Theme below its 200-day average | 5 | 20% | -6.7 |

## Live readings (data through October 2026)

- **ON:** copper (bought February 2026; COPX is -11% since, 21 points behind SPY, and still held because
  copper remains above its 6-month average).
- **Close to triggering:** sugar (z 2.0) and cocoa (z 1.9) pass the unusual-move test but are not at
  24-month highs. Europe gas is at a 24-month high and up 85% in six months but scores only z 1.0.
- **Just exited (November 2026):** tin, cotton.
- Everything else is off. Precious metals, aluminium and urea are in sharp declines.

Full table: `outputs/live_signals.csv`.

## Limitations

- **No memory-chip (DRAM/HBM) test.** I found no free, point-in-time DRAM contract price series. The
  semiconductor PPI is a weak stand-in (one signal, November 2022). Any monthly price CSV can be added as
  an item, so a DRAM or HBM contract series would slot straight in.
- **Stale feeds.** The uranium and lithium series end June 2025 and the four BLS series end January 2025
  (the mirror stopped updating). They are back-tested up to those dates and give no live reading.
- **Hindsight in theme choice.** The mapping is "obvious producers", but it was written in 2026. Some
  tickers that existed then are gone (for example PotlatchDeltic returned no data); coal names that
  merged are missing.
- **Volatility memory.** After an extreme episode the 10-year standard deviation stays inflated, which is
  why Europe gas up 85% scores only z 1.0 today. The detector is slow to re-arm after a blow-off.
- **Not modelled:** currency moves on the non-US tickers, futures roll yield on the four soft
  commodities (Yahoo's front-month series is unadjusted), small revisions to World Bank and PPI data.
- **One regime.** 2018 to 2026 contains one very large shortage cluster (2020 to 2022). 71 signals is a
  small sample and they are not independent of each other.

## Run it

```bash
pip install -r requirements.txt
python run.py            # uses cached data in data/raw
python run.py --refresh  # re-download everything
python charts.py
```

| File | Contents |
|---|---|
| `shortage/config.py` | items, themes, parameters, publication lags |
| `shortage/signals.py` | the detector |
| `shortage/backtest.py` | trade dating, event study, placebo, portfolio |
| `outputs/events.csv` | every signal with entry, exit and returns |
| `outputs/live_signals.csv` | current reading for every item |
| `outputs/sensitivity.csv`, `placebo.csv`, `yearly.csv`, `by_theme.csv` | supporting tables |
