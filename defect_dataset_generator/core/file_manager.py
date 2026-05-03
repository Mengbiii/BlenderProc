import json
from pathlib import Path
from typing import Any, Dict, List, Set, Union


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}
SCRIPT_SUFFIXES = {".py", ".ps1"}
CONFIG_SUFFIXES = {".json", ".yaml", ".yml"}
MODEL_SUFFIXES = {".blend", ".stl", ".obj", ".fbx"}


def resolve_path(path_value: Union[str, Path], base_dir: Path) -> Path:
    path = Path(path_value)
    if not path.is_absolute():
        path = base_dir / path
    return path.resolve()


def ensure_output_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def load_json_file(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"JSON file not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def validate_blend_file(path: Path) -> Path:
    if not path.exists():
        raise FileNotFoundError(f"Blend file not found: {path}")
    if path.suffix.lower() != ".blend":
        raise ValueError(f"Expected a .blend file, got: {path}")
    return path


def validate_reference_images(path: Path) -> List[Path]:
    if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES:
        return [path]
    if path.is_dir():
        images = sorted(p for p in path.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES)
        if images:
            return images
    raise FileNotFoundError(f"No reference images found at: {path}")


def collect_project_inspection(project_root: Path) -> Dict[str, Any]:
    my_project = project_root / "examples" / "my_project"
    assets_models = project_root / "assets" / "models"
    memory_files = [
        "README_PROJECT_MEMORY.md",
        "PROJECT_STATUS.md",
        "CURRENT_BASELINES.md",
        "DEFECT_SCHEMA.md",
        "MODEL_AND_APPEARANCE_SCHEMA.md",
        "NEXT_TASKS.md",
        "DECISIONS.md",
    ]

    important_scripts = []
    if my_project.exists():
        for path in sorted(my_project.glob("*.py")):
            important_scripts.append(classify_script(path))

    output_dirs = []
    if my_project.exists():
        output_dirs = [
            str(p.relative_to(project_root))
            for p in sorted(my_project.iterdir())
            if p.is_dir() and _looks_like_output_dir(p.name)
        ][:120]

    return {
        "project_root": str(project_root),
        "my_project_dir": str(my_project),
        "memory_files": [
            {"path": str(project_root / name), "exists": (project_root / name).exists()}
            for name in memory_files
        ],
        "model_assets": summarize_files(assets_models, MODEL_SUFFIXES),
        "important_scripts": important_scripts,
        "output_like_dirs_sample": output_dirs,
        "config_files_sample": summarize_files(my_project, CONFIG_SUFFIXES, recursive=False),
    }


def classify_script(path: Path) -> Dict[str, str]:
    name = path.name
    lower = name.lower()
    if lower == "reference_blend_blackdot_multi_model.py":
        role = "current stable black_dot handoff generator"
    elif lower == "generate_black_spot_multi_model.py":
        role = "large multi-model generator and schema bridge"
    elif lower.startswith("reference_blend_"):
        role = "reference-scene debug/prototype renderer"
    elif lower.startswith("generate_"):
        role = "generation experiment or legacy generator"
    elif lower.startswith("evaluate_") or lower.startswith("audit_"):
        role = "evaluation/audit utility"
    elif lower.startswith("prepare_") or lower.startswith("apply_") or lower.startswith("refine_"):
        role = "dataset preparation or label utility"
    elif "debug" in lower:
        role = "debug inspection utility"
    elif lower.endswith(".ps1"):
        role = "PowerShell helper"
    else:
        role = "utility or experiment script"
    return {"path": str(path), "role": role}


def summarize_files(
    root: Path, suffixes: Set[str], recursive: bool = False, limit: int = 80
) -> List[str]:
    if not root.exists():
        return []
    iterator = root.rglob("*") if recursive else root.glob("*")
    files = [p for p in iterator if p.is_file() and p.suffix.lower() in suffixes]
    return [str(p) for p in sorted(files)[:limit]]


def _looks_like_output_dir(name: str) -> bool:
    prefixes = (
        "output",
        "FINAL",
        "REFERENCE",
        "EVALUATION",
        "UNIFIED",
        "smoke",
        "debug",
        "P101040",
        "QC71336",
        "QC752",
    )
    return name.startswith(prefixes) or "SMOKE" in name or "BATCH" in name
