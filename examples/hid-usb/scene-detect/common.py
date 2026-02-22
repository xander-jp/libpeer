"""Monster Strike auto-test: shared utilities.

USB HID mouse control via HTTP API.
Command format: "{op} {x} {y}"
  op=0: move / mouse-up
  op=1: mouse-down / drag
  x, y: relative delta (HID units, NOT pixels)

Note: HID delta ~100 moves the cursor roughly 1/4 of the screen.
      Full screen ≈ 400 HID units (varies by OS mouse acceleration).
"""

import glob
import os
import requests
import threading
import time
import math
import random

import cv2
import numpy as np

# --------------- config ---------------
API_BASE = os.environ.get("SFU_API_BASE", "http://127.0.0.1:8888/api/message")
_device_id = ""         # set by init(device_id)
MOVE_DELAY = 0.06       # inter-report delay (s)
CLICK_HOLD = 0.15       # mouse-down duration (s)
UI_WAIT = 1.0           # wait for UI transition (s)
SCAN_STEP = 10          # calibration scan step (px)
MAX_DELTA = 10          # max delta per-report (both dx, dy)
API_WAIT_DURATION = 0.3 # api duration
# --------------- state ---------------
screen_w = 0            # screen width  (HID units)
screen_h = 0            # screen height (HID units)
_cx = 0                 # tracked cursor x (HID units)
_cy = 0                 # tracked cursor y (HID units)
_seq = 0                # packet sequence number (IPS/IDS evasion)

RESET_SWEEP = 500       # HID units to guarantee reaching any corner

# --------------- batch config (IPS/IDS evasion) ---------------
BATCH_MIN = 6           # min commands per batch
BATCH_MAX = 14          # max commands per batch
PAD_MIN = 0             # min random padding length
PAD_MAX = 32            # max random padding length


# ============================================================
#  Global last frame (set by caller, used by notify_slack)
# ============================================================
_last_frame = None      # latest ROI frame (numpy BGR)

# ============================================================
#  Slack webhook notification
# ============================================================

SLACK_WEBHOOK_URL = "https://hooks.slack.com/triggers/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"
SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN", "")
SLACK_CHANNEL = os.environ.get("SLACK_CHANNEL", "")

THUMB_W = 60
THUMB_H = 120


def notify_slack(script, prev_state, new_state):
    """Send FSM transition event to Slack webhook (non-blocking).

    If _last_frame is set and SLACK_BOT_TOKEN / SLACK_CHANNEL are configured,
    also uploads a 120x60 thumbnail of the current frame.
    Skips thumbnail for "action" events (same frame as preceding transition).
    """
    print(f"  [Slack] sending: {script} {prev_state} -> {new_state}")
    # snapshot frame now (before thread); skip for action events (redundant frame)
    skip_thumb = (prev_state == "action")
    frame = _last_frame.copy() if (_last_frame is not None and not skip_thumb) else None

    def _send():
        msg = f"[{script}] {_device_id}: {prev_state} -> {new_state}"
        # try:
        #     # 1) webhook message (existing)
        #     payload = {"msg": msg}
        #     resp = requests.post(SLACK_WEBHOOK_URL, json=payload, timeout=5)
        #     print(f"  [Slack] {prev_state} -> {new_state} ({resp.status_code}) {resp.text}")
        # except Exception as e:
        #     print(f"  [Slack] webhook error: {e}")

        if not SLACK_BOT_TOKEN or not SLACK_CHANNEL:
            return
        headers = {"Authorization": f"Bearer {SLACK_BOT_TOKEN}"}

        # 2a) thumbnail + message via file upload
        if frame is not None:
            try:
                thumb = cv2.resize(frame, (THUMB_W, THUMB_H))
                _, jpeg = cv2.imencode(".jpg", thumb, [cv2.IMWRITE_JPEG_QUALITY, 70])
                jpeg_bytes = jpeg.tobytes()

                r1 = requests.get(
                    "https://slack.com/api/files.getUploadURLExternal",
                    headers=headers,
                    params={"filename": "frame.jpg", "length": len(jpeg_bytes)},
                    timeout=10,
                ).json()
                if not r1.get("ok"):
                    print(f"  [Slack] getUploadURL: err={r1.get('error', '-')}")
                    return

                requests.post(
                    r1["upload_url"],
                    data=jpeg_bytes,
                    headers={"Content-Type": "image/jpeg"},
                    timeout=10,
                )

                r3 = requests.post(
                    "https://slack.com/api/files.completeUploadExternal",
                    headers={**headers, "Content-Type": "application/json"},
                    json={
                        "files": [{"id": r1["file_id"], "title": "frame.jpg"}],
                        "channel_id": SLACK_CHANNEL,
                        "initial_comment": msg,
                    },
                    timeout=10,
                ).json()
                print(f"  [Slack] thumbnail: ok={r3.get('ok')} err={r3.get('error', '-')}")
            except Exception as e:
                print(f"  [Slack] thumbnail error: {e}")
        # 2b) text-only message (no thumbnail)
        else:
            try:
                r = requests.post(
                    "https://slack.com/api/chat.postMessage",
                    headers={**headers, "Content-Type": "application/json"},
                    json={"channel": SLACK_CHANNEL, "text": msg},
                    timeout=10,
                ).json()
                print(f"  [Slack] text: ok={r.get('ok')} err={r.get('error', '-')}")
            except Exception as e:
                print(f"  [Slack] text error: {e}")

    threading.Thread(target=_send, daemon=True).start()


# ============================================================
#  Flow grid (shared renderer)
# ============================================================

GRID_COLS = 8
GRID_THUMB_W = 60
GRID_THUMB_H = 120
GRID_LABEL_H = 24
GRID_SEP = 2


def compose_flow_grid(frames):
    """Create grid of frames (8 per row) with state labels.

    Args:
        frames: list of (state_name, frame_bgr)
    Returns: numpy BGR image or None.
    """
    if not frames:
        return None

    n = len(frames)
    cols = GRID_COLS
    rows = (n + cols - 1) // cols

    cell_w = GRID_THUMB_W + GRID_SEP
    cell_h = GRID_THUMB_H + GRID_LABEL_H + GRID_SEP
    total_w = cell_w * cols - GRID_SEP
    total_h = cell_h * rows - GRID_SEP
    grid = np.zeros((total_h, total_w, 3), dtype=np.uint8)

    font = cv2.FONT_HERSHEY_PLAIN
    scale = 0.6
    for i, (state_name, frame) in enumerate(frames):
        r = i // cols
        c = i % cols
        x = c * cell_w
        y = r * cell_h

        thumb = cv2.resize(frame, (GRID_THUMB_W, GRID_THUMB_H))
        grid[y:y + GRID_THUMB_H, x:x + GRID_THUMB_W] = thumb

        # label (two lines for long names)
        label = state_name
        if len(label) > 10:
            mid = label.rfind("-", 0, 11)
            if mid > 0:
                line1, line2 = label[:mid], label[mid + 1:]
            else:
                line1, line2 = label[:10], label[10:]
            cv2.putText(grid, line1, (x + 1, y + GRID_THUMB_H + 10),
                        font, scale, (200, 200, 200), 1)
            cv2.putText(grid, line2[:12], (x + 1, y + GRID_THUMB_H + 20),
                        font, scale, (200, 200, 200), 1)
        else:
            cv2.putText(grid, label, (x + 1, y + GRID_THUMB_H + 10),
                        font, scale, (200, 200, 200), 1)

    return grid


def _upload_grid(jpeg_bytes, filename, msg, tag):
    """Upload a grid JPEG to Slack (runs in thread)."""
    try:
        headers = {"Authorization": f"Bearer {SLACK_BOT_TOKEN}"}
        r1 = requests.get(
            "https://slack.com/api/files.getUploadURLExternal",
            headers=headers,
            params={"filename": filename, "length": len(jpeg_bytes)},
            timeout=10,
        ).json()
        if not r1.get("ok"):
            print(f"  [{tag}] getUploadURL: err={r1.get('error', '-')}")
            return

        requests.post(
            r1["upload_url"],
            data=jpeg_bytes,
            headers={"Content-Type": "image/jpeg"},
            timeout=10,
        )

        r3 = requests.post(
            "https://slack.com/api/files.completeUploadExternal",
            headers={**headers, "Content-Type": "application/json"},
            json={
                "files": [{"id": r1["file_id"], "title": filename}],
                "channel_id": SLACK_CHANNEL,
                "initial_comment": msg,
            },
            timeout=10,
        ).json()
        print(f"  [{tag}] uploaded: ok={r3.get('ok')} err={r3.get('error', '-')}")
    except Exception as e:
        print(f"  [{tag}] upload error: {e}")


# ============================================================
#  Full test (start → INFORMATION-COMPLETE-DOWNLOAD → HOME)
# ============================================================
full_test_frames = []   # [(state_name, frame_bgr), ...]
_test_start_time = None


def save_full_test_frame(state_name, frame):
    """Append a snapshot for the full test flow."""
    global _test_start_time
    if frame is not None:
        if not full_test_frames:
            _test_start_time = time.strftime("%Y-%m-%d %H:%M:%S")
        full_test_frames.append((state_name, frame.copy()))
        print(f"  [FullTest] #{len(full_test_frames)}: {state_name}")


def reset_full_test():
    """Clear full test data for next run."""
    global _test_start_time
    full_test_frames.clear()
    _test_start_time = None


def send_full_test_result(script, extra_msg=""):
    """Compose full test grid and upload to Slack (non-blocking)."""
    grid = compose_flow_grid(full_test_frames)
    if grid is None:
        return
    if not SLACK_BOT_TOKEN or not SLACK_CHANNEL:
        print(f"  [FullTest] grid composed {grid.shape} but Slack not configured")
        return

    end_time = time.strftime("%Y-%m-%d %H:%M:%S")
    n_frames = len(full_test_frames)
    states_str = " -> ".join(s for s, _ in full_test_frames)
    start_time = _test_start_time or "?"
    _, jpeg = cv2.imencode(".jpg", grid, [cv2.IMWRITE_JPEG_QUALITY, 85])
    jpeg_bytes = jpeg.tobytes()

    msg = (f"\u2705 [{script}] device {_device_id}: test complete!\n"
           f"Start: {start_time}  End: {end_time}\n"
           f"FSM transitions: {n_frames}\n"
           f"{states_str}")
    if extra_msg:
        msg += f"\n\n{extra_msg}"

    threading.Thread(
        target=_upload_grid,
        args=(jpeg_bytes, "test_result.jpg", msg, "FullTest"),
        daemon=True,
    ).start()


# ============================================================
#  Subtotal (SPECIAL-REWARD → REWARD-NEXT)
# ============================================================
subtotal_frames = []    # [(state_name, frame_bgr), ...]
_subtotal_start_time = None
_subtotal_count = 0


def save_subtotal_frame(state_name, frame):
    """Append a snapshot for the current subtotal segment."""
    global _subtotal_start_time
    if frame is not None:
        if not subtotal_frames:
            _subtotal_start_time = time.strftime("%Y-%m-%d %H:%M:%S")
        subtotal_frames.append((state_name, frame.copy()))


def reset_subtotal():
    """Clear subtotal frames for next segment."""
    global _subtotal_start_time
    subtotal_frames.clear()
    _subtotal_start_time = None


def send_subtotal_result(script, extra_msg=""):
    """Compose subtotal grid and upload to Slack (non-blocking)."""
    global _subtotal_count
    _subtotal_count += 1
    grid = compose_flow_grid(subtotal_frames)
    if grid is None:
        return
    if not SLACK_BOT_TOKEN or not SLACK_CHANNEL:
        print(f"  [Subtotal] grid composed {grid.shape} but Slack not configured")
        return

    end_time = time.strftime("%Y-%m-%d %H:%M:%S")
    n_frames = len(subtotal_frames)
    states_str = " -> ".join(s for s, _ in subtotal_frames)
    start_time = _subtotal_start_time or "?"
    _, jpeg = cv2.imencode(".jpg", grid, [cv2.IMWRITE_JPEG_QUALITY, 85])
    jpeg_bytes = jpeg.tobytes()

    msg = (f"\U0001f4ca [{script}] device {_device_id}: "
           f"subtotal #{_subtotal_count}\n"
           f"Start: {start_time}  End: {end_time}\n"
           f"FSM transitions: {n_frames}\n"
           f"{states_str}")
    if extra_msg:
        msg += f"\n\n{extra_msg}"

    threading.Thread(
        target=_upload_grid,
        args=(jpeg_bytes, f"subtotal_{_subtotal_count}.jpg", msg, "Subtotal"),
        daemon=True,
    ).start()


# ============================================================
#  Low-level API
# ============================================================

def init(device_id: str):
    """Set device ID (must be called before any mouse operation)."""
    global _device_id
    _device_id = device_id
    print(f"[common] device_id = {device_id}")


def _api_url() -> str:
    return f"{API_BASE}/{_device_id}/00/00"


def send(op: int, x: int, y: int, delay: float = MOVE_DELAY):
    """Send a single mouse report."""
    global _seq
    _seq += 1
    url = _api_url()
    payload = {"type": "mouse", "command": f"{op} {x} {y}", "seq": f"{_seq}"}
    print(f"  [API] POST {url} {payload}")
    resp = requests.post(url, json=payload)
    print(f"  [API] -> {resp.status_code}")
    if delay > 0:
        time.sleep(delay)


def _send_batch(commands: list):
    """Send a batch of commands in one packet with random padding."""
    pad = "x" * random.randint(PAD_MIN, PAD_MAX)
    payload = {"type": "mouse", "commands": commands, "p": pad}
    url = _api_url()
    resp = requests.post(url, json=payload)
    print(f"  [API] POST {url} batch={len(commands)} pad={len(pad)} -> {resp.status_code}")


def _chunked_move(op: int, dx: int, dy: int):
    """Move in MAX_DELTA chunks, sent as random-sized batches."""
    global _cx, _cy
    print(f"_chunked_move:  {dx}, {dy}\n")

    # Collect all chunks first
    chunks = []
    while dx != 0 or dy != 0:
        sx = max(-MAX_DELTA, min(MAX_DELTA, dx))
        sy = max(-MAX_DELTA, min(MAX_DELTA, dy))
        chunks.append(f"{op} {sx} {sy}")
        dx -= sx
        dy -= sy
        _cx += sx
        _cy += sy

    # Send in random-sized batches
    i = 0
    while i < len(chunks):
        n = random.randint(BATCH_MIN, BATCH_MAX)
        batch = chunks[i:i + n]
        _send_batch(batch)
        i += len(batch)
        time.sleep(MOVE_DELAY * len(batch))




# ============================================================
#  High-level operations
# ============================================================

def _sweep_distance():
    """Return sweep distance that guarantees reaching the corner."""
    return max(RESET_SWEEP, screen_w, screen_h)


def reset_origin():
    """Cursor to top-left (0,0) via large negative deltas."""
    global _cx, _cy
    sweep = _sweep_distance()
    steps = sweep // 100 + 1
    cmds = [f"0 -100 -100" for _ in range(steps)]
    _send_batch(cmds)
    time.sleep(0.01 * steps)
    _cx = 0
    _cy = 0


def reset_origin_visual():
    """Cursor to top-left with visual feedback.

    First sweep to bottom-right so the user can see the cursor moving,
    then sweep far left/up to guarantee reaching (0,0).
    """
    global _cx, _cy
    sweep = _sweep_distance()
    step = 20
    n_left = sweep // step + 1
    print(f"[reset_origin_visual] → top-left origin ({n_left} steps, sweep={sweep}) ...")

    # Collect all commands, send in random batches
    cmds = [f"0 {-step} {-step}" for _ in range(n_left)]
    i = 0
    while i < len(cmds):
        n = random.randint(BATCH_MIN, BATCH_MAX)
        batch = cmds[i:i + n]
        _send_batch(batch)
        i += len(batch)
        time.sleep(MOVE_DELAY * len(batch))

    _cx = 0
    _cy = 0
    print("[reset_origin_visual] done")


def move_to(x: int, y: int):
    """Move cursor to absolute position (from origin)."""
    print(f"move_to : {_cx} , {x}, {_cy} , {y}")
    _chunked_move(0, x - _cx, y - _cy)


def click(x: int, y: int, repeat: int = 1, interval: float = 0.3):
    """Tap at absolute position.

    repeat:   number of clicks
    interval: delay between clicks (s)
    """
    print(f"click {x} {y} (x{repeat})")
    move_to(x, y)
    for i in range(repeat):
        send(1, 0, 0, delay=CLICK_HOLD)      # mouse-down
        send(0, 0, 0, delay=0.1)             # mouse-up
        if i < repeat - 1:
            time.sleep(interval)


def click_pct(rx: float, ry: float, repeat: int = 1, interval: float = 0.3):
    """Tap at relative position (0.0-1.0 of screen)."""
    click(int(screen_w * rx), int(screen_h * ry), repeat=repeat, interval=interval)


def long_press(x: int, y: int, duration: float = 1.0):
    """Long press at absolute position."""
    move_to(x, y)
    send(1, 0, 0, delay=duration)
    send(0, 0, 0, delay=0.1)


def drag(x1, y1, x2, y2, steps: int = 20):
    """Drag from (x1,y1) to (x2,y2) with smooth interpolation."""
    move_to(x1, y1)
    send(1, 0, 0, delay=0.1)                 # mouse-down

    # Collect intermediate drag commands
    dx = x2 - x1
    dy = y2 - y1
    cmds = []
    for i in range(1, steps + 1):
        sx = (dx * i // steps) - (dx * (i - 1) // steps)
        sy = (dy * i // steps) - (dy * (i - 1) // steps)
        cmds.append(f"1 {sx} {sy}")

    # Send in random batches
    i = 0
    while i < len(cmds):
        n = random.randint(BATCH_MIN, BATCH_MAX)
        batch = cmds[i:i + n]
        _send_batch(batch)
        i += len(batch)
        time.sleep(0.02 * len(batch))

    global _cx, _cy
    _cx = x2
    _cy = y2
    time.sleep(0.1)
    send(0, 0, 0, delay=0.1)                 # mouse-up


def wait(sec: float):
    """Sleep with log."""
    print(f"  wait {sec:.1f}s")
    time.sleep(sec)


# ============================================================
#  Scene template utilities
# ============================================================

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


def make_roi_rect(frame_h, frame_w, roi_x, roi_y, roi_w, roi_h):
    """Convert normalized ROI to pixel coordinates."""
    x1 = int(frame_w * roi_x)
    y1 = int(frame_h * roi_y)
    x2 = int(frame_w * (roi_x + roi_w))
    y2 = int(frame_h * (roi_y + roi_h))
    return x1, y1, x2, y2


def load_templates(snapshot_dir, scene_regions):
    """Load template images grouped by scene name.

    Args:
        snapshot_dir: directory containing snapshot JPEGs (name_N.jpg)
        scene_regions: dict of scene_name -> [(x, y, w, h), ...]

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
        if name in scene_regions:
            region_hists = []
            for region in scene_regions[name]:
                region_hists.append([calc_hist(crop_region(img, region)) for img in imgs])
            templates_region[name] = region_hists
        n_regions = len(scene_regions.get(name, []))
        print(f"  template: {name:35s} x{len(imgs)}"
              f"{'  +' + str(n_regions) + ' regions' if n_regions else ''}")
    return templates_hist, templates_region


# ============================================================
#  Object template detection (sliding-window classify)
# ============================================================

def load_obj_templates(obj_dir):
    """Load object templates from *obj_dir*.

    Naming convention: ``{name}_{nn}.jpg``
      e.g. ``bt-ok-modal-dialog_00.jpg``, ``bt-ok-modal-dialog_01.jpg``

    Returns:
        dict  name -> {"hists": [hist, ...], "w": int, "h": int}
        *w* / *h* are average template pixel dimensions (used as ROI size).
    """
    raw = {}
    for path in sorted(glob.glob(os.path.join(obj_dir, "*.jpg"))):
        basename = os.path.splitext(os.path.basename(path))[0]
        parts = basename.rsplit("_", 1)
        if len(parts) == 2 and parts[1].isdigit():
            name = parts[0]
        else:
            continue
        img = cv2.imread(path)
        if img is None:
            continue
        raw.setdefault(name, []).append(img)

    result = {}
    for name, imgs in raw.items():
        hists = [calc_hist(img) for img in imgs]
        avg_w = int(sum(img.shape[1] for img in imgs) / len(imgs))
        avg_h = int(sum(img.shape[0] for img in imgs) / len(imgs))
        result[name] = {"hists": hists, "w": avg_w, "h": avg_h}
        print(f"  obj_template: {name:35s} x{len(imgs)}  size=({avg_w}x{avg_h})")
    return result


def detect_obj_in_frame(frame, obj_templates,
                        dx_step=0.1, dy_step=0.3, threshold=0.5):
    """Slide ROI windows across *frame* and classify against *obj_templates*.

    The frame is tiled into ROI windows of size
    ``(dx_step * fw, dy_step * fh)`` starting from the top-left corner.
    Each ROI's HSV histogram is compared against every template histogram
    (scale-invariant — template pixel size need not match ROI size).

    Args:
        frame:          input image (same format as roi_resized).
        obj_templates:  dict returned by :func:`load_obj_templates`.
        dx_step:        horizontal stride / ROI width as fraction of frame (default 0.1).
        dy_step:        vertical   stride / ROI height as fraction of frame (default 0.3).
        threshold:      minimum HSV-histogram correlation to accept.

    Returns:
        ``(name, cx, cy)`` with *cx* / *cy* normalised 0.0–1.0,
        or ``None`` if nothing matched.
    """
    fh, fw = frame.shape[:2]
    roi_w = max(1, int(fw * dx_step))
    roi_h = max(1, int(fh * dy_step))

    best = None
    best_corr = threshold

    ry = 0
    while ry + roi_h <= fh:
        rx = 0
        while rx + roi_w <= fw:
            crop = frame[ry:ry + roi_h, rx:rx + roi_w]
            crop_hist = calc_hist(crop)

            for name, info in obj_templates.items():
                for tmpl_hist in info["hists"]:
                    corr = cv2.compareHist(crop_hist, tmpl_hist,
                                           cv2.HISTCMP_CORREL)
                    if corr > best_corr:
                        cx = (rx + roi_w / 2.0) / fw
                        cy = (ry + roi_h / 2.0) / fh
                        best = (name, cx, cy)
                        best_corr = corr

            rx += roi_w
        ry += roi_h

    if best is None:
        print("  [OBJ] no object detected in frame")
        return None

    name, cx, cy = best
    print(f"  [OBJ] detected: {name} at ({cx:.3f},{cy:.3f}) corr={best_corr:.3f}")
    return best


# ============================================================
#  Screen capture / CV  (stub -- implement per environment)
# ============================================================

def capture_screen():
    """Capture current screen.
    Returns: numpy ndarray (BGR) or None.
    TODO: implement via WebRTC video frame, adb screencap, etc.
    """
    return None


def detect_hamburger_menu(img) -> bool:
    """Return True if hamburger-menu overlay is visible.
    TODO: implement with cv2.matchTemplate or similar.
    """
    if img is None:
        return False
    # Example:
    # import cv2, numpy as np
    # tmpl = cv2.imread("templates/hamburger_menu.png")
    # res = cv2.matchTemplate(img, tmpl, cv2.TM_CCOEFF_NORMED)
    # return res.max() > 0.8
    return False


def detect_home_screen(img) -> bool:
    """Return True if Monster Strike home screen is visible."""
    if img is None:
        return False
    return False


# ============================================================
#  Calibration
# ============================================================

def calibrate(manual_size: tuple = None):
    """Detect screen size in HID units.

    If manual_size is given as (w, h) in HID units, skip auto-detection.
    Otherwise: scan from origin with step+click until hamburger
    menu is detected by CV.
    """
    global screen_w, screen_h, _cx, _cy

    if manual_size:
        screen_w, screen_h = manual_size
        print(f"[calibrate] manual: {screen_w}x{screen_h}")
        reset_origin_visual()
        return True

    print("[calibrate] reset to origin ...")
    reset_origin_visual()

    print(f"[calibrate] scanning (step={SCAN_STEP}) ...")
    max_steps = 500                            # safety limit
    for step in range(1, max_steps + 1):
        send(0, SCAN_STEP, SCAN_STEP)
        _cx += SCAN_STEP
        _cy += SCAN_STEP

        # click at current position
        send(1, 0, 0, delay=CLICK_HOLD)
        send(0, 0, 0, delay=0.3)

        img = capture_screen()
        if detect_hamburger_menu(img):
            # hamburger icon is near bottom-right corner
            screen_w = int(_cx / 0.95)
            screen_h = int(_cy / 0.97)
            print(f"[calibrate] detected: {screen_w}x{screen_h}")

            # close menu
            reset_origin()
            click(screen_w // 2, screen_h // 4)
            wait(API_WAIT_DURATION)
            return True

        if step % 50 == 0:
            print(f"  step {step}  pos=({_cx},{_cy})")

    print("[calibrate] FAILED")
    return False


# ============================================================
#  Actions (callable from CLI)
# ============================================================

ACTIONS = {}


def action(name):
    """Decorator to register a CLI action."""
    def _reg(fn):
        ACTIONS[name] = fn
        return fn
    return _reg


@action("calibrate")
def act_calibrate(args):
    """Run calibration.  [hid_w hid_h]"""
    manual = None
    if len(args) == 2:
        manual = (int(args[0]), int(args[1]))
    calibrate(manual_size=manual)


@action("quest_bt_click")
def act_quest_bt_click(args):
    """Click Quest button.  <hid_w> <hid_h>"""
    if len(args) < 2:
        print("quest_bt_click requires: <hid_w> <hid_h>")
        return
    calibrate(manual_size=(int(args[0]), int(args[1])))
    reset_origin()
    print("[action] tap クエスト (0.50, 0.85) x5")
    click_pct(0.50, 0.85, repeat=1)


@action("normal_bt_click")
def act_normal_bt_click(args):
    """Click ノーマル button.  <hid_w> <hid_h>"""
    if len(args) < 2:
        print("normal_bt_click requires: <hid_w> <hid_h>")
        return
    calibrate(manual_size=(int(args[0]), int(args[1])))
    reset_origin()
    print("[action] tap ノーマル (0.50, 0.50)")
    click_pct(0.50, 0.50, repeat=1)


@action("normal_ikusei_bt_click")
def act_normal_ikusei_bt_click(args):
    """Click ノーマル育成 button.  <hid_w> <hid_h>"""
    if len(args) < 2:
        print("normal_ikusei_bt_click requires: <hid_w> <hid_h>")
        return
    calibrate(manual_size=(int(args[0]), int(args[1])))
    reset_origin()
    print("[action] tap ノーマル育成 (0.27, 0.72)")
    click_pct(0.27, 0.72, repeat=1)


@action("shojin_bt_click")
def act_shojin_bt_click(args):
    """Scroll down to bottom & click 初陣.  <hid_w> <hid_h>"""
    if len(args) < 2:
        print("shojin_bt_click requires: <hid_w> <hid_h>")
        return
    calibrate(manual_size=(int(args[0]), int(args[1])))

    # scroll down to bottom
    for s in range(1, 4):
        reset_origin()
        print(f"[action] scroll down.. {s}")
        x1 = int(screen_w * 0.50)
        y1 = int(screen_h * 0.90)
        x2 = int(screen_w * 0.50)
        y2 = int(screen_h * 0.30)
        drag(x1, y1, x2, y2)
        wait(API_WAIT_DURATION)

    # tap 初陣
    reset_origin()
    print("[action] tap 初陣 (0.50, 0.86)")
    click_pct(0.50, 0.86, repeat=1)


@action("karyu_bt_click")
def act_karyu_bt_click(args):
    """Click 火竜の試練 button.  <hid_w> <hid_h>"""
    if len(args) < 2:
        print("karyu_bt_click requires: <hid_w> <hid_h>")
        return
    calibrate(manual_size=(int(args[0]), int(args[1])))
    reset_origin()
    print("[action] tap 火竜の試練 (0.50, 0.60)")
    click_pct(0.50, 0.60, repeat=1)


@action("welcome_bt_click")
def act_welcome_bt_click(args):
    """Click Welcome Quest.  <hid_w> <hid_h>"""
    if len(args) < 2:
        print("karyu_bt_click requires: <hid_w> <hid_h>")
        return
    calibrate(manual_size=(int(args[0]), int(args[1])))
    reset_origin()
    print("[action] tap Welcome Quest")
    click_pct(0.50, 0.38, repeat=1)


@action("solo_bt_click")
def act_solo_bt_click(args):
    """Click ソロ button.  <hid_w> <hid_h>"""
    if len(args) < 2:
        print("solo_bt_click requires: <hid_w> <hid_h>")
        return
    calibrate(manual_size=(int(args[0]), int(args[1])))
    reset_origin()
    print("[action] tap ソロ (0.25, 0.60)")
    click_pct(0.25, 0.60, repeat=1)


@action("helper_select")
def act_helper_select(args):
    """Scroll to みんなのクリアモンスター & select.  <hid_w> <hid_h>"""
    if len(args) < 2:
        print("helper_select requires: <hid_w> <hid_h>")
        return
    calibrate(manual_size=(int(args[0]), int(args[1])))

    for step in range(1, 4):
        reset_origin()
        print(f"[action] scroll up, reset.. {step}")
        x1 = int(screen_w * 0.50)
        y1 = int(screen_h * 0.30)
        x2 = int(screen_w * 0.50)
        y2 = int(screen_h * 0.90)
        drag(x1, y1, x2, y2)
        wait(API_WAIT_DURATION)

    reset_origin()

    # scroll down: drag (0.5, 0.5) → (0.5, 0.2)
    x1 = int(screen_w * 0.50)
    y1 = int(screen_h * 0.60)
    x2 = int(screen_w * 0.50)
    y2 = int(screen_h * 0.20)
    print(f"[action] scroll down: drag ({x1},{y1}) → ({x2},{y2})")
    drag(x1, y1, x2, y2)
    wait(API_WAIT_DURATION)
    # select helper
    reset_origin()
    print("[action] tap helper (0.50, 0.46)")
    click_pct(0.50, 0.46, repeat=1)


@action("shutsugeki_bt_click")
def act_shutsugeki_bt_click(args):
    """Click 出撃 button (deck screen).  <hid_w> <hid_h>"""
    if len(args) < 2:
        print("shutsugeki_bt_click requires: <hid_w> <hid_h>")
        return
    calibrate(manual_size=(int(args[0]), int(args[1])))
    reset_origin()
    print("[action] tap 出撃")
    click_pct(0.50, 0.66, repeat=1)


@action("play_turn")
def act_play_turn(args):
    """Play 1 turn (random flick from center).  <hid_w> <hid_h>"""
    if len(args) < 2:
        print("play_turn requires: <hid_w> <hid_h>")
        return
    calibrate(manual_size=(int(args[0]), int(args[1])))
    reset_origin()

    # random angle: 10deg increments (0, 10, 20, ... 350)
    angle_deg = random.choice(range(0, 360, 10))
    angle_rad = math.radians(angle_deg)
    # random strength: 100-200 HID units
    strength = random.randint(100, 300)
    # random hold time: 1-4 seconds
    hold_sec = random.uniform(1.0, 4.0)

    dx = int(strength * math.cos(angle_rad))
    dy = int(strength * math.sin(angle_rad))

    cx = int(screen_w * 0.50)
    cy = int(screen_h * 0.50)

    print(f"[action] play_turn: angle={angle_deg}deg strength={strength} "
          f"hold={hold_sec:.1f}s  drag ({cx},{cy})→({cx+dx},{cy+dy})")

    # move to center
    move_to(cx, cy)
    # mouse down
    send(1, 0, 0, delay=0.1)
    # drag to target
    _chunked_move(1, dx, dy)
    # hold (aiming)
    print(f"  holding {hold_sec:.1f}s ...")
    time.sleep(hold_sec)
    # release
    send(0, 0, 0, delay=0.1)
    print("[action] released")


@action("clear_ok")
def act_clear_ok(args):
    """Click OK on quest clear dialog.  <hid_w> <hid_h>"""
    if len(args) < 2:
        print("clear_ok requires: <hid_w> <hid_h>")
        return
    calibrate(manual_size=(int(args[0]), int(args[1])))
    reset_origin()
    print("[action] tap OK (0.50, 0.63)")
    click_pct(0.50, 0.63, repeat=1)
    


@action("special_reward")
def act_special_reward(args):
    """Click special reward (center).  <hid_w> <hid_h>"""
    if len(args) < 2:
        print("special_reward requires: <hid_w> <hid_h>")
        return
    calibrate(manual_size=(int(args[0]), int(args[1])))
    reset_origin()
    print("[action] tap center (0.50, 0.50)")
    click_pct(0.50, 0.50, repeat=1)


# --- Modal dialog OK actions (confirm → click OK) ---
MODAL_DIALOGS = {
    "confirm_ok":              (0.50, 0.68),
    "information_ok":          (0.50, 0.90),
    "information_gaze_ok":     (0.50, 0.70),
    "information_gimic_ok":    (0.50, 0.70),
    "login_bonus_ok":          (0.50, 0.70),
    "login_stamp_ok":          (0.50, 0.64),
    "login_stamp2_ok":         (0.50, 0.81),
    "need_download_ok":        (0.34, 0.74),
    "tutorial_boss_atack_ok":  (0.50, 0.76),
    "tutorial_yujo_combo_ok":  (0.50, 0.76),
    "tutorial_damage_ok":      (0.50, 0.79),
    "tutorial_atack_ok":       (0.50, 0.74),
    "need_start_ok":           (0.50, 0.61),
    "calender_ok":             (0.50, 0.50),
    "event_message_dialog_ok": (0.50, 0.50),
    "reward_chara_ok":         (0.50, 0.50),
    "tutorial_item_ok":        (0.50, 0.78),
    "tutorial_congraturate_ok": (0.50, 0.70),
    "information_wait_ok":     (0.50, 0.81),
    "information_complete_download_ok": (0.50, 0.68),
    "information_welcome_ok":  (0.50, 0.86),
    "information_striker_navi_ok": (0.50, 0.88),
    "tutorial_clear_ok":       (0.50, 0.61),
    "information_gimic2_ok":   (0.50, 0.78),
}

for _name, (_px, _py) in MODAL_DIALOGS.items():
    def _make_action(name, px, py):
        def _act(args):
            if len(args) < 2:
                print(f"{name} requires: <hid_w> <hid_h>")
                return
            calibrate(manual_size=(int(args[0]), int(args[1])))
            reset_origin()
            dw = int(screen_w * 0.01)
            dh = int(screen_h * 0.01)
            print(f"[action] tap OK ({px}, {py}) +4pts")
            # center
            click_pct(px, py, repeat=1)
            # up/down/left/right (+0.01 offset) in one batch
            _send_batch([
                f"0 0 {-dh}",        # move up
                "1 0 0", "0 0 0",    # click
                f"0 0 {2 * dh}",     # move down
                "1 0 0", "0 0 0",    # click
                f"0 {-dw} {-dh}",    # move left
                "1 0 0", "0 0 0",    # click
                f"0 {2 * dw} 0",     # move right
                "1 0 0", "0 0 0",    # click
            ])
        _act.__doc__ = f"Click OK on {name.replace('_', ' ')} dialog.  <hid_w> <hid_h>"
        return _act
    ACTIONS[_name] = _make_action(_name, _px, _py)


@action("need_nickname_ok")
def act_need_nickname_ok(args):
    """Click input field, auto-fill, then OK on nickname dialog.  <hid_w> <hid_h>"""
    if len(args) < 2:
        print("need_nickname_ok requires: <hid_w> <hid_h>")
        return
    calibrate(manual_size=(int(args[0]), int(args[1])))
    # 1. tap input field
    reset_origin()
    print("[action] tap input field (0.50, 0.50)")
    click_pct(0.50, 0.51, repeat=1)
    wait(UI_WAIT)
    # 2. tap auto-fill
    reset_origin()
    print("[action] tap auto-fill")
    click_pct(0.36, 0.82, repeat=1)
    wait(UI_WAIT)
    # 3. tap OK
    reset_origin()
    print("[action] tap OK")
    click_pct(0.50, 0.58, repeat=1)
    # 3.1 times 2
    reset_origin()
    print("[action] tap OK")
    click_pct(0.50, 0.58, repeat=1)


@action("confirm_retry_ok")
def act_confirm_retry_ok(args):
    """Click confirm-retry twice (second confirmation appears).  <hid_w> <hid_h>"""
    if len(args) < 2:
        print("confirm_retry_ok requires: <hid_w> <hid_h>")
        return
    calibrate(manual_size=(int(args[0]), int(args[1])))
    # 1. first click
    reset_origin()
    print("[action] tap confirm-retry (0.65, 0.64)")
    click_pct(0.65, 0.64, repeat=1)
    wait(UI_WAIT)
    # 2. second click (same position, second confirmation dialog)
    reset_origin()
    print("[action] tap confirm-retry again (0.65, 0.64)")
    click_pct(0.65, 0.62, repeat=1)


@action("information_gacha_ok")
def act_information_gacha_ok(args):
    """Click OK on gacha info, wait, then tap home.  <hid_w> <hid_h>"""
    if len(args) < 2:
        print("information_gacha_ok requires: <hid_w> <hid_h>")
        return
    calibrate(manual_size=(int(args[0]), int(args[1])))
    reset_origin()
    print("[action] tap OK (0.50, 0.82)")
    click_pct(0.50, 0.82, repeat=1)
    wait(3.0)
    reset_origin()
    print("[action] tap home (0.12, 0.92)")
    click_pct(0.12, 0.98, repeat=1)


@action("reward_next")
def act_reward_next(args):
    """Click reward page 2.  <hid_w> <hid_h>"""
    if len(args) < 2:
        print("reward_next requires: <hid_w> <hid_h>")
        return
    calibrate(manual_size=(int(args[0]), int(args[1])))
    reset_origin()
    print("[action] tap reward next (0.50, 0.98)")
    click_pct(0.50, 0.98, repeat=1)


@action("cv_ok_click")
def act_cv_ok_click(args):
    """Click OK at CV-detected position.  <hid_w> <hid_h> <px> <py>"""
    if len(args) < 4:
        print("cv_ok_click requires: <hid_w> <hid_h> <px> <py>")
        return
    calibrate(manual_size=(int(args[0]), int(args[1])))
    reset_origin()
    px, py = float(args[2]), float(args[3])
    print(f"[action] CV OK click at ({px:.3f}, {py:.3f})")
    click_pct(px, py, repeat=1)
    # Robustness: click 4 offset points (±1% of screen)
    dw = int(screen_w * 0.01)
    dh = int(screen_h * 0.01)
    _send_batch([
        f"0 0 {-dh}", "1 0 0", "0 0 0",
        f"0 0 {2 * dh}", "1 0 0", "0 0 0",
        f"0 {-dw} {-dh}", "1 0 0", "0 0 0",
        f"0 {2 * dw} 0", "1 0 0", "0 0 0",
    ])


if __name__ == "__main__":
    import sys

    usage = (
        "Usage: python common.py <device_id> <action> [args...]\n"
        "\n"
        "Actions:\n"
    )
    for name, fn in ACTIONS.items():
        usage += f"  {name:20s} {fn.__doc__ or ''}\n"

    if len(sys.argv) < 3:
        print(usage)
        sys.exit(1)

    dev = sys.argv[1]
    cmd = sys.argv[2]
    rest = sys.argv[3:]

    if cmd not in ACTIONS:
        print(f"Unknown action: {cmd}\n")
        print(usage)
        sys.exit(1)

    init(dev)
    ACTIONS[cmd](rest)
