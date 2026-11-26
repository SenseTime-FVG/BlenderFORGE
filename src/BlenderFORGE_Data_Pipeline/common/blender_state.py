"""Export native Blender state without prompt-oriented rounding or placeholders."""

import bpy
import math
from mathutils import Vector


def values(owner, names):
    return {name: plain(getattr(owner, name)) for name in names if hasattr(owner, name)}


def plain(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return [plain(item) for item in value]


def nodes(tree):
    """Record actual sockets and bindings, not a guessed material class.

    The native node graph remains in the packed blend. This is an observation,
    not a universal shader deserializer.
    """
    if tree is None:
        return None
    result = {"name": tree.name, "nodes": {}, "links": []}
    for node in tree.nodes:
        inputs = []
        for index, socket in enumerate(node.inputs):
            value = getattr(socket, "default_value", None)
            if isinstance(value, bpy.types.ID):
                value = {"datablock_name": value.name}
            inputs.append({"index": index, "name": socket.name, "identifier": socket.identifier,
                           "socket_type": socket.bl_idname, "value": plain(value), "linked": socket.is_linked})
        entry = {"type": node.bl_idname, "inputs": inputs}
        entry.update(values(node, ("operation", "blend_type", "distribution", "interpolation", "extension", "projection")))
        if getattr(node, "image", None):
            entry["image_name"] = node.image.name
        if getattr(node, "node_tree", None):
            entry["group"] = nodes(node.node_tree)
        result["nodes"][node.name] = entry
    for link in tree.links:
        result["links"].append({"from_node": link.from_node.name, "from_socket": link.from_socket.identifier,
                                "to_node": link.to_node.name, "to_socket": link.to_socket.identifier})
    return result


def export_state(sample_id, state, camera_names, editable_names, *, object_names=None,
                 include_material_nodes=True, shape_keys=None):
    scene = bpy.context.scene
    bpy.context.view_layer.update()
    depsgraph = bpy.context.evaluated_depsgraph_get()
    factor = scene.unit_settings.scale_length
    selected = set(object_names) if object_names is not None else set(scene.objects.keys())
    missing = selected - set(scene.objects.keys())
    if missing:
        raise ValueError(f"Missing observation objects: {sorted(missing)}")
    objects, materials = {}, {}
    for obj in sorted(scene.objects, key=lambda item: item.name):
        if obj.name not in selected:
            continue
        evaluated = obj.evaluated_get(depsgraph)
        matrix = [list(row) for row in evaluated.matrix_world]
        for row in range(3):
            matrix[row][3] *= factor
        rotation = obj.rotation_quaternion if obj.rotation_mode == "QUATERNION" else (
            obj.rotation_axis_angle if obj.rotation_mode == "AXIS_ANGLE" else obj.rotation_euler)
        record = {
            "object_type": obj.type, "parent_id": obj.parent.name if obj.parent else None,
            "transform": {"location_local": [v * factor for v in obj.location],
                          "rotation_mode": obj.rotation_mode, "rotation": list(rotation),
                          "scale_local": list(obj.scale), "matrix_world_evaluated": matrix},
            "editable": obj.name in editable_names,
            "hide_render": obj.hide_render,
            "material_slots": [slot.material.name if slot.material else None for slot in obj.material_slots],
        }
        if obj.type == "MESH":
            record["geometry"] = {"origin_convention": "blender_object_origin",
                                  "bbox_local": [[v * factor for v in corner] for corner in evaluated.bound_box],
                                  "bbox_world": [[v * factor for v in evaluated.matrix_world @ Vector(corner)] for corner in evaluated.bound_box]}
        if shape_keys is not None and obj.type == "MESH" and obj.data.shape_keys:
            data = obj.data.shape_keys
            record["shape_key_settings"] = {"use_relative": data.use_relative, "eval_time": data.eval_time,
                                            "show_only_shape_key": obj.show_only_shape_key}
            record["shapekeys"] = {
                key.name: {"value": key.value, "slider_min": key.slider_min, "slider_max": key.slider_max,
                           "relative_key": key.relative_key.name, "mute": key.mute,
                           "vertex_group": key.vertex_group, "interpolation": key.interpolation,
                           "is_basis": key == data.reference_key,
                           "has_driver": bool(data.animation_data and data.animation_data.drivers),
                           "editable": key.name in shape_keys.get(obj.name, ())}
                for key in data.key_blocks}
        if obj.type == "CAMERA":
            camera = obj.data
            frame = camera.view_frame(scene=scene)
            fov = [max(math.atan2(v[axis], -v.z) for v in frame) - min(math.atan2(v[axis], -v.z) for v in frame)
                   for axis in (0, 1)] if camera.type == "PERSP" else [None, None]
            record["camera"] = values(camera, ("type", "sensor_fit", "shift_x", "shift_y"))
            record["camera"].update({"lens_mm": camera.lens, "sensor_width_mm": camera.sensor_width,
                "sensor_height_mm": camera.sensor_height, "clip_start": camera.clip_start * factor,
                "clip_end": camera.clip_end * factor, "ortho_scale": camera.ortho_scale * factor,
                "fov_x_radians": fov[0], "fov_y_radians": fov[1],
                "resolution": [scene.render.resolution_x * scene.render.resolution_percentage // 100,
                               scene.render.resolution_y * scene.render.resolution_percentage // 100],
                "pixel_aspect": [scene.render.pixel_aspect_x, scene.render.pixel_aspect_y]})
        if obj.type == "LIGHT":
            record["light"] = values(obj.data, ("type", "energy", "color", "use_nodes", "shape", "spot_size", "spot_blend", "angle", "use_shadow", "normalize"))
            for key in ("shadow_soft_size", "size", "size_y"):
                if hasattr(obj.data, key):
                    record["light"][key] = getattr(obj.data, key) * factor
            record["light"]["nodes"] = nodes(obj.data.node_tree)
        objects[obj.name] = record
        for slot in obj.material_slots:
            mat = slot.material
            if mat and mat.name not in materials:
                materials[mat.name] = {"use_nodes": mat.use_nodes, "diffuse_color": list(mat.diffuse_color)}
                if include_material_nodes:
                    materials[mat.name]["nodes"] = nodes(mat.node_tree)
    return {"schema_version": "1.0", "sample_id": sample_id, "state": state,
            "scene": {"name": scene.name, "frame": scene.frame_current,
                      "units": {"length": "meter", "rotation": "radian", "meters_per_blender_unit": factor},
                      "coordinates": {"handedness": "right", "up_axis": "Z", "position_reference": "object_origin"}},
            "objects": objects, "materials": materials,
            "views": [{"camera_name": name, "image": None if state == "current" else f"{state}_views/{name}.png"} for name in camera_names]}


RENDER_FIELDS = ("engine", "resolution_x", "resolution_y", "resolution_percentage", "pixel_aspect_x", "pixel_aspect_y",
                 "film_transparent", "use_file_extension", "use_compositing", "use_sequencer", "dither_intensity", "use_motion_blur")
CYCLES_FIELDS = ("device", "samples", "seed", "use_animated_seed", "use_adaptive_sampling", "adaptive_threshold", "adaptive_min_samples",
                "use_denoising", "denoiser", "denoising_input_passes", "denoising_prefilter", "use_light_tree",
                "max_bounces", "diffuse_bounces", "glossy_bounces", "transmission_bounces", "volume_bounces", "transparent_max_bounces",
                "sample_clamp_direct", "sample_clamp_indirect", "blur_glossy", "caustics_reflective", "caustics_refractive")
IMAGE_FIELDS = ("file_format", "color_mode", "color_depth", "compression", "color_management")
COLOR_FIELDS = ("view_transform", "look", "exposure", "gamma", "use_curve_mapping")


def scene_settings(owner, settings, *, apply=False, path="scene"):
    """Apply/read configured RNA properties in JSON order, without preset values."""
    if not isinstance(settings, dict):
        raise ValueError(f"{path} must be an object")
    result = {}
    for key, value in settings.items():
        prop_path = f"{path}.{key}"
        prop = owner.bl_rna.properties.get(key) if hasattr(owner, "bl_rna") else None
        if prop is None:
            raise ValueError(f"Unknown Blender property: {prop_path}")
        if value is None:
            continue
        if isinstance(value, dict):
            result[key] = scene_settings(getattr(owner, key), value, apply=apply, path=prop_path)
        else:
            if prop.type not in {"BOOLEAN", "INT", "FLOAT", "STRING", "ENUM"} or prop.is_readonly:
                raise ValueError(f"{prop_path} must be a writable scalar/array or a nested object")
            try:
                if apply:
                    setattr(owner, key, set(value) if prop.type == "ENUM" and prop.is_enum_flag else value)
                actual = getattr(owner, key)
                result[key] = sorted(actual) if isinstance(actual, set) else plain(actual)
            except (TypeError, ValueError, AttributeError) as exc:
                raise ValueError(f"Invalid {prop_path}: {exc}") from exc
    return result


def configure_render(requested):
    """Apply the user-owned scene settings and initialize the requested devices."""
    if not isinstance(requested, dict):
        raise ValueError("render_config must be an object")
    unknown = set(requested) - {"scene", "view_layer", "devices"}
    if unknown:
        raise ValueError(f"Unknown render_config keys: {sorted(unknown)}; use scene/view_layer/devices")
    scene = bpy.context.scene
    scene_settings(scene, requested.get("scene", {}), apply=True)
    if requested.get("view_layer") is not None:
        scene_settings(bpy.context.view_layer, requested["view_layer"], apply=True, path="view_layer")
    devices = requested.get("devices")
    if devices is None:
        devices = {}
    if not isinstance(devices, dict):
        raise ValueError("render_config.devices must be an object or null")
    unknown = set(devices) - {"compute_device_type", "use_cpu", "fallback_to_cpu"}
    if unknown:
        raise ValueError(f"Unknown render_config.devices keys: {sorted(unknown)}")
    for key in ("use_cpu", "fallback_to_cpu"):
        if devices.get(key) is not None and type(devices[key]) is not bool:
            raise ValueError(f"render_config.devices.{key} must be a boolean or null")
    backend = devices.get("compute_device_type")
    if scene.render.engine == "CYCLES" and scene.cycles.device == "GPU" and backend is not None:
        try:
            preferences = bpy.context.preferences.addons["cycles"].preferences
            preferences.compute_device_type = backend
            preferences.get_devices()
            if not any(device.type == backend for device in preferences.devices):
                raise RuntimeError(f"No {backend} GPU devices available")
            for device in preferences.devices:
                if device.type == backend:
                    device.use = True
                elif device.type == "CPU" and devices.get("use_cpu") is not None:
                    device.use = devices["use_cpu"]
        except Exception as exc:
            if devices.get("fallback_to_cpu") is not True:
                raise
            scene.cycles.device = "CPU"
            print(f"GPU setup failed; configured CPU fallback: {exc}")


def capture_render_config(configured_scene=None, configured_view_layer=None):
    scene = bpy.context.scene
    world = scene.world
    preferences = bpy.context.preferences.addons.get("cycles")
    result = {
        "render": values(scene.render, RENDER_FIELDS), "cycles": values(scene.cycles, CYCLES_FIELDS),
        "image_settings": values(scene.render.image_settings, IMAGE_FIELDS),
        "color_management": values(scene.view_settings, COLOR_FIELDS),
        "display_device": scene.display_settings.display_device,
        "world": None if world is None else {"name": world.name, "color": list(world.color), "use_nodes": world.use_nodes, "nodes": nodes(world.node_tree)},
        "lights": {obj.name: {"type": obj.data.type, "energy": obj.data.energy, "color": list(obj.data.color)} for obj in scene.objects if obj.type == "LIGHT"},
        "compositor": nodes(scene.node_tree),
        "compute_device_type": preferences.preferences.compute_device_type if preferences else None,
        "devices": sorted([{"name": device.name, "type": device.type, "enabled": device.use} for device in preferences.preferences.devices],
                          key=lambda device: (device["type"], device["name"])) if preferences else [],
        "added_lights": [],
    }
    if configured_scene is not None:
        result["configured_scene"] = scene_settings(scene, configured_scene)
    if configured_view_layer is not None:
        result["configured_view_layer"] = scene_settings(bpy.context.view_layer, configured_view_layer, path="view_layer")
    return result


def apply_render_config(config):
    """Apply explicit render settings to the supplied snapshot, preserving its graph."""
    effective = config["effective"]
    scene = bpy.context.scene
    scene.display_settings.display_device = effective["display_device"]
    for key, owner in (("render", scene.render), ("cycles", scene.cycles),
                       ("image_settings", scene.render.image_settings), ("color_management", scene.view_settings)):
        for name, value in effective[key].items():
            setattr(owner, name, value)
    if "configured_scene" in effective:
        scene_settings(scene, effective["configured_scene"], apply=True)
    if "configured_view_layer" in effective:
        scene_settings(bpy.context.view_layer, effective["configured_view_layer"], apply=True, path="view_layer")
    preferences = bpy.context.preferences.addons.get("cycles")
    if preferences and effective["cycles"]["device"] == "GPU" and effective["compute_device_type"]:
        preferences.preferences.compute_device_type = effective["compute_device_type"]
        preferences.preferences.get_devices()
        enabled_types = {device["type"] for device in effective["devices"] if device["enabled"]}
        for device in preferences.preferences.devices:
            device.use = device.type in enabled_types
    bpy.context.view_layer.update()


def check_supported_scene(editable_names):
    """The paper mover assumes static, unparented Euler objects."""
    if bpy.data.libraries:
        raise ValueError("Linked libraries are unsupported; localize the source asset first")
    for obj in bpy.context.scene.objects:
        if obj.constraints or obj.animation_data:
            raise ValueError(f"Unsupported dynamic object: {obj.name}")
        if obj.name in editable_names:
            if obj.parent or obj.rotation_mode in ("QUATERNION", "AXIS_ANGLE"):
                raise ValueError(f"Placement requires unparented Euler editable objects: {obj.name}")
            if any(abs(v) > 1e-10 for v in (*obj.delta_location, *obj.delta_rotation_euler)) or any(abs(v - 1) > 1e-10 for v in obj.delta_scale):
                raise ValueError(f"Placement does not support delta transforms: {obj.name}")
            if obj.children:
                raise ValueError(f"Placement does not support moving a parent: {obj.name}")


def pack_resources(*, allow_static_geometry_nodes=False):
    bpy.ops.file.pack_all()
    for image in bpy.data.images:
        if image.source not in ("FILE", "GENERATED", "VIEWER"):
            raise ValueError(f"Unsupported external image source: {image.name} ({image.source})")
        if image.source == "FILE" and not image.packed_file:
            raise ValueError(f"Unpacked/missing texture: {image.name}")
    for obj in bpy.context.scene.objects:
        for modifier in obj.modifiers:
            if modifier.type in ("MESH_CACHE", "MESH_SEQUENCE_CACHE", "FLUID", "CLOTH", "NODES"):
                if modifier.type == "NODES" and allow_static_geometry_nodes:
                    continue
                raise ValueError(f"Unsupported external/simulated geometry: {obj.name}:{modifier.name}")
    if allow_static_geometry_nodes:
        for group in bpy.data.node_groups:
            if group.animation_data:
                raise ValueError(f"Animated node group: {group.name}")
            for node in group.nodes:
                if any(term in node.bl_idname for term in ("Simulation", "Bake", "Import", "InputSceneTime")):
                    raise ValueError(f"Unsupported dynamic/external node: {group.name}:{node.name}")


def restore_script(state, names):
    """Self-contained script with full float precision; JSON lengths are meters."""
    factor = state["scene"]["units"]["meters_per_blender_unit"]
    lines = ["import bpy", "", f'bpy.context.scene.frame_set({state["scene"]["frame"]!r})']
    for name in names:
        transform = state["objects"][name]["transform"]
        mode = transform["rotation_mode"]
        attr = "rotation_quaternion" if mode == "QUATERNION" else ("rotation_axis_angle" if mode == "AXIS_ANGLE" else "rotation_euler")
        lines.extend((f"obj = bpy.data.objects[{name!r}]", f"obj.rotation_mode = {mode!r}",
                      f"obj.location = {[v / factor for v in transform['location_local']]!r}",
                      f"obj.{attr} = {transform['rotation']!r}", f"obj.scale = {transform['scale_local']!r}"))
    lines.append("bpy.context.view_layer.update()")
    return "\n".join(lines) + "\n"
