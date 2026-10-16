"""Render the direct-method diagram used in the Substack article.

This diagram describes the pipeline signal; it does not label a package-level
transition as a confirmed reproduction of an advisory-specific bug.
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "method-flow-evidence-tiers.png"
FONT = "/System/Library/Fonts/Supplemental/Arial.ttf"
BOLD = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"

ink = "#1F2937"
muted = "#536171"
blue = "#2563EB"
teal = "#0D9488"
line = "#D7E0E8"
surface = "#FFFFFF"

image = Image.new("RGB", (1600, 610), surface)
draw = ImageDraw.Draw(image)


def font(size, bold=False):
    return ImageFont.truetype(BOLD if bold else FONT, size)


def centered(text, y, face, color=ink):
    box = draw.textbbox((0, 0), text, font=face)
    draw.text(((1600 - (box[2] - box[0])) / 2, y), text, font=face, fill=color)


centered("From advisory to a test signal", 42, font(43, True))
centered("The direct path compares one candidate fix with its parent commit", 101, font(25), muted)

steps = [
    ("1  Advisory", "Package, severity,\nand candidate references", blue),
    ("2  Candidate", "Select a commit;\nrecord its SHA", blue),
    ("3  Changed test", "Detect changed Go\ntest files", blue),
    ("4  Two runs", "Run tests on the\ncommit and its parent", blue),
    ("5  Evidence", "Record run status;\nattribution pending", teal),
]

left = 35
top = 175
width = 276
height = 260
gap = 44
for index, (title, detail, color) in enumerate(steps):
    x0 = left + index * (width + gap)
    x1 = x0 + width
    draw.rounded_rectangle((x0, top, x1, top + height), radius=22,
                           fill=surface, outline=color, width=4)
    title_box = draw.textbbox((0, 0), title, font=font(29, True))
    draw.text((x0 + (width - (title_box[2] - title_box[0])) / 2, top + 42),
              title, font=font(29, True), fill=ink)
    for row, part in enumerate(detail.split("\n")):
        box = draw.textbbox((0, 0), part, font=font(22))
        draw.text((x0 + (width - (box[2] - box[0])) / 2, top + 124 + row * 38),
                  part, font=font(22), fill=muted)
    if index < len(steps) - 1:
        arrow_x = x1 + 11
        arrow_y = top + height / 2
        draw.line((arrow_x, arrow_y, arrow_x + 22, arrow_y), fill=muted, width=4)
        draw.polygon([(arrow_x + 30, arrow_y), (arrow_x + 19, arrow_y - 9),
                      (arrow_x + 19, arrow_y + 9)], fill=muted)

draw.rounded_rectangle((60, 478, 1540, 570), radius=18,
                       fill="#F4F8FB", outline=line, width=2)
centered("An aggregate run transition is a lead, not an advisory-specific proof.",
         494, font(27, True), ink)
centered("Test attribution, clean replay, and deployed exposure are separate checks.",
         532, font(23), muted)

image.save(OUT, optimize=True)
print(OUT)
