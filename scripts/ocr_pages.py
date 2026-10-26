#!/usr/bin/env python3
"""Read the pages of a PDF that carries no text layer, for papers that exist only as images.

`extract_layout.py` needs a text layer: it builds segment ids from the characters
on the page. A scan with no OCR layer, or a translation saved as screenshots, has
none - and without one there are no segments to reference from the translation.
This script fills that gap for the translation side only. It runs an OCR engine
over each rendered page and writes the text boxes out as JSON in PDF points, so
paragraphs can be reassembled in reading order and display equations located by
the equation numbers that sit beside them.

It is deliberately *not* a fourth pipeline stage:

  * equations and figures still have to be cropped from the page images, because
    OCR mangling of mathematics is expected and not recoverable;
  * the body text has to be proof-read against those same images before it is
    trusted, so the OCR output is an aid, never a source of record.

Usage:
    python ocr_pages.py input.pdf out.json [--dpi 300]

Requires `rapidocr-onnxruntime` and `numpy` (see references/pitfalls.md for how
the environment is put together).
"""
from __future__ import annotations

import argparse
import json
import time

import numpy as np
import pymupdf
from rapidocr_onnxruntime import RapidOCR


def page_boxes(engine, doc, page_no, dpi):
    """OCR one page; boxes come back in pixels, converted here to PDF points."""
    zoom = dpi / 72.0
    pix = doc[page_no - 1].get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), colorspace=pymupdf.csRGB)
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3)
    result, _ = engine(img)
    boxes = []
    for item in result or []:
        poly, text, score = item[0], item[1], item[2]
        xs = [p[0] / zoom for p in poly]
        ys = [p[1] / zoom for p in poly]
        boxes.append(
            {
                "text": text,
                "score": round(float(score), 3),
                "bbox": [round(min(xs), 1), round(min(ys), 1), round(max(xs), 1), round(max(ys), 1)],
            }
        )
    boxes.sort(key=lambda b: (round(b["bbox"][1], 1), b["bbox"][0]))
    return boxes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("out")
    ap.add_argument("--dpi", type=int, default=300)
    args = ap.parse_args()

    doc = pymupdf.open(args.pdf)
    engine = RapidOCR()
    data = {"source": args.pdf, "dpi": args.dpi, "pages": []}
    t0 = time.time()
    for page_no in range(1, doc.page_count + 1):
        boxes = page_boxes(engine, doc, page_no, args.dpi)
        data["pages"].append({"page": page_no, "boxes": boxes})
        print("page %d: %d boxes" % (page_no, len(boxes)))
    doc.close()
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
    print("wrote %s in %.0fs" % (args.out, time.time() - t0))


if __name__ == "__main__":
    main()
