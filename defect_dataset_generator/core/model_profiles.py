from copy import deepcopy


MODEL_PROFILES = {
    "qc7_5236": {
        "schema_version": "0.1",
        "model_id": "qc7_5236",
        "aliases": ["qc7-5236", "qc7_5244", "qc75236", "qc75244"],
        "description": "Front-facing QC7-5236/QC7-5244 large-main-plane profile migrated from the mixed-color profile script.",
        "blend_path_hint": "assets/models/moxing1_test.blend",
        "stl_path_hint": "assets/models/QC7-5236.stl",
        "default_defect_placement": {
            "mode": "front_back_main_planes_only",
            "allowed_surface_sides": ["front", "back"],
            "allowed_surface_regions": ["main_plane"],
            "exclude_complex_edges": True,
            "exclude_holes": True,
            "exclude_side_walls": True,
            "notes": "Default production sampling is limited to front/back main-plane zones until each target is smoke validated.",
        },
        "camera_presets": [
            {
                "name": "baseline_front",
                "mode": "fixed_reference",
                "description": "Stable front reference composition inherited from the mixed-color reference scene.",
            },
            {
                "name": "defect_front_mild_jitter",
                "mode": "planned_only",
                "description": "Future mild-jitter preset; not used for rendering in scheduler dry-run.",
            },
        ],
        "main_surface_zones": {
            "upper_center": {
                "target_x": [0.610, 0.660],
                "target_y": [0.700, 0.748],
                "window": [0.575, 0.695, 0.675, 0.775],
            },
            "center_mid": {
                "target_x": [0.610, 0.690],
                "target_y": [0.655, 0.735],
                "window": [0.570, 0.730, 0.625, 0.765],
            },
            "center_right": {
                "target_x": [0.660, 0.735],
                "target_y": [0.630, 0.715],
                "window": [0.620, 0.775, 0.600, 0.745],
            },
            "lower_mid_right": {
                "target_x": [0.640, 0.720],
                "target_y": [0.590, 0.670],
                "window": [0.595, 0.760, 0.555, 0.705],
            },
            "mid_left": {
                "target_x": [0.535, 0.620],
                "target_y": [0.635, 0.730],
                "window": [0.500, 0.660, 0.600, 0.765],
            },
        },
        "zone_weights": [
            "center_mid",
            "center_mid",
            "center_mid",
            "lower_mid_right",
            "lower_mid_right",
            "mid_left",
            "mid_left",
            "center_right",
            "upper_center",
        ],
        "artifact_window": [0.86, 0.96, 0.74, 0.90],
        "fallback_window": [0.60, 0.84, 0.52, 0.78],
        "exclusion_zones": {
            "known_artifact_window": [0.86, 0.96, 0.74, 0.90],
        },
        "placement_offsets": {
            "upper_mid_right": [0.040, 0.015],
            "center_right": [0.050, -0.035],
            "center_mid": [-0.070, -0.145],
            "lower_mid_right": [0.015, -0.110],
            "upper_center": [-0.055, -0.070],
            "mid_left": [-0.115, -0.065],
            "debug_center_right": [-0.020, -0.055],
        },
        "radius_x_factor": [0.030, 0.068],
        "radius_y_factor": [0.0050, 0.0092],
        "use_projected_scoring": True,
        "apply_camera_plane_offsets": True,
        "defect_allowed_zones": {
            "mixed_color_contamination": ["upper_center", "center_mid", "center_right", "lower_mid_right", "mid_left"],
            "black_dot": ["center_mid", "center_right", "lower_mid_right", "mid_left"],
            "foreign_material": ["center_mid", "center_right", "lower_mid_right", "mid_left"],
            "splay": ["upper_center", "center_mid", "center_right", "lower_mid_right", "mid_left"],
        },
        "overlap_policy": {
            "default": "none",
            "two_defect_controlled": "separate_zones_preferred",
        },
    },
    "default_large_main_plane": {
        "schema_version": "0.1",
        "model_id": "default_large_main_plane",
        "aliases": [],
        "description": "Generic fallback for large visible main-plane plastic parts; requires smoke validation before rendering.",
        "blend_path_hint": None,
        "stl_path_hint": None,
        "default_defect_placement": {
            "mode": "front_back_main_planes_only",
            "allowed_surface_sides": ["front", "back"],
            "allowed_surface_regions": ["main_plane"],
            "exclude_complex_edges": True,
            "exclude_holes": True,
            "exclude_side_walls": True,
            "notes": "Generic fallback only samples main-plane zones by default.",
        },
        "camera_presets": [{"name": "baseline_front", "mode": "planned_only"}],
        "main_surface_zones": {
            "center": {"target_x": [0.44, 0.56], "target_y": [0.44, 0.56], "window": [0.34, 0.66, 0.34, 0.66]},
            "upper_center": {"target_x": [0.42, 0.58], "target_y": [0.58, 0.72], "window": [0.32, 0.68, 0.52, 0.78]},
            "lower_center": {"target_x": [0.42, 0.58], "target_y": [0.28, 0.42], "window": [0.32, 0.68, 0.22, 0.48]},
        },
        "zone_weights": ["center", "center", "upper_center", "lower_center"],
        "artifact_window": None,
        "fallback_window": [0.22, 0.78, 0.20, 0.80],
        "exclusion_zones": {},
        "placement_offsets": {},
        "radius_x_factor": [0.045, 0.085],
        "radius_y_factor": [0.008, 0.018],
        "use_projected_scoring": True,
        "apply_camera_plane_offsets": False,
        "defect_allowed_zones": {
            "mixed_color_contamination": ["center", "upper_center", "lower_center"],
            "black_dot": ["center"],
            "foreign_material": ["center"],
            "splay": ["center", "upper_center", "lower_center"],
        },
        "overlap_policy": {"default": "none"},
    },
}


def get_model_profile(model_id):
    normalized = normalize_model_id(model_id)
    for key, profile in MODEL_PROFILES.items():
        if normalize_model_id(key) == normalized:
            return deepcopy(profile)
        for alias in profile.get("aliases", []):
            if normalize_model_id(alias) == normalized:
                return deepcopy(profile)
    known = sorted(MODEL_PROFILES.keys())
    raise ValueError("Unknown model profile: {0}. Known profiles: {1}".format(model_id, known))


def list_model_profiles():
    return sorted(MODEL_PROFILES.keys())


def normalize_model_id(model_id):
    return str(model_id).strip().lower().replace("-", "_")
