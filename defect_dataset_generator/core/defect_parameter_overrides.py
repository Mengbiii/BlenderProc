"""Safe parameter override handling for UI-driven defect generation."""

import json
import math
from pathlib import Path


REFERENCE_BLACKDOT_TARGETS = {"p101040_blue", "qc71336_white", "qc71336_gray", "qc7_5244_white"}
GENERIC_PARAMETERS = {
    "size_factor_min",
    "size_factor_max",
    "width_multiplier",
    "height_multiplier",
    "size_scale",
    "roughness",
    "defect_count_max",
}
REFERENCE_BLACKDOT_PARAMETERS = {
    "black_dot_radius_min_scale",
    "black_dot_radius_max_scale",
    "black_dot_depth_min_scale",
    "black_dot_depth_max_scale",
    "black_dot_max_count",
}
QC71336_WHITE_FOREIGN_PARAMETERS = {
    "foreign_material_radius_scale",
    "foreign_material_depth_scale",
    "defect_count_max",
}
SAME_TYPE_COUNT_PARAMETERS = {"defect_count_max"}


def load_defect_parameter_overrides(path_value, target_id, requested_defects, mode):
    if not path_value:
        return {}
    path = Path(path_value).resolve()
    with path.open("r", encoding="utf-8-sig") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("--defect-params-json must contain a JSON object.")
    if payload.get("target") and payload["target"] != target_id:
        raise ValueError("Parameter file target does not match --target.")
    if payload.get("mode") and payload["mode"] != mode:
        raise ValueError("Parameter file mode does not match the selected generation mode.")
    raw_defects = payload.get("defects", payload)
    if not isinstance(raw_defects, dict):
        raise ValueError("Parameter file must contain a defects object.")

    requested = set(requested_defects)
    normalized = {}
    for defect_type, values in raw_defects.items():
        if defect_type in {"schema_version", "target", "mode"}:
            continue
        if defect_type not in requested:
            raise ValueError("Parameter file contains an unrequested defect: {0}".format(defect_type))
        if not isinstance(values, dict):
            raise ValueError("Parameters for {0} must be a JSON object.".format(defect_type))
        normalized_values = _validate_defect_values(target_id, defect_type, values)
        if normalized_values:
            normalized[defect_type] = normalized_values
    return normalized


def apply_blackdot_parameter_overrides(defect_config, overrides):
    if not overrides:
        return defect_config
    defects = defect_config.setdefault("defects", [{"type": "black_dot"}])
    if not defects:
        defects.append({"type": "black_dot"})
    for key in REFERENCE_BLACKDOT_PARAMETERS:
        if key in overrides:
            defects[0][key] = overrides[key]
            defect_config.setdefault("backend_parameters", {})[key] = overrides[key]
            appearance = defect_config.setdefault("black_dot_appearance_preset", {})
            appearance.setdefault("backend_parameters", {})[key] = overrides[key]
    defect_config["ui_parameter_overrides"] = {
        key: overrides[key] for key in REFERENCE_BLACKDOT_PARAMETERS if key in overrides
    }
    return defect_config


def _validate_defect_values(target_id, defect_type, values):
    allowed = _allowed_parameters(target_id, defect_type)
    unknown = sorted(set(values) - allowed)
    if unknown:
        raise ValueError(
            "Unsupported parameter(s) for {0}/{1}: {2}. Allowed: {3}".format(
                target_id,
                defect_type,
                unknown,
                sorted(allowed),
            )
        )
    normalized = {}
    for key, value in values.items():
        number = _finite_float(value, key)
        _validate_range(key, number)
        normalized[key] = number

    _validate_pair(normalized, "size_factor_min", "size_factor_max")
    _validate_pair(normalized, "black_dot_radius_min_scale", "black_dot_radius_max_scale")
    _validate_pair(normalized, "black_dot_depth_min_scale", "black_dot_depth_max_scale")
    return normalized


def _allowed_parameters(target_id, defect_type):
    if defect_type == "black_dot" and target_id in REFERENCE_BLACKDOT_TARGETS:
        return REFERENCE_BLACKDOT_PARAMETERS
    if target_id == "qc71336_white" and defect_type == "foreign_material":
        return QC71336_WHITE_FOREIGN_PARAMETERS
    if target_id == "qc71336_black" and defect_type in {"foreign_material", "splay"}:
        return SAME_TYPE_COUNT_PARAMETERS
    if target_id == "qc7_5244_white" and defect_type == "mixed_color_contamination":
        return SAME_TYPE_COUNT_PARAMETERS
    return GENERIC_PARAMETERS


def _finite_float(value, name):
    if isinstance(value, bool):
        raise ValueError("{0} must be a number, not a boolean.".format(name))
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError("{0} must be a number.".format(name)) from None
    if not math.isfinite(number):
        raise ValueError("{0} must be finite.".format(name))
    return number


def _validate_range(key, value):
    ranges = {
        "size_factor_min": (0.0001, 0.2),
        "size_factor_max": (0.0001, 0.2),
        "width_multiplier": (0.05, 20.0),
        "height_multiplier": (0.05, 20.0),
        "size_scale": (0.1, 5.0),
        "roughness": (0.0, 1.0),
        "defect_count_max": (1.0, 10.0),
        "black_dot_radius_min_scale": (0.0001, 0.05),
        "black_dot_radius_max_scale": (0.0001, 0.05),
        "black_dot_depth_min_scale": (0.0001, 0.2),
        "black_dot_depth_max_scale": (0.0001, 0.2),
        "black_dot_max_count": (1.0, 10.0),
        "foreign_material_radius_scale": (0.0, 0.05),
        "foreign_material_depth_scale": (0.0, 0.2),
    }
    low, high = ranges[key]
    if value < low or value > high:
        raise ValueError("{0} must be between {1} and {2}.".format(key, low, high))


def _validate_pair(values, min_key, max_key):
    if min_key in values and max_key in values and values[min_key] > values[max_key]:
        raise ValueError("{0} cannot be greater than {1}.".format(min_key, max_key))
