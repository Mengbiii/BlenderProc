import json
import random
from pathlib import Path

from core.defect_profiles import get_defect_profile, normalize_defect_type
from core.model_profiles import get_model_profile


PLAN_SCHEMA_VERSION = "0.1"
SUPPORTED_MODES = {"normal", "single_defect", "two_defect_controlled"}


def sample_camera_plan(model_profile, rng, camera_profile=None):
    presets = model_profile.get("camera_presets") or [{"name": "baseline_front", "mode": "planned_only"}]
    if camera_profile:
        preset = _find_camera_preset(model_profile, camera_profile)
    else:
        preset = presets[0] if len(presets) == 1 else rng.choice(presets)
    return {
        "camera_profile": preset.get("name", "baseline_front"),
        "camera_mode": preset.get("mode", "planned_only"),
        "description": preset.get("description"),
        "planned_only": True,
    }


def sample_candidate_zone(model_profile, defect_profile, rng, used_zones=None):
    used_zones = set(used_zones or [])
    model_allowed = model_profile.get("defect_allowed_zones", {}).get(defect_profile["defect_type"])
    defect_allowed = defect_profile.get("allowed_zones", [])
    if model_allowed:
        allowed = [zone for zone in model_allowed if zone in defect_allowed]
    else:
        allowed = [zone for zone in defect_allowed if zone in model_profile.get("main_surface_zones", {})]
    allowed = [zone for zone in allowed if zone in model_profile.get("main_surface_zones", {})]
    if not allowed:
        raise ValueError("No allowed zones for defect {0} on model {1}".format(defect_profile["defect_type"], model_profile["model_id"]))

    weighted = [zone for zone in model_profile.get("zone_weights", []) if zone in allowed]
    pool = weighted or allowed
    separate_pool = [zone for zone in pool if zone not in used_zones]
    selected = rng.choice(separate_pool or pool)
    zone_spec = model_profile["main_surface_zones"][selected]
    projected_xy = [
        round(rng.uniform(zone_spec["target_x"][0], zone_spec["target_x"][1]), 6),
        round(rng.uniform(zone_spec["target_y"][0], zone_spec["target_y"][1]), 6),
    ]
    return selected, zone_spec, projected_xy


def sample_defect_plan(model_profile, defect_profiles, mode, count, seed, camera_profile=None):
    if mode not in SUPPORTED_MODES:
        raise ValueError("Unsupported scheduling mode: {0}. Supported modes: {1}".format(mode, sorted(SUPPORTED_MODES)))
    if count < 1:
        raise ValueError("count must be >= 1")
    plans = []
    for sample_id in range(count):
        sample_seed = int(seed) + sample_id
        rng = random.Random(sample_seed)
        camera_plan = sample_camera_plan(model_profile, rng, camera_profile=camera_profile)
        defects = _sample_defects_for_sample(model_profile, defect_profiles, mode, rng)
        plans.append(
            {
                "plan_schema_version": PLAN_SCHEMA_VERSION,
                "schema_version": PLAN_SCHEMA_VERSION,
                "plan_type": "multi_defect_scheduler_dry_run",
                "sample_id": sample_id,
                "seed": sample_seed,
                "model_id": model_profile["model_id"],
                "camera_profile": camera_plan["camera_profile"],
                "camera_plan": camera_plan,
                "visible_surface_plan": {
                    "mode": "lightweight_profile_zones",
                    "placement_surface_mode": model_profile.get("default_defect_placement", {}).get(
                        "mode",
                        "front_back_main_planes_only",
                    ),
                    "allowed_surface_sides": model_profile.get("default_defect_placement", {}).get(
                        "allowed_surface_sides",
                        ["front", "back"],
                    ),
                    "allowed_surface_regions": model_profile.get("default_defect_placement", {}).get(
                        "allowed_surface_regions",
                        ["main_plane"],
                    ),
                    "excluded_surface_regions": {
                        "complex_edges": model_profile.get("default_defect_placement", {}).get("exclude_complex_edges", True),
                        "holes": model_profile.get("default_defect_placement", {}).get("exclude_holes", True),
                        "side_walls": model_profile.get("default_defect_placement", {}).get("exclude_side_walls", True),
                    },
                    "real_polygon_visibility": False,
                    "available_zones": sorted(model_profile.get("main_surface_zones", {}).keys()),
                    "exclusion_zones": model_profile.get("exclusion_zones", {}),
                    "notes": "First scheduler version uses profile projected front/back main-plane windows, not full mesh polygon visibility.",
                },
                "defects": defects,
                "notes": [
                    "Dry-run plan only; no BlenderProc rendering is invoked.",
                    "Existing defect appearance backends are not modified by this scheduler.",
                ],
            }
        )
    return plans


def write_defect_plans(plans, out_dir, context=None):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for plan in plans:
        path = out_dir / "defect_plan_{0:06d}.json".format(plan["sample_id"])
        path.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    summary = build_plan_summary(plans, context=context)
    (out_dir / "defect_plan_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return summary


def build_plan_summary(plans, context=None):
    context = context or {}
    zone_counts = {}
    defect_counts = {}
    camera_counts = {}
    size_tier_counts = {}
    for plan in plans:
        camera = plan.get("camera_profile")
        camera_counts[camera] = camera_counts.get(camera, 0) + 1
        for defect in plan.get("defects", []):
            zone = defect.get("placement_zone")
            dtype = defect.get("defect_type")
            size_tier = defect.get("size_tier")
            zone_counts[zone] = zone_counts.get(zone, 0) + 1
            defect_counts[dtype] = defect_counts.get(dtype, 0) + 1
            size_tier_counts[size_tier] = size_tier_counts.get(size_tier, 0) + 1
    return {
        "plan_schema_version": PLAN_SCHEMA_VERSION,
        "schema_version": PLAN_SCHEMA_VERSION,
        "plan_type": "multi_defect_scheduler_summary",
        "count": len(plans),
        "seed": context.get("seed"),
        "model_id": plans[0]["model_id"] if plans else None,
        "mode": context.get("mode"),
        "requested_defect_types": context.get("requested_defect_types", []),
        "camera_profiles": sorted(set(plan.get("camera_profile") for plan in plans)),
        "camera_profile_distribution": camera_counts,
        "defect_type_distribution": defect_counts,
        "placement_zone_distribution": zone_counts,
        "size_tier_distribution": size_tier_counts,
        "schema_validation_passed": context.get("schema_validation_passed"),
        "same_seed_reproducible": context.get("same_seed_reproducible"),
        "zones_valid": context.get("zones_valid"),
        "plan_files": ["defect_plan_{0:06d}.json".format(plan["sample_id"]) for plan in plans],
        "rendering_invoked": False,
    }


def validate_plan_schema(plans, model_profile):
    errors = []
    known_zones = set(model_profile.get("main_surface_zones", {}).keys())
    for plan in plans:
        for key in ["schema_version", "sample_id", "seed", "model_id", "camera_profile", "defects"]:
            if key not in plan:
                errors.append("sample {0}: missing {1}".format(plan.get("sample_id"), key))
        for defect in plan.get("defects", []):
            for key in ["defect_id", "defect_type", "placement_zone", "projected_xy", "size_tier", "overlap_policy"]:
                if key not in defect:
                    errors.append("sample {0} defect {1}: missing {2}".format(plan.get("sample_id"), defect.get("defect_id"), key))
            if defect.get("placement_zone") not in known_zones:
                errors.append("sample {0}: unknown zone {1}".format(plan.get("sample_id"), defect.get("placement_zone")))
    return {"passed": not errors, "errors": errors}


def make_plans(model_id, defect_types, mode, count, seed, camera_profile=None):
    model_profile = get_model_profile(model_id)
    if camera_profile:
        _find_camera_preset(model_profile, camera_profile)
    profiles = [get_defect_profile(item) for item in defect_types]
    plans = sample_defect_plan(model_profile, profiles, mode, count, seed, camera_profile=camera_profile)
    validation = validate_plan_schema(plans, model_profile)
    return model_profile, profiles, plans, validation


def check_seed_reproducibility(model_id, defect_types, mode, count, seed, camera_profile=None):
    _, _, first, _ = make_plans(model_id, defect_types, mode, count, seed, camera_profile=camera_profile)
    _, _, second, _ = make_plans(model_id, defect_types, mode, count, seed, camera_profile=camera_profile)
    return first == second


def zones_are_valid(plans, model_profile):
    known_zones = set(model_profile.get("main_surface_zones", {}).keys())
    for plan in plans:
        for defect in plan.get("defects", []):
            if defect.get("placement_zone") not in known_zones:
                return False
    return True


def _find_camera_preset(model_profile, camera_profile):
    for preset in model_profile.get("camera_presets", []):
        if preset.get("name") == camera_profile:
            return preset
    known = [preset.get("name") for preset in model_profile.get("camera_presets", [])]
    raise ValueError(
        "Unknown camera profile '{0}' for model '{1}'. Known camera profiles: {2}".format(
            camera_profile,
            model_profile.get("model_id"),
            known,
        )
    )


def _sample_defects_for_sample(model_profile, defect_profiles, mode, rng):
    if mode == "normal":
        return []
    if mode == "single_defect":
        profile = defect_profiles[0]
        return [_sample_one_defect(model_profile, profile, 0, rng, set())]
    if mode == "two_defect_controlled":
        if len(defect_profiles) < 2:
            raise ValueError("two_defect_controlled requires at least two defect types")
        used_zones = set()
        defects = []
        for defect_id, profile in enumerate(defect_profiles[:2]):
            defect = _sample_one_defect(model_profile, profile, defect_id, rng, used_zones)
            used_zones.add(defect["placement_zone"])
            defects.append(defect)
        return defects
    raise ValueError("Unsupported scheduling mode: {0}".format(mode))


def _sample_one_defect(model_profile, defect_profile, defect_id, rng, used_zones):
    zone, zone_spec, projected_xy = sample_candidate_zone(model_profile, defect_profile, rng, used_zones=used_zones)
    size_tier = rng.choice(defect_profile.get("default_size_tier_weights") or sorted(defect_profile.get("size_tiers", {}).keys()))
    size_params = defect_profile.get("size_tiers", {}).get(size_tier, {})
    radius_x_factor = _sample_range(model_profile.get("radius_x_factor"), rng)
    radius_y_factor = _sample_range(model_profile.get("radius_y_factor"), rng)
    if "radius_x_factor" in size_params:
        radius_x_factor = _sample_range(size_params["radius_x_factor"], rng)
    if "radius_y_factor" in size_params:
        radius_y_factor = _sample_range(size_params["radius_y_factor"], rng)
    return {
        "defect_id": defect_id,
        "defect_type": normalize_defect_type(defect_profile["defect_type"]),
        "placement_zone": zone,
        "zone_window": zone_spec.get("window"),
        "target_x_range": zone_spec.get("target_x"),
        "target_y_range": zone_spec.get("target_y"),
        "projected_xy": projected_xy,
        "size_tier": size_tier,
        "size_parameters": size_params,
        "radius_x_factor": radius_x_factor,
        "radius_y_factor": radius_y_factor,
        "overlap_policy": defect_profile.get("overlap_policy", model_profile.get("overlap_policy", {}).get("default", "none")),
        "appearance_backend": defect_profile.get("appearance_backend"),
        "notes": defect_profile.get("notes", []),
    }


def _sample_range(values, rng):
    if not values:
        return None
    if len(values) != 2:
        return values
    return round(rng.uniform(float(values[0]), float(values[1])), 6)
