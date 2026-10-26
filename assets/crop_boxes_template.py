#!/usr/bin/env python3
"""Crop rectangles for one paper, in PDF points (top-left origin).

Copy this file to 工具/论文对照/content/<论文>/crop_boxes.py and fill in the
rectangles for that paper. `make_crops.py --boxes` points at it.

Each rectangle only has to *contain* the wanted ink: make_crops.py tightens it
to the ink it keeps, so being generous costs nothing. Being too small is what
hurts - the box then chops a fraction bar or a superscript - which is why the
run reports, for every crop, how much clearance the ink kept from each edge.

Read references/pitfalls.md for how to locate the rectangles.
"""

# Figures: one entry per illustration, taken from the image area above its
# caption. Vector figures have no image object, so find them by the caption.
FIGURES = [
    # ("fig-01", 2, (66, 76, 530, 224)),
]

# Numbered algorithm / pseudocode listings cropped whole. Widen the box if a
# line overruns its column.
LISTINGS = [
    # ("alg-01", 3, (66, 382, 310, 576)),
]

# Display equations. Group consecutive equations that share a block (no prose
# between them) into one crop; group an equation with the sentence that
# introduces it only when the sentence is short.
EQUATIONS = [
    # ("eq-01", 4, (136, 286, 294, 318)),  # (1)
]

PAD = 3.0  # blank border kept around the detected ink
GROW = 5.0  # extra border, so vector art the detector missed is not clipped
