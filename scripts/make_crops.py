#!/usr/bin/env python3
"""Cut figures, listings and display equations out of the English original.

The rectangles live in `crop_boxes.py`. Containment is judged per axis, because
the two axes fail differently:

  * vertically, a box edge that lands inside a line of type would ship the
    shaved half of that line, so the decision is taken for the whole line - a
    line either fits inside the box vertically or it is left out entirely;
  * horizontally, a glyph is simply in or out, and dropping the odd glyph that
    pokes past the edge (an italic overhang, a wide brace) is harmless.

Lines are found with the same baseline-banding the extractor uses, seeded with
each page's own dominant point size: the appendix is set smaller than the body of
the paper, and seeding it with the body size would strand every one of its glyphs
as an orphan and wreck the containment test.

The box is then tightened to the ink it keeps, padded a little, and clamped so
the pad never reaches into the neighbouring line. The text inside each crop is
recorded in the manifest, so a crop can be confirmed to hold the equation it
should hold without looking at the image.

Usage:
    python make_crops.py input.pdf outdir manifest.json --boxes crop_boxes.py [--dpi 300]
"""
from __future__ import annotations

import argparse
import collections
import importlib.util
import json
import os
import sys

import pdfplumber
import pymupdf
from PIL import Image as PILImage

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import extract_layout as E  # noqa: E402


def load_boxes(path):
    """Import the paper's crop_boxes module, which holds its rectangle tables.

    The rectangles are per paper, so they live with that paper's content rather
    than inside this script.
    """
    spec = importlib.util.spec_from_file_location("crop_boxes", path)
    if spec is None or spec.loader is None:
        raise SystemExit("cannot load crop boxes from %s" % path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def page_units(page, body):
    """Text lines plus each drawing and image, as the units a box may cut."""
    chars = list(page.chars)
    bands, small = E.build_bands(chars, body)
    orphans = E.attach_small(bands, small, body)
    lines = []
    for b in bands:
        lines.append(
            {"top": b["top"], "bottom": b["bottom"], "chars": [(c["x0"], c["top"], c["x1"], c["bottom"]) for c in b["chars"]]}
        )
    for c in orphans:
        lines.append({"top": c["top"], "bottom": c["bottom"], "chars": [(c["x0"], c["top"], c["x1"], c["bottom"])]})
    solids = []
    for group in (page.rects, page.lines, page.curves):
        for o in group:
            solids.append(
                (min(o["x0"], o["x1"]), min(o["top"], o["bottom"]), max(o["x0"], o["x1"]), max(o["top"], o["bottom"]))
            )
    for im in page.images:
        box = (im["x0"], im["top"], im["x1"], im["bottom"])
        # A scanned paper carries one bitmap per page, covering the whole sheet.
        # That is the page background, not an illustration: counting it as a unit
        # would make it "bleed into" every crop on the page. The scan is what the
        # crops are cut from, so the ink is measured from the bitmap instead.
        if (box[2] - box[0]) * (box[3] - box[1]) > 0.85 * page.width * page.height:
            continue
        solids.append(box)
    return lines, solids


def scanned_page(page):
    """True when the page is one full-sheet bitmap, i.e. a scan."""
    area = page.width * page.height
    return any((im["x1"] - im["x0"]) * (im["bottom"] - im["top"]) > 0.85 * area for im in page.images)


def bitmap_ink(doc, page_no, box, dpi, threshold=190):
    """Tight ink bounds (PDF points) of a rectangle, read off the rendered page.

    Vector ink and text boxes do not exist on a scan, so for those pages the
    rectangle is tightened against the dark pixels it actually contains. That
    also guarantees a crop is never tightened around a stray OCR box belonging to
    a neighbouring line.
    """
    zoom = dpi / 72.0
    clip = pymupdf.Rect(*box)
    pix = doc[page_no - 1].get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), clip=clip, colorspace=pymupdf.csGRAY)
    im = PILImage.frombytes("L", (pix.width, pix.height), pix.samples)
    mask = im.point(lambda v: 255 if v < threshold else 0)
    found = mask.getbbox()
    if found is None:
        return None
    left, top, right, bottom = found
    return (
        box[0] + left / zoom,
        box[1] + top / zoom,
        box[0] + right / zoom,
        box[1] + bottom / zoom,
    )


def split_page(lines, solids, box):
    """Return the ink inside the box, and the units the box must not encroach on.

    A band here is a baseline band, which on this paper can span both columns.
    Only the part of a rejected band that shares the box's horizontal band can
    ever bleed into the crop, so only that part is recorded - otherwise every
    line of the opposite column looks like a collision.
    """
    x0, y0, x1, y1 = box
    inside, others = [], []
    for ln in lines:
        fits_v = ln["top"] >= y0 - 0.5 and ln["bottom"] <= y1 + 0.5
        kept = [(a, b, c, d) for (a, b, c, d) in ln["chars"] if a >= x0 - 0.5 and c <= x1 + 0.5]
        near = [(a, b, c, d) for (a, b, c, d) in ln["chars"] if c >= x0 - 8 and a <= x1 + 8]
        if fits_v and kept:
            inside.extend(kept)
        elif near:
            others.append((min(v[0] for v in near), ln["top"], max(v[2] for v in near), ln["bottom"]))
    for it in solids:
        if it[0] >= x0 - 0.5 and it[2] <= x1 + 0.5 and it[1] >= y0 - 0.5 and it[3] <= y1 + 0.5:
            inside.append(it)
        else:
            others.append(it)
    return inside, others


def h_overlap(a, b):
    return a[0] < b[2] and b[0] < a[2]


def v_overlap(a, b):
    return a[1] < b[3] and b[1] < a[3]


def crop_box(inside, others, box, pad, grow):
    """Ink bounds padded by pad+grow, then clamped clear of neighbouring ink."""
    x0, y0, x1, y1 = box
    ink = (
        min(it[0] for it in inside),
        min(it[1] for it in inside),
        max(it[2] for it in inside),
        max(it[3] for it in inside),
    )
    cx0 = max(x0, ink[0] - pad - grow)
    cy0 = max(y0, ink[1] - pad - grow)
    cx1 = min(x1, ink[2] + pad + grow)
    cy1 = min(y1, ink[3] + pad + grow)
    for it in others:
        if not (it[0] < cx1 and cx0 < it[2] and it[1] < cy1 and cy0 < it[3]):
            continue
        if h_overlap(it, ink):
            if it[1] < ink[1] and it[3] <= ink[1] + 0.5:
                cy0 = max(cy0, min(it[3] + 0.6, ink[1]))
            elif it[3] > ink[3] and it[1] >= ink[3] - 0.5:
                cy1 = min(cy1, max(it[1] - 0.6, ink[3]))
        if v_overlap(it, ink):
            if it[2] <= ink[0] + 0.5:
                cx0 = max(cx0, min(it[2] + 0.6, ink[0]))
            elif it[0] >= ink[2] - 0.5:
                cx1 = min(cx1, max(it[0] - 0.6, ink[2]))
    return (cx0, cy0, cx1, cy1), ink


def leaks(others, crop):
    return [
        it
        for it in others
        if it[0] < crop[2] - 0.2 and crop[0] + 0.2 < it[2] and it[1] < crop[3] - 0.2 and crop[1] + 0.2 < it[3]
    ]


def box_text(page, box):
    x0, y0, x1, y1 = box
    chars = [
        c for c in page.chars if c["x0"] >= x0 - 0.5 and c["x1"] <= x1 + 0.5 and c["top"] >= y0 - 0.5 and c["bottom"] <= y1 + 0.5
    ]
    chars.sort(key=lambda c: (round(c["top"], 1), c["x0"]))
    return "".join(c["text"] for c in chars)


def ink_fraction(path):
    from PIL import Image

    im = Image.open(path).convert("L")
    hist = im.histogram()
    return 1.0 - (hist[255] / float(sum(hist)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("outdir")
    ap.add_argument("manifest")
    ap.add_argument("--boxes", required=True, help="path to the paper's crop_boxes.py")
    ap.add_argument("--dpi", type=int, default=300)
    ap.add_argument("--report", action="store_true")
    args = ap.parse_args()

    os.makedirs(args.outdir, exist_ok=True)
    boxes = load_boxes(args.boxes)
    FIGURES, LISTINGS, EQUATIONS = boxes.FIGURES, boxes.LISTINGS, boxes.EQUATIONS
    PAD, GROW = boxes.PAD, boxes.GROW
    EXACT_CROPS = getattr(boxes, "EXACT_CROPS", {})
    for old in os.listdir(args.outdir):
        if old.endswith(".png"):
            os.remove(os.path.join(args.outdir, old))
    doc = pymupdf.open(args.pdf)
    manifest = {"source": args.pdf, "dpi": args.dpi, "crops": []}
    problems = []
    zoom = args.dpi / 72.0
    with pdfplumber.open(args.pdf) as pdf:
        all_chars = [list(p.chars) for p in pdf.pages]
        sizes = collections.Counter(round(c["size"], 1) for chars in all_chars for c in chars)
        # A scan has no character layer at all, so the size histogram is empty.
        # The bitmap path further down handles those pages; the body size only
        # feeds page_units(), which they never reach.
        global_body = sizes.most_common(1)[0][0] if sizes else 9.6
        units_by_page = {}
        scans = {}
        for page, chars in zip(pdf.pages, all_chars):
            page_sizes = collections.Counter(round(c["size"], 1) for c in chars)
            page_size = page_sizes.most_common(1)[0][0] if page_sizes else global_body
            units_by_page[page.page_number] = page_units(page, max(page_size, global_body * 0.75))
            scans[page.page_number] = scanned_page(page)
        for kind_name, table in (("figure", FIGURES), ("listing", LISTINGS), ("equation", EQUATIONS)):
            for name, page_no, box in table:
                page = pdf.pages[page_no - 1]
                lines, solids = units_by_page[page_no]
                if name in EXACT_CROPS:
                    # Some PDF illustrations are split into several image
                    # objects whose transparent bounding boxes overlap headers,
                    # captions or other decorations. The declared rectangle is
                    # the visible figure boundary, so render it as-is and skip
                    # tightening against unrelated object bounds.
                    tight = tuple(EXACT_CROPS[name])
                    ink = tight
                    leak = []
                elif scans[page_no]:
                    # Scanned page: there is no vector ink and no reliable text
                    # box to tighten against, so the bitmap decides the bounds.
                    ink = bitmap_ink(doc, page_no, box, args.dpi)
                    if ink is None:
                        problems.append("%s: no dark pixels inside %s" % (name, box))
                        continue
                    tight = (
                        max(box[0], ink[0] - PAD),
                        max(box[1], ink[1] - PAD),
                        min(box[2], ink[2] + PAD),
                        min(box[3], ink[3] + PAD),
                    )
                    leak = []
                else:
                    inside, others = split_page(lines, solids, box)
                    if not inside:
                        # A page built from bitmap tiles - a translation saved as
                        # screenshots, say - has no vector ink anywhere, so a box
                        # that holds no text would report "no ink" even though the
                        # picture is right there. Fall back to the bitmap rather
                        # than dropping the crop.
                        ink = bitmap_ink(doc, page_no, box, args.dpi)
                        if ink is None:
                            problems.append("%s: no ink inside %s" % (name, box))
                            continue
                        tight = (
                            max(box[0], ink[0] - PAD),
                            max(box[1], ink[1] - PAD),
                            min(box[2], ink[2] + PAD),
                            min(box[3], ink[3] + PAD),
                        )
                        leak = []
                    else:
                        tight, ink = crop_box(inside, others, box, PAD, GROW)
                        leak = leaks(others, tight)
                if leak:
                    problems.append("%s: %d neighbouring item(s) bleed into the crop" % (name, len(leak)))
                path = os.path.join(args.outdir, name + ".png")
                pix = doc[page_no - 1].get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), clip=pymupdf.Rect(*tight))
                pix.save(path)
                frac = ink_fraction(path)
                if frac < 0.004:
                    problems.append("%s: crop looks blank (ink fraction %.4f)" % (name, frac))
                manifest["crops"].append(
                    {
                        "name": name,
                        "page": page_no,
                        "kind": kind_name,
                        "box": [round(v, 1) for v in tight],
                        "ink": [round(v, 1) for v in ink],
                        "px": [pix.width, pix.height],
                        "fill": round(frac, 4),
                        "text": box_text(page, tight),
                    }
                )
    doc.close()
    with open(args.manifest, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=1)
    print("wrote %d crops to %s" % (len(manifest["crops"]), args.outdir))
    for p in problems:
        print("PROBLEM: " + p)
    if args.report:
        for c in manifest["crops"]:
            print("%-8s p%-3d %-8s %s" % (c["name"], c["page"], c["kind"], c["text"][:95]))


if __name__ == "__main__":
    main()
