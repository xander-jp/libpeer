#!/usr/bin/env python3
"""Train scene classifier CNN on GPU (PyTorch) and export to ONNX.

Usage:
    python3 train_onnx_gpu.py [--epochs 300] [--aug 500] [--lr 0.005]

Same data pipeline as train_onnx.py but uses PyTorch for GPU training.
Architecture: Conv(16)->Conv(32)->Conv(64)->Flatten->FC(256)->FC(n_classes)
"""

import argparse
import json
import os
import time

import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import TensorDataset, DataLoader

from train_onnx import (
    SNAPSHOT_DIR, MODEL_PATH, LABELS_PATH,
    INPUT_W, INPUT_H, INPUT_CH, N_FEATURES,
    CONV1_CH, CONV2_CH, CONV3_CH,
    SAMPLES_PER_CLASS,
    load_images, build_dataset,
)

FC1_DIM = 256
FLATTEN_DIM = CONV3_CH * (INPUT_H // 8) * (INPUT_W // 8)  # 64*8*4 = 2048


def get_device():
    if torch.cuda.is_available():
        return torch.device("cuda")
    if torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


class SceneCNN(nn.Module):
    """Conv(16)->Conv(32)->Conv(64)->Flatten->FC(256)->FC(n_classes)"""

    def __init__(self, n_classes):
        super().__init__()
        self.features = nn.Sequential(
            nn.Conv2d(INPUT_CH, CONV1_CH, 3, stride=2, padding=1),
            nn.ReLU(),
            nn.Conv2d(CONV1_CH, CONV2_CH, 3, stride=2, padding=1),
            nn.ReLU(),
            nn.Conv2d(CONV2_CH, CONV3_CH, 3, stride=2, padding=1),
            nn.ReLU(),
        )
        self.classifier = nn.Sequential(
            nn.Flatten(),
            nn.Linear(FLATTEN_DIM, FC1_DIM),
            nn.ReLU(),
            nn.Linear(FC1_DIM, n_classes),
        )

    def forward(self, x):
        x = x.view(-1, INPUT_CH, INPUT_H, INPUT_W)
        x = self.features(x)
        x = self.classifier(x)
        return x


def train(model, device, train_loader, optimizer, criterion, epoch, epochs):
    model.train()
    total_loss = 0.0
    n_batches = 0
    for X_b, y_b in train_loader:
        X_b, y_b = X_b.to(device), y_b.to(device)
        optimizer.zero_grad()
        output = model(X_b)
        loss = criterion(output, y_b)
        loss.backward()
        optimizer.step()
        total_loss += loss.item()
        n_batches += 1
    return total_loss / n_batches


def evaluate(model, device, X_tensor, y_np):
    model.eval()
    with torch.no_grad():
        output = model(X_tensor.to(device))
        preds = output.argmax(dim=1).cpu().numpy()
    return (preds == y_np).mean(), preds


def export_onnx(model, n_classes, labels, path, device):
    model.eval()
    dummy = torch.randn(1, N_FEATURES, device=device)
    torch.onnx.export(
        model, dummy, path,
        input_names=["input"],
        output_names=["output"],
        opset_version=13,
        dynamic_axes=None,
    )

    # Append Softmax (torch exports raw logits)
    import onnx
    from onnx import helper
    orig = onnx.load(path)
    # Rename original output
    orig_out = orig.graph.output[0].name
    for node in orig.graph.node:
        for i, o in enumerate(node.output):
            if o == orig_out:
                node.output[i] = "logits"
    orig.graph.output[0].name = "logits"
    # Add softmax node
    sm_node = helper.make_node("Softmax", ["logits"], ["output"], axis=1)
    orig.graph.node.append(sm_node)
    # Update output info
    from onnx import TensorProto
    new_out = helper.make_tensor_value_info("output", TensorProto.FLOAT,
                                            [1, n_classes])
    del orig.graph.output[:]
    orig.graph.output.append(new_out)
    onnx.checker.check_model(orig)
    onnx.save(orig, path)
    print(f"ONNX model saved: {path}  ({os.path.getsize(path)} bytes)")


def main():
    parser = argparse.ArgumentParser(
        description="Train scene classifier (PyTorch GPU) -> ONNX")
    parser.add_argument("--epochs", type=int, default=300)
    parser.add_argument("--aug", type=int, default=SAMPLES_PER_CLASS,
                        help="target samples per class after augmentation")
    parser.add_argument("--lr", type=float, default=0.001)
    parser.add_argument("--batch", type=int, default=64)
    args = parser.parse_args()

    device = get_device()

    print(f"Device: {device}")
    print(f"Input: {INPUT_W}x{INPUT_H}x{INPUT_CH} RGB = {N_FEATURES} features")
    print(f"CNN: Conv({CONV1_CH})->Conv({CONV2_CH})->Conv({CONV3_CH})"
          f"->Flatten({FLATTEN_DIM})->FC({FC1_DIM})->FC(n_classes)")
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

    print(f"\nDataset: {X.shape[0]} samples, {N_FEATURES} features, "
          f"{n_classes} classes")
    print(f"Classes: {labels}")
    print()

    # PyTorch tensors
    X_tensor = torch.from_numpy(X)
    y_tensor = torch.from_numpy(y.astype(np.int64))
    train_ds = TensorDataset(X_tensor, y_tensor)
    train_loader = DataLoader(train_ds, batch_size=args.batch, shuffle=True)

    # Model
    model = SceneCNN(n_classes).to(device)
    n_params = sum(p.numel() for p in model.parameters())
    print(f"Training...")
    print(f"  Parameters: {n_params}")

    optimizer = optim.Adam(model.parameters(), lr=args.lr)
    criterion = nn.CrossEntropyLoss()

    # Sanity check: accuracy before training (should be ~1/n_classes ≈ 2%)
    acc0, _ = evaluate(model, device, X_tensor, y)
    print(f"  Before training acc={acc0:.4f} (expect ~{1.0/n_classes:.4f})")

    t0 = time.monotonic()
    for epoch in range(args.epochs):
        avg_loss = train(model, device, train_loader, optimizer, criterion,
                         epoch, args.epochs)

        if (epoch + 1) % 20 == 0 or epoch == 0:
            acc, _ = evaluate(model, device, X_tensor, y)
            print(f"  epoch {epoch+1:4d}/{args.epochs}  "
                  f"loss={avg_loss:.4f}  acc={acc:.4f}")

    elapsed = time.monotonic() - t0
    acc, pred_labels = evaluate(model, device, X_tensor, y)
    print(f"  final accuracy: {acc:.4f}")
    print(f"Training took {elapsed:.1f}s")
    print()

    # Per-class accuracy
    for i, name in enumerate(labels):
        mask = y == i
        if mask.sum() == 0:
            continue
        cls_acc = (pred_labels[mask] == i).mean()
        print(f"  {name:35s} acc={cls_acc:.4f}  (n={mask.sum()})")
    print()

    export_onnx(model, n_classes, labels, MODEL_PATH, device)

    with open(LABELS_PATH, "w") as f:
        json.dump(labels, f, indent=2)
    print(f"Labels saved: {LABELS_PATH}")

    # Verify with onnxruntime
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
