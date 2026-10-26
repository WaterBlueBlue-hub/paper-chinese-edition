#!/usr/bin/env python3
"""Typeset the Chinese edition of a paper in the layout of the original PDF.

Page geometry is taken from the source paper rather than invented: Letter paper,
72pt left and 86pt right margins, a 19pt gutter, 217.5pt columns, 9pt body type
and a centred running head. Cropped equations and figures are placed at their
native point size, so they appear exactly as they do in the original.

A figure wider than one column goes into a full-width frame at the top of its own
page, with the two columns resuming underneath - what the original does with its
wide plates. That needs one page template per plate, each with a wide frame whose
height is measured from the flowables it holds. The front matter gets the same
treatment: it sits full width at the top of page one, and the two columns below
start flush against it.

Content lives in content/<PAPER>/part*.py as a BLOCKS list; English is referenced
by segment id so the translation stays traceable to the extracted original.

Checks after typesetting: referenced images exist, the finished PDF's text is
extracted back and counted against the source, and every character used must
exist in one of the embedded faces.

Usage:
    python build_pdf.py segments.json content_dir out.pdf --figs figs_dir [--dpi 300]
"""
from __future__ import annotations

import argparse
import glob
import importlib.util
import json
import os
import re

import pymupdf
from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    Image,
    KeepTogether,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
)

SONG = ("Song", "C:/Windows/Fonts/simsun.ttc", 0)
HEI = ("Hei", "C:/Windows/Fonts/simhei.ttf", 0)
SYM = ("Sym", "C:/Windows/Fonts/seguisym.ttf", 0)

# Geometry defaults copied from the PBD 2007 source paper. A second paper rarely
# shares those margins, so every one of them can be overridden on the command
# line and set_geometry() recomputes the derived values from whatever it is given.
PAGE_W, PAGE_H = letter  # 612 x 792


def set_page_size(spec):
    """Adopt the source paper's sheet size: "letter", "a4", or "WxH" in points.

    The text block is set by the margins, so the sheet size only decides how much
    white space surrounds it - but a Eurographics paper on A4 and the same page on
    Letter do not look alike, and the skill promises the original trim size.
    """
    global PAGE_W, PAGE_H
    named = {"letter": (612.0, 792.0), "a4": (595.276, 841.890), "a3": (841.890, 1190.551)}
    key = (spec or "letter").strip().lower()
    if key in named:
        PAGE_W, PAGE_H = named[key]
        return
    try:
        w, h = (float(v) for v in key.replace("*", "x").split("x"))
    except ValueError:
        raise SystemExit("unknown page size: %s (use letter, a4, or WxH in points)" % spec)
    PAGE_W, PAGE_H = w, h
COLUMNS = 2
MARGIN_L = 72.0
MARGIN_R = 86.0
FULL_W = PAGE_W - MARGIN_L - MARGIN_R  # 454
GUTTER = 19.0
COL_W = (FULL_W - GUTTER) / 2.0  # 217.5
COL_X_R = MARGIN_L + COL_W + GUTTER
TEXT_TOP = PAGE_H - 84.0
COL_BOTTOM = PAGE_H - 696.0
WIDE_GAP = 12.0

RUNNING_HEAD = "基于位置的动力学 · PBD 2007 中译"
DOC_TITLE = "基于位置的动力学（PBD 2007 中译）"
DOC_AUTHOR = "Matthias Müller, Bruno Heidelberger, Marcus Hennix, John Ratcliff"
DOC_SUBJECT = "Workshop in Virtual Reality Interactions and Physical Simulation (VRIPHYS 2006) 中译"


def set_geometry(left=None, right=None, gutter=None, top=None, bottom=None, columns=None):
    """Adopt the paper's own margins; `top`/`bottom` are distances from the page
    top to the first and last line of type, in points."""
    global MARGIN_L, MARGIN_R, FULL_W, GUTTER, COL_W, COL_X_R, TEXT_TOP, COL_BOTTOM, COLUMNS
    if columns:
        COLUMNS = columns
    if left is not None:
        MARGIN_L = left
    if right is not None:
        MARGIN_R = right
    if gutter is not None and COLUMNS > 1:
        GUTTER = gutter
    FULL_W = PAGE_W - MARGIN_L - MARGIN_R
    if COLUMNS == 1:
        GUTTER = 0.0
        COL_W = FULL_W
    else:
        COL_W = (FULL_W - GUTTER) / 2.0
    COL_X_R = MARGIN_L + COL_W + GUTTER
    if top is not None:
        TEXT_TOP = PAGE_H - top
    if bottom is not None:
        COL_BOTTOM = PAGE_H - bottom

SUBSTITUTIONS = {
    "\ufb00": "ff",
    "\ufb01": "fi",
    "\ufb02": "fl",
    "\ufb03": "ffi",
    "\ufb04": "ffl",
    "\u2019": "'",
    "\u2217": "*",
}

SUPERSCRIPTS = {
    "\u2070": "0", "\u00b9": "1", "\u00b2": "2", "\u00b3": "3", "\u2074": "4",
    "\u2075": "5", "\u2076": "6", "\u2077": "7", "\u2078": "8", "\u2079": "9",
    "\u207a": "+", "\u207b": "-", "\u207f": "n", "\u02e2": "s", "\u2071": "i",
    "\u1d40": "T", "\u1d34": "H",
}
SUBSCRIPTS = {
    "\u2080": "0", "\u2081": "1", "\u2082": "2", "\u2083": "3", "\u2084": "4",
    "\u2085": "5", "\u2086": "6", "\u2087": "7", "\u2088": "8", "\u2089": "9",
    "\u208a": "+", "\u208b": "-",
}

_SONG_FONT = None


def song_font():
    global _SONG_FONT
    if _SONG_FONT is None:
        _SONG_FONT = pymupdf.Font(fontfile=SONG[1])
    return _SONG_FONT


def register_fonts():
    for name, path, idx in (SONG, HEI, SYM):
        pdfmetrics.registerFont(TTFont(name, path, subfontIndex=idx))


def styles():
    s = {}
    s["h1"] = ParagraphStyle("h1", fontName="Hei", fontSize=16, leading=23, alignment=TA_CENTER, spaceAfter=5)
    s["h1en"] = ParagraphStyle(
        "h1en", fontName="Song", fontSize=10, leading=14.5, alignment=TA_CENTER,
        textColor=colors.HexColor("#555555"), spaceAfter=9,
    )
    s["byline"] = ParagraphStyle("byline", fontName="Song", fontSize=9, leading=13, alignment=TA_CENTER, spaceAfter=2)
    s["source"] = ParagraphStyle(
        "source", fontName="Song", fontSize=8, leading=11.5, alignment=TA_CENTER,
        textColor=colors.HexColor("#666666"), spaceAfter=6,
    )
    s["h2"] = ParagraphStyle("h2", fontName="Hei", fontSize=10.5, leading=15, spaceBefore=9, spaceAfter=3.5)
    s["h3"] = ParagraphStyle("h3", fontName="Hei", fontSize=9.5, leading=13.5, spaceBefore=7, spaceAfter=2.5)
    s["body"] = ParagraphStyle(
        "body", fontName="Song", fontSize=9, leading=12.8, alignment=TA_JUSTIFY, firstLineIndent=18, spaceAfter=2, wordWrap="CJK"
    )
    s["bullet"] = ParagraphStyle(
        "bullet", fontName="Song", fontSize=9, leading=12.4, alignment=TA_JUSTIFY,
        leftIndent=14, bulletIndent=3, spaceAfter=1.5, wordWrap="CJK",
    )
    s["note"] = ParagraphStyle(
        "note", fontName="Song", fontSize=8.4, leading=12, alignment=TA_JUSTIFY,
        leftIndent=10, rightIndent=6, textColor=colors.HexColor("#333333"), spaceAfter=4, wordWrap="CJK",
    )
    s["caption"] = ParagraphStyle(
        "caption", fontName="Song", fontSize=8, leading=11.5, alignment=TA_CENTER,
        textColor=colors.HexColor("#222222"), spaceBefore=2, spaceAfter=6,
    )
    s["eqnote"] = ParagraphStyle(
        "eqnote", fontName="Song", fontSize=7.6, leading=11, alignment=TA_LEFT,
        textColor=colors.HexColor("#444444"), spaceBefore=1, spaceAfter=5,
    )
    s["ref"] = ParagraphStyle("ref", fontName="Song", fontSize=7.8, leading=11.2, leftIndent=16, firstLineIndent=-16, spaceAfter=2)
    s["algzh"] = ParagraphStyle("algzh", fontName="Song", fontSize=8.2, leading=12.4, leftIndent=20, firstLineIndent=-20, spaceAfter=0.5)
    s["alghead"] = ParagraphStyle("alghead", fontName="Hei", fontSize=8.6, leading=12.5, spaceBefore=3, spaceAfter=2.5)
    return s


def normalize(text):
    for a, b in SUBSTITUTIONS.items():
        text = text.replace(a, b)
    return text


def _esc(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _with_fallback(escaped):
    """Wrap glyphs the body face lacks in the embedded symbol face."""
    font = song_font()
    out = []
    inside = False
    for ch in escaped:
        need = not font.has_glyph(ord(ch))
        if need and not inside:
            out.append('<font name="Sym">')
            inside = True
        elif not need and inside:
            out.append("</font>")
            inside = False
        out.append(ch)
    if inside:
        out.append("</font>")
    return "".join(out)


def _script(tag, content):
    """One super/subscript run, escaped and glyph-checked like the body text.

    The fallback has to be applied inside the element as well: the body face has
    no U+2212, so a minus sign in an exponent would otherwise come out as an
    empty box - text inside <sup>/<sub> used to bypass the check entirely.
    """
    return "<%s>%s</%s>" % (tag, _with_fallback(_esc(normalize(content))), tag)


def render(text):
    """Escape and enrich one string for use inside a Paragraph."""
    text = normalize(text)
    # The superscript tag has to be written the short way round: the split below
    # recognises <sup>/<sub>, and anything else is escaped and printed literally,
    # which is how "x^{2}" used to ship as "x<super>2</super>".
    text = re.sub(r"\^\{([^}]*)\}", lambda m: _script("sup", m.group(1)), text)
    text = re.sub(r"_\{([^}]*)\}", lambda m: _script("sub", m.group(1)), text)
    parts = re.split(r"(<su[bp]>.*?</su[bp]>)", text)
    out = []
    for part in parts:
        if part.startswith(("<sup>", "<sub>")):
            out.append(part)
            continue
        buf = []
        for ch in part:
            if ch in SUPERSCRIPTS:
                buf.append("<super>%s</super>" % _esc(SUPERSCRIPTS[ch]))
            elif ch in SUBSCRIPTS:
                buf.append("<sub>%s</sub>" % _esc(SUBSCRIPTS[ch]))
            else:
                buf.append(_with_fallback(_esc(ch)))
        out.append("".join(buf))
    return "".join(out)


def plain(text):
    text = normalize(text)
    for ch, rep in list(SUPERSCRIPTS.items()) + list(SUBSCRIPTS.items()):
        text = text.replace(ch, rep)
    return re.sub(r"<[^>]+>", "", text)


def load_blocks(content_dir):
    blocks = []
    parts = sorted(glob.glob(os.path.join(content_dir, "part*.py")))
    for path in parts:
        spec = importlib.util.spec_from_file_location(os.path.basename(path)[:-3], path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        blocks.extend(mod.BLOCKS)
    return blocks, parts


def join_segments(ids, segs):
    out = ""
    for sid in ids:
        piece = segs[sid]["text"].strip()
        if not piece:
            continue
        if out.endswith("-") and piece[:1].islower():
            out = out[:-1] + piece
        elif out:
            out += " " + piece
        else:
            out = piece
    return out


def zh_of(block, segs, key="zh"):
    if block.get(key):
        return block[key]
    en = block.get("en")
    if isinstance(en, list):
        return join_segments(en, segs)
    return en or ""


def crop_size(path, dpi):
    iw, ih = PILImage.open(path).size
    return iw * 72.0 / dpi, ih * 72.0 / dpi


def image_flowable(path, max_w, dpi):
    w, h = crop_size(path, dpi)
    scale = min(1.0, max_w / w)
    img = Image(path, width=w * scale, height=h * scale)
    img.hAlign = "CENTER"
    return img


def measure(flowables, width):
    total = 0.0
    for f in flowables:
        if isinstance(f, Paragraph):
            _, h = f.wrap(width, 10000)
            total += h + f.style.spaceBefore + f.style.spaceAfter
        elif isinstance(f, Image):
            total += f.drawHeight
        elif isinstance(f, Spacer):
            total += f.height
        elif isinstance(f, KeepTogether):
            # A plate in the front matter arrives as a KeepTogether, which cannot
            # be wrapped without a canvas; measure what it holds instead.
            total += measure(f._content, width)
        else:
            _, h = f.wrap(width, 10000)
            total += h
    return total


def flowables_for(b, segs, st, figs_dir, dpi, col_w):
    kind = b["t"]
    out = []
    if kind == "h1":
        out.append(Paragraph(render(b["zh"]), st["h1"]))
        if b.get("en"):
            out.append(Paragraph(render(b["en"]), st["h1en"]))
    elif kind == "byline":
        out.append(Paragraph(render(b["zh"]), st["byline"]))
    elif kind == "source":
        out.append(Paragraph(render(b["zh"]), st["source"]))
    elif kind in ("h2", "h3"):
        out.append(Paragraph(render(zh_of(b, segs)), st[kind]))
    elif kind == "p":
        out.append(Paragraph(render(zh_of(b, segs)), st["body"]))
    elif kind == "note":
        out.append(Paragraph(render(zh_of(b, segs)), st["note"]))
    elif kind == "ul":
        for item in b["items"]:
            out.append(Paragraph(render(zh_of(item, segs)), st["bullet"], bulletText="•"))
        out.append(Spacer(1, 3))
    elif kind == "eq":
        out.append(image_flowable(os.path.join(figs_dir, b["crop"] + ".png"), col_w, dpi))
        if b.get("zh"):
            out.append(Paragraph(render(b["zh"]), st["eqnote"]))
        out.append(Spacer(1, 5))
    elif kind == "fig":
        out.append(
            KeepTogether(
                [
                    image_flowable(os.path.join(figs_dir, b["crop"] + ".png"), col_w, dpi),
                    Paragraph(render(zh_of(b, segs)), st["caption"]),
                ]
            )
        )
    elif kind == "alg":
        block = [image_flowable(os.path.join(figs_dir, b["crop"] + ".png"), col_w, dpi)]
        if b.get("zh_head"):
            block.append(Paragraph(render(b["zh_head"]), st["alghead"]))
        for line in b.get("zh_lines", []):
            block.append(Paragraph(render(line), st["algzh"]))
        out.append(KeepTogether(block))
        out.append(Spacer(1, 5))
    elif kind == "refs":
        for item in b["items"]:
            out.append(Paragraph(render(item), st["ref"]))
    elif kind == "pagebreak":
        out.append(PageBreak())
    else:
        raise SystemExit("unknown block type: %s" % kind)
    return out


def collect_text(blocks):
    chunks = []
    for b in blocks:
        v = b.get("zh")
        if isinstance(v, str):
            chunks.append(v)
        if isinstance(b.get("zh_head"), str):
            chunks.append(b["zh_head"])
        chunks.extend(b.get("zh_lines", []))
        for item in b.get("items", []):
            chunks.append(item["zh"] if isinstance(item, dict) else item)
    return "".join(chunks)


def decorate(canvas, doc):
    canvas.saveState()
    if doc.page > 1:
        canvas.setFont("Song", 8)
        canvas.setFillColor(colors.HexColor("#777777"))
        canvas.drawCentredString(PAGE_W / 2.0, PAGE_H - 72.0, RUNNING_HEAD)
    canvas.setFont("Song", 8.5)
    canvas.setFillColor(colors.HexColor("#555555"))
    canvas.drawCentredString(PAGE_W / 2.0, 58.0, str(doc.page))
    canvas.restoreState()


def column_frames(top, height):
    if COLUMNS == 1:
        # A single-column paper keeps one full-measure frame; the two-column
        # machinery below is what most journals use, not what all of them do.
        return [
            Frame(MARGIN_L, top, FULL_W, height, id="L", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
        ]
    return [
        Frame(MARGIN_L, top, COL_W, height, id="L", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0),
        Frame(COL_X_R, top, COL_W, height, id="R", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0),
    ]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("segments")
    ap.add_argument("content_dir")
    ap.add_argument("out")
    ap.add_argument("--figs", required=True)
    ap.add_argument("--dpi", type=int, default=300)
    ap.add_argument("--margin-l", type=float, default=None, help="left margin, pt")
    ap.add_argument("--margin-r", type=float, default=None, help="right margin, pt")
    ap.add_argument("--gutter", type=float, default=None, help="column gutter, pt")
    ap.add_argument("--top", type=float, default=None, help="page top to first line of type, pt")
    ap.add_argument("--bottom", type=float, default=None, help="page top to last line of type, pt")
    ap.add_argument("--columns", type=int, default=None, choices=(1, 2), help="1 for a single-column paper")
    ap.add_argument("--page-size", default=None,
                    help="sheet size: 'letter' (default), 'a4', or 'WxH' in points")
    ap.add_argument("--running-head", default=None)
    ap.add_argument("--title", default=None)
    ap.add_argument("--author", default=None)
    ap.add_argument("--subject", default=None)
    args = ap.parse_args()

    global RUNNING_HEAD, DOC_TITLE, DOC_AUTHOR, DOC_SUBJECT
    if args.page_size:
        set_page_size(args.page_size)
    set_geometry(args.margin_l, args.margin_r, args.gutter, args.top, args.bottom, args.columns)
    if args.running_head:
        RUNNING_HEAD = args.running_head
    if args.title:
        DOC_TITLE = args.title
    if args.author:
        DOC_AUTHOR = args.author
    if args.subject:
        DOC_SUBJECT = args.subject

    with open(args.segments, encoding="utf-8") as fh:
        data = json.load(fh)
    segs = {s["id"]: s for s in data["segments"]}
    blocks, parts = load_blocks(args.content_dir)
    register_fonts()
    st = styles()
    print("loaded %d blocks from %d part file(s)" % (len(blocks), len(parts)))

    used = set()
    for b in blocks:
        en = b.get("en")
        if isinstance(en, list):
            used.update(en)
        for item in b.get("items", []):
            if isinstance(item, dict) and isinstance(item.get("en"), list):
                used.update(item["en"])
    unknown = sorted(i for i in used if i not in segs)
    if unknown:
        print("WARNING: unknown segment ids referenced: %s" % ", ".join(unknown))
    absent = sorted(
        {b["crop"] for b in blocks if b.get("crop") and not os.path.exists(os.path.join(args.figs, b["crop"] + ".png"))}
    )
    if absent:
        print("WARNING: missing crop images: %s" % ", ".join(absent))

    # Front matter runs full width at the top of page one, as in the original.
    front, body = [], []
    target = front
    for b in blocks:
        target.append(b)
        if b["t"] == "note" and target is front:
            target = body
    front_flow = []
    for b in front:
        # The front matter sits full width, so its art may use the full measure as
        # well: the first page of a paper often carries a wide plate above the
        # abstract, and shrinking it to a column would misreport the original.
        front_flow.extend(flowables_for(b, segs, st, args.figs, args.dpi, FULL_W))
    front_h = measure(front_flow, FULL_W) + 6
    if front_h > TEXT_TOP - COL_BOTTOM - 120:
        print("WARNING: front matter is %d pt tall" % front_h)

    # The body is a sequence of text runs and full-width plates. Plates that sit
    # back to back are stacked on one page: a page carrying a single picture and
    # nothing else wastes a sheet and reads badly. A stack is only allowed while
    # it still leaves room for the columns underneath.
    PLATE_LIMIT = (TEXT_TOP - COL_BOTTOM) * 0.95
    plan = []  # each entry: {"plate": [flowables] or None, "text": [flowables]}
    run = []
    for b in body:
        wide = False
        if b["t"] == "fig":
            w, _ = crop_size(os.path.join(args.figs, b["crop"] + ".png"), args.dpi)
            wide = w > COL_W * 1.04
        if wide:
            flow = [
                image_flowable(os.path.join(args.figs, b["crop"] + ".png"), FULL_W, args.dpi),
                Paragraph(render(zh_of(b, segs)), st["caption"]),
            ]
            if plan and plan[-1]["plate"] is not None and not run:
                merged = plan[-1]["plate"] + flow
                if measure(merged, FULL_W) + 4 <= PLATE_LIMIT:
                    plan[-1]["plate"] = merged
                    continue
            plan.append({"plate": flow, "text": run})
            run = []
            continue
        run.extend(flowables_for(b, segs, st, args.figs, args.dpi, COL_W))
    plan.append({"plate": None, "text": run})

    templates = [
        PageTemplate(
            id="title",
            frames=[
                Frame(MARGIN_L, TEXT_TOP - front_h, FULL_W, front_h, id="F", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
            ]
            + column_frames(COL_BOTTOM, TEXT_TOP - front_h - WIDE_GAP - COL_BOTTOM),
            onPage=decorate,
        )
    ]
    for idx, entry in enumerate(plan):
        if entry["plate"] is None:
            continue
        h = measure(entry["plate"], FULL_W) + 4
        frames = [
            Frame(MARGIN_L, TEXT_TOP - h, FULL_W, h, id="W%d" % idx, leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
        ]
        frames.extend(column_frames(COL_BOTTOM, TEXT_TOP - h - WIDE_GAP - COL_BOTTOM))
        templates.append(PageTemplate(id="span%d" % idx, frames=frames, onPage=decorate))
    templates.append(PageTemplate(id="two", frames=column_frames(COL_BOTTOM, TEXT_TOP - COL_BOTTOM), onPage=decorate))

    plates = [e for e in plan if e["plate"] is not None]
    story = list(front_flow)
    story.append(NextPageTemplate("two"))
    for idx, entry in enumerate(plan):
        # The text stored with an entry is what precedes that plate, so it has to
        # be emitted before the break that moves the plate onto its own page.
        story.extend(entry["text"])
        if entry["plate"] is not None:
            story.append(NextPageTemplate("span%d" % idx))
            story.append(PageBreak())
            story.extend(entry["plate"])
            story.append(NextPageTemplate("two"))

    # A PDF viewer can hold the previous edition open, and Windows then refuses to
    # truncate it, so the new edition is built beside it and swapped in.
    tmp_path = args.out + ".part"
    doc = BaseDocTemplate(
        tmp_path,
        pagesize=(PAGE_W, PAGE_H),
        leftMargin=MARGIN_L,
        rightMargin=MARGIN_R,
        topMargin=72,
        bottomMargin=58,
        title=DOC_TITLE,
        author=DOC_AUTHOR,
        subject=DOC_SUBJECT,
    )
    doc.addPageTemplates(templates)
    doc.build(story)
    try:
        os.replace(tmp_path, args.out)
    except OSError:
        if os.path.exists(args.out):
            os.remove(args.out)
        os.replace(tmp_path, args.out)
    print("wrote %s" % args.out)

    src = re.sub(r"\s+", "", plain(collect_text(blocks)))
    pdf = pymupdf.open(args.out)
    pages = pdf.page_count
    pdf_text = re.sub(r"\s+", "", "".join(p.get_text() for p in pdf))
    pdf.close()
    print("pages: %d, full-width plates: %d" % (pages, len(plates)))
    print("chars: source %d, pdf %d, difference %+d" % (len(src), len(pdf_text), len(pdf_text) - len(src)))
    fonts = [pymupdf.Font(fontfile=SONG[1]), pymupdf.Font(fontfile=HEI[1]), pymupdf.Font(fontfile=SYM[1])]
    missing = sorted(ch for ch in set(src) if not any(f.has_glyph(ord(ch)) for f in fonts))
    if missing:
        print("MISSING GLYPHS: %s" % "".join(missing))
    else:
        print("glyph coverage: every character used is present in the embedded fonts")


if __name__ == "__main__":
    main()
