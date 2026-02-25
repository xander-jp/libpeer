"""ONNX inference for scene classification."""

import json
import os
import time

import cv2
import numpy as np
import onnxruntime as ort

import common as hid

# Default model / label paths (relative to this file)
_DIR = os.path.dirname(os.path.abspath(__file__))
ONNX_MODEL_PATH = os.path.join(_DIR, "scene_model.onnx")
ONNX_LABELS_PATH = os.path.join(_DIR, "scene_labels.json")

# ONNX input size (must match train_onnx.py)
ONNX_INPUT_W = 32
ONNX_INPUT_H = 64

# --- Stage 2: sub-region boost/penalty weights ---
REGION_BOOST = 0.10    # max positive adjustment per matching region
REGION_PENALTY = 0.15  # max negative adjustment per mismatching region
REGION_MATCH_THR = 0.5 # histogram correlation above this = positive
REGION_TOP_N = 3       # apply stage-2 to top-N candidates only


def load_onnx_model(model_path, labels_path):
    """Load ONNX model and label list.

    Returns (session, labels).  Raises if files are missing.
    """
    if not os.path.exists(model_path):
        raise FileNotFoundError(
            f"ONNX model not found: {model_path}\n"
            "  Run: python3 train_onnx.py   to generate it")
    if not os.path.exists(labels_path):
        raise FileNotFoundError(f"ONNX labels not found: {labels_path}")

    sess = ort.InferenceSession(model_path)
    with open(labels_path) as f:
        labels = json.load(f)
    print(f"  ONNX model loaded: {model_path} ({len(labels)} classes)")
    return sess, labels


def onnx_preprocess(frame):
    """Preprocess frame for ONNX inference. Returns [1, N_FEATURES] float32.

    Converts to Canny edge image (single channel) to match train_onnx.py.
    """
    resized = cv2.resize(frame, (ONNX_INPUT_W, ONNX_INPUT_H))
    gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150)
    vec = edges.astype(np.float32).flatten() / 255.0
    return vec.reshape(1, -1)


def onnx_classify(frame, session, labels, scene_regions,
                  templates_region=None):
    """Two-stage scene classification.

    Stage 1: ONNX full-frame inference -> base probabilities
    Stage 2: For top candidates with scene_regions, compare each
             sub-region crop against stored template histograms.
             Positive match -> boost score.  Mismatch -> penalise.
    Returns [(scene_name, score), ...] sorted desc.
    """
    # --- Stage 1: ONNX ---
    t0 = time.monotonic()
    features = onnx_preprocess(frame)
    probs = session.run(None, {"input": features})[0][0]
    score_map = {labels[i]: float(probs[i]) for i in range(len(labels))
                 if labels[i] in scene_regions}
    t1 = time.monotonic()
    print(f"  [PERF] ONNX inference: {(t1 - t0)*1000:.1f}ms")

    # --- Stage 2: sub-region template matching ---
    if templates_region:
        t2 = time.monotonic()
        # Sort to find top-N for region check
        ranked = sorted(score_map.items(), key=lambda x: x[1], reverse=True)
        for name, base_score in ranked[:REGION_TOP_N]:
            if name not in templates_region or name not in scene_regions:
                continue
            regions = scene_regions[name]
            n_regions = len(regions)
            if n_regions == 0:
                continue

            adjustments = []
            for ri, region in enumerate(regions):
                frame_crop = hid.crop_region(frame, region)
                frame_crop_hist = hid.calc_hist(frame_crop)
                best_corr = max(
                    cv2.compareHist(frame_crop_hist, h, cv2.HISTCMP_CORREL)
                    for h in templates_region[name][ri]
                )
                if best_corr >= REGION_MATCH_THR:
                    adjustments.append(+REGION_BOOST * best_corr)
                else:
                    adjustments.append(-REGION_PENALTY * (REGION_MATCH_THR - best_corr))

            adj = sum(adjustments) / n_regions
            score_map[name] = max(0.0, min(1.0, base_score + adj))
        t3 = time.monotonic()
        print(f"  [PERF] sub-region matching: {(t3 - t2)*1000:.1f}ms")

    results = sorted(score_map.items(), key=lambda x: x[1], reverse=True)
    return results
