"""Regenerate the Secure Notes brand mark (assets/notes.png and assets/notes.ico).

Run from the project root:  python tools/generate_brand_assets.py
"""

from pathlib import Path

from PIL import Image, ImageDraw

ASSETS = Path(__file__).resolve().parents[1] / "assets"
CANVAS = 1024
INDIGO = (79, 70, 229, 255)
INDIGO_LIGHT = (199, 210, 254, 255)
WHITE = (255, 255, 255, 255)


def draw_mark() -> Image.Image:
    image = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((0, 0, CANVAS - 1, CANVAS - 1), radius=230, fill=INDIGO)

    # Page with a folded corner.
    left, top, right, bottom, fold = 262, 176, 762, 848, 150
    draw.polygon([(left, top), (right - fold, top), (right, top + fold), (right, bottom), (left, bottom)], fill=WHITE)
    draw.polygon([(right - fold, top), (right - fold, top + fold), (right, top + fold)], fill=INDIGO_LIGHT)

    # Keyhole: the "secure" in Secure Notes.
    cx, cy = (left + right) // 2, 470
    draw.ellipse((cx - 78, cy - 78, cx + 78, cy + 78), fill=INDIGO)
    draw.polygon([(cx - 44, cy + 30), (cx + 44, cy + 30), (cx + 70, cy + 230), (cx - 70, cy + 230)], fill=INDIGO)

    # Two text lines beneath the keyhole.
    draw.rounded_rectangle((left + 90, 752, right - 90, 784), radius=16, fill=INDIGO_LIGHT)
    return image


def main() -> None:
    mark = draw_mark()
    mark.resize((256, 256), Image.Resampling.LANCZOS).save(ASSETS / "notes.png")
    sizes = [(16, 16), (20, 20), (24, 24), (32, 32), (40, 40), (48, 48), (64, 64), (128, 128), (256, 256)]
    mark.resize((256, 256), Image.Resampling.LANCZOS).save(ASSETS / "notes.ico", sizes=sizes)
    # macOS app bundles need .icns; Pillow writes every required size from a 1024px source.
    mark.save(ASSETS / "notes.icns")
    print(f"Wrote {ASSETS / 'notes.png'}, {ASSETS / 'notes.ico'} and {ASSETS / 'notes.icns'}")


if __name__ == "__main__":
    main()

