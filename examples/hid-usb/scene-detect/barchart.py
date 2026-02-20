"""Bar chart, toast, and region overlay drawing."""

import cv2
import numpy as np

# Bar chart panel
CHART_W = 200
BAR_H = 28
BAR_GAP = 6
BAR_MAX_W = 80  # max bar length in pixels

TOAST_DURATION = 3.0  # seconds before fully faded


def draw_chart(scores, chart_w, chart_h):
    """Draw horizontal bar chart. Returns BGR image."""
    panel = np.zeros((chart_h, chart_w, 3), dtype=np.uint8)
    panel[:] = (30, 30, 30)

    # Sort: score DESC (rounded to 2 decimals), then name ASC
    sorted_scores = sorted(scores, key=lambda s: (-round(s[1], 2), s[0]))

    label_x = 8
    bar_x0 = 105
    y = 10

    for i, (name, score) in enumerate(sorted_scores):
        cy = y + BAR_H // 2

        if i == 0:
            colour = (0, 220, 100)
        elif score < 0:
            colour = (60, 60, 180)
        else:
            colour = (160, 160, 160)

        short = name if len(name) <= 14 else name[:13] + ".."
        cv2.putText(panel, short, (label_x, cy + 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.33, (200, 200, 200), 1)

        bar_w = int(max(score, 0.0) * BAR_MAX_W)
        if bar_w > 0:
            cv2.rectangle(panel, (bar_x0, y + 2), (bar_x0 + bar_w, y + BAR_H - 2),
                          colour, -1)

        cv2.putText(panel, f"{score:.2f}", (bar_x0 + bar_w + 4, cy + 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.38, colour, 1)

        y += BAR_H + BAR_GAP

    return panel


def draw_toast(display, text, elapsed):
    """Draw a centred toast message with fade-out. elapsed = time since toast fired."""
    if elapsed >= TOAST_DURATION:
        return
    alpha = 1.0 - (elapsed / TOAST_DURATION)
    h, w = display.shape[:2]
    font = cv2.FONT_HERSHEY_SIMPLEX
    scale = 1.0
    thickness = 3
    (tw, th), baseline = cv2.getTextSize(text, font, scale, thickness)
    tx = (w - tw) // 2
    ty = (h + th) // 2
    # Semi-transparent background
    pad = 12
    overlay = display.copy()
    cv2.rectangle(overlay,
                  (tx - pad, ty - th - pad),
                  (tx + tw + pad, ty + baseline + pad),
                  (0, 0, 0), -1)
    cv2.addWeighted(overlay, alpha * 0.6, display, 1.0 - alpha * 0.6, 0, display)
    # Text
    colour = (0, 255, 200)
    faded = tuple(int(c * alpha) for c in colour)
    cv2.putText(display, text, (tx, ty), font, scale, faded, thickness)


def draw_region_boxes(display, fsm_state, scene_regions, output_w, output_h,
                      candidate_scene=None, alpha=0.5):
    """Draw sub-region rectangles for FSM state (red fill) and candidate (green border)."""
    # Layer 1: current FSM state -> red fill, 50% alpha
    fsm_name = fsm_state.lower()
    fsm_regions = scene_regions.get(fsm_name, [])
    if fsm_regions:
        overlay = display.copy()
        for rx, ry, rw, rh in fsm_regions:
            x1 = int(output_w * rx)
            y1 = int(output_h * ry)
            x2 = int(output_w * (rx + rw))
            y2 = int(output_h * (ry + rh))
            cv2.rectangle(overlay, (x1, y1), (x2, y2), (0, 0, 255), -1)
        cv2.addWeighted(overlay, alpha, display, 1.0 - alpha, 0, display)

    # Layer 2: candidate (detected) scene -> green border, no fill
    if candidate_scene:
        cand_name = candidate_scene.lower()
        cand_regions = scene_regions.get(cand_name, [])
        for rx, ry, rw, rh in cand_regions:
            x1 = int(output_w * rx)
            y1 = int(output_h * ry)
            x2 = int(output_w * (rx + rw))
            y2 = int(output_h * (ry + rh))
            cv2.rectangle(display, (x1, y1), (x2, y2), (0, 255, 0), 2)
