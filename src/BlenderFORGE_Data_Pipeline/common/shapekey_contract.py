"""Shape-key-specific joins and edit invariants for the common v1 contract."""
from common.contract import require


def key_pairs(items):
    return [(item["object_name"], item["key_name"]) for item in items]


def check_shapekey_states(metadata, start, goal):
    editable = key_pairs(metadata["editable"]["shape_keys"])
    require(editable and len(editable) == len(set(editable)), "Missing/duplicate editable shape keys")
    names = {name for name, _ in editable}
    require(set(metadata["editable"]["object_names"]) == names, "Editable object/key scope mismatch")
    require(len(metadata["editable"]["object_names"]) == len(names), "Duplicate editable object names")
    require(len(editable) <= metadata["generator"]["config"]["Max_num_of_key_displayed"], "Displayed key count exceeds config")
    require(start["objects"].keys() == goal["objects"].keys(), "Entity set changed")
    require(start["scene"] == goal["scene"] and start["materials"] == goal["materials"], "Non-shapekey scene/material edit")
    cameras = [view["camera_name"] for view in start["views"]]
    require(cameras == [view["camera_name"] for view in goal["views"]], "Camera set/order changed")
    for state in (start, goal):
        objects = state["objects"]
        require(names == {name for name, obj in objects.items() if obj["editable"]}, "Editable scope mismatch")
        scope = names | set(cameras)
        for name in tuple(scope):
            seen = {name}
            parent = objects[name]["parent_id"]
            while parent is not None:
                require(parent not in seen, "Parent cycle")
                seen.add(parent)
                scope.add(parent)
                parent = objects[parent]["parent_id"]
        require(set(objects) == scope, "Unrelated objects in shapekey state")
        actual = {(name, key) for name, obj in objects.items() for key, value in obj.get("shapekeys", {}).items() if value["editable"]}
        require(actual == set(editable), "Editable shape-key flags disagree with metadata")
        for name, key in editable:
            obj = objects[name]
            value = obj["shapekeys"][key]
            require(obj["object_type"] == "MESH" and obj["shape_key_settings"]["use_relative"], "Only relative mesh shape keys are supported")
            require(not obj["shape_key_settings"]["show_only_shape_key"], "Solo shape-key display is unsupported")
            require(not value["is_basis"] and not value["has_driver"] and not value["mute"], "Uneditable shape key")
            require(value["slider_min"] <= value["value"] <= value["slider_max"], "Shape-key value outside slider range")
        materials = {slot for obj in objects.values() for slot in obj["material_slots"] if slot is not None}
        require(set(state["materials"]) == materials, "Unrelated materials")
        require(all("nodes" not in material for material in state["materials"].values()), "Shapekey state must omit shader graphs")
    changed = set()
    for name, obj in start["objects"].items():
        other = goal["objects"][name]
        require(obj.keys() == other.keys(), "Object schema changed")
        fixed = obj.keys() - {"shapekeys", "geometry"}
        require(all(obj[key] == other[key] for key in fixed), f"Non-shapekey edit: {name}")
        keys = obj.get("shapekeys", {})
        require(keys.keys() == other.get("shapekeys", {}).keys(), "Shape-key identities changed")
        for key, value in keys.items():
            target = other["shapekeys"][key]
            require(value.keys() == target.keys() and all(value[k] == target[k] for k in value if k != "value"), "Shape-key settings changed")
            if value["value"] != target["value"]:
                require((name, key) in editable, "Changed a non-editable key")
                changed.add((name, key))
        if name not in {obj_name for obj_name, _ in changed}:
            require(obj == other, f"Undeclared geometry edit: {name}")
    edits = metadata["edit_summary"]
    listed = key_pairs(edits["shape_keys"])
    require(set(listed) == changed and len(listed) == len(changed), "Changed key summary mismatch")
    require(1 <= len(changed) == edits["actual_changed"] <= edits["requested_max"], "Invalid up-to-N key count")
    require(edits["requested_max"] == metadata["generator"]["config"]["num_of_key_change"], "Requested key count mismatch")
    require(set(edits["object_names"]) == {name for name, _ in changed}, "Changed object summary mismatch")
    require(len(edits["object_names"]) == len(set(edits["object_names"])), "Duplicate changed object names")
