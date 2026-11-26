"""Module 7: Sample snapshots, metadata and replay acceptance for placement."""

import hashlib
import sys
import uuid
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from common.blender_state import (apply_render_config, capture_render_config, check_supported_scene,
                                  export_state, pack_resources, restore_script)
from common.contract import compare_values, publish_success, read_json, require, write_json


def export_placement_state(sample_id, state, camera_names, editable_names):
    # Candidate identity is fixed from the source scene, not inferred from a
    # perturbed pose or from the private changed-object list.
    return export_state(sample_id, state, camera_names, editable_names,
                        object_names=set(editable_names) | set(camera_names),
                        include_material_nodes=False)


def save_scene_state(state_name, movable_objects, cameras, output_dir, config):
    root = Path(output_dir)
    editable = [obj["name"] for obj in movable_objects]
    camera_names = [camera["name"] for camera in cameras]
    require(len(camera_names) == config["camera_config"]["num_views"], "Not all requested views were placed")
    for name in camera_names:
        require(not any(c in name for c in '/\\\x00'), f"Unsafe camera filename: {name}")
    sample_id = str(uuid.uuid4()) if state_name == "start" else read_json(root / "start_info.json")["sample_id"]
    state = export_placement_state(sample_id, state_name, camera_names, editable)
    # Packing preserves pixel content and makes both snapshots independent of source paths.
    pack_resources()
    blend_path = root / f"{state_name}.blend"
    if blend_path.is_symlink():
        blend_path.unlink()
    save_versions = bpy.context.preferences.filepaths.save_version
    try:
        bpy.context.preferences.filepaths.save_version = 0
        bpy.ops.wm.save_as_mainfile(filepath=str(blend_path.resolve()), copy=True)
    finally:
        bpy.context.preferences.filepaths.save_version = save_versions
    write_json(root / f"{state_name}_info.json", state)
    (root / f"{state_name}.py").write_text(restore_script(state, editable))
    if state_name == "start":
        write_json(root / "render_config.json", {"schema_version": "1.0", "sample_id": sample_id,
                   "requested": config.get("render_config", {}),
                   "effective": capture_render_config(config.get("render_config", {}).get("scene", {}))})
    else:
        require(read_json(root / "render_config.json")["effective"] == capture_render_config(config.get("render_config", {}).get("scene", {})),
                "Render configuration changed between START and GOAL")
    return state




def replay_checks(root):
    root = Path(root).resolve()
    start, goal = (read_json(root / f"{state}_info.json") for state in ("start", "goal"))
    render = read_json(root / "render_config.json")
    editable = read_json(root / "metadata.json")["editable"]["object_names"]
    cameras = [view["camera_name"] for view in start["views"]]
    checks = []
    for name, snapshot, scripts, expected in (
        ("start_replay", "start", ("start",), start),
        ("goal_replay", "start", ("start", "goal"), goal),
        ("goal_snapshot", "goal", (), goal),
    ):
        bpy.ops.wm.open_mainfile(filepath=str(root / f"{snapshot}.blend"))
        for script in scripts:
            filename = root / f"{script}.py"
            exec(compile(filename.read_text(), str(filename), "exec"), {"__name__": "__main__"})
        apply_render_config(render)
        actual = export_placement_state(start["sample_id"], expected["state"], cameras, editable)
        error = compare_values(actual, expected)
        compare_values(capture_render_config(render["effective"].get("configured_scene")), render["effective"])
        checks.append({"name": name, "executed": True, "passed": True,
                       "metrics": {"max_absolute_numeric_error": error}, "tolerance": 1e-6, "reason": None})
    return checks


def finalize_sample(output_dir, config, source, movable_objects, quality_passed, quality_reason,
                    start_visibility, goal_visibility, validation):
    root = Path(output_dir)
    start, goal = (read_json(root / f"{state}_info.json") for state in ("start", "goal"))
    sample_id = start["sample_id"]
    changed_names = [name
               for name, obj in start["objects"].items() if obj["transform"] != goal["objects"][name]["transform"]]
    with Path(source).open("rb") as stream:
        source_hash = hashlib.file_digest(stream, "sha256").hexdigest()
    metadata = {"schema_version": "1.0", "sample_id": sample_id, "task": "placement", "backend": None,
                "source": {"asset_id": Path(source).parent.name, "filename": Path(source).name, "sha256": source_hash},
                "generator": {"name": "placement/generation", "config": config,
                              "seed": config.get("random_seed"), "seed_scope": "invocation",
                              "blender_version": bpy.app.version_string},
                "dependencies": {"external_files": [], "resources_packed": True, "python_modules_for_replay": ["bpy"]},
                "editable": {"object_names": [obj["name"] for obj in movable_objects],
                             "properties": ["transform.location_local", "transform.rotation"],
                             "policy": "paper_scene_analyzer"}, "num_views": len(start["views"]),
                "edit_summary": {"requested_max": config["object_movement"]["num_of_objects_change"],
                                 "actual_changed": len(changed_names), "object_names": changed_names}}
    write_json(root / "metadata.json", metadata)
    from PIL import Image
    import numpy as np
    l1 = {}
    for view in start["views"]:
        name = view["camera_name"]
        with Image.open(root / view["image"]) as a, Image.open(root / "goal_views" / f"{name}.png") as b:
            l1[name] = float(np.abs(np.asarray(a, dtype=float) - np.asarray(b, dtype=float)).mean() / 255)
    validation.update({"schema_version": "1.0", "sample_id": sample_id, "profile": "placement-v1",
                  "checks": [{"name": "quality", "executed": True, "passed": bool(quality_passed),
                              "metrics": {"image_l1_by_camera": l1,
                                          "start_visibility_coverage": start_visibility["summary"].get("coverage_rate", 0),
                                          "goal_visibility_coverage": goal_visibility["summary"].get("coverage_rate", 0)},
                              "tolerance": config.get("validation_config", {}), "reason": None if quality_passed else quality_reason},
                             {"name": "replay_image_comparison", "executed": False, "passed": None,
                              "metrics": {}, "tolerance": None, "reason": "Optional integration test; not rerendered for every production sample"}]})
    try:
        require(quality_passed, quality_reason)
        validation["checks"].extend(replay_checks(root))
        publish_success(root, validation["checks"])
    except Exception as exc:
        (root / ".SUCCESS").unlink(missing_ok=True)
        validation["checks"].append({"name": "acceptance_failure", "executed": True, "passed": False, "metrics": {}, "tolerance": None, "reason": str(exc)})
        raise
    return metadata
