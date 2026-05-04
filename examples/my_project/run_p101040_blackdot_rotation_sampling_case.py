"""Run the P101040 blue black-dot fixed-camera rotation sampling case.

This is a thesis/demo wrapper around the existing black-dot reference backend.
It intentionally does not change production generation code. Each angle is
rendered into an isolated per-angle folder and then copied into a compact case
folder for review.
"""

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
BACKEND_SCRIPT = SCRIPT_DIR / "reference_blend_blackdot_multi_model.py"


def parse_vector(text: str) -> Tuple[float, float, float]:
    parts = [part.strip() for part in text.replace(";", ",").split(",") if part.strip()]
    if len(parts) != 3:
        raise argparse.ArgumentTypeError("expected three comma-separated numbers, e.g. 1,0,0")
    try:
        return tuple(float(part) for part in parts)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def parse_range(text: str) -> Tuple[float, float]:
    parts = [part.strip() for part in text.replace(";", ",").split(",") if part.strip()]
    if len(parts) != 2:
        raise argparse.ArgumentTypeError("expected two comma-separated numbers, e.g. -0.28,0.28")
    try:
        return (float(parts[0]), float(parts[1]))
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def parse_args() -> argparse.Namespace:
    default_out = SCRIPT_DIR / f"P101040_BLACKDOT_ROTATION_CASE_{datetime.now():%Y%m%d_%H%M%S}"
    parser = argparse.ArgumentParser(
        description=(
            "Render a P101040_blue black-dot sequence with fixed camera/lights and "
            "object-only rotation/translation."
        )
    )
    parser.add_argument("--out", default=str(default_out), help="Output folder for the case.")
    parser.add_argument("--step-deg", type=float, default=20.0, help="Rotation step in degrees.")
    parser.add_argument(
        "--rotation-axis",
        choices=["x", "y", "z"],
        default="z",
        help="World axis used for the full-circle object rotation.",
    )
    parser.add_argument(
        "--translation-direction",
        type=parse_vector,
        default=(1.0, 0.0, 0.0),
        help="Direction vector for object translation, e.g. 1,0,0.",
    )
    parser.add_argument(
        "--translation-distance",
        type=float,
        default=0.03,
        help="Fixed translation distance applied to the object for every frame.",
    )
    parser.add_argument("--samples", type=int, default=16, help="Cycles samples per frame.")
    parser.add_argument("--width", type=int, default=1536)
    parser.add_argument("--height", type=int, default=1024)
    parser.add_argument("--seed", type=int, default=90504, help="Fixed seed; keeps the defect placement stable.")
    parser.add_argument(
        "--safe-anchor-local-x",
        type=parse_range,
        default=(-0.28, 0.28),
        help="Local X safe range for black-dot placement, e.g. -0.28,0.28.",
    )
    parser.add_argument(
        "--safe-anchor-local-y",
        type=parse_range,
        default=(-0.28, 0.28),
        help="Local Y safe range for black-dot placement, e.g. -0.28,0.28.",
    )
    parser.add_argument("--start-angle", type=float, default=0.0)
    parser.add_argument("--full-circle-deg", type=float, default=360.0)
    parser.add_argument("--python", default=sys.executable, help="Python executable used to launch BlenderProc CLI.")
    parser.add_argument("--dry-run", action="store_true", help="Write the run plan without launching renders.")
    parser.add_argument(
        "--allow-active-blender",
        action="store_true",
        help="Run even if another Blender process may be active. Use with care during production batches.",
    )
    return parser.parse_args()


def normalize_vector(vector: Tuple[float, float, float]) -> Tuple[float, float, float]:
    length = math.sqrt(sum(value * value for value in vector))
    if length <= 1e-12:
        return (0.0, 0.0, 0.0)
    return tuple(value / length for value in vector)


def rotation_for_axis(axis: str, angle: float) -> List[float]:
    rotation = {"x": [angle, 0.0, 0.0], "y": [0.0, angle, 0.0], "z": [0.0, 0.0, angle]}
    return rotation[axis]


def frame_angles(start: float, step: float, full_circle: float) -> List[float]:
    if step <= 0:
        raise ValueError("--step-deg must be positive")
    count = int(round(full_circle / step))
    if count <= 0:
        raise ValueError("full-circle/step produced no frames")
    return [start + index * step for index in range(count)]


def copy_if_exists(src: Path, dst: Path) -> Optional[str]:
    if not src.exists():
        return None
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return str(dst)


def build_contact_sheet(case_dir: Path, frames: List[Dict]) -> Optional[str]:
    try:
        from PIL import Image, ImageDraw
    except Exception:
        return None

    thumbs = []
    for frame in frames:
        rgb_path = Path(frame["rgb"])
        mask_path = Path(frame["mask"])
        if not rgb_path.exists() or not mask_path.exists():
            continue
        rgb = Image.open(rgb_path).convert("RGB")
        mask = Image.open(mask_path).convert("L").resize(rgb.size)
        overlay = rgb.copy()
        red = Image.new("RGB", rgb.size, (255, 0, 0))
        overlay.paste(red, mask=mask.point(lambda p: 120 if p >= 128 else 0))
        tile = Image.new("RGB", (360, 270), (245, 245, 245))
        overlay.thumbnail((340, 220), Image.LANCZOS)
        tile.paste(overlay, ((360 - overlay.width) // 2, 18))
        draw = ImageDraw.Draw(tile)
        draw.text((12, 240), f"{frame['frame_id']}  angle={frame['angle_deg']:.1f}", fill=(20, 20, 20))
        thumbs.append(tile)
    if not thumbs:
        return None
    cols = 3
    rows = math.ceil(len(thumbs) / cols)
    sheet = Image.new("RGB", (cols * 360, rows * 270), (230, 230, 230))
    for index, tile in enumerate(thumbs):
        sheet.paste(tile, ((index % cols) * 360, (index // cols) * 270))
    path = case_dir / "P101040_blackdot_rotation_contact_sheet.jpg"
    sheet.save(path, quality=92)
    return str(path)


def active_blender_processes() -> List[str]:
    if os.name != "nt":
        return []
    powershell = shutil.which("powershell") or shutil.which("powershell.exe")
    if not powershell:
        system_powershell = Path(r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe")
        if system_powershell.exists():
            powershell = str(system_powershell)
    if powershell:
        try:
            result = subprocess.run(
                [
                    powershell,
                    "-NoProfile",
                    "-Command",
                    "Get-Process blender -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id",
                ],
                universal_newlines=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            ids = [line.strip() for line in result.stdout.splitlines() if line.strip()]
            if ids:
                return ["blender.exe pid=" + pid for pid in ids]
        except Exception:
            pass
    try:
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq blender.exe", "/FO", "CSV", "/NH"],
            universal_newlines=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except Exception:
        return []
    processes = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line or "INFO:" in line:
            continue
        if "blender.exe" in line.lower():
            processes.append(line)
    return processes


def first_accepted_sample(run_dir: Path) -> Optional[Dict]:
    metadata_path = run_dir / "metadata.json"
    if not metadata_path.exists():
        return None
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    samples = metadata.get("samples") or []
    return samples[0] if samples else None


def main() -> int:
    args = parse_args()
    case_dir = Path(args.out).resolve()
    raw_dir = case_dir / "per_angle_runs"
    rgb_dir = case_dir / "rgb"
    mask_dir = case_dir / "masks"
    overlay_dir = case_dir / "overlay"
    label_dir = case_dir / "labels_yolo"
    for folder in (raw_dir, rgb_dir, mask_dir, overlay_dir, label_dir):
        folder.mkdir(parents=True, exist_ok=True)

    direction = normalize_vector(args.translation_direction)
    translation = [value * args.translation_distance for value in direction]
    angles = frame_angles(args.start_angle, args.step_deg, args.full_circle_deg)
    plan = {
        "case": "p101040_blue_blackdot_fixed_camera_object_rotation",
        "created_at_local": datetime.now().isoformat(timespec="seconds"),
        "interference_policy": {
            "production_files_modified": False,
            "backend_modified": False,
            "output_root_isolated": str(case_dir),
            "note": "This wrapper only calls the existing black-dot reference backend with diagnostic transform args.",
        },
        "backend_script": str(BACKEND_SCRIPT),
        "model": "P101040_blue",
        "defect": "black_dot",
        "anchor_side": "front",
        "fixed_camera_lighting": True,
        "object_transform_mode": "keep_camera",
        "object_transform_camera_side": "front",
        "rotation_axis": args.rotation_axis,
        "step_deg": args.step_deg,
        "angles_deg": angles,
        "translation_direction_normalized": direction,
        "translation_distance": args.translation_distance,
        "translation_xyz": translation,
        "safe_anchor_local_x": [args.safe_anchor_local_x[0], args.safe_anchor_local_x[1]],
        "safe_anchor_local_y": [args.safe_anchor_local_y[0], args.safe_anchor_local_y[1]],
        "samples": args.samples,
        "seed": args.seed,
        "frames": [],
    }
    (case_dir / "rotation_case_plan.json").write_text(
        json.dumps(plan, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    if args.dry_run:
        print(f"Dry run wrote plan: {case_dir / 'rotation_case_plan.json'}")
        return 0

    active_blenders = active_blender_processes()
    if active_blenders and not args.allow_active_blender:
        print("Active blender.exe process detected; refusing to start the demo render to avoid GPU contention.")
        print("Re-run with --allow-active-blender only if the active render is not production-critical.")
        for process in active_blenders:
            print(process)
        return 2

    failures = []
    frames = []
    for index, angle in enumerate(angles):
        frame_id = f"angle_{int(round(angle)) % 360:03d}"
        run_dir = raw_dir / frame_id
        rotate = rotation_for_axis(args.rotation_axis, angle)
        command = [
            args.python,
            str(REPO_ROOT / "cli.py"),
            "run",
            str(BACKEND_SCRIPT),
            "--",
            "--model",
            "P101040_blue",
            "--output",
            str(run_dir),
            "--num",
            "1",
            "--start_index",
            "0",
            "--width",
            str(args.width),
            "--height",
            str(args.height),
            "--samples",
            str(args.samples),
            "--seed",
            str(args.seed),
            "--anchor_sides",
            "front",
            "--object_transform_mode",
            "keep_camera",
            "--object_transform_camera_side",
            "front",
            "--object_rotate_deg",
            *(str(value) for value in rotate),
            "--object_translate",
            *(f"{value:.8f}" for value in translation),
            "--safe_anchor_local_x",
            f"{args.safe_anchor_local_x[0]:.6f}",
            f"{args.safe_anchor_local_x[1]:.6f}",
            "--safe_anchor_local_y",
            f"{args.safe_anchor_local_y[0]:.6f}",
            f"{args.safe_anchor_local_y[1]:.6f}",
            "--safe_anchor_normal_z_min",
            "0.82",
        ]
        print(f"[{index + 1:02d}/{len(angles):02d}] render {frame_id}: rotate={rotate}, translate={translation}")
        result = subprocess.run(command, cwd=REPO_ROOT, universal_newlines=True)
        if result.returncode != 0:
            failures.append({"frame_id": frame_id, "angle_deg": angle, "returncode": result.returncode})
            continue

        sample = first_accepted_sample(run_dir)
        if sample is None:
            failures.append({"frame_id": frame_id, "angle_deg": angle, "error": "no accepted sample metadata"})
            continue
        rgb_out = rgb_dir / f"{frame_id}.png"
        mask_out = mask_dir / f"{frame_id}.png"
        overlay_out = overlay_dir / f"{frame_id}.png"
        label_out = label_dir / f"{frame_id}.txt"
        frame = {
            "frame_id": frame_id,
            "angle_deg": angle,
            "rotation_degrees_xyz": rotate,
            "translation_xyz": translation,
            "source_run_dir": str(run_dir),
            "source_image_id": sample.get("image_id"),
            "bbox": sample.get("bbox"),
            "rgb": copy_if_exists(run_dir / sample["rgb"], rgb_out),
            "mask": copy_if_exists(run_dir / sample["mask"], mask_out),
            "overlay": copy_if_exists(run_dir / sample["overlay"], overlay_out),
            "label_yolo": copy_if_exists(run_dir / sample["label_yolo"], label_out),
            "metadata": str(run_dir / "metadata.json"),
        }
        frames.append(frame)

    plan["frames"] = frames
    plan["failures"] = failures
    plan["contact_sheet"] = build_contact_sheet(case_dir, frames)
    (case_dir / "rotation_case_summary.json").write_text(
        json.dumps(plan, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"Done. frames={len(frames)} failures={len(failures)} output={case_dir}")
    if plan["contact_sheet"]:
        print(f"Contact sheet: {plan['contact_sheet']}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
