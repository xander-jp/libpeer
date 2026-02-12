#!/usr/bin/env python3
"""Monster Strike auto-test: initial.py

Scenario: Game launch → Home screen.

1. Calibrate screen (scan for hamburger menu)
2. Dismiss initial animation (tap anywhere)
3. Dismiss pop-up dialogs (tap OK / confirm buttons)
4. Wait until home screen is displayed
"""

import sys
import common as c

# --------------- UI positions (% of screen) ---------------
# Tap target to dismiss splash / animation
SPLASH_TAP = (0.50, 0.50)

# "OK" / "確認" / "閉じる" dialog buttons (common positions)
DIALOG_OK_POSITIONS = [
    (0.50, 0.65),   # center OK button
    (0.50, 0.70),   # slightly lower
    (0.65, 0.65),   # right-side OK
    (0.50, 0.80),   # bottom OK
]

MAX_DIALOG_RETRIES = 10
ANIMATION_WAIT = 5.0     # initial animation duration (s)
DIALOG_WAIT = 2.0        # wait between dialog dismiss attempts


def dismiss_splash():
    """Tap center to skip initial animation."""
    print("[initial] waiting for splash animation ...")
    c.wait(ANIMATION_WAIT)

    print("[initial] tap to dismiss splash")
    c.click_pct(*SPLASH_TAP)
    c.wait(2.0)


def dismiss_dialogs():
    """Repeatedly tap common OK button positions to clear dialogs."""
    print("[initial] dismissing dialogs ...")

    for attempt in range(1, MAX_DIALOG_RETRIES + 1):
        img = c.capture_screen()

        if c.detect_home_screen(img):
            print(f"[initial] home screen detected (attempt {attempt})")
            return True

        # Try each possible OK button position
        for pos in DIALOG_OK_POSITIONS:
            c.click_pct(*pos)
            c.wait(DIALOG_WAIT)

        print(f"  attempt {attempt}/{MAX_DIALOG_RETRIES}")

    print("[initial] max retries reached (home screen not confirmed)")
    return False


def run(device_id: str, manual_size=None):
    print("=" * 50)
    print(" initial.py  -- Launch → Home screen")
    print("=" * 50)

    c.init(device_id)

    if not c.calibrate(manual_size=manual_size):
        print("[initial] calibration failed, abort")
        return False

    dismiss_splash()
    ok = dismiss_dialogs()

    if ok:
        print("[initial] DONE -- home screen ready")
    else:
        print("[initial] DONE -- home screen not confirmed, "
              "but dialogs were dismissed")
    return ok


if __name__ == "__main__":
    # Usage:
    #   python initial.py DEVICE_ID                 # auto-calibrate
    #   python initial.py DEVICE_ID 1170 2532       # manual screen size
    if len(sys.argv) < 2:
        print("Usage: python initial.py <device_id> [width height]")
        sys.exit(1)
    dev = sys.argv[1]
    manual = None
    if len(sys.argv) == 4:
        manual = (int(sys.argv[2]), int(sys.argv[3]))
    run(device_id=dev, manual_size=manual)
