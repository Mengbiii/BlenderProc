#!/usr/bin/env python
"""Run the 500-image rehearsal generation plan.

This runner intentionally calls the public app.py commands instead of importing
renderer internals, so the rehearsal exercises the same CLI path as production.
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
APP_PATH = PROJECT_ROOT / "defect_dataset_generator" / "app.py"
DEFAULT_PLAN = PROJECT_ROOT / "defect_dataset_generator" / "config" / "3k_5k_rehearsal_generation_plan_v1.json"
MODEL_COLOR_PROFILES = PROJECT_ROOT / "defect_dataset_generator" / "config" / "model_color_profiles.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the 3k-5k rehearsal generation plan.")
    parser.add_argument("--plan", default=str(DEFAULT_PLAN), help="Path to rehearsal generation plan JSON.")
    parser.add_argument("--out", default=None, help="Output root. Defaults to plan output_recommendation.rehearsal_root.")
    parser.add_argument("--samples", type=int, default=None, help="Override render samples.")
    parser.add_argument("--python", default=sys.executable, help="Python executable used to launch app.py.")
    parser.add_argument("--dry-run", action="store_true", help="Build block commands and pass --dry-run to app.py.")
    parser.add_argument("--plan-only", action="store_true", help="Only write expanded block plan; do not launch app.py.")
    parser.add_argument("--max-blocks", type=int, default=None, help="Run only the first N expanded blocks.")
    parser.add_argument(
        "--no-persistent-generic",
        action="store_true",
        help="Disable generic-equivalent block merging and use the older one-block-per-allocation commands.",
    )
    parser.add_argument(
        "--include",
        nargs="+",
        choices=["single", "cooccurrence", "normal"],
        default=["single", "cooccurrence", "normal"],
        help="Subset of generation modes to run.",
    )
    parser.add_argument("--stop-on-failure", action="store_true", help="Stop after the first failed block.")
    return parser.parse_args()


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def resolve_project_path(value: str | None) -> Path:
    if value is None:
        raise ValueError("Path value is required")
    path = Path(value)
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def split_count_by_sides(count: int, side_weights: dict[str, float]) -> list[tuple[str, int]]:
    enabled = [(side, float(weight)) for side, weight in side_weights.items() if float(weight) > 0]
    if not enabled:
        enabled = [("front", 1.0)]
    total = sum(weight for _, weight in enabled)
    raw = [(side, count * weight / total) for side, weight in enabled]
    allocations = [(side, int(math.floor(value))) for side, value in raw]
    remainder = count - sum(value for _, value in allocations)
    fractions = sorted(
        ((index, raw[index][1] - math.floor(raw[index][1])) for index in range(len(raw))),
        key=lambda item: item[1],
        reverse=True,
    )
    for index, _ in fractions[:remainder]:
        side, value = allocations[index]
        allocations[index] = (side, value + 1)
    return [(side, value) for side, value in allocations if value > 0]


def side_weights_for_target(plan: dict, target: str) -> dict[str, float]:
    side_policy = plan.get("side_policy", {})
    if target in side_policy and isinstance(side_policy[target], dict):
        return side_policy[target]
    return side_policy.get("default_front_back_targets", {"front": 1.0})


def safe_name(value: str) -> str:
    return value.replace("/", "_").replace("\\", "_").replace("+", "_").replace(",", "_")


def build_blocks(plan: dict, out_root: Path, samples: int, include: set[str], use_persistent_generic: bool = True) -> list[dict]:
    blocks = []
    persistent_groups = {}
    profiles = load_json(MODEL_COLOR_PROFILES).get("profiles", {})
    single_seed = int(plan.get("seed_policy", {}).get("single_defect_seed_start", 26000))
    multi_seed = int(plan.get("seed_policy", {}).get("multi_defect_seed_start", 36000))
    normal_seed = int(plan.get("seed_policy", {}).get("normal_seed_start", 46000))

    if "single" in include:
        block_index = 0
        for item in plan.get("single_defect_allocation", []):
            target = item["target"]
            defect = item["defect"]
            for side, count in split_count_by_sides(int(item["count"]), side_weights_for_target(plan, target)):
                seed = single_seed + block_index * 100
                output_dir = out_root / "single" / safe_name(target) / safe_name(defect) / ("side_" + side)
                if use_persistent_generic and defects_are_generic(profiles, target, [defect]):
                    add_persistent_samples(persistent_groups, target, side, "single", [defect], count, seed)
                else:
                    command = [
                        sys.executable,
                        str(APP_PATH),
                        "generate-target",
                        "--target",
                        target,
                        "--defects",
                        defect,
                        "--count",
                        str(count),
                        "--samples",
                        str(samples),
                        "--seed",
                        str(seed),
                        "--out",
                        str(output_dir),
                        "--anchor-sides",
                        side,
                    ]
                    blocks.append(make_block("single", target, [defect], side, count, seed, output_dir, command))
                block_index += 1

    if "cooccurrence" in include:
        block_index = 0
        for item in plan.get("multi_defect_cooccurrence_allocation", []):
            target = item["target"]
            defects = list(item["defects"])
            for side, count in split_count_by_sides(int(item["count"]), side_weights_for_target(plan, target)):
                seed = multi_seed + block_index * 100
                output_dir = out_root / "cooccurrence" / safe_name(target) / safe_name("+".join(defects)) / ("side_" + side)
                if use_persistent_generic and defects_are_generic(profiles, target, defects):
                    add_persistent_samples(persistent_groups, target, side, "cooccurrence", defects, count, seed)
                else:
                    command = [
                        sys.executable,
                        str(APP_PATH),
                        "generate-target-cooccurrence",
                        "--target",
                        target,
                        "--defects",
                        ",".join(defects),
                        "--count",
                        str(count),
                        "--samples",
                        str(samples),
                        "--seed",
                        str(seed),
                        "--out",
                        str(output_dir),
                        "--anchor-sides",
                        side,
                    ]
                    blocks.append(make_block("cooccurrence", target, defects, side, count, seed, output_dir, command))
                block_index += 1

    if "normal" in include:
        block_index = 0
        for item in plan.get("normal_allocation", []):
            target = item["target"]
            for side, count in split_count_by_sides(int(item["count"]), side_weights_for_target(plan, target)):
                seed = normal_seed + block_index * 100
                if use_persistent_generic:
                    add_persistent_samples(persistent_groups, target, side, "normal", [], count, seed)
                else:
                    output_dir = out_root / "normal" / safe_name(target) / ("side_" + side)
                    command = [
                        sys.executable,
                        str(APP_PATH),
                        "generate-target-normal",
                        "--target",
                        target,
                        "--count",
                        str(count),
                        "--samples",
                        str(samples),
                        "--seed",
                        str(seed),
                        "--out",
                        str(output_dir),
                        "--anchor-sides",
                        side,
                    ]
                    blocks.append(make_block("normal", target, [], side, count, seed, output_dir, command))
                block_index += 1

    if use_persistent_generic:
        blocks.extend(build_persistent_blocks(persistent_groups, out_root, samples))
    return blocks


def make_block(mode: str, target: str, defects: list[str], side: str, count: int, seed: int, output_dir: Path, command: list[str]) -> dict:
    return {
        "mode": mode,
        "target": target,
        "defects": defects,
        "side": side,
        "count": count,
        "seed": seed,
        "output_dir": str(output_dir),
        "command": command,
        "status": "planned",
    }


def target_defect_backend_name(target: str, defect: str) -> str:
    if defect == "black_dot" and target in {"p101040_blue", "qc71336_white", "qc71336_gray", "qc7_5244_white"}:
        return "reference_blackdot"
    if target == "qc71336_black" and defect in {"foreign_material", "splay"}:
        return "qc71336_black_reference"
    if target == "qc71336_white" and defect == "foreign_material":
        return "qc71336_white_foreign_reference"
    if target == "qc7_5244_white" and defect == "mixed_color_contamination":
        return "qc75244_mixed_color_reference"
    return "generic_main_plane"


def defects_are_generic(profiles: dict, target: str, defects: list[str]) -> bool:
    supported = set(profiles.get(target, {}).get("supported_defects", []))
    return all(defect in supported and target_defect_backend_name(target, defect) == "generic_main_plane" for defect in defects)


def add_persistent_samples(groups: dict, target: str, side: str, mode: str, defects: list[str], count: int, seed: int) -> None:
    key = (target, side)
    group = groups.setdefault(key, {"target": target, "side": side, "samples": [], "source_modes": set(), "source_defects": set()})
    for offset in range(count):
        group["samples"].append(
            {
                "index": len(group["samples"]),
                "mode": mode,
                "defects": list(defects),
                "side": side,
                "seed": int(seed) + offset,
            }
        )
    group["source_modes"].add(mode)
    group["source_defects"].update(defects)


def build_persistent_blocks(groups: dict, out_root: Path, samples: int) -> list[dict]:
    blocks = []
    plan_dir = out_root / "_persistent_batch_plans"
    for key in sorted(groups):
        group = groups[key]
        if not group["samples"]:
            continue
        target = group["target"]
        side = group["side"]
        output_dir = out_root / "persistent" / safe_name(target) / ("side_" + side)
        plan_path = plan_dir / f"{safe_name(target)}__side_{safe_name(side)}.json"
        batch_plan = {
            "schema_version": "persistent_batch_plan_v0.1",
            "target": target,
            "description": "Auto-merged generic-equivalent rehearsal block.",
            "samples": group["samples"],
            "source_modes": sorted(group["source_modes"]),
            "source_defects": sorted(group["source_defects"]),
        }
        write_json(plan_path, batch_plan)
        command = [
            sys.executable,
            str(APP_PATH),
            "generate-target-persistent-batch",
            "--target",
            target,
            "--plan",
            str(plan_path),
            "--out",
            str(output_dir),
            "--samples",
            str(samples),
            "--seed",
            str(group["samples"][0]["seed"]),
        ]
        block = make_block(
            "persistent_generic",
            target,
            sorted(group["source_defects"]),
            side,
            len(group["samples"]),
            int(group["samples"][0]["seed"]),
            output_dir,
            command,
        )
        block["source_modes"] = sorted(group["source_modes"])
        block["persistent_plan"] = str(plan_path)
        blocks.append(block)
    return blocks


def remap_python(command: list[str], python_executable: str) -> list[str]:
    remapped = list(command)
    remapped[0] = python_executable
    return remapped


def run_block(block: dict, python_executable: str, dry_run: bool) -> dict:
    command = remap_python(block["command"], python_executable)
    if dry_run:
        command.append("--dry-run")
    record = dict(block)
    record["command"] = command
    started = datetime.now().isoformat(timespec="seconds")
    completed = subprocess.run(
        command,
        cwd=str(PROJECT_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
    )
    finished = datetime.now().isoformat(timespec="seconds")
    record["started_at"] = started
    record["finished_at"] = finished
    record["returncode"] = completed.returncode
    record["stdout_tail"] = completed.stdout[-6000:]
    record["status"] = "failed" if completed.returncode != 0 else "completed"
    plan_path = Path(record["output_dir"]) / "generation_plan.json"
    if plan_path.exists():
        try:
            block_plan = load_json(plan_path)
            record["backend_status"] = block_plan.get("status")
            record["total_requested"] = block_plan.get("total_requested", block_plan.get("count"))
            record["total_succeeded"] = block_plan.get("total_succeeded")
            record["total_failed"] = block_plan.get("total_failed")
            record["gpu_summary"] = extract_gpu_summary(Path(record["output_dir"]))
            if block_plan.get("status") in {"failed", "rendered_with_failures"} or block_plan.get("total_failed", 0):
                record["status"] = "failed"
        except Exception as exc:
            record["status"] = "failed"
            record["plan_read_error"] = str(exc)
    return record


def extract_gpu_summary(output_dir: Path) -> dict:
    metadata_path = output_dir / "metadata.json"
    backend_log_path = output_dir / "backend_run_log.json"
    summary = {"metadata_found": metadata_path.exists(), "backend_log_found": backend_log_path.exists(), "gpu_enabled": None}
    if metadata_path.exists():
        try:
            metadata = load_json(metadata_path)
            info = metadata.get("render_device_info")
            if isinstance(info, dict):
                summary.update(
                    {
                        "gpu_enabled": bool(info.get("gpu_enabled")) if "gpu_enabled" in info else info.get("cycles_device") == "GPU",
                        "cycles_device": info.get("cycles_device"),
                        "compute_device_type": info.get("compute_device_type"),
                        "enabled_devices": info.get("enabled_devices", []),
                    }
                )
        except Exception as exc:
            summary["metadata_error"] = str(exc)
    if summary.get("gpu_enabled") is None and backend_log_path.exists():
        try:
            log = load_json(backend_log_path)
            stdout = str(log.get("stdout", ""))
            has_gpu_hint = "Device NVIDIA" in stdout or "OPTIX" in stdout or "CUDA" in stdout
            has_gpu_device = "cycles_device\": \"GPU" in stdout or "cycles_device': 'GPU" in stdout
            summary["backend_log_gpu_hint"] = has_gpu_hint
            if stdout:
                summary["gpu_enabled"] = has_gpu_device or has_gpu_hint
        except Exception as exc:
            summary["backend_log_error"] = str(exc)
    return summary


def summarize(records: list[dict], plan: dict, out_root: Path) -> dict:
    total_requested = sum(int(record.get("count", 0)) for record in records)
    total_succeeded = sum(int(record.get("total_succeeded") or 0) for record in records)
    total_failed_samples = sum(int(record.get("total_failed") or 0) for record in records)
    failed_blocks = [record for record in records if record.get("status") != "completed"]
    gpu_failed_blocks = [
        record
        for record in records
        if record.get("status") == "completed" and record.get("gpu_summary", {}).get("gpu_enabled") is False
    ]
    by_mode = {}
    for record in records:
        mode = record["mode"]
        by_mode.setdefault(mode, {"blocks": 0, "requested": 0, "succeeded": 0, "failed_samples": 0, "failed_blocks": 0})
        by_mode[mode]["blocks"] += 1
        by_mode[mode]["requested"] += int(record.get("count", 0))
        by_mode[mode]["succeeded"] += int(record.get("total_succeeded") or 0)
        by_mode[mode]["failed_samples"] += int(record.get("total_failed") or 0)
        if record.get("status") != "completed":
            by_mode[mode]["failed_blocks"] += 1
    return {
        "schema_version": "0.1",
        "plan_id": plan.get("plan_id"),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "output_root": str(out_root),
        "block_count": len(records),
        "total_requested": total_requested,
        "total_succeeded": total_succeeded,
        "total_failed_samples": total_failed_samples,
        "failed_block_count": len(failed_blocks),
        "gpu_failed_block_count": len(gpu_failed_blocks),
        "by_mode": by_mode,
        "failed_blocks": failed_blocks,
        "gpu_failed_blocks": gpu_failed_blocks,
        "records": records,
    }


def main() -> int:
    args = parse_args()
    plan_path = Path(args.plan).resolve()
    plan = load_json(plan_path)
    out_root = resolve_project_path(args.out or plan.get("output_recommendation", {}).get("rehearsal_root"))
    samples = int(args.samples or plan.get("render_policy", {}).get("rehearsal_samples", 16))
    blocks = build_blocks(plan, out_root, samples, set(args.include), use_persistent_generic=not args.no_persistent_generic)
    if args.max_blocks is not None:
        blocks = blocks[: args.max_blocks]

    out_root.mkdir(parents=True, exist_ok=True)
    expanded = {
        "schema_version": "0.1",
        "plan_path": str(plan_path),
        "output_root": str(out_root),
        "samples": samples,
        "dry_run": bool(args.dry_run),
        "plan_only": bool(args.plan_only),
        "persistent_generic_enabled": not args.no_persistent_generic,
        "blocks": blocks,
        "total_requested": sum(block["count"] for block in blocks),
    }
    write_json(out_root / "expanded_rehearsal_plan.json", expanded)
    if args.plan_only:
        print(json.dumps(expanded, indent=2, ensure_ascii=False))
        return 0

    records = []
    for index, block in enumerate(blocks, start=1):
        print("[{0}/{1}] {mode} {target} {defects} side={side} count={count}".format(index, len(blocks), **block), flush=True)
        record = run_block(block, args.python, args.dry_run)
        records.append(record)
        write_json(out_root / "rehearsal_run_summary.partial.json", summarize(records, plan, out_root))
        if record.get("status") != "completed" and args.stop_on_failure:
            break

    summary = summarize(records, plan, out_root)
    write_json(out_root / "rehearsal_run_summary.json", summary)
    print(json.dumps({k: summary[k] for k in ["output_root", "block_count", "total_requested", "total_succeeded", "failed_block_count", "gpu_failed_block_count"]}, indent=2, ensure_ascii=False))
    return 1 if summary["failed_block_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
