"""Charts from outputs/_state.pkl (run run.py first)."""
import numpy as np, pandas as pd, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from shortage import config as C

S = pd.read_pickle("outputs/_state.pkl")
INK, INK2, SURF, GRID = "#0b0b0b", "#52514e", "#fcfcfb", "#e6e5e0"
BLUE, ORANGE, AQUA, YELLOW = "#2a78d6", "#eb6834", "#1baf7a", "#eda100"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.edgecolor": GRID, "axes.labelcolor": INK2,
                     "xtick.color": INK2, "ytick.color": INK2, "figure.facecolor": SURF, "axes.facecolor": SURF,
                     "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "grid.color": GRID,
                     "grid.linewidth": 0.6, "axes.axisbelow": True})

# 1 equity curves
eq = (1 + S["curves"]).cumprod()
fig, ax = plt.subplots(figsize=(10, 5.2))
for col, c in [("Shortage (rest SPY)", BLUE), ("Shortage (rest cash)", ORANGE), ("All themes always-on", AQUA), ("SPY", YELLOW)]:
    ax.plot(eq.index, eq[col], color=c, lw=2, label=col)
    dy = {"Shortage (rest cash)": 7, "All themes always-on": -7}.get(col, 0)   # these two end together
    ax.annotate(f"{col}  {eq[col].iloc[-1]:.1f}x", (eq.index[-1], eq[col].iloc[-1]), xytext=(6, dy),
                textcoords="offset points", va="center", color=INK, fontsize=9)
ax.set_yscale("log"); ax.set_yticks([1, 2, 4, 8]); ax.set_yticklabels(["1x", "2x", "4x", "8x"]); ax.minorticks_off()
ax.set_xlim(eq.index[0], eq.index[-1] + pd.Timedelta(days=620))
ax.set_title("Growth of 1 since Jan 2018 (log scale, after 10 bp costs)", loc="left", color=INK, fontsize=12)
ax.legend(frameon=False, loc="upper left")
fig.tight_layout(); fig.savefig("outputs/equity_curves.png", dpi=160); plt.close(fig)

# 2 every event: theme return minus SPY over the holding period
es = S["es"].sort_values("excess")
fig, ax = plt.subplots(figsize=(10, 13))
lab = [f"{l} · {pd.Timestamp(d):%b %Y}" for l, d in zip(es.label, es.entry)]
ax.barh(lab, es.excess * 100, color=[BLUE if x > 0 else ORANGE for x in es.excess], height=0.7)
ax.axvline(0, color=INK2, lw=0.8)
ax.set_xlabel("theme return minus SPY, entry to exit (percentage points)")
ax.set_title(f"All {len(es)} shortage signals 2018-2026: blue beat SPY, orange lagged", loc="left", color=INK, fontsize=12)
ax.tick_params(axis="y", labelsize=7.5); ax.grid(axis="y", visible=False); ax.margins(y=0.005)
fig.tight_layout(); fig.savefig("outputs/events.png", dpi=160); plt.close(fig)

# 3 timeline of active themes
w = S["w"]; act = (w > 0)
order = [t for t in C.THEMES if act[t].any()]
fig, ax = plt.subplots(figsize=(10, 6.5))
for i, t in enumerate(order):
    a = act[t].astype(int); d = a.diff().fillna(a.iloc[0])
    st = list(a.index[d == 1]); en = list(a.index[d == -1]) + [a.index[-1]]
    for s0 in st:
        e0 = next(x for x in en if x >= s0)
        ax.barh(i, (e0 - s0).days, left=s0, color=BLUE, height=0.6)
ax.set_yticks(range(len(order))); ax.set_yticklabels([C.THEMES[t]["name"] for t in order]); ax.invert_yaxis()
ax.xaxis_date(); ax.grid(axis="y", visible=False)
ax.set_title("When each shortage theme was held", loc="left", color=INK, fontsize=12)
fig.tight_layout(); fig.savefig("outputs/timeline.png", dpi=160); plt.close(fig)
