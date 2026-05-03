from typing import Any, Dict, List


SUPPORTED_DEFECT_TYPES = [
    "black_spot",
    "black_dot",
    "mixed_color_contamination",
    "foreign_material",
    "splay",
    "sink_mark",
    "dent",
    "short_shot",
    "flash",
]


class DefectParameters:
    def __init__(
        self,
        defect_type,
        size,
        opacity,
        color,
        blur,
        depth,
        position,
        visibility,
        randomness,
    ):
        self.defect_type = defect_type
        self.size = size
        self.opacity = opacity
        self.color = color
        self.blur = blur
        self.depth = depth
        self.position = position
        self.visibility = visibility
        self.randomness = randomness

    def to_dict(self):
        return {
            "defect_type": self.defect_type,
            "size": self.size,
            "opacity": self.opacity,
            "color": self.color,
            "blur": self.blur,
            "depth": self.depth,
            "position": self.position,
            "visibility": self.visibility,
            "randomness": self.randomness,
        }


def normalize_defect_config(config: Dict[str, Any]) -> Dict[str, Any]:
    defects = config.get("defects", [])
    normalized = []
    for item in defects:
        defect_type = item.get("type", "black_dot")
        if defect_type == "black_spot":
            defect_type = "black_dot"
        if defect_type not in SUPPORTED_DEFECT_TYPES:
            raise ValueError(f"Unsupported defect type: {defect_type}")
        normalized.append(
            DefectParameters(
                defect_type=defect_type,
                size=item.get("size", [0.02, 0.06]),
                opacity=item.get("opacity", 0.75),
                color=item.get("color", [0.02, 0.02, 0.02, 1.0]),
                blur=item.get("blur", 0.15),
                depth=item.get("depth", 0.1),
                position=item.get("position", "random_visible_surface"),
                visibility=item.get("visibility", 1.0),
                randomness=item.get("randomness", 0.5),
            ).to_dict()
        )
    result = {
        "schema_version": config.get("schema_version", "0.1"),
        "mode": config.get("mode", "randomized"),
        "position_mode": config.get("position_mode", "random_visible_surface"),
        "placement_surface_mode": config.get("placement_surface_mode", "front_back_main_planes_only"),
        "allowed_surface_sides": config.get("allowed_surface_sides", ["front", "back"]),
        "allowed_surface_regions": config.get("allowed_surface_regions", ["main_plane"]),
        "defects": normalized,
    }
    if config.get("black_dot_appearance_preset"):
        result["black_dot_appearance_preset"] = config.get("black_dot_appearance_preset")
    if config.get("backend_parameters"):
        result["backend_parameters"] = config.get("backend_parameters")
    return result
