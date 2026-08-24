from pathlib import Path

import numpy as np
import torch
from torch.utils.data import Dataset, DataLoader

import albumentations as A
from albumentations.pytorch import ToTensorV2
import cv2
import segmentation_models_pytorch as smp

DATA_DIR = Path("/home/abishekraj/Desktop/smart-india-hackathon/ml/data")
WEIGHTS_PATH = Path("/home/abishekraj/Desktop/smart-india-hackathon/ml/weights/unet_best.pth")
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")

IMAGENET_MEAN = (0.485, 0.456, 0.406)
IMAGENET_STD = (0.229, 0.224, 0.225)


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


val_transform = A.Compose([
    A.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD),
    ToTensorV2(),
])

val_ds = OilSpillDataset(DATA_DIR / "images/val", DATA_DIR / "masks/val", val_transform)
val_loader = DataLoader(val_ds, batch_size=16, shuffle=False, num_workers=2, pin_memory=True)
print(f"evaluating on {len(val_ds)} held-out val images")

ckpt = torch.load(WEIGHTS_PATH, map_location=DEVICE)
model = smp.Unet(encoder_name=ckpt["encoder"], encoder_weights=None, in_channels=3, classes=1).to(DEVICE)
model.load_state_dict(ckpt["model_state_dict"])
model.eval()
print(f"loaded checkpoint from epoch {ckpt['epoch']} (train-time val_iou={ckpt['val_iou']:.4f})")

# Confusion matrix totals across the full val set (pixel-level, threshold 0.5)
tp = fp = fn = tn = 0
per_image_iou = []
n_empty_gt_correct = 0  # images with no oil at all, correctly predicted empty
n_empty_gt = 0

with torch.no_grad():
    for imgs, masks in val_loader:
        imgs = imgs.to(DEVICE)
        masks = masks.to(DEVICE)
        logits = model(imgs)
        preds = (torch.sigmoid(logits) > 0.5).float()

        tp += (preds * masks).sum().item()
        fp += (preds * (1 - masks)).sum().item()
        fn += ((1 - preds) * masks).sum().item()
        tn += ((1 - preds) * (1 - masks)).sum().item()

        for i in range(imgs.size(0)):
            p, m = preds[i], masks[i]
            inter = (p * m).sum().item()
            union = (p + m).clamp(0, 1).sum().item()
            if union == 0:
                per_image_iou.append(1.0)
                n_empty_gt += 1
                n_empty_gt_correct += 1
            else:
                per_image_iou.append(inter / union)
                if m.sum().item() == 0:
                    n_empty_gt += 1
                    if p.sum().item() == 0:
                        n_empty_gt_correct += 1

pixel_accuracy = (tp + tn) / (tp + tn + fp + fn)
precision = tp / (tp + fp + 1e-9)
recall = tp / (tp + fn + 1e-9)
f1 = 2 * precision * recall / (precision + recall + 1e-9)
mean_iou_dataset = tp / (tp + fp + fn + 1e-9)  # dataset-level IoU (all pixels pooled)
mean_iou_per_image = float(np.mean(per_image_iou))  # per-image IoU averaged (matches training metric)

print("\n=== Pixel-level metrics (threshold 0.5, full val set) ===")
print(f"Pixel accuracy:         {pixel_accuracy:.4f}")
print(f"Precision (oil class):  {precision:.4f}")
print(f"Recall (oil class):     {recall:.4f}")
print(f"F1 / Dice (oil class):  {f1:.4f}")
print(f"IoU (dataset-pooled):   {mean_iou_dataset:.4f}")
print(f"IoU (mean per-image):   {mean_iou_per_image:.4f}")
print(f"\nConfusion counts (pixels): TP={tp:.0f} FP={fp:.0f} FN={fn:.0f} TN={tn:.0f}")
print(f"\nCorrectly-empty negative patches: {n_empty_gt_correct}/{n_empty_gt} ({100*n_empty_gt_correct/max(n_empty_gt,1):.1f}%)")
print(f"\nClassical detector baseline (from plan.md, different eval methodology): IoU 0.878")
