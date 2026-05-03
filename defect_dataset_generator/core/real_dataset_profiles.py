"""Helpers for reading the reorganized real defect dataset folders."""

from pathlib import Path


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp"}

COLOR_SUFFIXES = {
    # Legacy mojibake spellings kept for compatibility with old reports.
    "钃濊壊": "blue",
    "鐧借壊": "white",
    "鐏拌壊": "gray",
    "榛戣壊": "black",
    # Current real dataset folder names.
    "蓝色": "blue",
    "白色": "white",
    "灰色": "gray",
    "黑色": "black",
}

DEFECT_KEYWORDS = [
    ("榛戠偣", "black_dot"),
    ("娣疯壊", "mixed_color_contamination"),
    ("寮傜墿", "foreign_material"),
    ("鏂欒姳", "splay"),
    ("姝ｅ父", "normal"),
    ("黑点", "black_dot"),
    ("混色", "mixed_color_contamination"),
    ("异物", "foreign_material"),
    ("料花", "splay"),
    ("正常", "normal"),
]


def parse_model_appearance_folder_name(name):
    """Infer model id and appearance color from a top-level real-data folder."""
    normalized = name.strip()
    for suffix, color_id in COLOR_SUFFIXES.items():
        if normalized.endswith(suffix):
            model_id = normalized[: -len(suffix)].strip("-_ ")
            return {
                "folder_name": name,
                "model_id": model_id,
                "appearance_color": color_id,
                "appearance_label": suffix,
            }
    return {
        "folder_name": name,
        "model_id": normalized,
        "appearance_color": "unknown",
        "appearance_label": None,
    }


def infer_defect_type_from_folder_name(name):
    """Map a Chinese defect folder name to the canonical project defect type."""
    for keyword, defect_type in DEFECT_KEYWORDS:
        if keyword in name:
            return defect_type
    return "unknown"


def scan_real_dataset_root(root):
    """Scan the reorganized real dataset root and summarize model/color folders."""
    root = Path(root)
    profiles = []
    for model_dir in sorted([p for p in root.iterdir() if p.is_dir()]):
        profile = parse_model_appearance_folder_name(model_dir.name)
        children = []
        for child in sorted([p for p in model_dir.iterdir() if p.is_dir()]):
            image_count = sum(
                1
                for item in child.iterdir()
                if item.is_file() and item.suffix.lower() in IMAGE_EXTENSIONS
            )
            children.append(
                {
                    "folder_name": child.name,
                    "path": str(child),
                    "defect_type": infer_defect_type_from_folder_name(child.name),
                    "image_count": image_count,
                }
            )
        profile.update(
            {
                "path": str(model_dir),
                "defect_folders": children,
            }
        )
        profiles.append(profile)
    return {
        "schema_version": "0.2",
        "root": str(root),
        "model_profile_count": len(profiles),
        "model_profiles": profiles,
    }
