# Scene Detect

Real-time scene detection and automated gameplay for Monster Strike, using a Raspberry Pi camera and USB HID mouse control over a WebRTC SFU.

## Overview

`scene.py` captures live video from a Pi Camera, crops a configurable ROI (region of interest), and compares each frame against a library of snapshot templates using HSV histogram correlation. A **Moore FSM** (finite state machine) tracks game state transitions and dispatches HID mouse actions (clicks, drags, scrolls) to navigate menus and play quests autonomously.

### Architecture

```
Pi Camera (Picamera2)
    |
    v
  ROI crop + resize (400x800)
    |
    v
  HSV histogram matching   <-- snapshots/*.jpg templates
    |                            (full-frame + sub-region)
    v
  Moore FSM (state machine)
    |
    v
  HID action dispatch      --> HTTP API --> SFU --> USB HID mouse
    |
    v
  OpenCV display (live view + score bar chart)
```

## Requirements

- **Hardware**: Raspberry Pi (tested on RPi 5) with Pi Camera module
- **Python 3.10+**
- **Dependencies**:
  - `opencv-python` (`cv2`)
  - `numpy`
  - `picamera2`
  - `requests`

## Files

| File | Description |
|------|-------------|
| `scene.py` | Main entry point: camera capture, scene detection, FSM, and display loop |
| `common.py` | USB HID mouse control via HTTP API: low-level send, click, drag, calibration |
| `snapshots/` | Template images for each scene (`<scene-name>_<index>.jpg`) |

## Usage

```bash
# Display-only mode (no HID control)
python scene.py

# With HID control enabled
python scene.py --device-id <DEVICE_ID> --hid-w <WIDTH> --hid-h <HEIGHT>

# Or via environment variables
DEVICE_ID=abc123 HID_W=400 HID_H=800 python scene.py
```

### Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `q` | Quit |
| `s` | Save current ROI frame as a snapshot template |
| `m` | Send a mouse click at the current cursor position |

## Scene Detection

Each template image is stored as `snapshots/<scene-name>_<N>.jpg`. On startup, all templates are loaded and their HSV histograms are pre-computed.

Detection runs at **1 Hz** and uses two layers of comparison:

1. **Full-frame histogram** - `cv2.compareHist` with `HISTCMP_CORREL` against every template
2. **Sub-region histograms** - For scenes defined in `SCENE_REGIONS`, specific UI areas (buttons, bars) are cropped and compared independently. Region scores are blended with the base score to boost or penalise the match.

A `SCENE_CUSTOMS` mechanism provides differential weighting for rival scenes (e.g., `quest` vs `event`) that share similar layouts but differ in which button is highlighted.

## FSM (Finite State Machine)

The Moore FSM enforces valid game-flow transitions:

```
UNKNOWN -> HOME -> EVENT/QUEST -> NORMAL-QUEST -> NORMAL-QUEST-UIJIN
  -> NORMAL-QUEST-UIJIN-KARYU -> HELPER-SELECT -> DECK-SELECT
  -> IN-PLAY -> CLEAR-OK -> SPECIAL-REWARD -> REWARD-NEXT -> HOME (loop)
```

Key properties:

- **Transition guard**: Only transitions listed in `FSM_TRANSITIONS` are allowed
- **Confirmation count**: A candidate state must be detected **3 consecutive times** before the FSM transitions (debouncing)
- **Action dispatch**: On each transition, the corresponding HID action from `FSM_ACTIONS` is enqueued to a background worker thread

## HID Control (`common.py`)

Mouse commands are sent as HTTP POST requests to the SFU API:

```
POST {SFU_API_BASE}/{device_id}/00/00
{"type": "mouse", "command": "{op} {dx} {dy}"}
```

- `op=0`: move / mouse-up
- `op=1`: mouse-down / drag
- `dx`, `dy`: relative delta in HID units

Commands are chunked into small deltas (`MAX_DELTA=10`) and sent in random-sized batches for robustness. High-level operations include `click_pct`, `drag`, `long_press`, and cursor calibration.

## Adding New Scenes

1. Run `scene.py` and navigate to the target screen in the game
2. Press `s` to save a snapshot
3. Enter a filename in the format `<scene-name>_<N>` (e.g., `my-scene_00`)
4. Add multiple snapshots per scene for robustness (3-5 recommended)
5. Optionally define sub-regions in `SCENE_REGIONS` and add FSM transitions in `FSM_TRANSITIONS`

## Configuration

Key constants in `scene.py`:

| Constant | Default | Description |
|----------|---------|-------------|
| `ROI_X/Y/W/H` | 0.442/0.432/0.126/0.332 | Normalized ROI within camera frame |
| `OUTPUT_W/H` | 400x800 | Resized ROI dimensions for matching |
| `CAP_W/H` | 2028x1520 | Camera capture resolution |
| `MIN_SIMILARITY` | 0.4 | Minimum score threshold |
| `FSM_CONFIRM_COUNT` | 3 | Consecutive detections required for state transition |

Environment variables:

| Variable | Description |
|----------|-------------|
| `DEVICE_ID` | SFU device identifier |
| `HID_W` | HID screen width in HID units |
| `HID_H` | HID screen height in HID units |
| `SFU_API_BASE` | SFU API endpoint (default: `http://192.168.124.45:8888/api/message`) |
