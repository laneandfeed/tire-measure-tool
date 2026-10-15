"""
marker_snap.py
--------------
Sub-pixel calibration correction for ruler & gauge graduation marks.

THE PROBLEM:
  A ruler/gauge mark photographed is not 1 pixel wide — it is 2–6 pixels wide.
  The outer pixels are grey (anti-aliased), while the inner core pixels are dark.
  When you click to mark a line, landing on a grey edge pixel introduces 
  a 1–3 pixel positioning error.

THE FIX — snap_to_mark_centre():
  Samples a local patch around the click point.
  Computes the weighted intensity centroid (center of mass) of the dark 
  pixels within the expected marker width.
  Returns the exact sub-pixel center coordinate of the graduation line.
"""

from __future__ import annotations
import sys
import os
import math
import numpy as np
import cv2
from dataclasses import dataclass


@dataclass
class SnapResult:
    raw_x: float
    raw_y: float
    snapped_x: float
    snapped_y: float
    offset_px: float
    confidence: float
    search_radius: int

    def as_tuple(self) -> tuple[float, float]:
        return (self.snapped_x, self.snapped_y)

    def __str__(self) -> str:
        return (
            f"Raw ({self.raw_x:.1f}, {self.raw_y:.1f}) → "
            f"Snapped ({self.snapped_x:.1f}, {self.snapped_y:.1f}) "
            f"[shifted {self.offset_px:.2f}px, conf {self.confidence:.2f}]"
        )


def snap_to_mark_centre(
    img_array: np.ndarray,
    click_x: float,
    click_y: float,
    marker_width_px: int = 3,
) -> SnapResult:
    """
    Find the sub-pixel center of a ruler mark by calculating the weighted
    intensity centroid of dark pixels around (click_x, click_y).
    """
    if img_array is None or img_array.size == 0:
        return SnapResult(click_x, click_y, click_x, click_y, 0.0, 0.0, 0)

    # Convert to grayscale if BGR/RGB
    if img_array.ndim == 3:
        gray = cv2.cvtColor(img_array, cv2.COLOR_BGR2GRAY)
    else:
        gray = img_array.copy()

    img_h, img_w = gray.shape

    cx = int(round(max(0, min(click_x, img_w - 1))))
    cy = int(round(max(0, min(click_y, img_h - 1))))

    # Search window radius = marker_width_px * 3
    radius = max(4, marker_width_px * 3)
    x0 = max(0, cx - radius)
    y0 = max(0, cy - radius)
    x1 = min(img_w - 1, cx + radius)
    y1 = min(img_h - 1, cy + radius)

    patch = gray[y0:y1 + 1, x0:x1 + 1].astype(np.float32)

    if patch.size == 0:
        return SnapResult(click_x, click_y, click_x, click_y, 0.0, 0.0, radius)

    # Invert patch: dark mark lines -> high weight values
    inverted = 255.0 - patch

    # Thresholding to ignore background noise and focus on dark core
    mean_val = inverted.mean()
    std_val = inverted.std()
    threshold = mean_val + 0.3 * std_val
    mask = (inverted >= threshold).astype(np.float32)

    if mask.sum() == 0:
        mask = (inverted >= inverted.max() * 0.8).astype(np.float32)

    weights = inverted * mask
    total_w = weights.sum()

    if total_w == 0:
        return SnapResult(click_x, click_y, click_x, click_y, 0.0, 0.0, radius)

    # Calculate weighted centroid (Center of Mass)
    ys, xs = np.mgrid[0:patch.shape[0], 0:patch.shape[1]].astype(np.float32)
    cx_patch = float((weights * xs).sum() / total_w)
    cy_patch = float((weights * ys).sum() / total_w)

    snapped_x = x0 + cx_patch
    snapped_y = y0 + cy_patch

    # Round to 0.1 px precision
    snapped_x = round(snapped_x, 2)
    snapped_y = round(snapped_y, 2)

    offset = math.hypot(snapped_x - click_x, snapped_y - click_y)
    darkest_val = float(inverted.max())
    confidence = min(1.0, darkest_val / 220.0)

    return SnapResult(
        raw_x=float(click_x),
        raw_y=float(click_y),
        snapped_x=snapped_x,
        snapped_y=snapped_y,
        offset_px=round(offset, 2),
        confidence=round(confidence, 2),
        search_radius=radius,
    )


def load_image_array(image_path: str) -> np.ndarray:
    arr = cv2.imread(image_path)
    if arr is None:
        raise FileNotFoundError(f"Could not load image: {image_path}")
    return arr
