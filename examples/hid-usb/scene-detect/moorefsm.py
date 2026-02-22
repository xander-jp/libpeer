"""Moore FSM for Monster Strike scene detection."""

# --------------- States ---------------

S_UNKNOWN = "UNKNOWN"
S_HOME = "HOME"
S_QUEST = "QUEST"
S_NORMAL_QUEST = "NORMAL-QUEST"
S_NORMAL_QUEST_UIJIN = "NORMAL-QUEST-UIJIN"
S_NORMAL_QUEST_UIJIN_KARYU = "NORMAL-QUEST-UIJIN-KARYU"
S_HELPER_SELECT = "HELPER-SELECT"
S_DECK_SELECT = "DECK-SELECT"
S_IN_PLAY = "NORMAL-QUEST-UIJIN-IN-PLAY"
S_WELCOME_IN_PLAY = "WELCOME-QUEST-00-IN-PLAY"
S_CLEAR_OK = "CLEAR-OK"
S_SPECIAL_REWARD = "SPECIAL-REWARD"
S_EVENT = "EVENT"
S_NEED_DOWNLOAD = "NEED-DOWNLOAD"
S_TUTORIAL_YUJO_COMBO = "TUTORIAL-YUJO-COMBO"
S_REWARD_NEXT = "REWARD-NEXT"
S_INFORMATION = "INFORMATION"
S_INFORMATION_GAZE = "INFORMATION-GAZE"
S_INFORMATION_GIMIC = "INFORMATION-GIMIC"
S_LOGIN_BONUS = "LOGIN-BONUS"
S_LOGIN_STAMP = "LOGIN-STAMP"
S_LOGIN_STAMP2 = "LOGIN-STAMP2"
S_CALENDER = "CALENDER"
S_EVENT_MESSAGE_DIALOG = "EVENT-MESSAGE-DIALOG"
S_REWARD_CHARA = "REWARD-CHARA"
S_TUTORIAL_BOSS_ATACK = "TUTORIAL-BOSS-ATACK"
S_CONFIRM = "CONFIRM"
S_NEED_NICKNAME = "NEED-NICKNAME"
S_TUTORIAL_ATACK = "TUTORIAL-ATACK"
S_CONFIRM_RETRY = "CONFIRM-RETRY"
S_NEED_START = "NEED-START"
S_TUTORIAL_ITEM = "TUTORIAL-ITEM"
S_TUTORIAL_DAMAGE = "TUTORIAL-DAMAGE"
S_TUTORIAL_CONGRATURATE = "TUTORIAL-CONGRATURATE"
S_INFORMATION_WAIT = "INFORMATION-WAIT"
S_INFORMATION_COMPLETE_DOWNLOAD = "INFORMATION-COMPLETE-DOWNLOAD"
S_INFORMATION_GACHA = "INFORMATION-GACHA"
S_INFORMATION_WELCOME = "INFORMATION-WELCOME"
S_INFORMATION_STRIKER_NAVI = "INFORMATION-STRIKER-NAVI"
S_TUTORIAL_CLEAR = "TUTORIAL-CLEAR"
S_INFORMATION_GIMIC2 = "INFORMATION-GIMIC2"

# --------------- Transition table / Action mapping ---------------
# Set from entry-point source before calling fsm_update().

FSM_TRANSITIONS = None  # state -> [allowed next states]
FSM_ACTIONS = None      # state -> HID action name

# --------------- Scene name -> state mapping ---------------

SCENE_NAME_TO_STATE = {
    "home": S_HOME,
    "event": S_EVENT,
    "quest": S_QUEST,
    "normal-quest": S_NORMAL_QUEST,
    "normal-quest-uijin": S_NORMAL_QUEST_UIJIN,
    "normal-quest-uijin-karyu": S_NORMAL_QUEST_UIJIN_KARYU,
    "helper-select": S_HELPER_SELECT,
    "deck-select": S_DECK_SELECT,
    "normal-quest-uijin-in-play": S_IN_PLAY,
    "welcome-quest-00-in-play": S_WELCOME_IN_PLAY,
    "welcome-quest-01-in-play": S_WELCOME_IN_PLAY,
    "welcome-quest-02-in-play": S_WELCOME_IN_PLAY,
    "welcome-quest-03-in-play": S_WELCOME_IN_PLAY,
    "welcome-quest-04-in-play": S_WELCOME_IN_PLAY,
    "welcome-quest-05-in-play": S_WELCOME_IN_PLAY,
    "need-download": S_NEED_DOWNLOAD,
    "tutorial-yujo-combo": S_TUTORIAL_YUJO_COMBO,
    "clear-ok": S_CLEAR_OK,
    "special-reward": S_SPECIAL_REWARD,
    "reward-next": S_REWARD_NEXT,
    "information": S_INFORMATION,
    "information-gaze": S_INFORMATION_GAZE,
    "information-gimic": S_INFORMATION_GIMIC,
    "login-bonus": S_LOGIN_BONUS,
    "login-stamp": S_LOGIN_STAMP,
    "login-stamp2": S_LOGIN_STAMP2,
    "calender": S_CALENDER,
    "event-message-dialog": S_EVENT_MESSAGE_DIALOG,
    "reward-chara": S_REWARD_CHARA,
    "tutorial-boss-atack": S_TUTORIAL_BOSS_ATACK,
    "confirm": S_CONFIRM,
    "need-nickname": S_NEED_NICKNAME,
    "tutorial-atack": S_TUTORIAL_ATACK,
    "confirm-retry": S_CONFIRM_RETRY,
    "need-start": S_NEED_START,
    "tutorial-quest-00-in-play": S_WELCOME_IN_PLAY,
    "tutorial-item": S_TUTORIAL_ITEM,
    "tutorial-damage": S_TUTORIAL_DAMAGE,
    "tutorial-congraturate": S_TUTORIAL_CONGRATURATE,
    "information-wait": S_INFORMATION_WAIT,
    "information-complete-download": S_INFORMATION_COMPLETE_DOWNLOAD,
    "information-gacha": S_INFORMATION_GACHA,
    "information-welcome": S_INFORMATION_WELCOME,
    "information-striker-navi": S_INFORMATION_STRIKER_NAVI,
    "tutorial-clear": S_TUTORIAL_CLEAR,
    "information-gimic2": S_INFORMATION_GIMIC2,
}

# --------------- Modal dialog states ---------------
# All modal states: auto-generates action name from state value
# e.g. "CONFIRM" -> "confirm_ok", "INFORMATION-GAZE" -> "information_gaze_ok"

MODAL_STATES = [
    S_CONFIRM, S_INFORMATION, S_INFORMATION_GAZE, S_INFORMATION_GIMIC,
    S_LOGIN_BONUS, S_LOGIN_STAMP, S_LOGIN_STAMP2,
    S_NEED_DOWNLOAD, S_NEED_NICKNAME,
    S_CONFIRM_RETRY, S_TUTORIAL_ATACK, S_TUTORIAL_BOSS_ATACK, S_TUTORIAL_YUJO_COMBO,
    S_NEED_START, S_CALENDER, S_EVENT_MESSAGE_DIALOG, S_REWARD_CHARA,
    S_TUTORIAL_ITEM, S_TUTORIAL_DAMAGE, S_TUTORIAL_CONGRATURATE,
    S_INFORMATION_WAIT,
    S_INFORMATION_COMPLETE_DOWNLOAD,
    S_INFORMATION_GACHA,
    S_INFORMATION_WELCOME,
    S_INFORMATION_STRIKER_NAVI,
    S_TUTORIAL_CLEAR,
    S_INFORMATION_GIMIC2,
]

MODAL_FSM_ACTIONS = {s: s.lower().replace("-", "_") + "_ok" for s in MODAL_STATES}

# --------------- ONNX evaluation thresholds ---------------

ONNX_CONF_HIGH = 0.60   # confident: accept directly
ONNX_CONF_LOW = 0.30    # below this: UNKNOWN


def _evaluate_state_onnx(scores):
    """Evaluate state from ONNX softmax probabilities."""
    if not scores:
        return S_UNKNOWN

    top_name, top_score = scores[0]

    # "unknown" class -> UNKNOWN regardless of confidence
    if top_name == "unknown":
        return S_UNKNOWN

    if top_score < ONNX_CONF_LOW:
        return S_UNKNOWN

    # High confidence: trust the model
    if top_score >= ONNX_CONF_HIGH:
        return SCENE_NAME_TO_STATE.get(top_name, S_UNKNOWN)

    # Medium confidence: require margin over second place
    if len(scores) >= 2:
        second_score = scores[1][1]
        margin = top_score - second_score
        if margin >= 0.15:
            return SCENE_NAME_TO_STATE.get(top_name, S_UNKNOWN)

    return S_UNKNOWN


# --------------- FSM update ---------------

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

    candidate = _evaluate_state_onnx(scores)
    if state == S_QUEST and candidate == S_NORMAL_QUEST_UIJIN:
        candidate = S_NORMAL_QUEST
    # output logging when difference candidate
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
