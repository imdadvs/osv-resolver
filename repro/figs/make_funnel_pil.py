"""Render the audited Substack funnel from the frozen local counts."""
from PIL import Image, ImageDraw, ImageFont

OUT = "/Users/cipher/osv-resolver/repro/figs/fig2_funnel.png"
W, H = 1872, 1150
BG = "#ffffff"
INK = "#1f2430"
MUTED = "#596579"
LINE = "#d9e1ea"
SLATE = "#94a3b8"
BLUE = "#2563eb"
ORANGE = "#e66a27"
TEAL = "#0d9488"

font_dir = "/System/Library/Fonts/Supplemental"
regular = font_dir + "/Arial.ttf"
bold = font_dir + "/Arial Bold.ttf"
F = lambda size, heavy=False: ImageFont.truetype(bold if heavy else regular, size)

im = Image.new("RGB", (W, H), BG)
d = ImageDraw.Draw(im)

d.text((74, 62), "What the pipeline actually found", font=F(50, True), fill=INK)
d.text((76, 134), "A log-level transition is narrower than a verified advisory finding.", font=F(27), fill=MUTED)
d.line((74, 191, W-74, 191), fill=LINE, width=2)

bar_x, bar_max, bar_h = 606, 1136, 69
scale = bar_max / 1525
rows = [
    {
        "y": 258, "value": 1525, "label": "Advisories evaluated",
        "note": "High- and critical-severity Go advisories after alias deduplication",
        "color": SLATE,
    },
    {
        "y": 451, "value": 871, "label": "Test-path cases",
        "note": "630 had no test in the selected fix; 24 had other exclusions",
        "color": BLUE,
    },
    {
        "y": 644, "value": 477, "label": "Pipeline flags",
        "note": "364 direct + 108 partial revert + 5 alternate commit; 394 test-path cases unflagged",
        "color": ORANGE,
    },
    {
        "y": 837, "value": 338, "label": "Direct raw-log transitions",
        "note": "Archived old run FAIL and fixed run PASS; advisory attribution still needs review",
        "color": TEAL,
    },
]

for row in rows:
    y, value = row["y"], row["value"]
    d.text((76, y-23), row["label"], font=F(31, True), fill=INK)
    d.text((76, y+63), row["note"], font=F(22), fill=MUTED)
    width = round(value * scale)
    d.rounded_rectangle((bar_x, y-23, bar_x+width, y-23+bar_h),
                        radius=12, fill=row["color"])
    d.text((bar_x+width+21, y-23), f"{value:,}", font=F(40, True), fill=INK)

d.rounded_rectangle((74, 1008, W-74, 1084), radius=14, fill="#f1f5f9")
d.text((100, 1028), "139 further flags need review; one partial-revert row has no patch or attempt record.",
       font=F(24, True), fill=INK)
d.text((76, 1105), "Source: local merged manifest and archived logs, audited 16 Oct 2026.", font=F(20), fill=MUTED)

im.save(OUT, "PNG", optimize=True)
print(OUT)
