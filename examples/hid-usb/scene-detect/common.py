"""Monster Strike auto-test: shared utilities.

USB HID mouse control via HTTP API.
Command format: "{op} {x} {y}"
  op=0: move / mouse-up
  op=1: mouse-down / drag
  x, y: relative delta (HID units, NOT pixels)

Note: HID delta ~100 moves the cursor roughly 1/4 of the screen.
      Full screen ≈ 400 HID units (varies by OS mouse acceleration).
"""

import os
import requests
import time
import math
import random

# --------------- config ---------------
API_BASE = os.environ.get("SFU_API_BASE", "http://192.168.124.45:8888/api/message")
_device_id = ""         # set by init(device_id)
MOVE_DELAY = 0.13       # inter-report delay (s)
CLICK_HOLD = 0.15       # mouse-down duration (s)
UI_WAIT = 1.0           # wait for UI transition (s)
SCAN_STEP = 10          # calibration scan step (px)
MAX_DELTA = 10          # max delta per-report (both dx, dy)

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
    print(f"  [API] POST {url} batch={len(commands)} pad={len(pad)}")
    resp = requests.post(url, json=payload)
    print(f"  [API] -> {resp.status_code}")


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

def reset_origin():
    """Cursor to top-left (0,0) via large negative deltas."""
    global _cx, _cy
    steps = RESET_SWEEP // 100 + 1            # e.g. 500/100+1 = 6
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
    step = 20
    n_left = RESET_SWEEP // step + 1           # → top-left
    print(f"[reset_origin_visual] → top-left origin ({n_left} steps) ...")

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
            wait(1.0)
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
        wait(1.0)

    # tap 初陣
    reset_origin()
    print("[action] tap 初陣 (0.50, 0.90)")
    click_pct(0.50, 0.90, repeat=1)


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
        wait(1.0)

    reset_origin()

    # scroll down: drag (0.5, 0.5) → (0.5, 0.2)
    x1 = int(screen_w * 0.50)
    y1 = int(screen_h * 0.60)
    x2 = int(screen_w * 0.50)
    y2 = int(screen_h * 0.20)
    print(f"[action] scroll down: drag ({x1},{y1}) → ({x2},{y2})")
    drag(x1, y1, x2, y2)
    wait(1.0)
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
    print("[action] tap 出撃 (0.50, 0.70)")
    click_pct(0.50, 0.70, repeat=1)


@action("play_turn")
def act_play_turn(args):
    """Play 1 turn (random flick from center).  <hid_w> <hid_h>"""
    if len(args) < 2:
        print("play_turn requires: <hid_w> <hid_h>")
        return
    calibrate(manual_size=(int(args[0]), int(args[1])))
    reset_origin()

    # random angle: 30deg increments (0, 30, 60, ... 330)
    angle_deg = random.choice(range(0, 360, 30))
    angle_rad = math.radians(angle_deg)
    # random strength: 100-200 HID units
    strength = random.randint(100, 200)
    # random hold time: 2-4 seconds
    hold_sec = random.uniform(2.0, 4.0)

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
    print("[action] tap OK (0.50, 0.65)")
    click_pct(0.50, 0.65, repeat=1)
    wait(1.0)
    reset_origin()
    print("[action] tap helper (0.50, 0.75)")
    click_pct(0.50, 0.78, repeat=1)
    


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


@action("reward_next")
def act_reward_next(args):
    """Click reward page 2.  <hid_w> <hid_h>"""
    if len(args) < 2:
        print("reward_next requires: <hid_w> <hid_h>")
        return
    calibrate(manual_size=(int(args[0]), int(args[1])))
    reset_origin()
    print("[action] tap reward next (0.50, 1.1)")
    click_pct(0.50, 0.999, repeat=1)


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
