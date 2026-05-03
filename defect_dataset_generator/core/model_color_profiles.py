import json
from copy import deepcopy
from pathlib import Path


DEFAULT_PROFILE_PATH = Path(__file__).resolve().parents[1] / "config" / "model_color_profiles.json"


def load_model_color_profiles(path=None):
    profile_path = Path(path) if path else DEFAULT_PROFILE_PATH
    with profile_path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return data


def get_model_color_profile(target, path=None):
    data = load_model_color_profiles(path)
    profiles = data.get("profiles", {})
    key = normalize_target_id(target)
    for profile_id, profile in profiles.items():
        if normalize_target_id(profile_id) == key:
            result = deepcopy(profile)
            result["target_id"] = profile_id
            return result
    raise ValueError("Unknown target profile: {0}. Known targets: {1}".format(target, sorted(profiles.keys())))


def list_model_color_profiles(path=None):
    data = load_model_color_profiles(path)
    return sorted(data.get("profiles", {}).keys())


def normalize_target_id(target):
    return str(target).strip().lower().replace("-", "_")
