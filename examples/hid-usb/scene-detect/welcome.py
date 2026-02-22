#!/usr/bin/env python3
"""Monster Strike scene detector - camera capture base."""

"""Welcome Auto-play."""

import argparse
import os
import queue
import threading
import time

import cv2
import numpy as np
from picamera2 import Picamera2

import common as hid
import moorefsm
from moorefsm import (
    S_UNKNOWN, S_HOME, S_EVENT, S_QUEST, S_NORMAL_QUEST,
    S_NORMAL_QUEST_UIJIN, S_NORMAL_QUEST_UIJIN_KARYU,
    S_HELPER_SELECT, S_DECK_SELECT, S_WELCOME_IN_PLAY,
    S_CLEAR_OK, S_SPECIAL_REWARD, S_REWARD_NEXT,
    S_CONFIRM, S_INFORMATION, S_INFORMATION_GAZE, S_INFORMATION_GIMIC,
    S_LOGIN_BONUS, S_LOGIN_STAMP, S_LOGIN_STAMP2,
    S_NEED_DOWNLOAD, S_NEED_NICKNAME,
    S_CONFIRM_RETRY, S_TUTORIAL_ATACK, S_TUTORIAL_BOSS_ATACK, S_TUTORIAL_YUJO_COMBO,
    S_NEED_START, S_CALENDER, S_EVENT_MESSAGE_DIALOG, S_REWARD_CHARA,
    S_TUTORIAL_ITEM, S_TUTORIAL_DAMAGE, S_TUTORIAL_CONGRATURATE,
    S_INFORMATION_WAIT, S_INFORMATION_COMPLETE_DOWNLOAD, S_INFORMATION_GACHA,
    S_INFORMATION_WELCOME, S_INFORMATION_STRIKER_NAVI, S_TUTORIAL_CLEAR,
    S_INFORMATION_GIMIC2,
    MODAL_STATES,
    ONNX_CONF_LOW, fsm_update,
)
from barchart import (
    CHART_W, TOAST_DURATION, draw_chart, draw_toast, draw_region_boxes,
)
from onnxif import (
    ONNX_MODEL_PATH, ONNX_LABELS_PATH, load_onnx_model, onnx_classify,
)

SAVE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "snapshots")
OBJ_TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "obj_templates")

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
        (0.01, 0.906, 0.98, 0.07),  # ok button
    ],
    "clear-ok": [
        (0.04, 0.556, 0.92, 0.069),
    ],
    "welcome-quest-00-in-play": [],
    "welcome-quest-01-in-play": [],
    "welcome-quest-02-in-play": [],
    "welcome-quest-03-in-play": [],
    "welcome-quest-04-in-play": [],
    "welcome-quest-05-in-play": [],
    "confirm":            [],
    "information":        [
        (0.01, 0.906, 0.98, 0.07),
    ],
    "information-gaze":   [],
    "information-gimic":  [],
    "login-bonus":        [],
    "login-stamp":        [
        (0.11, 0.562, 0.78, 0.07),
    ],
    "login-stamp2":       [
        (0.06, 0.766, 0.88, 0.06),
    ],
    "need-download":      [],
    "tutorial-boss-atack":[],
    "confirm-retry":      [],
    "tutorial-atack":     [],
    "tutorial-yujo-combo":[],
    "need-nickname":      [],
    "need-start":         [],
    "calender":           [],
    "event-message-dialog": [],
    "reward-chara":       [],
    "tutorial-quest-00-in-play": [],
    "tutorial-item":  [],
    "tutorial-damage": [],
    "tutorial-congraturate": [],
    "information-wait": [],
    "information-welcome": [],
    "information-striker-navi": [],
    "information-gacha": [
        (0.11, 0.712, 0.78, 0.07),
    ],
    "information-complete-download": [
        (0.01, 0.906, 0.98, 0.07),
    ],
    "tutorial-clear": [],
    "information-gimic2": [],
}

# --------------- FSM config ---------------

# Non-modal scene states
_SCENE_STATES = [
    S_HOME, S_EVENT, S_QUEST, S_NORMAL_QUEST, S_NORMAL_QUEST_UIJIN,
    S_NORMAL_QUEST_UIJIN_KARYU, S_HELPER_SELECT, S_DECK_SELECT,
    S_WELCOME_IN_PLAY, S_CLEAR_OK, S_SPECIAL_REWARD, S_REWARD_NEXT,
]

FSM_TRANSITIONS = {
    S_UNKNOWN:                  _SCENE_STATES + MODAL_STATES,
    # --- normal flow (each also allows any modal) ---
    S_HOME:                     [S_EVENT, S_NORMAL_QUEST_UIJIN] + MODAL_STATES,
    S_EVENT:                    [S_NORMAL_QUEST] + MODAL_STATES,
    S_NORMAL_QUEST:             [S_NORMAL_QUEST_UIJIN] + MODAL_STATES,
    S_NORMAL_QUEST_UIJIN:      [S_NORMAL_QUEST_UIJIN_KARYU] + MODAL_STATES,
    S_NORMAL_QUEST_UIJIN_KARYU:[S_DECK_SELECT] + MODAL_STATES,
    S_DECK_SELECT:              [S_WELCOME_IN_PLAY, S_HOME] + MODAL_STATES,
    S_WELCOME_IN_PLAY:          [S_CLEAR_OK] + MODAL_STATES,
    S_CLEAR_OK:                 [S_SPECIAL_REWARD, S_REWARD_NEXT, S_HOME] + MODAL_STATES,
    S_SPECIAL_REWARD:           [S_REWARD_NEXT, S_HOME] + MODAL_STATES,
    S_REWARD_NEXT:              [S_HOME, S_SPECIAL_REWARD] + MODAL_STATES,
    # --- modals: OK → back to any scene or another modal ---
    **{s: _SCENE_STATES + MODAL_STATES for s in MODAL_STATES},
}

FSM_ACTIONS = {
    S_HOME:                     "quest_bt_click",
    S_CONFIRM:                  "confirm_ok",
    S_INFORMATION:              "information_ok",
    S_INFORMATION_GAZE:         "information_gaze_ok",
    S_INFORMATION_GIMIC:        "information_gimic_ok",
    S_LOGIN_BONUS:              "login_bonus_ok",
    S_LOGIN_STAMP:              "login_stamp_ok",
    S_LOGIN_STAMP2:             "login_stamp2_ok",
    S_EVENT:                    "normal_bt_click",
    S_NORMAL_QUEST:             "welcome_stage_click",
    S_NORMAL_QUEST_UIJIN:      "welcome_bt_click",
    S_NORMAL_QUEST_UIJIN_KARYU:"solo_bt_click",
    S_HELPER_SELECT:            "helper_select",
    S_DECK_SELECT:              "shutsugeki_bt_click",
    S_NEED_DOWNLOAD:            "need_download_ok",
    S_NEED_NICKNAME:            "need_nickname_ok",
    S_WELCOME_IN_PLAY:          "play_turn",
    S_CONFIRM_RETRY:             "confirm_retry_ok",
    S_NEED_START:                "need_start_ok",
    S_CALENDER:                  "calender_ok",
    S_EVENT_MESSAGE_DIALOG:      "event_message_dialog_ok",
    S_REWARD_CHARA:              "reward_chara_ok",
    S_TUTORIAL_ATACK:            "tutorial_atack_ok",
    S_TUTORIAL_YUJO_COMBO:      "tutorial_yujo_combo_ok",
    S_TUTORIAL_BOSS_ATACK:      "tutorial_boss_atack_ok",
    S_TUTORIAL_ITEM:            "tutorial_item_ok",
    S_TUTORIAL_DAMAGE:          "tutorial_damage_ok",
    S_TUTORIAL_CONGRATURATE:    "tutorial_congraturate_ok",
    S_INFORMATION_WAIT:         "information_wait_ok",
    S_INFORMATION_COMPLETE_DOWNLOAD: "information_complete_download_ok",
    S_INFORMATION_GACHA:        "information_gacha_ok",
    S_INFORMATION_WELCOME:      "information_welcome_ok",
    S_INFORMATION_STRIKER_NAVI: "information_striker_navi_ok",
    S_TUTORIAL_CLEAR:           "tutorial_clear_ok",
    S_INFORMATION_GIMIC2:       "information_gimic2_ok",
    S_CLEAR_OK:                 "clear_ok",
    S_SPECIAL_REWARD:           "special_reward",
    S_REWARD_NEXT:              "reward_next",
}

moorefsm.FSM_TRANSITIONS = FSM_TRANSITIONS
moorefsm.FSM_ACTIONS = FSM_ACTIONS

# --- Welcome quest stage progression ---
# Cycles: その1 → その2 → その3 → その4 → その5 → 全課程終了 → (loop)
_welcome_stage = 0
_current_flow_stage = None    # stage index being played in current flow
_completed_stages = set()     # indices of completed stages

# (scroll_down_count, scroll_up_count, click_y, label)
WELCOME_STAGES = [
    (1, 0, 0.85, "ギミックを学ぼう その1"),  # bottom-most button
    (1, 0, 0.73, "ギミックを学ぼう その2"),
    (1, 0, 0.60, "ギミックを学ぼう その3"),
    (1, 0, 0.47, "ギミックを学ぼう その4"),
    (1, 0, 0.34, "ギミックを学ぼう その5"),  # top-most of the 5
    (0, 1, 0.28, "全課程終了"),            # top of page (scroll up)
]


def _act_welcome_stage_click(args):
    """Click current welcome stage button, then advance to next."""
    global _welcome_stage, _current_flow_stage
    if len(args) < 2:
        print("welcome_stage_click requires: <hid_w> <hid_h>")
        return
    hid.calibrate(manual_size=(int(args[0]), int(args[1])))

    _current_flow_stage = _welcome_stage
    scroll_down, scroll_up, click_y, label = WELCOME_STAGES[_welcome_stage]
    print(f"[welcome] stage {_welcome_stage}/{len(WELCOME_STAGES)-1}: {label}")

    # Scroll down
    for i in range(scroll_down):
        hid.reset_origin()
        x1 = int(hid.screen_w * 0.50)
        y1 = int(hid.screen_h * 0.80)
        x2 = int(hid.screen_w * 0.50)
        y2 = int(hid.screen_h * 0.30)
        hid.drag(x1, y1, x2, y2)
        hid.wait(hid.API_WAIT_DURATION)

    # Scroll up
    for i in range(scroll_up):
        hid.reset_origin()
        x1 = int(hid.screen_w * 0.50)
        y1 = int(hid.screen_h * 0.30)
        x2 = int(hid.screen_w * 0.50)
        y2 = int(hid.screen_h * 0.80)
        hid.drag(x1, y1, x2, y2)
        hid.wait(hid.API_WAIT_DURATION)

    # Click the stage button
    hid.reset_origin()
    print(f"[action] tap {label} (0.50, {click_y})")
    hid.click_pct(0.50, click_y, repeat=1)
    hid.notify_slack("welcome", "NORMAL-QUEST", f"welcome-stage-{_welcome_stage}/{len(WELCOME_STAGES)-1}:{label}")

    # Advance to next stage (cycle back after 全課程終了)
    _welcome_stage = (_welcome_stage + 1) % len(WELCOME_STAGES)
    print(f"[welcome] next stage: {_welcome_stage} ({WELCOME_STAGES[_welcome_stage][3]})")


hid.ACTIONS["welcome_stage_click"] = _act_welcome_stage_click

_action_queue = queue.Queue()
_worker_idle = threading.Event()
_worker_idle.set()


def _action_worker():
    """Worker thread: consume actions from FIFO queue sequentially."""
    while True:
        action_name, hid_args = _action_queue.get()
        _worker_idle.clear()
        print(f"  [HID] dispatching: {action_name} (queue size: {_action_queue.qsize()})")
        if action_name != "play_turn":
            hid.notify_slack("welcome", "action", action_name)
        try:
            hid.ACTIONS[action_name](hid_args)
            print(f"  [HID] done: {action_name}")
        except Exception as e:
            print(f"  [HID] error in {action_name}: {e}")
        _action_queue.task_done()
        if _action_queue.empty():
            _worker_idle.set()


threading.Thread(target=_action_worker, daemon=True).start()



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

    print("Loading ONNX model...")
    onnx_session, onnx_labels = load_onnx_model(ONNX_MODEL_PATH, ONNX_LABELS_PATH)

    print("Loading templates...")
    templates_hist, templates_region = hid.load_templates(SAVE_DIR, SCENE_REGIONS)
    print(f"Using ONNX + sub-region pipeline ({len(onnx_labels)} classes, "
          f"{len(templates_region)} scenes with regions)")

    print("Loading object templates...")
    obj_templates = hid.load_obj_templates(OBJ_TEMPLATES_DIR)
    print(f"Loaded {len(obj_templates)} object template type(s)")

    picam2 = Picamera2()
    config = picam2.create_video_configuration(
        main={"size": (CAP_W, CAP_H), "format": "RGB888"},
    )
    picam2.configure(config)
    picam2.start()
    time.sleep(0.5)

    print(f"Capture: {CAP_W}x{CAP_H}  ROI: ({ROI_X},{ROI_Y},{ROI_W},{ROI_H})  Output: {OUTPUT_W}x{OUTPUT_H}")
    print("Keys: q=quit  s=save snapshot  m=click at cursor")

    # Track mouse position for 'm' key click
    _mouse_pos = [0, 0]

    def on_mouse(event, x, y, flags, param):
        if event == cv2.EVENT_MOUSEMOVE:
            _mouse_pos[0] = x
            _mouse_pos[1] = y

    cv2.namedWindow("Scene Detect")
    cv2.setMouseCallback("Scene Detect", on_mouse)

    frame_count = 0
    fps_time = time.monotonic()
    last_detect = 0.0
    scores = [(name, 0.0) for name in SCENE_REGIONS]
    fsm_state = S_UNKNOWN
    toast_text = ""
    toast_time = 0.0
    last_play_turn = 0.0
    PLAY_TURN_INTERVAL = 5.0
    last_fsm_change = time.monotonic()
    last_real_fsm_change = last_fsm_change
    last_modal_cv_attempt = 0.0
    FSM_STUCK_TIMEOUT = 60.0
    FSM_STUCK_TIMEOUT_MODAL = 60.0    # OBJ template detection

    try:
        while True:
            frame = picam2.capture_array()
            h, w = frame.shape[:2]

            x1, y1, x2, y2 = hid.make_roi_rect(h, w, ROI_X, ROI_Y, ROI_W, ROI_H)
            roi = frame[y1:y2, x1:x2]
            roi_resized = cv2.resize(roi, (OUTPUT_W, OUTPUT_H))
            hid._last_frame = roi_resized
            display = roi_resized.copy()

            # --- Scene detection (1Hz) ---
            now = time.monotonic()
            detect_ready = now - last_detect >= 1.0
            if detect_ready:
                scores = onnx_classify(roi_resized, onnx_session, onnx_labels,
                                       SCENE_REGIONS, templates_region)
                last_detect = now
                # FSM update
                prev_fsm_state = fsm_state
                fsm_state, fsm_changed = fsm_update(fsm_state, scores)
                if fsm_changed:
                    print(f"  FSM -> {fsm_state}")
                    toast_text = fsm_state
                    toast_time = now
                    last_fsm_change = now
                    last_real_fsm_change = now
                    hid.notify_slack("welcome", prev_fsm_state, fsm_state)
                    # --- Save to all trackers ---
                    hid.save_full_test_frame(fsm_state, roi_resized)
                    hid.save_subtotal_frame(fsm_state, roi_resized)
                    # --- Subtotal (ANY → REWARD-NEXT) ---
                    if fsm_state == S_REWARD_NEXT:
                        if _current_flow_stage is not None:
                            _completed_stages.add(_current_flow_stage)
                        n_total = len(WELCOME_STAGES)
                        lines = []
                        for si, (_, _, _, slabel) in enumerate(WELCOME_STAGES):
                            mark = "\u2705" if si in _completed_stages else "\u2b1c"
                            tag = " \u2190 NOW" if si == _current_flow_stage else ""
                            lines.append(f"{mark} {si}/{n_total-1}: {slabel}{tag}")
                        progress = "\n".join(lines)
                        if len(_completed_stages) >= n_total:
                            progress += "\n\n\U0001f389 All Clear! Complete!"
                        hid.send_subtotal_result("welcome", extra_msg=progress)
                        hid.reset_subtotal()
                    # --- Full test (INFORMATION-COMPLETE-DOWNLOAD → HOME) ---
                    if (fsm_state == S_HOME
                            and prev_fsm_state == S_INFORMATION_COMPLETE_DOWNLOAD):
                        n_total = len(WELCOME_STAGES)
                        lines = []
                        for si, (_, _, _, slabel) in enumerate(WELCOME_STAGES):
                            mark = "\u2705" if si in _completed_stages else "\u2b1c"
                            lines.append(f"{mark} {si}/{n_total-1}: {slabel}")
                        progress = "\n".join(lines)
                        if len(_completed_stages) >= n_total:
                            progress += "\n\n\U0001f389 All Clear! Complete!"
                        hid.send_full_test_result("welcome", extra_msg=progress)
                        hid.reset_full_test()
                        _completed_stages.clear()
                    print(f"  [DEBUG] hid_enabled={hid_enabled} fsm_state={fsm_state} "
                          f"in_actions={fsm_state in FSM_ACTIONS}")
                    if hid_enabled and fsm_state in FSM_ACTIONS:
                        _action_queue.put((FSM_ACTIONS[fsm_state], hid_args))
                # IN-PLAY: periodic play_turn (skip if busy)
                if (hid_enabled and fsm_state == S_WELCOME_IN_PLAY
                        and now - last_play_turn >= PLAY_TURN_INTERVAL
                        and _worker_idle.is_set()):
                    _action_queue.put(("play_turn", hid_args))
                    last_play_turn = now
                # Stuck timeout: click center if UNKNOWN or low-confidence for too long
                top_score = scores[0][1] if scores else 0.0
                if (hid_enabled
                        and (fsm_state == S_UNKNOWN or top_score < ONNX_CONF_LOW)
                        and now - last_fsm_change >= FSM_STUCK_TIMEOUT
                        and _worker_idle.is_set()):
                    print(f"  [FSM] stuck {FSM_STUCK_TIMEOUT:.0f}s — tap center")
                    _action_queue.put(("confirm_ok", hid_args))
                    last_fsm_change = now
                # Re-trigger: same non-UNKNOWN state for 60s → re-fire action
                FSM_RETRIGGER_TIMEOUT = 60.0
                if (hid_enabled
                        and fsm_state not in (S_UNKNOWN, S_WELCOME_IN_PLAY)
                        and now - last_fsm_change >= FSM_RETRIGGER_TIMEOUT
                        and fsm_state in FSM_ACTIONS
                        and _worker_idle.is_set()):
                    print(f"  [FSM] retrigger {fsm_state} after {FSM_RETRIGGER_TIMEOUT:.0f}s")
                    _action_queue.put((FSM_ACTIONS[fsm_state], hid_args))
                    last_fsm_change = now
                # Modal OBJ: stuck 60s → detect OK button via obj templates → click
                _dt_real = now - last_real_fsm_change
                _dt_modal = now - last_modal_cv_attempt
                if int(_dt_real) % 10 == 0 and int(_dt_real) > 0:
                    print(f"  [OBJ-DBG] hid={hid_enabled} st={fsm_state} "
                          f"dt_real={_dt_real:.0f}/{FSM_STUCK_TIMEOUT_MODAL:.0f} "
                          f"dt_modal={_dt_modal:.0f}/{FSM_STUCK_TIMEOUT_MODAL:.0f} "
                          f"tpl={len(obj_templates)} idle={_worker_idle.is_set()}")
                if (hid_enabled
                        and fsm_state != S_WELCOME_IN_PLAY
                        and _dt_real >= FSM_STUCK_TIMEOUT_MODAL
                        and _dt_modal >= FSM_STUCK_TIMEOUT_MODAL
                        and obj_templates
                        and _worker_idle.is_set()):
                    print(f"  [OBJ] calling detect_obj_in_frame (dt_real={_dt_real:.0f}s)")
                    last_modal_cv_attempt = now
                    obj_result = hid.detect_obj_in_frame(roi_resized, obj_templates)
                    if obj_result:
                        obj_name, cx_ok, cy_ok = obj_result
                        print(f"  [FSM] OBJ {obj_name} at ({cx_ok:.3f}, {cy_ok:.3f}) — clicking")
                        _action_queue.put(("cv_ok_click",
                                           hid_args + [str(cx_ok), str(cy_ok)]))
                        last_fsm_change = now
                        last_real_fsm_change = now

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
                if top[1] < ONNX_CONF_LOW:
                    cv2.putText(display, f"-- ({top[1]:.3f})", (10, 60),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (100, 100, 100), 2)
                else:
                    cv2.putText(display, f"{top[0]} ({top[1]:.3f})", (10, 60),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
            cv2.putText(display, f"FSM: {fsm_state}", (10, 90),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 200, 255), 2)
            candidate_scene = scores[0][0] if scores and scores[0][1] >= ONNX_CONF_LOW else None
            draw_region_boxes(display, fsm_state, SCENE_REGIONS, OUTPUT_W, OUTPUT_H,
                              candidate_scene=candidate_scene)
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
            elif key == ord("m"):
                mx, my = _mouse_pos
                if mx < OUTPUT_W and hid_enabled:
                    xx = mx / OUTPUT_W
                    yy = my / OUTPUT_H
                    hid_x = int(args.hid_w * xx)
                    hid_y = int(args.hid_h * yy)
                    print(f"  [CLICK] pct({xx:.3f}, {yy:.3f})  hid({hid_x}, {hid_y})")
                    def do_click(px=xx, py=yy):
                        hid.calibrate(manual_size=(args.hid_w, args.hid_h))
                        hid.click_pct(px, py, repeat=1)
                    threading.Thread(target=do_click, daemon=True).start()
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
