"""Render the listing-to-print workflow as stills, an MP4 and a GIF, from real runs.

Replays the shelf bracket benchmark (tests/fixtures/bracket.*) through the actual
pipeline, as scripts/workflow_media.py does for the peg. Needs Blender, Bambu
Studio and ffmpeg.

    .venv/bin/python scripts/listing_media.py         # writes docs/listing*
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

from workflow_media import (
    BLUE, GREEN, GREY, HEAD, INK, OUT, RED, ROOT, YELLOW, H, W,
    encode, font, frame, paste, turntable,
)
from print3d.photo import open_upright
from print3d.pipeline import run_job
from test_bracket_benchmark import BENCH, LISTING, build_spec

PROMPT = "a shelf bracket"
SLUG = "a_shelf_bracket"
PHOTO = ROOT / "tests" / "fixtures" / "bracket.jpg"
CREDIT = "Photo: Fructibus, CC0, via Wikimedia Commons"
NAME = "listing"
CHECKS = ("short_leg", "width", "thickness")


def run(work: Path) -> tuple[dict, Path]:
    job = work / "jobs" / SLUG
    build_spec(job)
    report = run_job(PROMPT, script=ROOT / "examples" / "shelf_bracket.py", jobs_dir=work / "jobs", execute=True)
    if report["severity"] == "error":
        raise SystemExit(f"The benchmark run is red: {report['advice']}")
    return report, job


def table(draw, x: int, y: int, columns: list[int], rows: list[tuple], colours: list) -> int:
    mono = font(19, mono=True)
    for i, row in enumerate(rows):
        for cx, cell in zip(columns, row):
            draw.text((x + cx, y), cell, font=mono, fill=GREY if i == 0 else colours[i])
        y += 40 if i == 0 else 34
    return y


def build_frames(report: dict, job: Path, turn: list[Path]) -> list[list[Image.Image]]:
    total = 8
    photo = open_upright(PHOTO)
    spec = json.loads((job / "spec.json").read_text())
    dims = spec["dims"]
    body = (48, HEAD + 16, W - 48, H - 56)
    left = (48, HEAD + 16, 760, H - 56)
    steps: list[list[Image.Image]] = []
    big = font(44, bold=True)

    # 1. The listing.
    canvas, draw = frame(1, total, "Something you would buy", "A shelf bracket, its photo and the sizes it is sold with. No ruler, no bank card.", CREDIT)
    paste(canvas, photo, left)
    draw.rounded_rectangle([800, HEAD + 60, W - 48, 470], radius=16, outline=(220, 220, 220), width=2)
    draw.text((828, HEAD + 92), LISTING["name"].split(",")[0], font=font(24, bold=True), fill=INK)
    y = HEAD + 150
    for line in ("20 x 12 cm", "Width: 2 cm", "Thickness: 4 mm"):
        draw.text((828, y), line, font=font(26), fill=INK)
        y += 44
    draw.text((828, 420), "the listing: stated sizes and a photo", font=font(18), fill=GREY)
    steps.append([canvas])

    # 2. Quote the stated sizes.
    canvas, draw = frame(2, total, "Quote what the shop states", "Each listed size keeps the listing's own words and how coarsely it is rounded.")
    rows = [("dimension", "mm", "rounding", "source")] + [
        (name, f"{dims[name]['mm']:g}", f"± {dims[name]['tolerance_mm']:g}", "listing") for name in LISTING["stated_mm"]
    ]
    y = table(draw, 80, HEAD + 50, [0, 260, 400, 580], rows, [INK] + [GREEN] * 4)
    mono = font(17, mono=True)
    command = [
        "print3d measure bracket dim short_leg --mm 120 \\",
        "    --source listing --tolerance 5 \\",
        f"    --quote \"{LISTING['quote']}\"",
    ]
    y += 40
    for line in command:
        draw.text((80, y), line, font=mono, fill=INK)
        y += 28
    draw.text((80, y + 30), "\"12 cm\" means 115 to 125 mm. That rounding is carried into every number after it.",
              font=font(21), fill=GREY)
    steps.append([canvas])

    # 3. Scale from a listed size.
    (x0, y0), (x1, y1) = BENCH["scale"]["points"]
    px = ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5
    canvas, _ = frame(3, total, "Scale it from a listed size", f"--ref dim:long_leg: the stated 200 mm spans {px:.0f} px along the long leg.", CREDIT)
    ruled = photo.copy()
    d = ImageDraw.Draw(ruled)
    d.line([(x0, y0 - 60), (x1, y1 - 60)], fill=RED, width=8)
    for x, yy in ((x0, y0), (x1, y1)):
        d.line([(x, yy - 90), (x, yy - 20)], fill=RED, width=8)
    d.text(((x0 + x1) / 2, (y0 + y1) / 2 - 80), f"200 mm (listed) = {px:.0f} px", font=big, fill=RED, anchor="mb",
           stroke_width=6, stroke_fill="white")
    paste(canvas, ruled, body)
    steps.append([canvas])

    # 4. Measure the other sizes back.
    canvas, draw = frame(4, total, "Measure the rest back", "The other stated sizes, read off the photo, must agree. The holes and strut come from the photo alone.", CREDIT)
    ann = photo.copy()
    d = ImageDraw.Draw(ann)
    (_, sy0), (_, sy1) = BENCH["checks"]["short_leg"]
    d.line([(40, sy0), (40, sy1)], fill=RED, width=8)
    for yy in (sy0, sy1):
        d.line([(20, yy), (60, yy)], fill=RED, width=8)
    d.text((60, (sy0 + sy1) / 2 + 160), f"{dims['short_leg_measured']['mm']:.1f}", font=big, fill=RED, anchor="lm",
           stroke_width=6, stroke_fill="white")
    a, b = BENCH["checks"]["width"]
    d.line([tuple(a), tuple(b)], fill=YELLOW, width=8)
    d.text((b[0] + 20, b[1] - 10), f"{dims['width_measured']['mm']:.1f}", font=big, fill=(200, 150, 0), anchor="lm",
           stroke_width=6, stroke_fill="white")
    # Each hole is measured along its leg; it shows on the leg's side face, drawn where it shows.
    for name, across in (("hole_wall_1", 150), ("hole_wall_2", 148), ("hole_shelf_1", 208),
                         ("hole_shelf_2", 208), ("hole_shelf_3", 192)):
        (hx0, hy0), (hx1, hy1) = BENCH["measured"][name]
        cx, cy = (hx1, across) if hy0 == hy1 else (across, hy1)
        d.ellipse([cx - 40, cy - 40, cx + 40, cy + 40], outline=BLUE, width=8)
    paste(canvas, ann, (48, HEAD + 16, 690, H - 56))
    rows = [("", "stated", "photo", "")] + [
        (name.replace("_", " "), f"{dims[name]['mm']:g} ± {dims[name]['tolerance_mm']:g}",
         f"{dims[name + '_measured']['mm']:.1f} ± {dims[name + '_measured']['tolerance_mm']:.1f}",
         "agrees" if abs(dims[name]["mm"] - dims[name + "_measured"]["mm"])
         <= dims[name]["tolerance_mm"] + dims[name + "_measured"]["tolerance_mm"] else "OFF")
        for name in CHECKS
    ]
    y = table(draw, 720, HEAD + 40, [0, 150, 300, 450], rows, [INK, RED, (200, 150, 0), INK])
    draw.text((720, y + 20), "holes: 29 mm from the corner on both legs", font=font(19), fill=BLUE)
    draw.text((720, y + 54), "bore: assumed 4.5 mm, seen edge-on", font=font(19), fill=GREY)
    draw.text((720, y + 100), "The photo pins the short leg tighter than", font=font(19), fill=INK)
    draw.text((720, y + 128), "\"12 cm\" does, so the model uses 127 mm.", font=font(19), fill=INK)
    steps.append([canvas])

    # 5. Outline, as a mask: the window between legs and strut stays open.
    canvas, _ = frame(5, total, "Mask the outline", "Legs and strut on the top plane. The window between them stays open, so it is a mask.", CREDIT)
    mask = Image.open(job / "top_mask.png").convert("L")
    tint = Image.new("RGB", photo.size, YELLOW)
    masked = Image.composite(Image.blend(photo, tint, 0.55), photo, mask)
    paste(canvas, masked, body)
    steps.append([canvas])

    # 6. Model (animated).
    code = [
        'd = params["dims"]',
        "# the photo is tighter than \"12 cm\":",
        'short_leg = d["short_leg_measured"]',
        "# the L, with its bend, on its side:",
        'bend = d["bend_radius"]',
        "# strut on the bed; teardrop holes:",
        'bore = d["hole_bore"] / 2',
    ]
    animated = []
    for path in turn:
        canvas, draw = frame(6, total, "Model it from the spec", "A Blender script reads params[\"dims\"]: listed, measured or assumed, never its own.")
        y = HEAD + 90
        for line in code:
            draw.text((60, y), line, font=font(19, mono=True), fill=GREY if line.startswith("#") else INK)
            y += 36
        paste(canvas, open_upright(path), (640, HEAD + 6, W - 48, H - 40))
        animated.append(canvas)
    steps.append(animated)

    # 7. Likeness.
    [like] = report["likeness"]
    canvas, draw = frame(7, total, "Check it matches the photo", "The model is projected from above and laid over the photo. Red: photo only. Blue: model only.", CREDIT)
    paste(canvas, open_upright(Path(like["overlay"])), (48, HEAD + 16, 720, H - 56))
    draw.text((780, 290), f"{like['iou']:.0%}", font=font(120, bold=True), fill=GREEN, anchor="lm")
    draw.text((784, 380), "overlap with the photo", font=font(26), fill=INK, anchor="lm")
    draw.text((784, 430), f"photo {like['photo_mm'][0]:.1f} x {like['photo_mm'][1]:.1f} mm", font=font(22), fill=GREY, anchor="lm")
    draw.text((784, 464), f"model {like['model_mm'][0]:.1f} x {like['model_mm'][1]:.1f} mm", font=font(22), fill=GREY, anchor="lm")
    draw.text((784, 510), "The legs stand 20 mm off the table:", font=font(19), fill=GREY, anchor="lm")
    draw.text((784, 536), "close, not exact, is what the photo allows.", font=font(19), fill=GREY, anchor="lm")
    steps.append([canvas])

    # 8. Slice.
    m = report["slice_metrics"]
    canvas, draw = frame(8, total, "Sliced for the Bambu A1", "Printed on its side, no supports. Open the .3mf in Bambu Studio and print.")
    paste(canvas, open_upright(Path(report["plate_png"])), (48, HEAD + 16, 640, H - 56))
    stats = [(f"{m['layer_count']}", "layers"), (m["estimated_time"], "print time"), (f"{m['filament_g']:.1f} g", "PLA")]
    y = 230
    for value, label in stats:
        draw.text((700, y), value, font=font(64, bold=True), fill=INK, anchor="ls")
        draw.text((704, y + 32), label, font=font(22), fill=GREY, anchor="ls")
        y += 120
    draw.text((700, H - 120), "unknown: PLA at 4 mm will not carry what steel does", font=font(20), fill=RED)
    draw.text((700, H - 86), f"jobs/{SLUG}/slice/{SLUG}.3mf", font=font(18, mono=True), fill=GREEN)
    steps.append([canvas])
    return steps


def results_card(dims: dict) -> Image.Image:
    canvas = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(canvas)
    draw.text((W // 2, 110), "Listing in, printable part out", font=font(54, bold=True), fill=INK, anchor="mm")
    draw.text((W // 2, 170), "Scaled from one stated size, scored against the other three", font=font(26), fill=GREY, anchor="mm")
    head = font(24, bold=True)
    for x, label in ((220, ""), (560, "stated"), (860, "from the photo, mm")):
        draw.text((x, 260), label, font=head, fill=GREY, anchor="lm")
    stated = {"short_leg": "12 cm", "width": "2 cm", "thickness": "4 mm"}
    y = 320
    for name in CHECKS:
        got = dims[f"{name}_measured"]
        draw.line([(200, y - 30), (1100, y - 30)], fill=(230, 230, 230), width=2)
        draw.text((220, y), name.replace("_", " "), font=font(30), fill=INK, anchor="lm")
        draw.text((560, y), stated[name], font=font(30), fill=INK, anchor="lm")
        draw.text((860, y), f"{got['mm']:.1f} ± {got['tolerance_mm']:.1f}", font=font(30, bold=True), fill=GREEN, anchor="lm")
        y += 70
    draw.text((W // 2, H - 110), "github.com/mfranzon/print3d", font=font(26, bold=True), fill=GREEN, anchor="mm")
    draw.text((W // 2, H - 60), CREDIT, font=font(16), fill=GREY, anchor="mm")
    return canvas


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        report, job = run(work)
        # Flat and wide: from further out and higher up than the peg, so the L reads as an L.
        turn = turntable(Path(report["model"]["mesh"]), work / "turn", frames=36, reach=1.8, rise=1.6)
        steps = build_frames(report, job, turn)
        steps.append([results_card(json.loads((job / "spec.json").read_text())["dims"])])

        stills = OUT / NAME
        stills.mkdir(parents=True, exist_ok=True)
        names = ["listing", "quote", "scale", "measure", "outline", "model", "likeness", "slice", "results"]
        for n, (name, step) in enumerate(zip(names, steps), start=1):
            step[len(step) // 3].save(stills / f"{n:02d}-{name}.png", optimize=True)
        encode(steps, work, NAME)
    for path in [OUT / f"{NAME}.gif", OUT / f"{NAME}.mp4", *sorted((OUT / NAME).glob("*.png"))]:
        print(f"{path.relative_to(ROOT)}  {path.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
