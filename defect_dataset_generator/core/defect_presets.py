"""Helpers for loading defect appearance presets."""

from copy import deepcopy
from pathlib import Path


def load_defect_preset(preset_file, preset_id):
    import json

    preset_file = Path(preset_file)
    data = json.loads(preset_file.read_text(encoding="utf-8"))
    presets = data.get("presets", {})
    if preset_id not in presets:
        available = ", ".join(sorted(presets.keys()))
        raise ValueError("Unknown defect preset '%s'. Available presets: %s" % (preset_id, available))
    preset = deepcopy(presets[preset_id])
    preset["preset_id"] = preset_id
    preset["preset_file"] = str(preset_file)
    preset["preset_schema_version"] = data.get("schema_version")
    return preset


def apply_black_dot_preset_to_config(defect_config, preset):
    """Merge backend black-dot controls into the framework defect config.

    The visual appearance remains implemented by the Blender backend. This
    function only carries stable JSON preset values through the wrapper.
    """
    updated = deepcopy(defect_config)
    updated["black_dot_appearance_preset"] = {
        "preset_id": preset.get("preset_id"),
        "preset_file": preset.get("preset_file"),
        "model_id": preset.get("model_id"),
        "appearance_color": preset.get("appearance_color"),
        "backend_model": preset.get("backend_model"),
        "backend_parameters": deepcopy(preset.get("backend_parameters", {})),
        "appearance_notes": deepcopy(preset.get("appearance_notes", {})),
    }
    return updated
