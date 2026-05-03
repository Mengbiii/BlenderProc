def build_light_settings(mode: str = "randomized", overrides: dict = None) -> dict:
    overrides = overrides or {}
    if mode == "fixed":
        settings = {
            "mode": "fixed",
            "strength": 450,
            "direction": [0.0, -1.0, -1.0],
            "area_size": 3.0,
            "background_brightness": 0.78,
        }
        settings.update(overrides)
        return settings
    settings = {
        "mode": "randomized",
        "profile": "light_domain_randomization_v1",
        "strength_base": 450,
        "strength_jitter_factor": [-0.20, 0.20],
        "strength_range": [360, 540],
        "direction_jitter_degrees": [-8, 8],
        "area_size_base": 3.0,
        "area_size_range": [2.7, 3.3],
        "background_brightness_base": 0.78,
        "background_brightness_range": [0.72, 0.84],
        "override_policy": "User-supplied values or ranges replace these defaults per profile or CLI config.",
    }
    settings.update(overrides)
    return settings
