#!/usr/bin/env python3
"""Monster Strike scene detector - camera capture base."""

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
    S_HELPER_SELECT, S_DECK_SELECT, S_IN_PLAY,
    S_CLEAR_OK, S_SPECIAL_REWARD, S_REWARD_NEXT,
    S_CONFIRM, S_INFORMATION, S_INFORMATION_GAZE, S_INFORMATION_GIMIC,
    S_LOGIN_BONUS, S_LOGIN_STAMP, S_LOGIN_STAMP2,
    S_NEED_DOWNLOAD, S_NEED_NICKNAME,
    S_CONFIRM_RETRY, S_TUTORIAL_ATACK, S_TUTORIAL_BOSS_ATACK, S_TUTORIAL_YUJO_COMBO,
    S_NEED_START, S_CALENDER, S_EVENT_MESSAGE_DIALOG, S_REWARD_CHARA,
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
        (0.04, 0.534, 0.92, 0.069),
    ],
    "normal-quest-uijin-in-play": [],
    "confirm":            [],
    "information":        [],
    "information-gaze":   [],
    "information-gimic":  [],
    "login-bonus":        [],
    "login-stamp":        [],
    "login-stamp2":       [],
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
}

# --------------- FSM config ---------------

# Non-modal scene states
_SCENE_STATES = [
    S_HOME, S_EVENT, S_QUEST, S_NORMAL_QUEST, S_NORMAL_QUEST_UIJIN,
    S_NORMAL_QUEST_UIJIN_KARYU, S_HELPER_SELECT, S_DECK_SELECT,
    S_IN_PLAY, S_CLEAR_OK, S_SPECIAL_REWARD, S_REWARD_NEXT,
]

FSM_TRANSITIONS = {
    S_UNKNOWN:                  _SCENE_STATES + MODAL_STATES,
    # --- normal flow (each also allows any modal) ---
    S_HOME:                     [S_EVENT, S_QUEST, S_NORMAL_QUEST_UIJIN] + MODAL_STATES,
    S_EVENT:                    [S_QUEST, S_NORMAL_QUEST_UIJIN, S_HOME] + MODAL_STATES,
    S_QUEST:                    [S_NORMAL_QUEST, S_HOME] + MODAL_STATES,
    S_NORMAL_QUEST:             [S_NORMAL_QUEST_UIJIN, S_QUEST, S_HOME] + MODAL_STATES,
    S_NORMAL_QUEST_UIJIN:      [S_NORMAL_QUEST_UIJIN_KARYU, S_NORMAL_QUEST, S_HOME] + MODAL_STATES,
    S_NORMAL_QUEST_UIJIN_KARYU:[S_HELPER_SELECT, S_HOME] + MODAL_STATES,
    S_HELPER_SELECT:            [S_DECK_SELECT, S_HOME] + MODAL_STATES,
    S_DECK_SELECT:              [S_IN_PLAY, S_HOME] + MODAL_STATES,
    S_IN_PLAY:                  [S_CLEAR_OK] + MODAL_STATES,
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
    S_EVENT:                    "normal_ikusei_bt_click",
    S_QUEST:                    "normal_bt_click",
    S_NORMAL_QUEST:             "shojin_bt_click",
    S_NORMAL_QUEST_UIJIN:      "karyu_bt_click",
    S_NORMAL_QUEST_UIJIN_KARYU:"solo_bt_click",
    S_HELPER_SELECT:            "helper_select",
    S_DECK_SELECT:              "shutsugeki_bt_click",
    S_NEED_DOWNLOAD:            "need_download_ok",
    S_NEED_NICKNAME:            "need_nickname_ok",
    S_IN_PLAY:                  "play_turn",
    S_CONFIRM_RETRY:             "confirm_retry_ok",
    S_NEED_START:                "need_start_ok",
    S_CALENDER:                  "calender_ok",
    S_EVENT_MESSAGE_DIALOG:      "event_message_dialog_ok",
    S_REWARD_CHARA:              "reward_chara_ok",
    S_TUTORIAL_ATACK:            "tutorial_atack_ok",
    S_TUTORIAL_YUJO_COMBO:      "tutorial_yujo_combo_ok",
    S_TUTORIAL_BOSS_ATACK:      "tutorial_boss_atack_ok",
    S_CLEAR_OK:                 "clear_ok",
    S_SPECIAL_REWARD:           "special_reward",
    S_REWARD_NEXT:              "reward_next",
}

moorefsm.FSM_TRANSITIONS = FSM_TRANSITIONS
moorefsm.FSM_ACTIONS = FSM_ACTIONS

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
            hid.notify_slack("scene", "action", action_name)
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
    FSM_STUCK_TIMEOUT = 30.0
    FSM_STUCK_TIMEOUT_MODAL = 60.0    # CV-based OK button detection

    try:
        while True:
            frame = picam2.capture_array()
            h, w = frame.shape[:2]

            x1, y1, x2, y2 = hid.make_roi_rect(h, w, ROI_X, ROI_Y, ROI_W, ROI_H)
            roi = frame[y1:y2, x1:x2]
            roi_resized = cv2.resize(roi, (OUTPUT_W, OUTPUT_H))
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
                    hid.notify_slack("scene", prev_fsm_state, fsm_state)
                    print(f"  [DEBUG] hid_enabled={hid_enabled} fsm_state={fsm_state} "
                          f"in_actions={fsm_state in FSM_ACTIONS}")
                    if hid_enabled and fsm_state in FSM_ACTIONS:
                        _action_queue.put((FSM_ACTIONS[fsm_state], hid_args))
                # IN-PLAY: periodic play_turn (skip if busy)
                if (hid_enabled and fsm_state == S_IN_PLAY
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
                        and fsm_state not in (S_UNKNOWN, S_IN_PLAY)
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
                        and fsm_state != S_IN_PLAY
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
            # Draw OBJ sliding-window grid when stuck
            if obj_templates and now - last_real_fsm_change >= FSM_STUCK_TIMEOUT_MODAL * 0.5:
                _obj_rw = int(OUTPUT_W * 0.25)
                _obj_rh = int(OUTPUT_H * 0.05)
                _obj_sx = max(1, _obj_rw // 2)
                _obj_sy = max(1, _obj_rh // 2)
                _gy = 0
                while _gy + _obj_rh <= OUTPUT_H:
                    _gx = 0
                    while _gx + _obj_rw <= OUTPUT_W:
                        cv2.rectangle(display, (_gx, _gy),
                                      (_gx + _obj_rw, _gy + _obj_rh),
                                      (0, 255, 255), 1)
                        _gx += _obj_sx
                    _gy += _obj_sy
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
                    print(f"  [CLICK] pct({xx:.3f}, {yy:.3f})")
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
