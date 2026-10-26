#!/usr/bin/env python3
"""Dump the raw line/font/bbox structure of given PDF pages (debugging aid).

Usage:
    python inspect_page.py input.pdf 1 [2 ...]
"""
from __future__ import annotations

import argparse

import pymupdf


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("pages", nargs="+", type=int)
    ap.add_argument("--min-size", type=float, default=0.0)
    args = ap.parse_args()

    doc = pymupdf.open(args.pdf)
    print("page_count=%d size=%.1fx%.1f" % (doc.page_count, doc[0].rect.width, doc[0].rect.height))
    for pno in args.pages:
        page = doc[pno - 1]
        print("\n=== page %d === rect=%s rot=%d" % (pno, page.rect, page.rotation))
        info = page.get_text("dict")
        for bi, blk in enumerate(info["blocks"]):
            if blk.get("type") == 1:
                print("  block %d IMAGE bbox=(%.0f,%.0f,%.0f,%.0f)" % (bi, *blk["bbox"]))
                continue
            for li, line in enumerate(blk["lines"]):
                for si, span in enumerate(line["spans"]):
                    if span["size"] < args.min_size:
                        continue
                    txt = span["text"].replace("\n", "\\n")
                    print(
                        "  b%-2d l%-2d s%-2d x=(%6.1f,%6.1f) y=(%6.1f,%6.1f) sz=%4.1f %-28s %r"
                        % (bi, li, si, span["bbox"][0], span["bbox"][2], span["bbox"][1], span["bbox"][3], span["size"], span["font"][:28], txt)
                    )
    doc.close()


if __name__ == "__main__":
    main()
