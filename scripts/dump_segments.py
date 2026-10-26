#!/usr/bin/env python3
"""Print a compact, human-readable view of a segments.json for review.

Usage:
    python dump_segments.py segments.json [--page N] [--type body]
"""
from __future__ import annotations

import argparse
import json


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("segments")
    ap.add_argument("--page", type=int, default=None)
    ap.add_argument("--type", default=None)
    ap.add_argument("--width", type=int, default=400)
    args = ap.parse_args()

    with open(args.segments, encoding="utf-8") as fh:
        data = json.load(fh)
    print(
        "source=%s page=%sx%s body_size=%s segments=%d"
        % (data["source"], data["page_width"], data["page_height"], data["body_size"], len(data["segments"]))
    )
    for seg in data["segments"]:
        if args.page and seg["page"] != args.page:
            continue
        if args.type and seg["type"] != args.type:
            continue
        text = " ".join(seg["text"].split())
        if len(text) > args.width:
            text = text[: args.width] + " …"
        bbox = ",".join("%.0f" % v for v in seg["bbox"])
        label = seg["type"] + ("%s" % seg["level"] if "level" in seg else "")
        if "special" in seg:
            label += ":" + seg["special"]
        print("%-11s %-9s [%s] %s" % (seg["id"], label, bbox, text))


if __name__ == "__main__":
    main()
