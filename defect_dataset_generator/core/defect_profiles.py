from copy import deepcopy


DEFECT_PROFILES = {
    "mixed_color_contamination": {
        "schema_version": "0.1",
        "defect_type": "mixed_color_contamination",
        "description": "Material-driven color drift inside plastic; not a transparent floating patch.",
        "appearance_backend": "reference_blend_qc75244_mixed_color_profile_debug.py",
        "preferred_surface_type": "large_continuous_main_plane",
        "allowed_zones": ["upper_center", "center_mid", "center_right", "lower_mid_right", "mid_left", "center"],
        "size_tiers": {
            "small": {"radius_x_factor": [0.030, 0.045], "radius_y_factor": [0.0050, 0.0070]},
            "normal": {"radius_x_factor": [0.045, 0.060], "radius_y_factor": [0.0065, 0.0083]},
            "large": {"radius_x_factor": [0.060, 0.068], "radius_y_factor": [0.0080, 0.0092]},
        },
        "default_size_tier_weights": ["normal", "normal", "small", "large"],
        "overlap_policy": "do_not_overlap_other_area_defects",
        "mask_area_limits_px": [120, 3500],
        "bbox_size_limits_px": {"width": [30, 220], "height": [8, 60]},
        "notes": [
            "RGB, mask, overlay, bbox, and YOLO label should remain tied to the same procedural footprint.",
            "Mask semantics cover the complete effective mixed-color footprint.",
        ],
    },
    "black_dot": {
        "schema_version": "0.1",
        "defect_type": "black_dot",
        "aliases": ["black_spot"],
        "description": "Small embedded/dark point defect on clean visible plastic.",
        "appearance_backend": "reference_blend_blackdot_multi_model.py",
        "preferred_surface_type": "clean_continuous_main_plane",
        "allowed_zones": ["center_mid", "center_right", "lower_mid_right", "mid_left", "center"],
        "size_tiers": {
            "tiny": {"bbox_width_px": [2, 8], "bbox_height_px": [2, 8]},
            "normal": {"bbox_width_px": [6, 18], "bbox_height_px": [6, 18]},
        },
        "default_size_tier_weights": ["normal", "normal", "tiny"],
        "overlap_policy": "avoid_inside_mixed_color",
        "mask_area_limits_px": [4, 700],
        "bbox_size_limits_px": {"width": [2, 30], "height": [2, 30]},
        "notes": ["Avoid complex edges, holes, and strong structure lines."],
    },
    "foreign_material": {
        "schema_version": "0.1",
        "defect_type": "foreign_material",
        "description": "Small attached/embedded foreign particle represented as a real mesh object.",
        "appearance_backend": "reference_blend_qc71336_black_prebuilt_normal_debug.py",
        "preferred_surface_type": "central_safe_visible_surface",
        "allowed_zones": ["center_mid", "center_right", "lower_mid_right", "mid_left", "center"],
        "size_tiers": {
            "tiny": {"max_dim_factor": [0.0012, 0.0021]},
            "normal": {"max_dim_factor": [0.0018, 0.0032]},
            "large_debug": {"max_dim_factor": [0.0026, 0.0040]},
        },
        "default_size_tier_weights": ["tiny", "normal", "normal"],
        "overlap_policy": "avoid_area_defects",
        "mask_area_limits_px": [3, 900],
        "bbox_size_limits_px": {"width": [2, 45], "height": [2, 45]},
        "notes": ["Keep as a mesh object; do not brighten just to improve bbox visibility."],
    },
    "splay": {
        "schema_version": "0.1",
        "defect_type": "splay",
        "description": "Local short oblique flow mark / silver streak represented as a local patch.",
        "appearance_backend": "reference_blend_qc71336_black_prebuilt_normal_debug.py",
        "preferred_surface_type": "visible_surface_near_main_or_edge",
        "allowed_zones": ["upper_center", "center_mid", "center_right", "lower_mid_right", "mid_left", "center"],
        "size_tiers": {
            "short": {"length_factor": [0.016, 0.024], "width_factor": [0.0014, 0.0024]},
            "normal": {"length_factor": [0.020, 0.034], "width_factor": [0.0015, 0.0028]},
            "long": {"length_factor": [0.032, 0.046], "width_factor": [0.0016, 0.0029]},
        },
        "default_size_tier_weights": ["normal", "normal", "short", "long"],
        "overlap_policy": "avoid_mixed_color_until_semantics_are_validated",
        "mask_area_limits_px": [20, 2400],
        "bbox_size_limits_px": {"width": [12, 180], "height": [4, 80]},
        "notes": ["Keep local patch implementation; do not return to global procedural texture pollution."],
    },
}


def get_defect_profile(defect_type):
    normalized = normalize_defect_type(defect_type)
    for key, profile in DEFECT_PROFILES.items():
        if normalize_defect_type(key) == normalized:
            return deepcopy(profile)
        for alias in profile.get("aliases", []):
            if normalize_defect_type(alias) == normalized:
                return deepcopy(profile)
    known = sorted(DEFECT_PROFILES.keys())
    raise ValueError("Unknown defect profile: {0}. Known profiles: {1}".format(defect_type, known))


def list_defect_profiles():
    return sorted(DEFECT_PROFILES.keys())


def normalize_defect_type(defect_type):
    value = str(defect_type).strip().lower().replace("-", "_")
    if value == "black_spot":
        return "black_dot"
    return value
