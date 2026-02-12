#!/usr/bin/env python3
"""Monster Strike scene detector - camera capture base."""

import argparse
import glob
import math
import os
import queue
import threading
import time

import cv2
import numpy as np
from picamera2 import Picamera2

import common as hid

SAVE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "snapshots")

# --- ROI config (matches: rpicam-still --roi 0.40,0.15,0.20,0.55) ---
ROI_X = 0.442   # left offset (normalized)
ROI_Y = 0.432   # top offset  (normalized)
ROI_W = 0.126   # width       (normalized)
ROI_H = 0.332   # height      (normalized)

OUTPUT_W = 400
OUTPUT_H = 800

# Camera capture resolution (full sensor crop source)
CAP_W = 2028
CAP_H = 1520

# Bar chart panel
CHART_W = 200
BAR_H = 28
BAR_GAP = 6
BAR_MAX_W = 80  # max bar length in pixels

# --- Scene-specific sub-region hints (normalized within OUTPUT frame) ---
# Each entry: scene_name -> [(x, y, w, h), ...]  all normalised 0..1
SCENE_REGIONS = {

    "home": [
        (0.01, 0.75, 0.32, 0.07),  # quest button area.0
        (0.37, 0.73, 0.26, 0.10),  # quest button area.1
        (0.66, 0.75, 0.32, 0.07),  # quest button area.2
        (0.01, 0.91, 0.98, 0.07),  # home bar
    ],
    "event": [
        (0.19, 0.59, 0.15, 0.08),  # normal quest
        (0.39, 0.58, 0.24, 0.12),  # event quest
        (0.68, 0.59, 0.15, 0.08),  # charange quest
        (0.01, 0.91, 0.98, 0.07),  # home bar
    ],
    "quest": [
        (0.16, 0.57, 0.23, 0.12),  # normal quest
        (0.44, 0.60, 0.15, 0.08),  # event quest
        (0.68, 0.59, 0.15, 0.08),  # charange quest
        (0.01, 0.91, 0.98, 0.07),  # home bar
    ],
    "normal-quest-uijin-karyu": [
        (0.1, 0.47, 0.35, 0.20),
        (0.52, 0.47, 0.35, 0.20),
        (0.01, 0.91, 0.98, 0.07),  # home bar
    ],
    "normal-quest": [
        (0.02, 0.12, 0.59, 0.045),
        (0.04, 0.22, 0.73, 0.07),
        (0.04, 0.352, 0.73, 0.07),
        (0.04, 0.482, 0.73, 0.07),
        (0.04, 0.612, 0.73, 0.07),
        (0.04, 0.742, 0.73, 0.07),
        (0.01, 0.91, 0.98, 0.07),  # home bar
    ],
    "normal-quest-uijin": [
        (0.02, 0.12, 0.59, 0.045),
        (0.04, 0.204, 0.73, 0.07),
        (0.08, 0.312, 0.71, 0.07),
        (0.08, 0.408, 0.71, 0.07),
        (0.08, 0.504, 0.71, 0.07),
        (0.01, 0.91, 0.98, 0.07),  # home bar
    ],
    "helper-select": [
        (0.02, 0.12, 0.46, 0.045),
        (0.14, 0.17, 0.78, 0.065),
        (0.01, 0.91, 0.98, 0.07),  # home bar
    ],
    "deck-select": [
        (0.02, 0.12, 0.46, 0.045),
        (0.06, 0.36, 0.82, 0.198),
        (0.01, 0.91, 0.98, 0.07),  # home bar
    ],
    "special-reward": [
        (0.18, 0.00, 0.70, 0.044),
    ],
    
    "reward-next": [
        (0.01, 0.91, 0.98, 0.07),  # ok button
    ],
    
}

# --- Custom differential for disambiguating similar scenes ---
# key_region: the button index that should be dominant for this scene
# other_regions: the other button indices to compare against (avg)
# Rule: if r[key] > avg(r[others]) → boost, otherwise → penalise
SCENE_CUSTOMS = {
    "quest": {
        "rival": "event",
        "key_region": 0,          # r0 (left button) biggest → quest
        "other_regions": [1, 2],
        "weight": 0.5,
    },
    "event": {
        "rival": "quest",
        "key_region": 1,          # r1 (middle button) biggest → event
        "other_regions": [0, 2],
        "weight": 0.5,
    },
}


# --------------- Scene templates ---------------

def calc_hist(img):
    """Compute normalised HSV histogram for an image."""
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist([hsv], [0, 1], None, [32, 32], [0, 180, 0, 256])
    cv2.normalize(hist, hist)
    return hist


def crop_region(img, region):
    """Crop a normalised (x, y, w, h) region from img."""
    h, w = img.shape[:2]
    rx, ry, rw, rh = region
    x1 = int(w * rx)
    y1 = int(h * ry)
    x2 = int(w * (rx + rw))
    y2 = int(h * (ry + rh))
    return img[y1:y2, x1:x2]


def load_templates(snapshot_dir):
    """Load template images grouped by scene name.

    Returns:
        templates_hist: dict of scene_name -> [hist, ...]  (full-frame)
        templates_region: dict of scene_name -> [[hist, ...], ...]  (sub-region)
    """
    raw = {}
    for path in sorted(glob.glob(os.path.join(snapshot_dir, "*.jpg"))):
        basename = os.path.splitext(os.path.basename(path))[0]
        parts = basename.rsplit("_", 1)
        if len(parts) == 2 and parts[1].isdigit():
            scene_name = parts[0]
        else:
            continue
        img = cv2.imread(path)
        if img is None:
            continue
        raw.setdefault(scene_name, []).append(img)

    templates_hist = {}
    templates_region = {}
    for name, imgs in raw.items():
        templates_hist[name] = [calc_hist(img) for img in imgs]
        if name in SCENE_REGIONS:
            region_hists = []
            for region in SCENE_REGIONS[name]:
                region_hists.append([calc_hist(crop_region(img, region)) for img in imgs])
            templates_region[name] = region_hists
        n_regions = len(SCENE_REGIONS.get(name, []))
        print(f"  template: {name:35s} x{len(imgs)}"
              f"{'  +' + str(n_regions) + ' regions' if n_regions else ''}")
    return templates_hist, templates_region


def scene_similarity(frame, templates_hist, templates_region):
    """Compare frame against all scene templates.

    Full-frame histogram + sub-region boost for scenes with defined regions.
    When rival scenes (SCENE_CUSTOMS) both score high, apply differential
    region weights to disambiguate.
    Returns list of (scene_name, combined_score) sorted descending.
    """
    frame_hist = calc_hist(frame)
    score_map = {}
    region_map = {}
    for name, hists in templates_hist.items():
        base = max(cv2.compareHist(frame_hist, h, cv2.HISTCMP_CORREL) for h in hists)

        if name in templates_region:
            region_scores = []
            for ri, region in enumerate(SCENE_REGIONS[name]):
                frame_crop = crop_region(frame, region)
                frame_crop_hist = calc_hist(frame_crop)
                rs = max(
                    cv2.compareHist(frame_crop_hist, h, cv2.HISTCMP_CORREL)
                    for h in templates_region[name][ri]
                )
                region_scores.append(rs)
            region_map[name] = region_scores
            # Compare avg of regions (excluding last = home bar) vs base
            content_regions = region_scores[:-1] if len(region_scores) > 1 else region_scores
            avg_content = sum(content_regions) / len(content_regions)
            diff = avg_content - base
            if diff >= 0:
                # Positive: regions match better than base → boost
                score = 0.15 * base + 0.85 * avg_content
            else:
                # Negative: regions match worse than base → penalise (log curve)
                score = base - 0.70 * math.log(1.0 + abs(diff))
        else:
            score = base

        score_map[name] = score

    # Apply SCENE_CUSTOMS: boost scene whose key_region > avg(other_regions)
    for name, custom in SCENE_CUSTOMS.items():
        rival = custom["rival"]
        if name not in score_map or rival not in score_map:
            continue
        if name not in region_map:
            continue
        rs = region_map[name]
        key_idx = custom["key_region"]
        other_idxs = custom["other_regions"]
        key_score = rs[key_idx]
        other_avg = sum(rs[i] for i in other_idxs) / len(other_idxs)
        diff = key_score - other_avg
        before = score_map[name]
        delta = custom["weight"] * diff
        score_map[name] += delta
        # print(f"  CUSTOM[{name}] r{key_idx}={key_score:.3f} "
        #       f"avg({','.join(f'r{i}' for i in other_idxs)})={other_avg:.3f} "
        #       f"diff={diff:+.4f} delta={delta:+.4f}  "
        #       f"{before:.4f}->{score_map[name]:.4f}")

    results = sorted(score_map.items(), key=lambda x: x[1], reverse=True)
    return results


# --------------- Moore FSM ---------------

# States
S_UNKNOWN = "UNKNOWN"
S_HOME = "HOME"
S_QUEST = "QUEST"
S_NORMAL_QUEST = "NORMAL-QUEST"
S_NORMAL_QUEST_UIJIN = "NORMAL-QUEST-UIJIN"
S_NORMAL_QUEST_UIJIN_KARYU = "NORMAL-QUEST-UIJIN-KARYU"
S_HELPER_SELECT = "HELPER-SELECT"
S_DECK_SELECT = "DECK-SELECT"
S_IN_PLAY = "NORMAL-QUEST-UIJIN-IN-PLAY"
S_CLEAR_OK = "CLEAR-OK"
S_SPECIAL_REWARD = "SPECIAL-REWARD"
S_EVENT = "EVENT"
S_REWARD_NEXT = "REWARD-NEXT"

# --- FSM transition table ---
# state -> [allowed next states]  (game flow order)
FSM_TRANSITIONS = {
    S_UNKNOWN: [S_HOME, S_EVENT, S_QUEST, S_NORMAL_QUEST, S_NORMAL_QUEST_UIJIN,
                S_NORMAL_QUEST_UIJIN_KARYU, S_HELPER_SELECT, S_DECK_SELECT,
                S_IN_PLAY, S_CLEAR_OK, S_SPECIAL_REWARD, S_REWARD_NEXT],
    S_HOME:                     [S_EVENT, S_QUEST, S_NORMAL_QUEST_UIJIN],
    S_EVENT:                    [S_NORMAL_QUEST_UIJIN, S_HOME],
    S_QUEST:                    [S_NORMAL_QUEST, S_HOME],
    S_NORMAL_QUEST:             [S_NORMAL_QUEST_UIJIN, S_QUEST, S_HOME],
    S_NORMAL_QUEST_UIJIN:      [S_NORMAL_QUEST_UIJIN_KARYU, S_NORMAL_QUEST, S_HOME],
    S_NORMAL_QUEST_UIJIN_KARYU:[S_HELPER_SELECT, S_HOME],
    S_HELPER_SELECT:            [S_DECK_SELECT, S_HOME],
    S_DECK_SELECT:              [S_IN_PLAY, S_HOME],
    S_IN_PLAY:                  [S_CLEAR_OK],
    S_CLEAR_OK:                 [S_SPECIAL_REWARD, S_REWARD_NEXT, S_HOME],
    S_SPECIAL_REWARD:           [S_REWARD_NEXT],
    S_REWARD_NEXT:              [S_HOME],
}


# --- FSM state -> HID action mapping ---
FSM_ACTIONS = {
    S_HOME:                     "quest_bt_click",
    S_EVENT:                    "normal_ikusei_bt_click",
    S_QUEST:                    "normal_bt_click",
    S_NORMAL_QUEST:             "shojin_bt_click",
    S_NORMAL_QUEST_UIJIN:      "karyu_bt_click",
    S_NORMAL_QUEST_UIJIN_KARYU:"solo_bt_click",
    S_HELPER_SELECT:            "helper_select",
    S_DECK_SELECT:              "shutsugeki_bt_click",
    S_IN_PLAY:                  "play_turn",
    S_CLEAR_OK:                 "clear_ok",
    S_SPECIAL_REWARD:           "special_reward",
    S_REWARD_NEXT:              "reward_next",
}

_action_queue = queue.Queue()
_worker_idle = threading.Event()
_worker_idle.set()


def _action_worker():
    """Worker thread: consume actions from FIFO queue sequentially."""
    while True:
        action_name, hid_args = _action_queue.get()
        _worker_idle.clear()
        print(f"  [HID] dispatching: {action_name} (queue size: {_action_queue.qsize()})")
        try:
            hid.ACTIONS[action_name](hid_args)
            print(f"  [HID] done: {action_name}")
        except Exception as e:
            print(f"  [HID] error in {action_name}: {e}")
        _action_queue.task_done()
        if _action_queue.empty():
            _worker_idle.set()


threading.Thread(target=_action_worker, daemon=True).start()


def dispatch_action(action_name, hid_args):
    """Enqueue an HID action for sequential execution."""
    print(f"  [HID] enqueue: {action_name} (queue size: {_action_queue.qsize()})")
    _action_queue.put((action_name, hid_args))


def dispatch_if_idle(action_name, hid_args):
    """Dispatch only if worker is idle. Skip otherwise."""
    if _worker_idle.is_set():
        print(f"  [HID] enqueue (idle): {action_name}")
        _action_queue.put((action_name, hid_args))
    else:
        print(f"  [HID] skip (busy): {action_name}")


def _score_of(scores, name):
    """Return score for a scene name, or -1 if not found."""
    for n, s in scores:
        if n == name:
            return s
    return -1.0


def _top_names(scores, n):
    """Return the top-n scene names in order."""
    return [name for name, _ in scores[:n]]


def _evaluate_state(scores):
    """Determine which state the scores indicate, ignoring transitions."""
    if not scores:
        return S_UNKNOWN

    top_name, top_score = scores[0]
    names = _top_names(scores, 3)

    # HOME stable
    if (top_name == "home" and top_score >= 0.8
            and len(names) >= 3
            and names[1] == "clear-ok"
            and names[2] in ("helper-select", "deck-select")):
        return S_HOME

    # EVENT stable
    if (top_name == "event" and top_score >= 0.8
            and len(names) >= 2
            and names[1] == "quest"):
        return S_EVENT

    # QUEST stable
    if (top_name == "quest" and top_score >= 0.8
            and len(names) >= 2
            and names[1] == "event"):
        return S_QUEST

    # NORMAL-QUEST stable
    if (top_name == "normal-quest" and top_score >= 0.8
            and _score_of(scores, "normal-quest-uijin") >= 0.7
            and len(names) >= 2
            and names[1] == "normal-quest-uijin"):
        return S_NORMAL_QUEST

    # NORMAL-QUEST-UIJIN stable
    if (top_name == "normal-quest-uijin" and top_score >= 0.8
            and _score_of(scores, "normal-quest") >= 0.7
            and _score_of(scores, "deck-select") >= 0.5
            and _score_of(scores, "event") >= 0.45
            and _score_of(scores, "quest") >= 0.45
            and len(names) >= 2
            and names[1] == "normal-quest"):
        return S_NORMAL_QUEST_UIJIN

    # NORMAL-QUEST-UIJIN-KARYU stable
    if (top_name == "normal-quest-uijin-karyu" and top_score >= 0.7
            and (_score_of(scores, "helper-select") >= 0.5
                 or _score_of(scores, "deck-select") >= 0.5
                 or _score_of(scores, "normal-quest") >= 0.6)
            and len(names) >= 2
            and names[1] in ("helper-select", "deck-select", "normal-quest")):
        return S_NORMAL_QUEST_UIJIN_KARYU

    # HELPER-SELECT stable
    if (top_name == "helper-select" and top_score >= 0.8
            and _score_of(scores, "clear-ok") >= 0.6
            and _score_of(scores, "deck-select") >= 0.6
            and len(names) >= 2
            and names[1] in ("clear-ok", "deck-select")):
        return S_HELPER_SELECT

    # DECK-SELECT stable
    if (top_name == "deck-select" and top_score >= 0.8
            and (_score_of(scores, "event") >= 0.6
                 or _score_of(scores, "quest") >= 0.6)
            and len(names) >= 2
            and names[1] in ("event", "quest")):
        return S_DECK_SELECT

    # NORMAL-QUEST-UIJIN-IN-PLAY stable
    if (top_name == "normal-quest-uijin-in-play" and top_score >= 0.6
            and sum(1 for n, s in scores[1:] if s <= 0.2) >= 8):
        return S_IN_PLAY

    # CLEAR-OK stable
    if top_name == "clear-ok" and top_score >= 0.8:
        return S_CLEAR_OK

    # SPECIAL-REWARD stable
    if (top_name == "special-reward" and top_score >= 0.6
            and (_score_of(scores, "reward-next") >= 0.3
            and all(s <= 0.2 for n, s in scores
                    if n not in ("special-reward", "reward-next")))
            or (all(s <= 0.2 for n, s in scores
                    if n not in ("special-reward")))):
        return S_SPECIAL_REWARD

    # REWARD-NEXT stable
    if (top_name == "reward-next" and top_score >= 0.6
            and _score_of(scores, "special-reward") < 0.6
            and all(s < 0.3 for n, s in scores
                    if n not in ("reward-next", "special-reward"))):
        return S_REWARD_NEXT

    return S_UNKNOWN


_fsm_pending = None   # candidate state awaiting confirmation
_fsm_pending_count = 0  # consecutive times candidate has been seen
FSM_CONFIRM_COUNT = 3   # required consecutive hits before transition


def fsm_update(state, scores):
    """Evaluate Moore FSM transition based on current scores.

    Only transitions defined in FSM_TRANSITIONS are allowed.
    Requires FSM_CONFIRM_COUNT consecutive detections of the same
    candidate before actually transitioning.
    Returns (new_state, changed).
    """
    global _fsm_pending, _fsm_pending_count

    candidate = _evaluate_state(scores)
    if state == S_QUEST and candidate == S_NORMAL_QUEST_UIJIN:
        candidate = S_NORMAL_QUEST
    # candidate が現在と異なる場合だけログ出力
    if candidate != state:
        print(f"  [FSM] candidate={candidate} ({_fsm_pending_count}/{FSM_CONFIRM_COUNT})")
    if candidate == state:
        _fsm_pending = None
        _fsm_pending_count = 0
        return state, False

    allowed = FSM_TRANSITIONS.get(state, [])
    if candidate in allowed:
        if _fsm_pending == candidate:
            _fsm_pending_count += 1
        else:
            _fsm_pending = candidate
            _fsm_pending_count = 1
        if _fsm_pending_count >= FSM_CONFIRM_COUNT:
            _fsm_pending = None
            _fsm_pending_count = 0
            return candidate, True
        return state, False

    # candidate not allowed — reset pending
    print(f"  [FSM] BLOCKED: {candidate} (allowed={allowed})")
    _fsm_pending = None
    _fsm_pending_count = 0
    return state, False


# --------------- Bar chart drawing ---------------

def draw_chart(scores, chart_w, chart_h):
    """Draw horizontal bar chart. Returns BGR image."""
    panel = np.zeros((chart_h, chart_w, 3), dtype=np.uint8)
    panel[:] = (30, 30, 30)

    label_x = 8
    bar_x0 = 105
    y = 10

    for i, (name, score) in enumerate(scores):
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


TOAST_DURATION = 3.0  # seconds before fully faded


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


def draw_region_boxes(display, fsm_state, alpha=0.5):
    """Draw sub-region rectangles with semi-transparent red fill."""
    scene_name = fsm_state.lower()
    regions = SCENE_REGIONS.get(scene_name, [])
    if not regions:
        return
    overlay = display.copy()
    for rx, ry, rw, rh in regions:
        x1 = int(OUTPUT_W * rx)
        y1 = int(OUTPUT_H * ry)
        x2 = int(OUTPUT_W * (rx + rw))
        y2 = int(OUTPUT_H * (ry + rh))
        cv2.rectangle(overlay, (x1, y1), (x2, y2), (0, 0, 255), -1)
    cv2.addWeighted(overlay, alpha, display, 1.0 - alpha, 0, display)


def make_roi_rect(frame_h, frame_w):
    """Convert normalized ROI to pixel coordinates."""
    x1 = int(frame_w * ROI_X)
    y1 = int(frame_h * ROI_Y)
    x2 = int(frame_w * (ROI_X + ROI_W))
    y2 = int(frame_h * (ROI_Y + ROI_H))
    return x1, y1, x2, y2


# --------------- Main loop ---------------

def main():
    parser = argparse.ArgumentParser(description="Monster Strike scene detector")
    parser.add_argument("--device-id",
                        default=os.environ.get("DEVICE_ID", ""),
                        help="SFU device ID for HID control (env: DEVICE_ID)")
    parser.add_argument("--hid-w", type=int,
                        default=int(os.environ.get("HID_W", "0")),
                        help="HID screen width (env: HID_W)")
    parser.add_argument("--hid-h", type=int,
                        default=int(os.environ.get("HID_H", "0")),
                        help="HID screen height (env: HID_H)")
    args = parser.parse_args()

    print(f"  [DEBUG] device_id='{args.device_id}' hid_w={args.hid_w} hid_h={args.hid_h}")
    hid_enabled = bool(args.device_id and args.hid_w and args.hid_h)
    hid_args = [str(args.hid_w), str(args.hid_h)]
    print(f"  [DEBUG] hid_enabled={hid_enabled} hid_args={hid_args}")
    if hid_enabled:
        hid.init(args.device_id)
        print(f"HID control enabled: device={args.device_id} "
              f"size={args.hid_w}x{args.hid_h}")
        print(f"  API: {hid.API_BASE}")
    else:
        print("HID control disabled "
              "(set --device-id --hid-w --hid-h to enable)")

    print("Loading templates...")
    templates_hist, templates_region = load_templates(SAVE_DIR)
    if not templates_hist:
        print(f"WARNING: no templates found in {SAVE_DIR}")

    picam2 = Picamera2()
    config = picam2.create_video_configuration(
        main={"size": (CAP_W, CAP_H), "format": "RGB888"},
    )
    picam2.configure(config)
    picam2.start()
    time.sleep(0.5)

    print(f"Capture: {CAP_W}x{CAP_H}  ROI: ({ROI_X},{ROI_Y},{ROI_W},{ROI_H})  Output: {OUTPUT_W}x{OUTPUT_H}")
    print("Keys: q=quit  s=save snapshot")

    frame_count = 0
    fps_time = time.monotonic()
    last_detect = 0.0
    scores = [(name, 0.0) for name in templates_hist]
    fsm_state = S_UNKNOWN
    toast_text = ""
    toast_time = 0.0
    last_play_turn = 0.0
    PLAY_TURN_INTERVAL = 5.0

    try:
        while True:
            frame = picam2.capture_array()
            h, w = frame.shape[:2]

            x1, y1, x2, y2 = make_roi_rect(h, w)
            roi = frame[y1:y2, x1:x2]
            roi_resized = cv2.resize(roi, (OUTPUT_W, OUTPUT_H))
            display = roi_resized.copy()

            # --- Scene detection (1Hz) ---
            now = time.monotonic()
            if templates_hist and now - last_detect >= 1.0:
                scores = scene_similarity(roi_resized, templates_hist, templates_region)
                last_detect = now
                # FSM update
                fsm_state, fsm_changed = fsm_update(fsm_state, scores)
                if fsm_changed:
                    print(f"  FSM -> {fsm_state}")
                    toast_text = fsm_state
                    toast_time = now
                    print(f"  [DEBUG] hid_enabled={hid_enabled} fsm_state={fsm_state} "
                          f"in_actions={fsm_state in FSM_ACTIONS}")
                    if hid_enabled and fsm_state in FSM_ACTIONS:
                        print(f"  [DEBUG] calling dispatch_action({FSM_ACTIONS[fsm_state]}, {hid_args})")
                        dispatch_action(FSM_ACTIONS[fsm_state], hid_args)
                    else:
                        print(f"  [DEBUG] SKIPPED: hid_enabled={hid_enabled}")
                # IN-PLAY: periodic play_turn (skip if busy)
                if (hid_enabled and fsm_state == S_IN_PLAY
                        and now - last_play_turn >= PLAY_TURN_INTERVAL):
                    dispatch_if_idle("play_turn", hid_args)
                    last_play_turn = now
                # Debug: show base vs region for scenes with regions
                for sname, sscore in scores[:3]:
                    if sname in templates_region:
                        frame_hist = calc_hist(roi_resized)
                        base = max(cv2.compareHist(frame_hist, h, cv2.HISTCMP_CORREL)
                                   for h in templates_hist[sname])
                        rs = []
                        for ri, region in enumerate(SCENE_REGIONS[sname]):
                            fc = crop_region(roi_resized, region)
                            fch = calc_hist(fc)
                            r = max(cv2.compareHist(fch, h, cv2.HISTCMP_CORREL)
                                    for h in templates_region[sname][ri])
                            rs.append(r)
                        rs_str = " ".join(f"r{i}={v:.3f}" for i, v in enumerate(rs))
                        print(f"  [{sname}] base={base:.3f} {rs_str} -> {sscore:.3f}")
                    else:
                        print(f"  [{sname}] base={sscore:.3f}")

            # --- FPS ---
            frame_count += 1
            elapsed = now - fps_time
            if elapsed >= 1.0:
                fps = frame_count / elapsed
                frame_count = 0
                fps_time = now
            else:
                fps = frame_count / max(elapsed, 0.001)

            # Overlay
            cv2.putText(display, f"FPS: {fps:.1f}", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
            if scores:
                top = scores[0]
                cv2.putText(display, f"{top[0]} ({top[1]:.3f})", (10, 60),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
            cv2.putText(display, f"FSM: {fsm_state}", (10, 90),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 200, 255), 2)
            draw_region_boxes(display, fsm_state)
            if toast_text:
                draw_toast(display, toast_text, now - toast_time)
                if now - toast_time >= TOAST_DURATION:
                    toast_text = ""

            # Composite
            chart = draw_chart(scores, CHART_W, OUTPUT_H)
            composite = np.hstack([display, chart])
            cv2.imshow("Scene Detect", composite)

            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break
            elif key == ord("s"):
                os.makedirs(SAVE_DIR, exist_ok=True)
                default = f"snapshot_{int(time.time())}"
                name = input(f"Filename [{default}]: ").strip()
                if not name:
                    name = default
                if not name.endswith((".jpg", ".png")):
                    name += ".jpg"
                fpath = os.path.join(SAVE_DIR, name)
                cv2.imwrite(fpath, roi_resized)
                print(f"Saved: {fpath}")

    except KeyboardInterrupt:
        pass
    finally:
        picam2.stop()
        cv2.destroyAllWindows()
        print("Done.")


if __name__ == "__main__":
    main()
