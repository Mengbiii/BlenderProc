import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = PROJECT_ROOT / "defect_dataset_generator"
APP = APP_ROOT / "app.py"
PROFILES = APP_ROOT / "config" / "model_color_profiles.json"
REAL_MANIFEST = APP_ROOT / "outputs" / "real_annotations_v2_screened_bestbox" / "manifests" / "high_conf_l1_samples.csv"
EVAL_TOOL = APP_ROOT / "tools" / "evaluate_defect_realism.py"


def run_command(command, log_path):
    log_path.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        command,
        cwd=str(PROJECT_ROOT),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    log_path.write_text(proc.stdout, encoding="utf-8")
    return proc.returncode


def load_profiles():
    data = json.loads(PROFILES.read_text(encoding="utf-8"))
    profiles = data["profiles"]
    for key, profile in profiles.items():
        profile["target_id"] = key
    return profiles


def iter_json_files(path):
    if not path.exists():
        return []
    return sorted(path.rglob("*.json"))


def collect_anchor_markers(value, markers, normals):
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"anchor_side", "anchor_band", "main_plane_axis"} and isinstance(item, str):
                markers.append(item)
            elif key == "world_normal" and isinstance(item, list) and len(item) == 3:
                try:
                    normals.append([float(v) for v in item])
                except Exception:
                    pass
            else:
                collect_anchor_markers(item, markers, normals)
    elif isinstance(value, list):
        for item in value:
            collect_anchor_markers(item, markers, normals)


def side_coverage(dataset_dir):
    markers = []
    normals = []
    for path in iter_json_files(dataset_dir / "metadata"):
        try:
            collect_anchor_markers(json.loads(path.read_text(encoding="utf-8")), markers, normals)
        except Exception:
            continue
    sides = set()
    for marker in markers:
        low = marker.lower()
        if low in {"front", "front_face"}:
            sides.add("front")
        elif low in {"back", "back_face"}:
            sides.add("back")
        elif low == "side":
            sides.add("side")
    for normal in normals:
        if normal[2] >= 0.55:
            sides.add("front")
        elif normal[2] <= -0.55:
            sides.add("back")
    return sorted(sides)


def count_files(dataset_dir):
    return {
        "rgb": len(list((dataset_dir / "rgb").glob("*.png"))) if (dataset_dir / "rgb").exists() else 0,
        "mask": len(list((dataset_dir / "masks").glob("*.png"))) if (dataset_dir / "masks").exists() else 0,
        "label": len(list((dataset_dir / "labels_yolo").glob("*.txt"))) if (dataset_dir / "labels_yolo").exists() else 0,
    }


def summarize_generation(dataset_dir):
    summary_path = dataset_dir / "target_generation_summary.json"
    if not summary_path.exists():
        return {"status": "missing_summary", "succeeded": 0, "failed": 0}
    try:
        data = json.loads(summary_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"status": f"bad_summary:{exc}", "succeeded": 0, "failed": 0}
    succeeded = 0
    failed = 0
    statuses = []
    for plan in data.get("plans", []):
        succeeded += int(plan.get("total_succeeded", 0) or 0)
        failed += int(plan.get("total_failed", 0) or 0)
        statuses.append(str(plan.get("status", "")))
    return {"status": ";".join(statuses) or data.get("status", ""), "succeeded": succeeded, "failed": failed}


def parse_eval_status(eval_dir):
    summary = eval_dir / "defect_realism_summary.json"
    if not summary.exists():
        return {"eval_status": "missing", "real_count": 0, "synthetic_count": 0, "pass": 0, "warn": 0, "fail": 0}
    data = json.loads(summary.read_text(encoding="utf-8"))
    counts = data.get("synthetic_assessment", {}).get("status_counts", {})
    return {
        "eval_status": "ok",
        "real_count": data.get("real_metrics", {}).get("count", 0),
        "synthetic_count": data.get("synthetic_metrics", {}).get("count", 0),
        "pass": counts.get("pass", 0),
        "warn": counts.get("warn", 0),
        "fail": counts.get("fail", 0),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(APP_ROOT / "outputs" / "production_readiness_matrix_20260502_v1"))
    parser.add_argument("--count-per-side", type=int, default=2)
    parser.add_argument("--ql3-count", type=int, default=4)
    parser.add_argument("--samples", type=int, default=4)
    parser.add_argument("--seed", type=int, default=9200)
    args = parser.parse_args()

    out_root = Path(args.out)
    dataset_root = out_root / "datasets"
    eval_root = out_root / "eval"
    log_root = out_root / "logs"
    out_root.mkdir(parents=True, exist_ok=True)

    profiles = load_profiles()
    rows = []
    task_index = 0
    for target_id, profile in profiles.items():
        for defect in profile.get("supported_defects", []):
            side_groups = [("ql3_profile", None)] if target_id == "ql3_1052_black" else [("front", "front"), ("back", "back")]
            for side_label, side in side_groups:
                task_index += 1
                dataset_dir = dataset_root / target_id / defect / side_label
                count = args.ql3_count if target_id == "ql3_1052_black" else args.count_per_side
                command = [
                    sys.executable,
                    str(APP),
                    "generate-target",
                    "--target",
                    target_id,
                    "--defects",
                    defect,
                    "--count",
                    str(count),
                    "--samples",
                    str(args.samples),
                    "--seed",
                    str(args.seed + task_index * 17),
                    "--out",
                    str(dataset_dir),
                ]
                if side is not None:
                    command.extend(["--anchor-sides", side])
                gen_rc = run_command(command, log_root / target_id / defect / f"{side_label}_generate.log")
                gen_summary = summarize_generation(dataset_dir)

                eval_dir = eval_root / target_id / defect / side_label
                eval_rc = None
                files = count_files(dataset_dir)
                if gen_summary["succeeded"] > 0 and files["rgb"] > 0 and REAL_MANIFEST.exists():
                    eval_command = [
                        sys.executable,
                        str(EVAL_TOOL),
                        "--real-manifest",
                        str(REAL_MANIFEST),
                        "--real-model",
                        profile["model_id"],
                        "--real-color",
                        profile["appearance_color"],
                        "--defect-type",
                        defect,
                        "--synthetic-dataset",
                        str(dataset_dir),
                        "--max-samples",
                        "80",
                        "--out",
                        str(eval_dir),
                    ]
                    eval_rc = run_command(eval_command, log_root / target_id / defect / f"{side_label}_eval.log")
                eval_summary = parse_eval_status(eval_dir)
                coverage = side_coverage(dataset_dir)
                required = {"side"} if target_id == "ql3_1052_black" and defect == "foreign_material" else ({"front"} if target_id == "ql3_1052_black" else {side_label})
                side_ok = required.issubset(set(coverage))
                rows.append(
                    {
                        "target": target_id,
                        "model": profile["model_id"],
                        "color": profile["appearance_color"],
                        "defect": defect,
                        "requested_side": side_label,
                        "generated_sides": "|".join(coverage),
                        "side_ok": side_ok,
                        "gen_rc": gen_rc,
                        "eval_rc": "" if eval_rc is None else eval_rc,
                        **gen_summary,
                        **files,
                        **eval_summary,
                        "dataset_dir": str(dataset_dir),
                        "eval_dir": str(eval_dir),
                    }
                )

    csv_path = out_root / "matrix_summary.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    rollup = {
        "out_root": str(out_root),
        "rows": len(rows),
        "generated_images": sum(int(row["rgb"]) for row in rows),
        "generation_fail_rows": sum(1 for row in rows if int(row["gen_rc"]) != 0 or int(row["failed"]) > 0),
        "eval_fail_rows": sum(1 for row in rows if row["eval_rc"] not in {"", 0}),
        "side_coverage_fail_rows": sum(1 for row in rows if not row["side_ok"]),
        "summary_csv": str(csv_path),
    }
    (out_root / "matrix_rollup.json").write_text(json.dumps(rollup, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(rollup, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
