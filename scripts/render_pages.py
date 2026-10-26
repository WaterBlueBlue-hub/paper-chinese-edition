#!/usr/bin/env python3
"""Render PDF pages to PNG for visual inspection / proofreading.

Usage:
    python render_pages.py input.pdf outdir [--dpi 150] [--pages 1,2,5]
"""
from __future__ import annotations

import argparse
import os

import pymupdf


def parse_pages(spec, count):
    if not spec:
        return list(range(count))
    out = []
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            lo, hi = part.split("-")
            out.extend(range(int(lo) - 1, int(hi)))
        else:
            out.append(int(part) - 1)
    return [i for i in out if 0 <= i < count]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("outdir")
    ap.add_argument("--dpi", type=int, default=150)
    ap.add_argument("--pages", default=None)
    ap.add_argument("--prefix", default="page")
    args = ap.parse_args()

    os.makedirs(args.outdir, exist_ok=True)
    doc = pymupdf.open(args.pdf)
    zoom = args.dpi / 72.0
    for i in parse_pages(args.pages, doc.page_count):
        page = doc[i]
        pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom))
        path = os.path.join(args.outdir, "%s-%02d.png" % (args.prefix, i + 1))
        pix.save(path)
        print("wrote %s (%dx%d)" % (path, pix.width, pix.height))
    doc.close()


if __name__ == "__main__":
    main()
