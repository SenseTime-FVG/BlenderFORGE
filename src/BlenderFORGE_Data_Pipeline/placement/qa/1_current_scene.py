#!/usr/bin/env python3
import argparse
import copy
import json
import math
import random
import sys
from pathlib import Path

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from common.blender_state import configure_render as apply_render_config


def parse_args() -> argparse.Namespace:
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1 :]
    else:
        argv = []
    parser = argparse.ArgumentParser(description="Single-process blender worker for QA placement data")
    parser.add_argument("--sample_dir", type=str, required=True)
    parser.add_argument("--output_dir", type=str, required=True)
    parser.add_argument("--config", type=str, required=True)
    return parser.parse_args(argv)


def write_result(output_dir: Path, status: str, reason: str = "", extra: dict | None = None) -> None:
    payload = {"status": status, "reason": reason}
    if extra:
        payload.update(extra)
    with (output_dir / "result_status.json").open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def euclidean(a, b) -> float:
    return math.sqrt(sum((float(x) - float(y)) ** 2 for x, y in zip(a, b)))


def compute_scene_bounds_xy() -> dict:
    x_min, y_min = float("inf"), float("inf")
    x_max, y_max = float("-inf"), float("-inf")
    z_min, z_max = float("inf"), float("-inf")

    mesh_objects = [o for o in bpy.data.objects if o.type == "MESH"]
    for obj in mesh_objects:
        corners = [obj.matrix_world @ Vector(v) for v in obj.bound_box]
        xs = [c.x for c in corners]
        ys = [c.y for c in corners]
        zs = [c.z for c in corners]
        x_min = min(x_min, min(xs))
        y_min = min(y_min, min(ys))
        z_min = min(z_min, min(zs))
        x_max = max(x_max, max(xs))
        y_max = max(y_max, max(ys))
        z_max = max(z_max, max(zs))

    return {
        "x_min": x_min,
        "x_max": x_max,
        "y_min": y_min,
        "y_max": y_max,
        "z_min": z_min,
        "z_max": z_max,
    }


def world_aabb(obj) -> tuple[float, float, float, float, float, float]:
    corners = [obj.matrix_world @ Vector(v) for v in obj.bound_box]
    xs = [c.x for c in corners]
    ys = [c.y for c in corners]
    zs = [c.z for c in corners]
    return min(xs), max(xs), min(ys), max(ys), min(zs), max(zs)


def aabb_overlap(a, b, eps: float = 0.01) -> bool:
    ax0, ax1, ay0, ay1, az0, az1 = a
    bx0, bx1, by0, by1, bz0, bz1 = b
    overlap_x = (ax0 < bx1 - eps) and (ax1 > bx0 + eps)
    overlap_y = (ay0 < by1 - eps) and (ay1 > by0 + eps)
    overlap_z = (az0 < bz1 - eps) and (az1 > bz0 + eps)
    return overlap_x and overlap_y and overlap_z


def collides_with_others(target_obj) -> bool:
    target_aabb = world_aabb(target_obj)
    for obj in bpy.data.objects:
        if obj.type != "MESH":
            continue
        if obj.name == target_obj.name:
            continue
        if aabb_overlap(target_aabb, world_aabb(obj)):
            return True
    return False


def visible_in_camera(scene, camera_obj, point, margin: float = 0.02) -> bool:
    co = world_to_camera_view(scene, camera_obj, point)
    if co.z <= 0:
        return False
    return margin <= co.x <= (1.0 - margin) and margin <= co.y <= (1.0 - margin)


def visible_in_all_cameras(scene, camera_names: list[str], point) -> bool:
    for cam_name in camera_names:
        cam = bpy.data.objects.get(cam_name)
        if cam is None:
            return False
        if not visible_in_camera(scene, cam, point):
            return False
    return True


def render_current_views(output_dir: Path, camera_names: list[str]) -> list[dict]:
    scene = bpy.context.scene
    if scene.render.image_settings.file_format != "PNG":
        raise ValueError("QA views require PNG output in render_config.scene.render.image_settings")
    current_dir = output_dir / "current_views"
    current_dir.mkdir(parents=True, exist_ok=True)

    renders = []
    for cam_name in camera_names:
        camera_obj = bpy.data.objects[cam_name]
        scene.camera = camera_obj
        image_path = current_dir / f"{cam_name}.png"
        scene.render.filepath = str(image_path)
        bpy.ops.render.render(write_still=True)

        camera_data = camera_obj.data
        fov_radians = float(camera_data.angle)
        render_info = {
            "camera_name": cam_name,
            "image": f"current_views/{cam_name}.png",
            "camera_pose": {
                "position": [float(v) for v in camera_obj.location],
                "rotation": [float(v) for v in camera_obj.rotation_euler],
                "fov": math.degrees(fov_radians),
                "fov_radians": fov_radians,
                "focal_length": float(camera_data.lens),
                "resolution": [int(scene.render.resolution_x), int(scene.render.resolution_y)],
            },
        }
        renders.append(render_info)

    return renders


def get_png_stems(dir_path: Path) -> set[str]:
    if not dir_path.exists():
        return set()
    return {p.stem for p in dir_path.glob("*.png")}


def validate_view_alignment(output_dir: Path, camera_names: list[str]) -> tuple[bool, str]:
    expected = set(camera_names)
    start_stems = get_png_stems(output_dir / "start_views")
    goal_stems = get_png_stems(output_dir / "goal_views")
    current_stems = get_png_stems(output_dir / "current_views")

    if start_stems != expected:
        return False, f"start_views mismatch, expected cameras={sorted(expected)}, got={sorted(start_stems)}"
    if goal_stems != expected:
        return False, f"goal_views mismatch, expected cameras={sorted(expected)}, got={sorted(goal_stems)}"
    if current_stems != expected:
        return False, f"current_views mismatch, expected cameras={sorted(expected)}, got={sorted(current_stems)}"
    return True, "ok"


def sample_current_position(
    target_obj,
    A,
    B,
    dist_ab: float,
    camera_names: list[str],
    scene_bounds: dict,
    max_retries: int,
) -> tuple[bool, list[float], float, str]:
    scene = bpy.context.scene
    original_loc = [float(v) for v in target_obj.location]

    z_min = max(scene_bounds["z_min"], min(A[2], B[2]) - 0.2)
    z_max = max(z_min + 0.05, max(A[2], B[2]) + 0.4)

    for _ in range(max_retries):
        mode = "near" if random.random() < 0.5 else "far"
        if mode == "near":
            ratio = random.uniform(0.12, 0.49)
        else:
            ratio = random.uniform(1.05, 2.0)

        radius = ratio * dist_ab
        theta = random.uniform(0.0, 2.0 * math.pi)
        x = B[0] + radius * math.cos(theta)
        y = B[1] + radius * math.sin(theta)
        z = random.uniform(z_min, z_max)

        if not (scene_bounds["x_min"] <= x <= scene_bounds["x_max"]):
            continue
        if not (scene_bounds["y_min"] <= y <= scene_bounds["y_max"]):
            continue

        C = [x, y, z]
        r = euclidean(C, B) / max(dist_ab, 1e-6)
        if not (r < 0.5 or r > 1.0):
            continue

        target_obj.location = C
        bpy.context.view_layer.update()

        if collides_with_others(target_obj):
            target_obj.location = original_loc
            bpy.context.view_layer.update()
            continue

        if not visible_in_all_cameras(scene, camera_names, target_obj.location):
            target_obj.location = original_loc
            bpy.context.view_layer.update()
            continue

        return True, C, r, "ok"

    target_obj.location = original_loc
    bpy.context.view_layer.update()
    return False, original_loc, 0.0, "failed to sample valid current position within 50 retries"


def update_object_pose_in_info(info_dict: dict, object_name: str, new_position: list[float], new_rotation: list[float]) -> None:
    for obj in info_dict.get("objects", []):
        if obj.get("name") == object_name:
            obj["position"] = [float(v) for v in new_position]
            obj["rotation"] = [float(v) for v in new_rotation]
            break

    scene_info = info_dict.get("scene_info", {})
    for obj in scene_info.get("objects", []):
        if obj.get("name") == object_name:
            obj["location"] = ", ".join(f"{float(v):.3f}" for v in new_position)
            obj["rotation_euler"] = ", ".join(f"{float(v):.3f}" for v in new_rotation)
            break


def main() -> None:
    args = parse_args()
    sample_dir = Path(args.sample_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        with (sample_dir / "metadata.json").open("r", encoding="utf-8") as f:
            metadata = json.load(f)
        if metadata.get("schema_version") == "1.0":
            raise ValueError("placement/qa is legacy-only until its v1 migration")
        with (sample_dir / "start_info.json").open("r", encoding="utf-8") as f:
            start_info = json.load(f)
        with (sample_dir / "goal_info.json").open("r", encoding="utf-8") as f:
            goal_info = json.load(f)
        with Path(args.config).open("r", encoding="utf-8") as f:
            config = json.load(f)
    except Exception as e:
        write_result(output_dir, "failed", f"failed to load inputs: {e}")
        return

    moved_objects = metadata.get("task", {}).get("moved_objects", [])
    if not moved_objects:
        write_result(output_dir, "skip", "no moved_objects in metadata")
        return

    start_blend = sample_dir / "start.blend"
    if not start_blend.exists():
        write_result(output_dir, "failed", f"missing blend file: {start_blend}")
        return

    try:
        bpy.ops.wm.open_mainfile(filepath=str(start_blend))
    except Exception as e:
        write_result(output_dir, "failed", f"failed to open blend: {e}")
        return

    camera_names = [v["camera_name"] for v in start_info.get("views", []) if "camera_name" in v]
    if not camera_names:
        write_result(output_dir, "failed", "no camera names in start_info views")
        return

    for cam_name in camera_names:
        if bpy.data.objects.get(cam_name) is None:
            write_result(output_dir, "failed", f"camera missing in scene: {cam_name}")
            return

    scene_bounds = compute_scene_bounds_xy()
    max_retries = int(config.get("object_movement", {}).get("target_move_retries", 50))
    max_retries = min(max_retries, 50)

    render_config = config.get("render_config", {})
    apply_render_config(render_config)

    qa_items = []
    object_results = []
    moved_state_map = {}

    # Move all targets in the same CURRENT scene; any failure rejects the sample.
    for idx, moved in enumerate(moved_objects):
        object_name = moved.get("name")
        target_obj = bpy.data.objects.get(object_name)
        if target_obj is None:
            write_result(output_dir, "failed", f"moved object not found in blend: {object_name}")
            return

        A = [float(v) for v in moved.get("new_pos", [0, 0, 0])]
        B = [float(v) for v in moved.get("orig_pos", [0, 0, 0])]
        dist_ab = euclidean(A, B)
        if dist_ab < 0.5:
            write_result(output_dir, "skip", f"object '{object_name}' start-goal distance too small: {dist_ab:.4f} < 0.5")
            return

        target_obj.location = A
        bpy.context.view_layer.update()

        success, C, ratio_r, reason = sample_current_position(
            target_obj=target_obj,
            A=A,
            B=B,
            dist_ab=dist_ab,
            camera_names=camera_names,
            scene_bounds=scene_bounds,
            max_retries=max_retries,
        )

        if not success:
            write_result(output_dir, "skip", f"object '{object_name}' sampling failed: {reason}")
            return

        moved_state_map[object_name] = {
            "target_id": moved.get("target_id", idx),
            "A": A,
            "B": B,
            "C": C,
            "ratio_r": ratio_r,
            "dist_ab": dist_ab,
        }

    # Render current_views once after every object has been sampled successfully.
    try:
        render_results = render_current_views(output_dir=output_dir, camera_names=camera_names)
    except Exception as e:
        write_result(output_dir, "failed", f"render failed: {e}")
        return

    current_info = copy.deepcopy(start_info)
    moved_names = list(moved_state_map.keys())
    for object_name, state in moved_state_map.items():
        target_obj = bpy.data.objects.get(object_name)
        new_rot = [float(v) for v in target_obj.rotation_euler] if target_obj else [0.0, 0.0, 0.0]
        update_object_pose_in_info(
            info_dict=current_info,
            object_name=object_name,
            new_position=state["C"],
            new_rotation=new_rot,
        )

    current_views = current_info.get("views", [])
    for view_idx, view in enumerate(current_views):
        if view_idx >= len(render_results):
            break
        view["image"] = render_results[view_idx]["image"]
        view["camera_pose"] = render_results[view_idx]["camera_pose"]
        view["visible_objects"] = moved_names

    with (output_dir / "current_info.json").open("w", encoding="utf-8") as f:
        json.dump(current_info, f, indent=2)

    # Emit one QA item per object, sharing current_views and current_info.
    for object_name, state in moved_state_map.items():
        dist_cb = euclidean(state["C"], state["B"])
        answer_pos = "Yes" if dist_cb < state["dist_ab"] else "No"
        qa_item = {
            "sample_id": sample_dir.name,
            "moved_object": object_name,
            "target_id": state["target_id"],
            "start_images": [f"start_views/{name}.png" for name in camera_names],
            "goal_images": [f"goal_views/{name}.png" for name in camera_names],
            "current_images": [f"current_views/{name}.png" for name in camera_names],
            "start_info": "start_info.json",
            "goal_info": "goal_info.json",
            "current_info": "current_info.json",
            "metrics": {
                "dist_start_goal": state["dist_ab"],
                "dist_current_goal": dist_cb,
                "ratio_r": state["ratio_r"],
                "visible_views": len(camera_names),
            },
            "question_pos": f"For object '{object_name}', is its current position more similar to the goal scene than the start scene?",
            "answer_pos": answer_pos,
        }
        qa_items.append(qa_item)
        object_results.append(
            {
                "object_name": object_name,
                "target_id": state["target_id"],
                "status": "success",
                "ratio_r": state["ratio_r"],
                "dist_start_goal": state["dist_ab"],
                "dist_current_goal": dist_cb,
                "answer_pos": answer_pos,
            }
        )

    with (output_dir / "qa_items.json").open("w", encoding="utf-8") as f:
        json.dump(qa_items, f, indent=2)

    aligned, align_reason = validate_view_alignment(output_dir=output_dir, camera_names=camera_names)
    if not aligned:
        write_result(
            output_dir,
            "failed",
            f"view alignment check failed: {align_reason}",
            {
                "sample_id": sample_dir.name,
                "object_results": object_results,
            },
        )
        return

    write_result(
        output_dir,
        "success",
        "ok",
        {
            "sample_id": sample_dir.name,
            "qa_item_count": len(qa_items),
            "success_objects": len(object_results),
            "view_alignment": "passed",
            "object_results": object_results,
        },
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        output_dir = Path(".")
        argv = sys.argv
        if "--" in argv:
            args = argv[argv.index("--") + 1 :]
            for i, token in enumerate(args):
                if token == "--output_dir" and i + 1 < len(args):
                    output_dir = Path(args[i + 1])
                    break
        output_dir.mkdir(parents=True, exist_ok=True)
        write_result(output_dir, "failed", f"unhandled exception: {e}")
        raise
