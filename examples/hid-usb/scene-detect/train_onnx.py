#!/usr/bin/env python3
"""Train scene classifier CNN and export to ONNX.

Usage:
    python3 train_onnx.py [--epochs 300] [--aug 500] [--lr 0.005]

Reads snapshots from ./snapshots/, trains a tiny CNN on Canny edge images,
and writes:
    scene_model.onnx   - ONNX inference model
    scene_labels.json  - ordered class labels
"""

import argparse
import glob
import json
import os
import time

import cv2
import numpy as np

# --- Config ---
SNAPSHOT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "snapshots")
MODEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scene_model.onnx")
LABELS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scene_labels.json")

INPUT_W = 64
INPUT_H = 128
N_FEATURES = INPUT_W * INPUT_H  # 8192 (single-channel Canny edge)

CONV1_CH = 8
CONV2_CH = 16

SAMPLES_PER_CLASS = 500  # target augmented samples per class


# ============================================================
#  Data loading & augmentation
# ============================================================

def load_images(snapshot_dir):
    """Load images grouped by scene name."""
    scenes = {}
    for path in sorted(glob.glob(os.path.join(snapshot_dir, "*.jpg"))):
        base = os.path.splitext(os.path.basename(path))[0]
        parts = base.rsplit("_", 1)
        if len(parts) == 2 and parts[1].isdigit():
            name = parts[0]
        else:
            continue
        img = cv2.imread(path)
        if img is None:
            continue
        scenes.setdefault(name, []).append(img)
    return scenes


def preprocess(img):
    """Canny on full-res, then resize to flat vector [N_FEATURES]."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150)
    resized = cv2.resize(edges, (INPUT_W, INPUT_H))
    return resized.astype(np.float32).flatten() / 255.0


def augment(img, n):
    """Generate n augmented copies of img."""
    results = []
    h, w = img.shape[:2]
    for _ in range(n):
        aug = img.copy().astype(np.float32)

        # brightness shift
        aug += np.random.uniform(-40, 40)

        # contrast
        aug *= np.random.uniform(0.7, 1.3)

        aug = np.clip(aug, 0, 255).astype(np.uint8)

        # Gaussian noise
        if np.random.random() < 0.5:
            noise = np.random.normal(0, 8, aug.shape).astype(np.float32)
            aug = np.clip(aug.astype(np.float32) + noise, 0, 255).astype(np.uint8)

        # blur
        if np.random.random() < 0.3:
            ksize = np.random.choice([3, 5])
            aug = cv2.GaussianBlur(aug, (ksize, ksize), 0)

        # small spatial shift
        if np.random.random() < 0.5:
            dx = np.random.randint(-8, 9)
            dy = np.random.randint(-16, 17)
            M = np.float32([[1, 0, dx], [0, 1, dy]])
            aug = cv2.warpAffine(aug, M, (w, h), borderMode=cv2.BORDER_REFLECT)

        # small rotation
        if np.random.random() < 0.3:
            angle = np.random.uniform(-3, 3)
            M = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
            aug = cv2.warpAffine(aug, M, (w, h), borderMode=cv2.BORDER_REFLECT)

        results.append(aug)
    return results


UNKNOWN_LABEL = "unknown"


def generate_unknown_images(real_images, n, h=800, w=400):
    """Generate synthetic 'unknown' images that look nothing like any scene.

    Mix of: random noise, uniform colour, gradients, heavy distortion
    of real images, and cross-class blends.
    """
    results = []
    for i in range(n):
        kind = np.random.randint(0, 5)

        if kind == 0:
            # Random noise
            img = np.random.randint(0, 256, (h, w, 3), dtype=np.uint8)

        elif kind == 1:
            # Uniform random colour
            colour = np.random.randint(0, 256, 3).tolist()
            img = np.full((h, w, 3), colour, dtype=np.uint8)

        elif kind == 2:
            # Gradient (vertical)
            c1 = np.random.randint(0, 256, 3).astype(np.float32)
            c2 = np.random.randint(0, 256, 3).astype(np.float32)
            t = np.linspace(0, 1, h).reshape(-1, 1, 1)
            img = ((1 - t) * c1 + t * c2).astype(np.uint8)
            img = np.broadcast_to(img, (h, w, 3)).copy()

        elif kind == 3:
            # Heavily distorted version of a real image
            src = real_images[np.random.randint(0, len(real_images))].copy()
            src = cv2.resize(src, (w, h))
            # extreme colour shift + heavy blur
            src = src.astype(np.float32)
            src += np.random.uniform(-120, 120)
            src *= np.random.uniform(0.2, 0.5)
            src = np.clip(src, 0, 255).astype(np.uint8)
            img = cv2.GaussianBlur(src, (31, 31), 0)

        else:
            # Blend two random real images (cross-class)
            a = real_images[np.random.randint(0, len(real_images))]
            b = real_images[np.random.randint(0, len(real_images))]
            a = cv2.resize(a, (w, h)).astype(np.float32)
            b = cv2.resize(b, (w, h)).astype(np.float32)
            alpha = np.random.uniform(0.3, 0.7)
            img = (alpha * a + (1 - alpha) * b).astype(np.uint8)
            # add noise on top
            noise = np.random.normal(0, 30, img.shape).astype(np.float32)
            img = np.clip(img.astype(np.float32) + noise, 0, 255).astype(np.uint8)

        results.append(img)
    return results


def build_dataset(scenes, samples_per_class):
    """Build balanced dataset with augmentation + synthetic 'unknown' class."""
    labels = sorted(scenes.keys())

    # Always append 'unknown' as the last class
    labels.append(UNKNOWN_LABEL)
    label_to_idx = {name: i for i, name in enumerate(labels)}

    X_list = []
    y_list = []

    # --- Real scenes ---
    all_real_images = []
    for name in labels:
        if name == UNKNOWN_LABEL:
            continue
        imgs = scenes[name]
        all_real_images.extend(imgs)
        idx = label_to_idx[name]
        n_orig = len(imgs)

        aug_per_img = max(0, (samples_per_class - n_orig) // n_orig)

        for img in imgs:
            X_list.append(preprocess(img))
            y_list.append(idx)
            for aug_img in augment(img, aug_per_img):
                X_list.append(preprocess(aug_img))
                y_list.append(idx)

        actual = n_orig + n_orig * aug_per_img
        print(f"  {name:35s} orig={n_orig:2d}  aug/img={aug_per_img:3d}  total={actual}")

    # --- Synthetic unknown class ---
    # Also include any unknown_*.jpg snapshots the user saved
    unknown_real = scenes.get(UNKNOWN_LABEL, [])
    unknown_synth = generate_unknown_images(all_real_images, samples_per_class)
    unknown_all = unknown_real + unknown_synth
    idx_unk = label_to_idx[UNKNOWN_LABEL]
    for img in unknown_all:
        X_list.append(preprocess(img))
        y_list.append(idx_unk)
    print(f"  {UNKNOWN_LABEL:35s} real={len(unknown_real):2d}  "
          f"synth={len(unknown_synth):3d}  total={len(unknown_all)}")

    X = np.array(X_list, dtype=np.float32)
    y = np.array(y_list, dtype=np.int32)
    return X, y, labels


# ============================================================
#  Numpy CNN helpers
# ============================================================

def relu(x):
    return np.maximum(0, x)


def relu_deriv(x):
    return (x > 0).astype(np.float32)


def softmax(x):
    e = np.exp(x - x.max(axis=1, keepdims=True))
    return e / e.sum(axis=1, keepdims=True)


def cross_entropy(pred, target):
    return -np.mean(np.sum(target * np.log(pred + 1e-8), axis=1))


def im2col(x, kh, kw, stride=1, pad=0):
    """Convert 4D input (N,C,H,W) to column matrix for convolution."""
    N, C, H, W = x.shape
    out_h = (H + 2 * pad - kh) // stride + 1
    out_w = (W + 2 * pad - kw) // stride + 1
    if pad > 0:
        x = np.pad(x, ((0, 0), (0, 0), (pad, pad), (pad, pad)),
                   mode='constant')
    col = np.zeros((N, C, kh, kw, out_h, out_w), dtype=x.dtype)
    for j in range(kh):
        j_end = j + stride * out_h
        for i in range(kw):
            i_end = i + stride * out_w
            col[:, :, j, i, :, :] = x[:, :, j:j_end:stride, i:i_end:stride]
    return col.transpose(0, 4, 5, 1, 2, 3).reshape(N * out_h * out_w, -1)


def col2im(col, x_shape, kh, kw, stride=1, pad=0):
    """Reverse of im2col: scatter-add columns back to image tensor."""
    N, C, H, W = x_shape
    out_h = (H + 2 * pad - kh) // stride + 1
    out_w = (W + 2 * pad - kw) // stride + 1
    col = col.reshape(N, out_h, out_w, C, kh, kw).transpose(0, 3, 4, 5, 1, 2)
    H_pad, W_pad = H + 2 * pad, W + 2 * pad
    img = np.zeros((N, C, H_pad, W_pad), dtype=col.dtype)
    for j in range(kh):
        j_end = j + stride * out_h
        for i in range(kw):
            i_end = i + stride * out_w
            img[:, :, j:j_end:stride, i:i_end:stride] += col[:, :, j, i, :, :]
    if pad > 0:
        return img[:, :, pad:-pad, pad:-pad]
    return img


class SimpleCNN:
    """Tiny CNN: Conv(8) -> ReLU -> Conv(16) -> ReLU -> GlobalAvgPool -> FC"""

    def __init__(self, out_dim):
        # Conv1: 1 -> CONV1_CH, 3x3, pad=1
        s1 = np.sqrt(2.0 / (1 * 3 * 3))
        self.conv1_W = (np.random.randn(CONV1_CH, 1, 3, 3) * s1).astype(np.float32)
        self.conv1_b = np.zeros(CONV1_CH, dtype=np.float32)
        # Conv2: CONV1_CH -> CONV2_CH, 3x3, pad=1
        s2 = np.sqrt(2.0 / (CONV1_CH * 3 * 3))
        self.conv2_W = (np.random.randn(CONV2_CH, CONV1_CH, 3, 3) * s2).astype(np.float32)
        self.conv2_b = np.zeros(CONV2_CH, dtype=np.float32)
        # FC: CONV2_CH -> out_dim
        s3 = np.sqrt(2.0 / CONV2_CH)
        self.fc_W = (np.random.randn(CONV2_CH, out_dim) * s3).astype(np.float32)
        self.fc_b = np.zeros(out_dim, dtype=np.float32)

    def _conv_forward(self, x, W, b):
        """Conv2d forward (3x3, pad=1). Returns (output, col_cache)."""
        out_ch = W.shape[0]
        N, _, H, W_in = x.shape
        col = im2col(x, 3, 3, pad=1)
        col_W = W.reshape(out_ch, -1).T  # (C_in*9, out_ch)
        out_flat = col @ col_W + b
        out = out_flat.reshape(N, H, W_in, out_ch).transpose(0, 3, 1, 2)
        return out, col

    def _conv_backward(self, dout, col, x_shape, W):
        """Conv2d backward. Returns (dx, dW, db)."""
        out_ch = W.shape[0]
        N = dout.shape[0]
        dout_flat = dout.transpose(0, 2, 3, 1).reshape(-1, out_ch)
        dW = (col.T @ dout_flat).T.reshape(W.shape) / N
        db = dout_flat.sum(axis=0) / N
        dcol = dout_flat @ W.reshape(out_ch, -1)
        dx = col2im(dcol, x_shape, 3, 3, pad=1)
        return dx, dW, db

    def forward(self, X_flat):
        N = X_flat.shape[0]
        x = X_flat.reshape(N, 1, INPUT_H, INPUT_W)

        # Conv1 + ReLU
        z1, self._col1 = self._conv_forward(x, self.conv1_W, self.conv1_b)
        self._x_shape = x.shape
        self._z1 = z1
        a1 = relu(z1)

        # Conv2 + ReLU
        z2, self._col2 = self._conv_forward(a1, self.conv2_W, self.conv2_b)
        self._a1_shape = a1.shape
        self._z2 = z2
        a2 = relu(z2)

        # GlobalAvgPool -> (N, CONV2_CH)
        self._a2 = a2
        pooled = a2.mean(axis=(2, 3))

        # FC + Softmax
        self._pooled = pooled
        z_fc = pooled @ self.fc_W + self.fc_b
        self.out = softmax(z_fc)
        return self.out

    def backward(self, y_onehot, lr):
        N = self.out.shape[0]

        # FC backward
        dz_fc = self.out - y_onehot
        dW_fc = self._pooled.T @ dz_fc / N
        db_fc = dz_fc.mean(axis=0)
        d_pooled = dz_fc @ self.fc_W.T  # (N, CONV2_CH)

        # GlobalAvgPool backward
        _, C, H, W = self._a2.shape
        d_a2 = d_pooled[:, :, np.newaxis, np.newaxis] \
            * np.ones((1, 1, H, W), dtype=np.float32) / (H * W)

        # Conv2 backward
        d_z2 = d_a2 * relu_deriv(self._z2)
        d_a1, dW2, db2 = self._conv_backward(
            d_z2, self._col2, self._a1_shape, self.conv2_W)

        # Conv1 backward
        d_z1 = d_a1 * relu_deriv(self._z1)
        _, dW1, db1 = self._conv_backward(
            d_z1, self._col1, self._x_shape, self.conv1_W)

        # Update weights
        self.fc_W -= lr * dW_fc
        self.fc_b -= lr * db_fc
        self.conv2_W -= lr * dW2
        self.conv2_b -= lr * db2
        self.conv1_W -= lr * dW1
        self.conv1_b -= lr * db1


def predict_batched(model, X, batch_size=256):
    """Run forward in batches to avoid OOM on large datasets."""
    preds = []
    for i in range(0, len(X), batch_size):
        preds.append(model.forward(X[i:i + batch_size]))
    return np.concatenate(preds, axis=0)


def train_cnn(X, y, n_classes, epochs, lr, batch_size=64):
    """Train CNN and return model."""
    y_onehot = np.zeros((len(y), n_classes), dtype=np.float32)
    y_onehot[np.arange(len(y)), y] = 1.0

    cnn = SimpleCNN(n_classes)

    n_params = (cnn.conv1_W.size + cnn.conv1_b.size +
                cnn.conv2_W.size + cnn.conv2_b.size +
                cnn.fc_W.size + cnn.fc_b.size)
    print(f"  Parameters: {n_params}")

    for epoch in range(epochs):
        indices = np.random.permutation(len(X))
        total_loss = 0.0
        n_batches = 0

        for i in range(0, len(X), batch_size):
            batch_idx = indices[i:i + batch_size]
            X_b = X[batch_idx]
            y_b = y_onehot[batch_idx]

            pred = cnn.forward(X_b)
            total_loss += cross_entropy(pred, y_b)
            cnn.backward(y_b, lr)
            n_batches += 1

        if (epoch + 1) % 20 == 0 or epoch == 0:
            pred_all = predict_batched(cnn, X)
            acc = (pred_all.argmax(axis=1) == y).mean()
            print(f"  epoch {epoch+1:4d}/{epochs}  "
                  f"loss={total_loss / n_batches:.4f}  acc={acc:.4f}")

    pred_all = predict_batched(cnn, X)
    acc = (pred_all.argmax(axis=1) == y).mean()
    print(f"  final accuracy: {acc:.4f}")
    return cnn


# ============================================================
#  ONNX export
# ============================================================

def export_onnx(cnn, labels, path):
    """Export trained CNN to ONNX."""
    import onnx
    from onnx import helper, TensorProto, numpy_helper

    n_classes = len(labels)

    # Initializers
    conv1_W = numpy_helper.from_array(cnn.conv1_W, name="conv1_W")
    conv1_b = numpy_helper.from_array(cnn.conv1_b, name="conv1_b")
    conv2_W = numpy_helper.from_array(cnn.conv2_W, name="conv2_W")
    conv2_b = numpy_helper.from_array(cnn.conv2_b, name="conv2_b")
    fc_W = numpy_helper.from_array(cnn.fc_W, name="fc_W")
    fc_b = numpy_helper.from_array(cnn.fc_b, name="fc_b")

    shape_4d = numpy_helper.from_array(
        np.array([1, 1, INPUT_H, INPUT_W], dtype=np.int64), name="shape_4d")
    shape_2d = numpy_helper.from_array(
        np.array([1, CONV2_CH], dtype=np.int64), name="shape_2d")

    X_in = helper.make_tensor_value_info(
        "input", TensorProto.FLOAT, [1, N_FEATURES])
    Y_out = helper.make_tensor_value_info(
        "output", TensorProto.FLOAT, [1, n_classes])

    nodes = [
        # Reshape flat edge vector to 4D: [1, 1, H, W]
        helper.make_node("Reshape", ["input", "shape_4d"], ["x_4d"]),
        # Conv1 + ReLU
        helper.make_node("Conv", ["x_4d", "conv1_W", "conv1_b"], ["z1"],
                         kernel_shape=[3, 3], pads=[1, 1, 1, 1]),
        helper.make_node("Relu", ["z1"], ["a1"]),
        # Conv2 + ReLU
        helper.make_node("Conv", ["a1", "conv2_W", "conv2_b"], ["z2"],
                         kernel_shape=[3, 3], pads=[1, 1, 1, 1]),
        helper.make_node("Relu", ["z2"], ["a2"]),
        # GlobalAveragePool -> Reshape to 2D
        helper.make_node("GlobalAveragePool", ["a2"], ["pooled_4d"]),
        helper.make_node("Reshape", ["pooled_4d", "shape_2d"], ["pooled"]),
        # FC + Softmax
        helper.make_node("Gemm", ["pooled", "fc_W", "fc_b"], ["logits"],
                         transB=0),
        helper.make_node("Softmax", ["logits"], ["output"], axis=1),
    ]

    graph = helper.make_graph(
        nodes, "scene_classifier",
        [X_in], [Y_out],
        initializer=[conv1_W, conv1_b, conv2_W, conv2_b,
                      fc_W, fc_b, shape_4d, shape_2d],
    )
    model = helper.make_model(
        graph, opset_imports=[helper.make_opsetid("", 13)])
    model.ir_version = 8

    onnx.checker.check_model(model)
    onnx.save(model, path)
    print(f"ONNX model saved: {path}  ({os.path.getsize(path)} bytes)")


# ============================================================
#  Main
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="Train scene classifier -> ONNX")
    parser.add_argument("--epochs", type=int, default=300)
    parser.add_argument("--aug", type=int, default=SAMPLES_PER_CLASS,
                        help="target samples per class after augmentation")
    parser.add_argument("--lr", type=float, default=0.005)
    parser.add_argument("--batch", type=int, default=64)
    args = parser.parse_args()

    print(f"Input: {INPUT_W}x{INPUT_H} Canny edge = {N_FEATURES} features")
    print(f"CNN: Conv({CONV1_CH})->ReLU->Conv({CONV2_CH})->ReLU->GAP->FC")
    print(f"Epochs: {args.epochs}  LR: {args.lr}  Batch: {args.batch}")
    print()

    print("Loading snapshots...")
    scenes = load_images(SNAPSHOT_DIR)
    if not scenes:
        print(f"ERROR: no snapshots in {SNAPSHOT_DIR}")
        return

    print(f"\nBuilding dataset (target {args.aug} samples/class)...")
    X, y, labels = build_dataset(scenes, args.aug)
    n_classes = len(labels)

    # Shuffle
    perm = np.random.permutation(len(X))
    X, y = X[perm], y[perm]

    print(f"\nDataset: {X.shape[0]} samples, {N_FEATURES} features, {n_classes} classes")
    print(f"Classes: {labels}")
    print()

    print("Training...")
    t0 = time.monotonic()
    cnn = train_cnn(X, y, n_classes, args.epochs, args.lr, args.batch)
    elapsed = time.monotonic() - t0
    print(f"Training took {elapsed:.1f}s")
    print()

    # Per-class accuracy
    pred_all = predict_batched(cnn, X)
    pred_labels = pred_all.argmax(axis=1)
    for i, name in enumerate(labels):
        mask = y == i
        if mask.sum() == 0:
            continue
        cls_acc = (pred_labels[mask] == i).mean()
        print(f"  {name:35s} acc={cls_acc:.4f}  (n={mask.sum()})")
    print()

    export_onnx(cnn, labels, MODEL_PATH)

    with open(LABELS_PATH, "w") as f:
        json.dump(labels, f, indent=2)
    print(f"Labels saved: {LABELS_PATH}")

    # Quick verification with onnxruntime
    print("\nVerifying with onnxruntime...")
    import onnxruntime as ort
    sess = ort.InferenceSession(MODEL_PATH)
    test_input = X[:1].reshape(1, -1)
    result = sess.run(None, {"input": test_input})
    probs = result[0][0]
    top_idx = probs.argmax()
    print(f"  test input -> {labels[top_idx]} ({probs[top_idx]:.4f})")
    print("Done.")


if __name__ == "__main__":
    main()
