"""Generate ytk.icns: lowercase brass wordmark on the hub's dark ground.

Matches the hub theme (brass #e2b04a, Newsreader, lowercase). Newsreader is
used when installed; falls back through Georgia to any serif. Writes a full
iconset and compiles it with iconutil.

  uv run python packaging/macos/make_icon.py [out_dir]
"""

import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

BRASS = (226, 176, 74, 255)
GROUND = (24, 22, 18, 255)
FONTS = [
    Path.home() / "Library/Fonts/Newsreader-Regular.ttf",
    Path("/Library/Fonts/Newsreader-Regular.ttf"),
    Path("/System/Library/Fonts/Supplemental/Georgia.ttf"),
    Path("/System/Library/Fonts/Supplemental/Times New Roman.ttf"),
]


def _font(px: int) -> ImageFont.FreeTypeFont:
    for p in FONTS:
        if p.exists():
            return ImageFont.truetype(str(p), px)
    return ImageFont.load_default(px)


def render(size: int = 1024) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # macOS icon grid: content in a rounded square with ~10% margin
    m = round(size * 0.09)
    radius = round(size * 0.22)
    d.rounded_rectangle([m, m, size - m, size - m], radius=radius, fill=GROUND)
    # thin brass keyline, hub-style understatement
    d.rounded_rectangle(
        [m, m, size - m, size - m], radius=radius,
        outline=(226, 176, 74, 90), width=max(2, size // 256),
    )
    font = _font(round(size * 0.42))
    bbox = d.textbbox((0, 0), "ytk", font=font)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    d.text(((size - w) / 2 - bbox[0], (size - h) / 2 - bbox[1] - size * 0.02),
           "ytk", font=font, fill=BRASS)
    return img


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
    out.mkdir(parents=True, exist_ok=True)
    base = render()
    with tempfile.TemporaryDirectory() as td:
        iconset = Path(td) / "ytk.iconset"
        iconset.mkdir()
        for pt in (16, 32, 128, 256, 512):
            for scale in (1, 2):
                px = pt * scale
                name = f"icon_{pt}x{pt}" + ("@2x" if scale == 2 else "") + ".png"
                base.resize((px, px), Image.LANCZOS).save(iconset / name)
        subprocess.run(
            ["iconutil", "-c", "icns", str(iconset), "-o", str(out / "ytk.icns")],
            check=True,
        )
    print(f"wrote {out / 'ytk.icns'}")


if __name__ == "__main__":
    main()
