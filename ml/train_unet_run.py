"""
Script mirror of train_unet.ipynb, for headless/background execution.
Trains, checkpoints the best val-IoU epoch to weights/unet_best.pth, and prints
per-epoch progress to stdout so it can be monitored.
"""
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader
from torch.amp import autocast, GradScaler

import albumentations as A
from albumentations.pytorch import ToTensorV2
import cv2
import segmentation_models_pytorch as smp

DATA_DIR = Path(__file__).parent / "data"
WEIGHTS_DIR = Path(__file__).parent / "weights"
WEIGHTS_DIR.mkdir(exist_ok=True)

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print("device:", DEVICE, flush=True)

SEED = 42
torch.manual_seed(SEED)
np.random.seed(SEED)

IMG_SIZE = 256
BATCH_SIZE = 8
EPOCHS = 20
LR = 1e-4
ENCODER = "resnet34"
ENCODER_WEIGHTS = "imagenet"
PATIENCE = 5


class OilSpillDataset(Dataset):
    def __init__(self, images_dir, masks_dir, transform=None):
        self.images_dir = images_dir
        self.masks_dir = masks_dir
        self.filenames = sorted(p.name for p in images_dir.iterdir() if p.suffix == ".png")
        self.transform = transform

    def __len__(self):
        return len(self.filenames)

    def __getitem__(self, idx):
        name = self.filenames[idx]
        image = cv2.imread(str(self.images_dir / name))
        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        mask = cv2.imread(str(self.masks_dir / name), cv2.IMREAD_GRAYSCALE)
        mask = (mask > 127).astype(np.float32)
        if self.transform:
            augmented = self.transform(image=image, mask=mask)
            image, mask = augmented["image"], augmented["mask"]
        return image, mask.unsqueeze(0).float()


IMAGENET_MEAN = (0.485, 0.456, 0.406)
IMAGENET_STD = (0.229, 0.224, 0.225)

train_transform = A.Compose([
    A.HorizontalFlip(p=0.5),
    A.VerticalFlip(p=0.5),
    A.RandomRotate90(p=0.5),
    A.RandomBrightnessContrast(p=0.3),
    A.GaussNoise(p=0.2),
    A.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD),
    ToTensorV2(),
])
val_transform = A.Compose([
    A.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD),
    ToTensorV2(),
])

train_ds = OilSpillDataset(DATA_DIR / "images/train", DATA_DIR / "masks/train", train_transform)
val_ds = OilSpillDataset(DATA_DIR / "images/val", DATA_DIR / "masks/val", val_transform)
print(f"train: {len(train_ds)}  val: {len(val_ds)}", flush=True)

train_loader = DataLoader(train_ds, batch_size=BATCH_SIZE, shuffle=True, num_workers=2, pin_memory=True, drop_last=True)
val_loader = DataLoader(val_ds, batch_size=BATCH_SIZE, shuffle=False, num_workers=2, pin_memory=True)

model = smp.Unet(encoder_name=ENCODER, encoder_weights=ENCODER_WEIGHTS, in_channels=3, classes=1).to(DEVICE)
bce_loss = nn.BCEWithLogitsLoss()
dice_loss = smp.losses.DiceLoss(mode="binary", from_logits=True)


def criterion(logits, targets):
    return bce_loss(logits, targets) + dice_loss(logits, targets)


optimizer = torch.optim.Adam(model.parameters(), lr=LR)
scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, mode="max", factor=0.5, patience=3)
scaler = GradScaler(enabled=(DEVICE.type == "cuda"))


@torch.no_grad()
def iou_score(logits, targets, threshold=0.5, eps=1e-7):
    preds = (torch.sigmoid(logits) > threshold).float()
    intersection = (preds * targets).sum(dim=(1, 2, 3))
    union = (preds + targets).clamp(0, 1).sum(dim=(1, 2, 3))
    return ((intersection + eps) / (union + eps)).mean().item()


best_iou = 0.0
epochs_without_improvement = 0
t_start = time.time()

for epoch in range(1, EPOCHS + 1):
    t_epoch = time.time()
    model.train()
    running_loss = 0.0
    for imgs, masks in train_loader:
        imgs, masks = imgs.to(DEVICE, non_blocking=True), masks.to(DEVICE, non_blocking=True)
        optimizer.zero_grad(set_to_none=True)
        with autocast(device_type=DEVICE.type, enabled=(DEVICE.type == "cuda")):
            logits = model(imgs)
            loss = criterion(logits, masks)
        scaler.scale(loss).backward()
        scaler.step(optimizer)
        scaler.update()
        running_loss += loss.item() * imgs.size(0)
    train_loss = running_loss / len(train_ds)

    model.eval()
    val_running_loss = 0.0
    val_running_iou = 0.0
    with torch.no_grad():
        for imgs, masks in val_loader:
            imgs, masks = imgs.to(DEVICE, non_blocking=True), masks.to(DEVICE, non_blocking=True)
            with autocast(device_type=DEVICE.type, enabled=(DEVICE.type == "cuda")):
                logits = model(imgs)
                loss = criterion(logits, masks)
            val_running_loss += loss.item() * imgs.size(0)
            val_running_iou += iou_score(logits, masks) * imgs.size(0)
    val_loss = val_running_loss / len(val_ds)
    val_iou = val_running_iou / len(val_ds)
    scheduler.step(val_iou)

    dt = time.time() - t_epoch
    print(f"EPOCH {epoch:02d}/{EPOCHS}  train_loss={train_loss:.4f}  val_loss={val_loss:.4f}  val_iou={val_iou:.4f}  ({dt:.0f}s)", flush=True)

    if val_iou > best_iou:
        best_iou = val_iou
        epochs_without_improvement = 0
        torch.save({
            "model_state_dict": model.state_dict(),
            "encoder": ENCODER,
            "encoder_weights": ENCODER_WEIGHTS,
            "img_size": IMG_SIZE,
            "val_iou": val_iou,
            "epoch": epoch,
        }, WEIGHTS_DIR / "unet_best.pth")
        print(f"  -> new best checkpoint saved (val_iou={val_iou:.4f})", flush=True)
    else:
        epochs_without_improvement += 1
        if epochs_without_improvement >= PATIENCE:
            print(f"EARLY STOP — no improvement for {PATIENCE} epochs", flush=True)
            break

total_time = time.time() - t_start
print(f"\nTRAINING DONE  best_val_iou={best_iou:.4f}  total_time={total_time/60:.1f}min", flush=True)
