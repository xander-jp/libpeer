#!/usr/bin/env python3
"""Monster Strike auto-test: home.py

Scenario: Home screen → Quest → Deploy (出撃).

Flow:
 1. [Home]  Tap "クエスト" button
 2. [Quest] Tap "ノーマル" tab (育成)
 3.         Tap quest list entry  (ノーマルクエスト)
 4.         Tap "初陣" quest
 5.         Tap "火竜の試練"
 6.         Tap "ソロ"
 7. [Helper] Select 2nd entry from "みんなのクリアモンスター"
 8. [Deck]  Keep current deck, tap "出撃"
"""

import sys
import common as c

# ===================================================================
#  UI positions -- percentage of screen (rx, ry)
#
#  Monster Strike portrait layout.  Adjust values to match
#  your device.  Use calibration + screenshot to fine-tune.
# ===================================================================

# Home screen
BTN_QUEST = (0.50, 0.85)          # "クエスト" button (bottom center)

# Quest category screen
TAB_NORMAL = (0.20, 0.18)         # "ノーマル" tab
BTN_NORMAL_IKUSEI = (0.50, 0.35)  # "ノーマル育成" entry

# Quest list
BTN_QUEST_SELECT = (0.50, 0.30)   # first quest in list (ノーマルクエスト)
BTN_SHOJIN = (0.50, 0.30)         # "初陣" quest entry
BTN_KARYU = (0.50, 0.45)          # "火竜の試練"

# Solo / Multi
BTN_SOLO = (0.25, 0.85)           # "ソロ" button

# Helper selection
BTN_MINNA_TAB = (0.70, 0.15)     # "みんなのクリアモンスター" tab
HELPER_2ND = (0.50, 0.38)         # 2nd entry from top

# Deck / Deploy
BTN_SHUTSUGEKI = (0.50, 0.90)     # "出撃" button

# Transition wait times (seconds)
WAIT_TRANSITION = 2.0
WAIT_LONG = 3.0


# ===================================================================
#  Steps
# ===================================================================

def step_quest():
    """Home → Tap quest button."""
    print("[home] tap クエスト")
    c.click_pct(*BTN_QUEST)
    c.wait(WAIT_TRANSITION)


def step_normal_ikusei():
    """Select ノーマル tab → ノーマル育成."""
    print("[home] tap ノーマル tab")
    c.click_pct(*TAB_NORMAL)
    c.wait(WAIT_TRANSITION)

    print("[home] tap ノーマル育成")
    c.click_pct(*BTN_NORMAL_IKUSEI)
    c.wait(WAIT_TRANSITION)


def step_select_quest():
    """Select ノーマルクエスト → 初陣 → 火竜の試練."""
    print("[home] tap ノーマルクエスト")
    c.click_pct(*BTN_QUEST_SELECT)
    c.wait(WAIT_TRANSITION)

    print("[home] tap 初陣クエスト")
    c.click_pct(*BTN_SHOJIN)
    c.wait(WAIT_TRANSITION)

    print("[home] tap 火竜の試練")
    c.click_pct(*BTN_KARYU)
    c.wait(WAIT_TRANSITION)


def step_solo():
    """Tap Solo button."""
    print("[home] tap ソロ")
    c.click_pct(*BTN_SOLO)
    c.wait(WAIT_LONG)


def step_select_helper():
    """Select helper: 2nd from top in みんなのクリアモンスター."""
    print("[home] tap みんなのクリアモンスター tab")
    c.click_pct(*BTN_MINNA_TAB)
    c.wait(WAIT_TRANSITION)

    print("[home] tap 2nd helper")
    c.click_pct(*HELPER_2ND)
    c.wait(WAIT_TRANSITION)


def step_deploy():
    """Keep deck as-is, tap 出撃."""
    print("[home] tap 出撃")
    c.click_pct(*BTN_SHUTSUGEKI)
    c.wait(WAIT_LONG)


# ===================================================================
#  Main
# ===================================================================

def run(device_id: str = None, manual_size=None):
    print("=" * 50)
    print(" home.py  -- Home → Quest → Deploy")
    print("=" * 50)

    if device_id:
        c.init(device_id)

    # Ensure screen size is set
    if c.screen_w == 0:
        if not c.calibrate(manual_size=manual_size):
            print("[home] calibration failed, abort")
            return False

    c.reset_origin()

    step_quest()
    step_normal_ikusei()
    step_select_quest()
    step_solo()
    step_select_helper()
    step_deploy()

    print("[home] DONE -- 出撃 pressed")
    return True


if __name__ == "__main__":
    # Usage:
    #   python home.py DEVICE_ID                 # auto-calibrate
    #   python home.py DEVICE_ID 1170 2532       # manual screen size
    if len(sys.argv) < 2:
        print("Usage: python home.py <device_id> [width height]")
        sys.exit(1)
    dev = sys.argv[1]
    manual = None
    if len(sys.argv) == 4:
        manual = (int(sys.argv[2]), int(sys.argv[3]))
    run(device_id=dev, manual_size=manual)
