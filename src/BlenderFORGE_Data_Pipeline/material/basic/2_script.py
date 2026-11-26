"""Original Principled material construction code for the paper prompt."""
from typing import Dict, Any

def generate_script(params: Dict[str, Any], obj_name: str, mat_name: str) -> str:
    """Generate the Python script to apply these parameters in Blender."""
    script = [
        "import bpy",
        "",
        f"obj = bpy.data.objects.get({obj_name!r})",
        "if obj:",
        f"    mat = bpy.data.materials.get({mat_name!r})",
        "    if not mat:",
        f"        mat = bpy.data.materials.new(name={mat_name!r})",
        "    mat.use_nodes = True",
        "    nodes = mat.node_tree.nodes",
        "    nodes.clear()",
        "",
        "    bsdf = nodes.new(type='ShaderNodeBsdfPrincipled')",
        "    bsdf.location = (0, 0)",
        "    output = nodes.new(type='ShaderNodeOutputMaterial')",
        "    output.location = (300, 0)",
        "    mat.node_tree.links.new(bsdf.outputs['BSDF'], output.inputs['Surface'])",
        "",
        "    if obj.data.materials:",
        "        obj.data.materials[0] = mat",
        "    else:",
        "        obj.data.materials.append(mat)",
        ""
    ]

    # Note: In Blender 4.0+, some names changed (e.g., 'Transmission' -> 'Transmission Weight')
    # We will use the names as defined in our config, which should match Blender's inputs
    for param_name, value in params.items():
        if isinstance(value, list):
            script.append(f"    if {param_name!r} in bsdf.inputs:")
            script.append(f"        bsdf.inputs[{param_name!r}].default_value = ({value[0]}, {value[1]}, {value[2]}, {value[3]})")
        else:
            script.append(f"    if {param_name!r} in bsdf.inputs:")
            script.append(f"        bsdf.inputs[{param_name!r}].default_value = {value}")

    return "\n".join(script)
