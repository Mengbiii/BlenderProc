def build_background_settings(mode: str = "randomized", overrides: dict = None) -> dict:
    overrides = overrides or {}
    if mode == "fixed":
        settings = {
            "mode": "fixed",
            "color": [0.78, 0.78, 0.78, 1.0],
        }
        settings.update(overrides)
        return settings
    settings = {
        "mode": "randomized",
        "profile": "light_domain_randomization_v1",
        "color_base": [0.78, 0.78, 0.78, 1.0],
        "color_jitter_rgb": [-0.03, 0.03],
        "color_range_rgb": [
            [0.75, 0.81],
            [0.75, 0.81],
            [0.75, 0.81],
        ],
        "override_policy": "User-supplied color or RGB ranges replace these defaults per profile or CLI config.",
    }
    settings.update(overrides)
    return settings
