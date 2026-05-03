import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


PROJECT_ROOT = Path(__file__).resolve().parents[1]
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp"}
LANCZOS = getattr(getattr(Image, "Resampling", Image), "LANCZOS", Image.BICUBIC)


def main():
    parser = argparse.ArgumentParser(description="Create a YOLO GT/prediction contact sheet.")
    parser.add_argument("--images-dir", required=True)
    parser.add_argument("--labels-dir", required=True)
    parser.add_argument("--pred-labels-dir", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--max-images", type=int, default=24)
    parser.add_argument("--max-preds-per-image", type=int, default=20)
    parser.add_argument("--thumb-width", type=int, default=420)
    args = parser.parse_args()

    images_dir = resolve_path(args.images_dir)
    labels_dir = resolve_path(args.labels_dir)
    pred_labels_dir = resolve_path(args.pred_labels_dir)
    out_path = resolve_path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    image_paths = sorted([p for p in images_dir.glob("*") if p.suffix.lower() in IMAGE_EXTS])[: args.max_images]
    tiles = [
        draw_tile(p, labels_dir / (p.stem + ".txt"), pred_labels_dir / (p.stem + ".txt"), args.thumb_width, args.max_preds_per_image)
        for p in image_paths
    ]
    if not tiles:
        raise SystemExit("No images found in {0}".format(images_dir))

    cols = 2
    rows = (len(tiles) + cols - 1) // cols
    tile_w = max(tile.width for tile in tiles)
    tile_h = max(tile.height for tile in tiles)
    sheet = Image.new("RGB", (cols * tile_w, rows * tile_h), "white")
    for idx, tile in enumerate(tiles):
        x = (idx % cols) * tile_w
        y = (idx // cols) * tile_h
        sheet.paste(tile, (x, y))
    sheet.save(out_path, quality=92)
    print(str(out_path))


def resolve_path(value):
    path = Path(value)
    if path.is_absolute():
        return path
    if path.parts and path.parts[0] in {"outputs", "tools", "config", "core", "docs"}:
        return (PROJECT_ROOT / path).resolve()
    project_path = (PROJECT_ROOT / path).resolve()
    if project_path.exists():
        return project_path
    return (PROJECT_ROOT.parent / path).resolve()


def draw_tile(image_path, gt_path, pred_path, thumb_width, max_preds_per_image):
    image = Image.open(image_path).convert("RGB")
    orig_w, orig_h = image.size
    scale = thumb_width / orig_w
    thumb_h = max(1, int(orig_h * scale))
    image = image.resize((thumb_width, thumb_h), LANCZOS)
    draw = ImageDraw.Draw(image)

    gt_boxes = read_yolo_boxes(gt_path, has_conf=False)
    pred_boxes_all = read_yolo_boxes(pred_path, has_conf=True)
    pred_boxes = sorted(pred_boxes_all, key=lambda item: item.get("conf", 0.0), reverse=True)[:max_preds_per_image]
    for box in gt_boxes:
        draw_box(draw, box, thumb_width, thumb_h, "lime", "GT")
    for box in pred_boxes:
        label = "P {0:.3f}".format(box.get("conf", 0.0))
        draw_box(draw, box, thumb_width, thumb_h, "red", label)

    caption_h = 54
    tile = Image.new("RGB", (thumb_width, thumb_h + caption_h), "white")
    tile.paste(image, (0, 0))
    caption = ImageDraw.Draw(tile)
    text = "{0}\nGT: {1}  Pred shown: {2}/{3}".format(image_path.name, len(gt_boxes), len(pred_boxes), len(pred_boxes_all))
    if not pred_boxes_all:
        text += "  no prediction at conf=0.001"
    caption.text((6, thumb_h + 6), text, fill="black", font=ImageFont.load_default())
    return tile


def read_yolo_boxes(path, has_conf):
    if not path.exists():
        return []
    boxes = []
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) < 5:
            continue
        try:
            class_id = int(float(parts[0]))
            x, y, w, h = [float(v) for v in parts[1:5]]
            conf = float(parts[5]) if has_conf and len(parts) > 5 else None
        except ValueError:
            continue
        item = {"class_id": class_id, "x": x, "y": y, "w": w, "h": h}
        if conf is not None:
            item["conf"] = conf
        boxes.append(item)
    return boxes


def draw_box(draw, box, width, height, color, label):
    x = box["x"] * width
    y = box["y"] * height
    w = box["w"] * width
    h = box["h"] * height
    left = x - w / 2
    top = y - h / 2
    right = x + w / 2
    bottom = y + h / 2
    draw.rectangle([left, top, right, bottom], outline=color, width=3)
    label_top = top - 14
    label_bottom = top
    if label_top < 0:
        label_top = top
        label_bottom = min(height, top + 14)
    draw.rectangle([left, label_top, left + 92, label_bottom], fill=color)
    draw.text((left + 2, label_top + 1), label, fill="black", font=ImageFont.load_default())


if __name__ == "__main__":
    main()
