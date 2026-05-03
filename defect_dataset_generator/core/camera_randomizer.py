def build_camera_settings(mode: str = "randomized", overrides: dict = None) -> dict:
    overrides = overrides or {}
    if mode == "fixed":
        settings = {
            "mode": "fixed",
            "distance": 2.2,
            "angle_degrees": [0.0, 0.0, 0.0],
            "focal_length_mm": 70,
        }
        settings.update(overrides)
        return settings
    settings = {
        "mode": "randomized",
        "profile": "light_domain_randomization_v1",
        "distance_base": 2.2,
        "distance_jitter_factor": [-0.05, 0.05],
        "distance_range": [2.09, 2.31],
        "azimuth_degrees": [-15, 15],
        "elevation_degrees": [-10, 10],
        "roll_degrees": [-5, 5],
        "focal_length_mm": [65, 75],
        "override_policy": "User-supplied values or ranges replace these defaults per profile or CLI config.",
    }
    settings.update(overrides)
    return settings
