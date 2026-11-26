# Copyright (C) 2023, Princeton University.
# This source code is licensed under the BSD 3-Clause license found in the LICENSE file in the root directory of this source tree.

# Authors: Alexander Raistrick



from infinigen.core import surface
from infinigen.core.nodes.node_wrangler import Nodes, NodeWrangler


def shader_bone(nw: NodeWrangler):
    # Code generated using version 2.4.3 of the node_transpiler

    texture_coordinate = nw.new_node(Nodes.TextureCoord)

    mapping = nw.new_node(
        Nodes.Mapping,
        input_kwargs={
            "Vector": texture_coordinate.outputs["Object"],
            "Location": (
                1.7 + 0.2938514396706451 * 0.05,
                0.29999999999999999 + -0.2994120652069354 * 0.05,
                -0.9544348486626832 * 0.05,
            ),
        },
    )

    noise_texture_2 = nw.new_node(
        Nodes.NoiseTexture,
        input_kwargs={
            "Vector": mapping,
            "Scale": 10.800000000000001 + -0.14876233606636569 * 3,
            "Detail": 15.0,
            "Roughness": 0.76670000000000005,
        },
    )

    voronoi_texture_1 = nw.new_node(
        Nodes.VoronoiTexture,
        input_kwargs={"Vector": noise_texture_2.outputs["Fac"], "Scale": 10.0},
    )

    colorramp_2 = nw.new_node(
        Nodes.ColorRamp, input_kwargs={"Fac": voronoi_texture_1.outputs["Color"]}
    )
    colorramp_2.color_ramp.elements[0].position = 0.4364 + 0.9220625604792223 * 0.05
    colorramp_2.color_ramp.elements[0].color = (0, 0, 0, 1.0)
    colorramp_2.color_ramp.elements[1].position = 0.58 + -0.6300561172051233 * 0.05
    colorramp_2.color_ramp.elements[1].color = (1, 1, 1, 1.0)

    mapping_2 = nw.new_node(
        Nodes.Mapping, input_kwargs={"Vector": texture_coordinate.outputs["Object"]}
    )

    noise_texture = nw.new_node(
        Nodes.NoiseTexture,
        input_kwargs={
            "Vector": mapping_2,
            "Scale": 98.900000000000006 + -0.1680497148135793 * 30,
            "Detail": 15.0,
            "Roughness": 0.76670000000000005,
        },
    )

    voronoi_texture = nw.new_node(
        Nodes.VoronoiTexture,
        input_kwargs={
            "Vector": noise_texture.outputs["Fac"],
            "Scale": 10.0 + -0.48016022041433604 * 0.05,
        },
    )

    colorramp = nw.new_node(
        Nodes.ColorRamp, input_kwargs={"Fac": voronoi_texture.outputs["Color"]}
    )
    colorramp.color_ramp.elements[0].position = 0.3089 + -0.7522096711511366 * 0.05
    colorramp.color_ramp.elements[0].color = (0.0, 0.0, 0.0, 1.0)
    colorramp.color_ramp.elements[1].position = 0.673 + -0.5788469802267071 * 0.05
    colorramp.color_ramp.elements[1].color = (1.0, 1.0, 1.0, 1.0)

    multiply = nw.new_node(
        Nodes.VectorMath,
        input_kwargs={0: colorramp_2.outputs["Color"], 1: colorramp.outputs["Color"]},
        attrs={"operation": "MULTIPLY"},
    )

    mapping_1 = nw.new_node(
        Nodes.Mapping,
        input_kwargs={
            "Vector": texture_coordinate.outputs["UV"],
            "Scale": (1.0, 1.0, 0.0),
        },
    )

    noise_texture_1 = nw.new_node(
        Nodes.NoiseTexture,
        input_kwargs={
            "Vector": mapping_1,
            "Scale": 6.4000000000000004 + -0.5583414573673653 * 1,
        },
    )

    colorramp_1 = nw.new_node(
        Nodes.ColorRamp, input_kwargs={"Fac": noise_texture_1.outputs["Fac"]}
    )
    colorramp_1.color_ramp.elements[0].position = 0.3682 + 0.6014931807083619 * 0.05
    colorramp_1.color_ramp.elements[0].color = (
        0.38129999999999997,
        0.2384,
        0.1183,
        1.0,
    )
    colorramp_1.color_ramp.elements[1].position = 0.7591 + 0.8739383172891615 * 0.05
    colorramp_1.color_ramp.elements[1].color = (
        0.49690000000000001,
        0.50290000000000001,
        0.46779999999999999,
        1.0,
    )

    mix = nw.new_node(
        Nodes.MixRGB,
        input_kwargs={
            "Fac": multiply.outputs["Vector"],
            "Color1": (0.19120000000000001, 0.045199999999999997, 0.0103, 1.0),
            "Color2": colorramp_1.outputs["Color"],
        },
    )

    principled_bsdf = nw.new_node(
        Nodes.PrincipledBSDF,
        input_kwargs={"Base Color": mix, "Roughness": 0.44090000000000001},
    )

    glass_bsdf = nw.new_node("ShaderNodeBsdfGlass")

    mix_shader = nw.new_node(
        Nodes.MixShader, input_kwargs={"Fac": 0.2, 1: principled_bsdf, 2: glass_bsdf}
    )

    material_output = nw.new_node(
        Nodes.MaterialOutput, input_kwargs={"Surface": mix_shader}
    )


class Bone:
    # shader = shader_bone

    def apply(self, obj, selection=None, **kwargs):
        surface.add_material(obj, shader_bone, selection=selection)
