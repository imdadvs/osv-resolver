"""Three figures for the Substack post. Static PNGs, CVD-safe palette
(blue / orange / slate), direct labels, recessive axes. Run with the venv python."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

INK = "#1f2430"; MUTED = "#6b7280"; GRID = "#e5e7eb"; SURF = "#ffffff"
BLUE = "#2563eb"; ORANGE = "#ea580c"; SLATE = "#94a3b8"; GREEN = "#0d9488"
plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 12, "text.color": INK,
    "axes.edgecolor": GRID, "axes.labelcolor": INK, "xtick.color": MUTED,
    "ytick.color": INK, "figure.facecolor": SURF, "axes.facecolor": SURF,
    "savefig.facecolor": SURF, "savefig.dpi": 200,
})

# ---------- Figure 1: the method flow ----------
fig, ax = plt.subplots(figsize=(11, 3.4)); ax.axis("off")
ax.set_xlim(0, 11.15); ax.set_ylim(0, 3.4)
steps = [
    (0.1, "OSV advisory", "a package, a severity,\nreference links, a fixed version", SLATE),
    (2.35, "Resolve the fix", "pick the real fix commit;\ndrop release / version bumps", BLUE),
    (4.6, "Check out both", "parent commit (before)\nand fix commit (after)", BLUE),
    (6.85, "Run the fix's test", "the maintainer's own test,\non each side", BLUE),
    (9.1, "Verdict", "fail before + pass after\n= reproduced", GREEN),
]
w, h = 1.95, 1.9; y = 0.9
for i, (x, title, sub, col) in enumerate(steps):
    box = FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.04,rounding_size=0.12",
                         linewidth=1.6, edgecolor=col, facecolor=SURF)
    ax.add_patch(box)
    ax.text(x + w/2, y + h - 0.42, title, ha="center", va="center", fontsize=13,
            fontweight="bold", color=INK)
    ax.text(x + w/2, y + 0.55, sub, ha="center", va="center", fontsize=9.5, color=MUTED)
    if i < len(steps) - 1:
        ax.add_patch(FancyArrowPatch((x + w + 0.02, y + h/2), (x + w + 0.28, y + h/2),
                     arrowstyle="-|>", mutation_scale=16, linewidth=1.6, color=MUTED))
ax.text(5.5, 3.15, "How one advisory is verified", ha="center", fontsize=15,
        fontweight="bold", color=INK)
ax.text(5.5, 0.35, "No AI. No exploit. The developer's own test, run in a throwaway container.",
        ha="center", fontsize=10, color=MUTED, style="italic")
plt.tight_layout(); plt.savefig("fig1_flow.png", bbox_inches="tight"); plt.close()

# ---------- Figure 2: audited funnel ----------
fig, ax = plt.subplots(figsize=(11.4, 5.3))
stages = [
    ("High/critical Go advisories\nevaluated", 1525, SLATE),
    ("Routed to test path", 871, BLUE),
    ("Pipeline flagged\nreproduced", 477, ORANGE),
    ("Direct raw logs:\nold fail, fixed pass", 338, GREEN),
]
ys = [3, 2, 1, 0]
for (label, val, col), yy in zip(stages, ys):
    ax.barh(yy, val, height=0.56, color=col, zorder=3)
    ax.text(val + 18, yy, f"{val:,}", va="center", ha="left", fontsize=14,
            fontweight="bold", color=INK)
    ax.text(-22, yy, label, va="center", ha="right", fontsize=11.5, color=INK)
ax.set_xlim(0, 1780); ax.set_ylim(-1.0, 4.0)
ax.set_yticks([]); ax.set_xticks([])
for s in ("top", "right", "left", "bottom"): ax.spines[s].set_visible(False)
ax.text(750, 3.72, "338 direct raw-log transitions · 477 pipeline flags",
        ha="center", fontsize=15, fontweight="bold", color=INK)
ax.text(925, 2.55, "630 no test in selected fix · 24 other exclusions",
        fontsize=9.5, color=MUTED)
ax.text(510, 1.55, "394 test-path cases were not flagged reproduced",
        fontsize=9.5, color=MUTED)
ax.text(375, 0.55, "139 further flags: 26 direct · 108 partial revert · 5 alternate commit",
        fontsize=9.5, color=MUTED)
ax.text(0, -0.77,
        "Raw log status is not advisory-level validation. One partial-revert flag lacks a patch or attempt record.",
        fontsize=9.5, color=MUTED)
plt.tight_layout(); plt.savefig("fig2_funnel.png", bbox_inches="tight"); plt.close()

# ---------- Figure 3: reproduced by method ----------
fig, ax = plt.subplots(figsize=(9, 2.6))
parts = [("Direct", 364, BLUE), ("Partial revert", 108, ORANGE),
         ("Other-commit", 5, SLATE)]
left = 0
for label, val, col in parts:
    ax.barh(0, val, left=left, height=0.5, color=col, zorder=3,
            edgecolor=SURF, linewidth=2)
    if val > 20:
        ax.text(left + val/2, 0, f"{label}\n{val}", ha="center", va="center",
                fontsize=11.5, color="white", fontweight="bold")
    left += val
ax.text(477 + 8, 0, "= 477", va="center", ha="left", fontsize=14, fontweight="bold", color=INK)
ax.annotate("5 (other-commit retry)", xy=(474, 0.26), xytext=(360, 0.78),
            fontsize=9.5, color=MUTED,
            arrowprops=dict(arrowstyle="-", color=MUTED, linewidth=1))
ax.set_xlim(0, 560); ax.set_ylim(-1.1, 1.05)
ax.axis("off")
ax.text(255, 0.9, "477 reproduced, by method", ha="center", fontsize=15,
        fontweight="bold", color=INK)
ax.text(255, -0.9, "Direct: run the fix's own test on both sides.   "
        "Partial revert: start from the fixed code and undo only the fix.",
        ha="center", fontsize=9.5, color=MUTED)
plt.tight_layout(); plt.savefig("fig3_method.png", bbox_inches="tight"); plt.close()
print("wrote fig1_flow.png fig2_funnel.png fig3_method.png")
