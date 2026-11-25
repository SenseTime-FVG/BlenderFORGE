"""Dependency-free checks for supported v1 scene-editing samples."""

import hashlib
import fcntl
import json
import math
import struct
import time
from pathlib import Path

VERSION = "1.0"
REQUIRED_FILES = (
    "metadata.json", "start.blend", "start.py", "start_info.json",
    "goal.blend", "goal.py", "goal_info.json", "render_config.json",
)
REQUIRED_CHECKS = {"quality", "start_replay", "goal_replay", "goal_snapshot", "contract"}


def write_json(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
    temporary.replace(path)


def read_json(path):
    return json.loads(Path(path).read_text())


def append_report(path, report):
    """Append one complete report under a POSIX lock shared by worker processes."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(report, ensure_ascii=False, allow_nan=False) + "\n"
    with path.open("a", encoding="utf-8") as stream:
        # Some shared filesystems return EAGAIN even for a blocking flock.
        deadline = time.monotonic() + 30
        while True:
            try:
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"Timed out waiting for the report lock: {path}")
                time.sleep(0.02)
        try:
            stream.write(line)
            stream.flush()
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def vector(value, length, label):
    require(isinstance(value, list) and len(value) == length, f"{label}: expected {length} numbers")
    require(all(type(x) in (int, float) and math.isfinite(x) for x in value), f"{label}: non-finite/non-numeric value")


def compare_values(actual, expected, tolerance=1e-6, path="state"):
    """Strict structure plus an absolute float tolerance, reporting the worst error."""
    if type(actual) in (int, float) and type(expected) in (int, float):
        error = abs(actual - expected)
        require(math.isfinite(error) and error <= tolerance, f"{path}: {actual} != {expected}")
        return error
    if isinstance(expected, dict):
        require(isinstance(actual, dict) and actual.keys() == expected.keys(), f"{path}: keys changed")
        return max((compare_values(actual[key], value, tolerance, f"{path}.{key}") for key, value in expected.items()), default=0)
    if isinstance(expected, list):
        require(isinstance(actual, list) and len(actual) == len(expected), f"{path}: list changed")
        return max((compare_values(a, b, tolerance, f"{path}[{i}]") for i, (a, b) in enumerate(zip(actual, expected))), default=0)
    require(actual == expected, f"{path}: {actual!r} != {expected!r}")
    return 0


def validate_state(state):
    require(state.get("schema_version") == VERSION, "Not a v1 state; legacy samples require an explicit exporter")
    require(isinstance(state.get("sample_id"), str) and state["sample_id"], "Missing sample_id")
    require(state.get("state") in ("start", "goal", "current"), "Invalid state")
    scene = state["scene"]
    require(scene["units"]["length"] == "meter" and scene["units"]["rotation"] == "radian", "Invalid units")
    require(scene["units"]["meters_per_blender_unit"] > 0, "Invalid unit scale")
    objects = state["objects"]
    require(isinstance(objects, dict) and objects, "objects must be a nonempty name-indexed table")
    require(isinstance(state["materials"], dict), "materials must be name-indexed")
    for name, obj in objects.items():
        require(type(obj["editable"]) is bool and type(obj["hide_render"]) is bool, f"{name}: invalid object flags")
        require(obj["parent_id"] is None or obj["parent_id"] in objects, f"{name}: missing parent")
        transform = obj["transform"]
        vector(transform["location_local"], 3, name + ".location_local")
        vector(transform["scale_local"], 3, name + ".scale_local")
        mode = transform["rotation_mode"]
        require(mode in ("XYZ", "XZY", "YXZ", "YZX", "ZXY", "ZYX", "QUATERNION", "AXIS_ANGLE"), "Invalid rotation mode")
        vector(transform["rotation"], 4 if mode in ("QUATERNION", "AXIS_ANGLE") else 3, name + ".rotation")
        require(len(transform["matrix_world_evaluated"]) == 4, "World matrix must have four rows")
        for row in transform["matrix_world_evaluated"]:
            vector(row, 4, name + ".matrix_world_evaluated")
        for slot in obj["material_slots"]:
            require(slot is None or slot in state["materials"], f"{name}: missing material {slot}")
        if "shapekeys" in obj:
            keys = obj["shapekeys"]
            require(isinstance(keys, dict) and keys, f"{name}: empty shape-key table")
            for key_name, key in keys.items():
                vector([key[k] for k in ("value", "slider_min", "slider_max")], 3, name + "." + key_name)
                require(key["slider_min"] <= key["slider_max"], "Invalid shape-key range")
                require(key["relative_key"] in keys, "Missing relative shape key")
                require(all(type(key[k]) is bool for k in ("editable", "mute", "is_basis", "has_driver")), "Invalid shape-key flags")
        if obj["object_type"] == "CAMERA":
            camera = obj["camera"]
            for key in ("type", "lens_mm", "sensor_width_mm", "sensor_height_mm", "sensor_fit", "shift_x", "shift_y", "clip_start", "clip_end", "ortho_scale", "fov_x_radians", "fov_y_radians", "resolution", "pixel_aspect"):
                require(key in camera, f"{name}: missing camera.{key}")
        if obj["object_type"] == "LIGHT":
            for key in ("type", "energy", "color", "use_nodes", "nodes"):
                require(key in obj["light"], f"{name}: missing light.{key}")
    names = [view["camera_name"] for view in state["views"]]
    require(names and len(names) == len(set(names)), "Missing/duplicate views")
    for view in state["views"]:
        name = view["camera_name"]
        require(name in objects and objects[name]["object_type"] == "CAMERA", f"Unknown view camera: {name}")
        require(not any(c in name for c in '/\\\x00') and name not in (".", ".."), "Unsafe camera name")
        if state["state"] == "current" and view["image"] is None:
            continue
        require(view["image"] == f'{state["state"]}_views/{name}.png', f"Image/camera mismatch: {name}")


def check_placement_states(metadata, start, goal):
    states = (start, goal)
    editable_names = metadata["editable"]["object_names"]
    require(len(editable_names) == len(set(editable_names)), "Duplicate editable candidates")
    for state in states:
        require(set(editable_names) == {name for name, obj in state["objects"].items() if obj["editable"]}, "Editable scope disagrees with state")
        camera_names = {view["camera_name"] for view in state["views"]}
        require(set(state["objects"]) == set(editable_names) | camera_names, "Placement state contains non-editable background objects")
        require(all(state["objects"][name]["object_type"] == "MESH" for name in editable_names), "Placement candidates must be meshes")
        material_names = {name for obj in state["objects"].values() for name in obj["material_slots"] if name is not None}
        require(set(state["materials"]) == material_names, "Placement state contains unrelated materials")
        require(all("nodes" not in material for material in state["materials"].values()), "Placement state must omit shader graphs")
    require(start["objects"].keys() == goal["objects"].keys(), "Entity set changed")
    require(start["scene"] == goal["scene"] and start["materials"] == goal["materials"], "Non-placement scene/material edit")
    require([v["camera_name"] for v in start["views"]] == [v["camera_name"] for v in goal["views"]], "Camera set/order changed")
    for view in start["views"]:
        name = view["camera_name"]
        require(start["objects"][name] == goal["objects"][name], f"Camera changed: {name}")
    edits = metadata["edit_summary"]
    changed_names = edits["object_names"]
    require(1 <= len(changed_names) == edits["actual_changed"] <= edits["requested_max"], "Invalid up-to-N counts")
    require(edits["requested_max"] == metadata["generator"]["config"]["object_movement"]["num_of_objects_change"], "Requested count disagrees with config")
    expected_changed = {name for name in start["objects"] if start["objects"][name]["transform"] != goal["objects"][name]["transform"]}
    require(set(changed_names) == expected_changed and len(changed_names) == len(expected_changed), "Changes do not match state differences")
    for name in changed_names:
        require(name in metadata["editable"]["object_names"], "Changed object not editable")
    for name, obj in start["objects"].items():
        other = goal["objects"][name]
        unchanged_keys = obj.keys() - {"transform", "geometry"}
        require(all(obj[key] == other[key] for key in unchanged_keys), f"Non-placement edit: {name}")
        if name not in expected_changed:
            require(obj == other, f"Unrecorded object edit: {name}")


def check_sample(directory, require_success=True):
    """Validate structure, named joins, edit summaries and file integrity.

    Replay runs before publication in Blender; detailed checks live in batch reports.
    Raises on any violation, including legacy samples.
    """
    root = Path(directory)
    require(not any((root / name).exists() for name in ("edits.json", "validation.json")),
            "Obsolete sample sidecars; regenerate with the current producer")
    for filename in REQUIRED_FILES:
        path = root / filename
        require(path.is_file() and not path.is_symlink() and path.stat().st_size > 0, f"Missing/empty/external file: {filename}")
    metadata = read_json(root / "metadata.json")
    require(metadata.get("schema_version") == VERSION and metadata.get("task") in ("placement", "shapekey", "lighting", "material"), "Not a supported v1 sample")
    if metadata['task'] == 'material':
        require(metadata['backend'] in ('principled_bsdf','infinigen'), 'Unknown material backend')
    else:
        require(metadata["backend"] is None, "This task's backend must be null")
    require(metadata["dependencies"]["resources_packed"] is True and metadata["dependencies"]["external_files"] == [], "Unexpected external resources")
    states = [read_json(root / f"{name}_info.json") for name in ("start", "goal")]
    for expected, state in zip(("start", "goal"), states):
        validate_state(state)
        require(state["state"] == expected and state["sample_id"] == metadata["sample_id"], "State identity mismatch")
        require(len(state["views"]) == metadata["num_views"], "View count mismatch")
        for view in state["views"]:
            path = root / view["image"]
            require(path.is_file() and not path.is_symlink(), f"Missing/external image: {path}")
            with path.open("rb") as stream:
                header = stream.read(24)
            require(header[:8] == b"\x89PNG\r\n\x1a\n" and len(header) == 24, f"Not a PNG: {path}")
            size = list(struct.unpack(">II", header[16:24]))
            require(size == state["objects"][view["camera_name"]]["camera"]["resolution"], "Image dimensions disagree with camera")
        expected_images = {Path(v["image"]).name for v in state["views"]}
        require({p.name for p in (root / f"{expected}_views").glob("*.png")} == expected_images, "Stale/unlisted images")
    start, goal = states
    if metadata["task"] == "placement":
        check_placement_states(metadata, start, goal)
    elif metadata["task"] == "shapekey":
        from common.shapekey_contract import check_shapekey_states
        check_shapekey_states(metadata, start, goal)
    elif metadata['task'] == 'lighting':
        from common.lighting_contract import check_lighting_states
        check_lighting_states(metadata, start, goal)
    else:
        from common.material_contract import check_material_states
        check_material_states(metadata,start,goal)
    render = read_json(root / "render_config.json")
    require(render["schema_version"] == VERSION and render["sample_id"] == metadata["sample_id"], "Render identity mismatch")
    require(isinstance(render["requested"], dict) and isinstance(render["effective"], dict), "Missing render configuration")
    if require_success:
        require((root / ".SUCCESS").is_file(), "Missing .SUCCESS")
        # Prevent a stale success marker from blessing modified JSON/scripts.
        marker = read_json(root / ".SUCCESS")
        require(marker == manifest(root), "Sample files changed after validation")
    return metadata


def publish_success(directory, checks):
    """Check the sample contract, then publish completion after all checks pass."""
    root = Path(directory)
    (root / ".SUCCESS").unlink(missing_ok=True)
    checks_by_name = {item["name"]: item for item in checks}
    require(REQUIRED_CHECKS - {"contract"} <= checks_by_name.keys(), "Missing required acceptance checks")
    require(all(checks_by_name[name]["executed"] is True and checks_by_name[name]["passed"] is True
                for name in REQUIRED_CHECKS & checks_by_name.keys()), "Required check failed/not executed")
    check_sample(root, require_success=False)
    if "contract" not in checks_by_name:
        checks.append({"name": "contract", "executed": True, "passed": True,
                       "metrics": {}, "tolerance": None, "reason": None})
    write_json(root / ".SUCCESS", manifest(root))


def manifest(root):
    root = Path(root)
    files = [root / name for name in REQUIRED_FILES]
    files += list(root.glob("start_views/*.png")) + list(root.glob("goal_views/*.png"))
    result = {}
    for path in sorted(files):
        with path.open("rb") as stream:
            result[path.relative_to(root).as_posix()] = hashlib.file_digest(stream, "sha256").hexdigest()
    return result


def is_complete(directory, num_views=None, task=None):
    try:
        metadata = check_sample(directory)
        return (task is None or metadata["task"] == task) and (num_views is None or metadata["num_views"] == num_views)
    except (OSError, ValueError, KeyError, TypeError, struct.error):
        return False
