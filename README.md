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

## Version 2: news, gluts, the futures curve, and trade management

Everything in this section was run with one extra safeguard: any rule choice was made on trades entered
**before 2023** and then judged on trades entered **from 2023 on**. Code is in `shortage/v2.py`, `run2.py`;
tables are in `outputs/v2/`.

![candidates](outputs/v2/candidates.png)

### What was added

| Addition | How it is measured | Source |
|---|---|---|
| News narrative | Monthly count of posts mentioning an industry word with "shortage", and separately with "glut", against that industry's own prior 2-year rate | Hacker News full-text search, 20 industries, 2015 onward |
| News-only themes | Memory chips (DRAM/HBM), AI accelerators, grid and power equipment, container shipping: no free price series exists, so the news count is the signal | same |
| Oversupply | Exact mirror of the shortage rule: a 6-month fall 1.5 standard deviations beyond history, at a 24-month low | same price data as v1 |
| Futures curve | Cash price against 3-month price, and warehouse stocks, for five LME metals; front-month fund against 12-month fund for oil and US gas | LME settlements (Westmetall), fund prices |
| Commodity expression | Roll-inclusive commodity funds (USO, UNG, CPER, DBB, WEAT, CORN, SOYB, CANE, GLD, SLV, PPLT, PALL), so contango cost is in the return | Yahoo |
| Trade management | Trailing stops (15%, 25%), profit targets (+50%, +100%), re-entry on a new high after a stop | simulated daily |

### Findings

**1. Shorting gluts does not work; buying when a glut ends might.**

| | Trades | Won | Mean return | Mean vs SPY |
|---|---|---|---|---|
| Shortage: long the producers | 71 | 56% | +19.8% | +12.9 |
| Oversupply: short the producers | 27 | 41% | -6.8% | +5.8 |
| Glut ends (price back above 6-month average): long producers for 12 months | 27 | 67% | +29.1% | +8.6 |

The short basket lost 2.6% a year with a 56% drawdown. The mirror rule fires near the bottom (April 2020:
oil, platinum, zinc, Europe gas) and producers then rebound. A shortage-versus-oversupply long-short basket
(Sharpe 0.65) was worse than shortage longs alone (0.96). Buying at the end of a glut was strong before
2023 (+22 points over SPY) but lagged SPY by 4 points afterwards, so it is not confirmed.

**2. The best shortage trades are the ones the news has not noticed yet.**

| Price-based shortage signal, news state at entry | Trades | Won | Mean return |
|---|---|---|---|
| Shortage coverage below 2x normal | 38 | 61% | +20.1% |
| Shortage coverage already 2x normal or more | 11 | 36% | +10.9% |
| News net balance disagrees with the price | 20 | 70% | +19.8% |
| News net balance agrees | 29 | 45% | +16.8% |

As a holding rule, "stay in after the price exit while shortage talk is still above normal" raised the mean
trade from +18.1% to +31.8% before 2023, but only from +17.9% to +19.2% on the nine trades after, and at
portfolio level it did not beat the simpler rule. "Leave when glut talk overtakes" clearly hurt.

**3. News alone found the memory, shipping and power-equipment shortages, on very few trades.**

| News-only long | Entry | Exit | Basket return |
|---|---|---|---|
| Container shipping | Feb 2021 | Mar 2022 | +184% |
| Memory chips (DRAM/HBM) | Dec 2025 | Sep 2026 | +346% |
| Grid and power equipment | Jun 2023 | Nov 2023 | +23% |
| AI accelerators | Nov 2020 | Jul 2022 | +4% |
| Grid and power equipment | Jun 2024 | Aug 2024 | -10% |
| AI accelerators | Jul 2026 | Oct 2026 | +18% |

Six trades, five winners, median +21%. The mean (+94%) is two trades. News-only glut shorts (three trades)
were flat. This answers the HBM question from v1, but six trades prove nothing.

![news heat](outputs/v2/news_heat.png)

**4. Producers beat commodity funds; the curve sample is too small to rule on.**
On the 34 shortage signals where both exist, producers averaged +8.6% and the commodity fund +4.1%. For
the 16 shortage signals that began in backwardation, producers made +10.4% while the fund lost 7.0%, the
opposite of the textbook expectation. With 20 curve observations in total this is inconclusive. LME
stocks were already falling in 9 of 11 metal shortages, so stocks confirm but do not discriminate.

**5. Stops cost return; a profit target helps a little.**

| Shortage longs | CAGR | Sharpe | Max drawdown | Sharpe 2018-22 | Sharpe 2023-26 |
|---|---|---|---|---|---|
| A. Price exit only (v1) | 19.0% | 0.99 | -28.7% | 0.94 | 1.05 |
| B. A + take profit at +100% | 18.9% | 1.09 | -25.7% | 0.97 | 1.28 |
| C. A + 15% trailing stop | 14.6% | 1.12 | -21.0% | 0.86 | 1.62 |
| D. A + glut-recovery longs | 24.9% | 1.04 | -42.3% | 0.93 | 1.19 |
| E. D + news-only shortage themes | 29.0% | 1.16 | -42.3% | 0.92 | 1.45 |
| B hedged with SPY | 12.0% | 0.84 | -25.3% | 0.82 | 0.86 |
| SPY | 14.2% | 0.79 | -33.7% | 0.52 | 1.33 |

- **B was the pick on pre-2023 data** (highest Sharpe there) and it held up afterwards.
- Stops made things worse before 2023 and better after; that is not a stable result. Re-entry after a stop
  never helped. A +50% target cut too many winners.
- In 2023-26 none of A to D beat SPY's Sharpe of 1.33. Only E did, and E's edge is the memory trade.
- Hedged with SPY, the shortage basket earned about 12% a year at Sharpe 0.8 in both periods with a
  correlation of -0.1 to SPY. That is its most consistent use: a diversifier, not a replacement.

### The strategy that survives

1. **Enter** on the v1 price rule. Skip nothing on news grounds, but size up when coverage is still quiet.
2. **Express** through producers, not commodity funds.
3. **Exit** when the price falls below its 6-month average, or take profit at +100%. No trailing stop.
4. **Re-enter** only on a fresh price signal.
5. **Do not short gluts.** Put a theme on the watchlist when its glut ends.
6. **Add news-only themes** (memory, power equipment, shipping, AI chips) at small size: enter when
   shortage mentions reach 2x their 2-year norm with at least five mentions, exit when back below normal.
7. **Hedge with SPY** if the goal is an uncorrelated return rather than beating the index.

### Live readings, v2

- Copper is the only price-based shortage on. No oversupply signal is on.
- All four news-only themes are below their norms. Memory exited in September 2026 after coverage faded.
- Cocoa's glut ended in June 2026, so it is the one open glut-recovery long (+33% since).

### Additional limitations in v2

- **The news source is one technology forum.** GDELT, the broad news archive I intended to use, refused
  requests from this environment (the loader is in `shortage/sentiment.py`). Hacker News counts are small
  (often under ten mentions a month), English-only and tech-biased; farm goods and metals are thin.
- **I did not "read" the industries.** A model reading old articles today knows how each story ended, so
  only counted, time-stamped mentions are used.
- **The curve for grains, softs, coal, uranium and lithium is not measured.** There is no free history of
  individual contract months.
- **Short-side costs are a flat 1% a year;** real borrow on small miners can be far higher.
- The 2023-26 judging period has 19 price-based shortage trades. It is a check, not proof.

## Limitations (v1)

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
python run.py            # v1, uses cached data in data/raw
python run.py --refresh  # re-download prices and commodity data
python charts.py
python -m shortage.hn    # refresh news counts (adds new months only)
python run2.py           # v2 research tables -> outputs/v2
python charts.py v2
```

| File | Contents |
|---|---|
| `shortage/config.py` | items, themes, parameters, publication lags |
| `shortage/signals.py` | the detector |
| `shortage/backtest.py` | trade dating, event study, placebo, portfolio |
| `outputs/events.csv` | every signal with entry, exit and returns |
| `outputs/live_signals.csv` | current reading for every item |
| `outputs/sensitivity.csv`, `placebo.csv`, `yearly.csv`, `by_theme.csv` | supporting tables |
