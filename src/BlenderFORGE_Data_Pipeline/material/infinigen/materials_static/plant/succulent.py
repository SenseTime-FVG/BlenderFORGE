# Copyright (C) 2023, Princeton University.
# This source code is licensed under the BSD 3-Clause license found in the LICENSE file in the root directory of this source tree.

# Authors: Beining Han
# Acknowledgements: This file draws inspiration from https://blenderartists.org/t/extrude-face-along-curve-with-geometry-nodes/1432653/3


from infinigen.core import surface
from infinigen.core.nodes.node_wrangler import Nodes, NodeWrangler
from infinigen.core.util.color import hsv2rgba


def shader_green_transition_succulent(nw: NodeWrangler):
    # Code generated using version 2.4.3 of the node_transpiler

    musgrave_texture_1 = nw.new_node(
        Nodes.MusgraveTexture, input_kwargs={"Scale": 12.785055930519938}
    )

    colorramp_3 = nw.new_node(Nodes.ColorRamp, input_kwargs={"Fac": musgrave_texture_1})
    colorramp_3.color_ramp.elements[0].position = 0.1182
    colorramp_3.color_ramp.elements[0].color = (0.0, 0.0, 0.0, 1.0)
    colorramp_3.color_ramp.elements[1].position = 0.7727
    colorramp_3.color_ramp.elements[1].color = (1.0, 1.0, 1.0, 1.0)

    texture_coordinate = nw.new_node(Nodes.TextureCoord)

    mapping = nw.new_node(
        Nodes.Mapping, input_kwargs={"Vector": texture_coordinate.outputs["Generated"]}
    )

    separate_xyz = nw.new_node(Nodes.SeparateXYZ, input_kwargs={"Vector": mapping})

    less_than = nw.new_node(
        Nodes.Math,
        input_kwargs={0: separate_xyz.outputs["Z"], 1: 0.85},
        attrs={"operation": "LESS_THAN"},
    )

    multiply = nw.new_node(
        Nodes.Math,
        input_kwargs={0: colorramp_3.outputs["Color"], 1: less_than},
        attrs={"operation": "MULTIPLY"},
    )

    multiply_1 = nw.new_node(
        Nodes.Math,
        input_kwargs={0: multiply, 1: 5.588354284772437},
        attrs={"operation": "MULTIPLY"},
    )

    main_hsv_color = (0.3533779453601806, 0.577222345087869, 0.5138301390200589)
    main_color = hsv2rgba(main_hsv_color)
    diffuse_color = hsv2rgba((0.38397569239844376,) + main_hsv_color[1:])
    split_point = 0.8748484296572513
    colorramp_1 = nw.new_node(
        Nodes.ColorRamp, input_kwargs={"Fac": separate_xyz.outputs["Z"]}
    )
    colorramp_1.color_ramp.interpolation = "B_SPLINE"
    colorramp_1.color_ramp.elements[0].position = split_point
    colorramp_1.color_ramp.elements[0].color = main_color
    colorramp_1.color_ramp.elements[1].position = split_point + 0.0128345153637739
    colorramp_1.color_ramp.elements[1].color = (
        0.7612676585780374,
        0.02628165680123895,
        0.03317772871771539,
        1.0,
    )
    principled_bsdf = nw.new_node(
        Nodes.PrincipledBSDF,
        input_kwargs={
            "Base Color": colorramp_1.outputs["Color"],
            "Subsurface Weight": 0.021697774039865485,
            "Subsurface Radius": (0.01, 0.1, 0.1),
            "Subsurface Color": colorramp_1.outputs["Color"],
            "Specular IOR Level": 0.0,
            "Roughness": 2.0,
            "Coat Roughness": 0.0,
            "IOR": 1.3,
            "Emission Strength": 0.0,
        },
    )

    diffuse_bsdf_1 = nw.new_node(
        Nodes.DiffuseBSDF,
        input_kwargs={"Color": diffuse_color, "Roughness": 0.6396512836860624},
    )

    mix_shader_2 = nw.new_node(
        Nodes.MixShader,
        input_kwargs={"Fac": multiply_1, 1: principled_bsdf, 2: diffuse_bsdf_1},
    )

    material_output = nw.new_node(
        Nodes.MaterialOutput, input_kwargs={"Surface": mix_shader_2}
    )


def shader_pink_transition_succulent(nw: NodeWrangler):
    # Code generated using version 2.4.3 of the node_transpiler

    musgrave_texture_1 = nw.new_node(
        Nodes.MusgraveTexture, input_kwargs={"Scale": 11.345571102611338}
    )

    colorramp_3 = nw.new_node(Nodes.ColorRamp, input_kwargs={"Fac": musgrave_texture_1})
    colorramp_3.color_ramp.elements[0].position = 0.1182
    colorramp_3.color_ramp.elements[0].color = (0.0, 0.0, 0.0, 1.0)
    colorramp_3.color_ramp.elements[1].position = 0.7727
    colorramp_3.color_ramp.elements[1].color = (1.0, 1.0, 1.0, 1.0)

    texture_coordinate = nw.new_node(Nodes.TextureCoord)

    mapping = nw.new_node(
        Nodes.Mapping, input_kwargs={"Vector": texture_coordinate.outputs["Generated"]}
    )

    separate_xyz = nw.new_node(Nodes.SeparateXYZ, input_kwargs={"Vector": mapping})

    less_than = nw.new_node(
        Nodes.Math,
        input_kwargs={0: separate_xyz.outputs["Z"], 1: 0.85},
        attrs={"operation": "LESS_THAN"},
    )

    multiply = nw.new_node(
        Nodes.Math,
        input_kwargs={0: colorramp_3.outputs["Color"], 1: less_than},
        attrs={"operation": "MULTIPLY"},
    )

    multiply_1 = nw.new_node(
        Nodes.Math,
        input_kwargs={0: multiply, 1: 4.2099887380065555},
        attrs={"operation": "MULTIPLY"},
    )

    main_hsv_color = (0.9359640202943221, 0.876250964143163, 0.6896018604549186)
    main_color = hsv2rgba(main_hsv_color)
    diffuse_color = hsv2rgba((0.9991921340669503,) + main_hsv_color[1:])
    split_point = 0.8493407001457336
    colorramp_1 = nw.new_node(
        Nodes.ColorRamp, input_kwargs={"Fac": separate_xyz.outputs["Z"]}
    )
    colorramp_1.color_ramp.interpolation = "B_SPLINE"
    colorramp_1.color_ramp.elements[0].position = split_point
    colorramp_1.color_ramp.elements[0].color = main_color
    colorramp_1.color_ramp.elements[1].position = split_point + 0.04363393330510686
    principled_bsdf = nw.new_node(
        Nodes.PrincipledBSDF,
        input_kwargs={
            "Base Color": colorramp_1.outputs["Color"],
            "Subsurface Weight": 0.02043666141785025,
            "Subsurface Radius": (0.01, 0.03, 0.03),
            "Subsurface Color": colorramp_1.outputs["Color"],
            "Specular IOR Level": 0.0,
            "Roughness": 2.0,
            "Coat Roughness": 0.0,
            "IOR": 1.3,
            "Emission Strength": 0.0,
        },
    )

    diffuse_bsdf_1 = nw.new_node(
        Nodes.DiffuseBSDF,
        input_kwargs={"Color": diffuse_color, "Roughness": 0.3885500772542548},
    )

    mix_shader_2 = nw.new_node(
        Nodes.MixShader,
        input_kwargs={"Fac": multiply_1, 1: principled_bsdf, 2: diffuse_bsdf_1},
    )

    material_output = nw.new_node(
        Nodes.MaterialOutput, input_kwargs={"Surface": mix_shader_2}
    )


def shader_green_succulent(nw: NodeWrangler):
    musgrave_texture_1 = nw.new_node(
        Nodes.MusgraveTexture, input_kwargs={"Scale": 8.743431270952485}
    )

    colorramp_3 = nw.new_node(Nodes.ColorRamp, input_kwargs={"Fac": musgrave_texture_1})
    colorramp_3.color_ramp.elements[0].position = 0.1182
    colorramp_3.color_ramp.elements[0].color = (0.0, 0.0, 0.0, 1.0)
    colorramp_3.color_ramp.elements[1].position = 0.7727
    colorramp_3.color_ramp.elements[1].color = (1.0, 1.0, 1.0, 1.0)

    texture_coordinate = nw.new_node(Nodes.TextureCoord)

    mapping = nw.new_node(
        Nodes.Mapping, input_kwargs={"Vector": texture_coordinate.outputs["Generated"]}
    )

    separate_xyz = nw.new_node(Nodes.SeparateXYZ, input_kwargs={"Vector": mapping})

    less_than = nw.new_node(
        Nodes.Math,
        input_kwargs={0: separate_xyz.outputs["Z"], 1: 1.0},
        attrs={"operation": "LESS_THAN"},
    )

    multiply = nw.new_node(
        Nodes.Math,
        input_kwargs={0: colorramp_3.outputs["Color"], 1: less_than},
        attrs={"operation": "MULTIPLY"},
    )

    multiply_1 = nw.new_node(
        Nodes.Math,
        input_kwargs={0: multiply, 1: 4.1511222920572335},
        attrs={"operation": "MULTIPLY"},
    )

    main_hsv_color = (0.38857376745894345, 0.6477701852728401, 0.43954325957599305)
    main_color = hsv2rgba(main_hsv_color)
    diffuse_color = hsv2rgba((0.34255431795775315,) + main_hsv_color[1:])
    colorramp_1 = nw.new_node(
        Nodes.ColorRamp, input_kwargs={"Fac": separate_xyz.outputs["Z"]}
    )
    colorramp_1.color_ramp.interpolation = "B_SPLINE"
    colorramp_1.color_ramp.elements[0].position = 1.0
    colorramp_1.color_ramp.elements[0].color = main_color
    principled_bsdf = nw.new_node(
        Nodes.PrincipledBSDF,
        input_kwargs={
            "Base Color": colorramp_1.outputs["Color"],
            "Subsurface Weight": 0.0445431577720817,
            "Subsurface Radius": (0.1, 0.1, 0.1),
            "Subsurface Color": colorramp_1.outputs["Color"],
            "Specular IOR Level": 0.0,
            "Roughness": 2.0,
            "Coat Roughness": 0.0,
            "IOR": 1.3,
            "Emission Strength": 0.0,
        },
    )

    diffuse_bsdf_1 = nw.new_node(
        Nodes.DiffuseBSDF,
        input_kwargs={"Color": diffuse_color, "Roughness": 0.3510020748809686},
    )

    mix_shader_2 = nw.new_node(
        Nodes.MixShader,
        input_kwargs={"Fac": multiply_1, 1: principled_bsdf, 2: diffuse_bsdf_1},
    )

    material_output = nw.new_node(
        Nodes.MaterialOutput, input_kwargs={"Surface": mix_shader_2}
    )


def shader_yellow_succulent(nw: NodeWrangler):
    musgrave_texture_1 = nw.new_node(
        Nodes.MusgraveTexture, input_kwargs={"Scale": 7.709032122622782}
    )

    colorramp_3 = nw.new_node(Nodes.ColorRamp, input_kwargs={"Fac": musgrave_texture_1})
    colorramp_3.color_ramp.elements[0].position = 0.1182
    colorramp_3.color_ramp.elements[0].color = (0.0, 0.0, 0.0, 1.0)
    colorramp_3.color_ramp.elements[1].position = 0.7727
    colorramp_3.color_ramp.elements[1].color = (1.0, 1.0, 1.0, 1.0)

    texture_coordinate = nw.new_node(Nodes.TextureCoord)

    mapping = nw.new_node(
        Nodes.Mapping, input_kwargs={"Vector": texture_coordinate.outputs["Generated"]}
    )

    separate_xyz = nw.new_node(Nodes.SeparateXYZ, input_kwargs={"Vector": mapping})

    less_than = nw.new_node(
        Nodes.Math,
        input_kwargs={0: separate_xyz.outputs["Z"], 1: 1.0},
        attrs={"operation": "LESS_THAN"},
    )

    multiply = nw.new_node(
        Nodes.Math,
        input_kwargs={0: colorramp_3.outputs["Color"], 1: less_than},
        attrs={"operation": "MULTIPLY"},
    )

    multiply_1 = nw.new_node(
        Nodes.Math,
        input_kwargs={0: multiply, 1: 1.9032235853737354},
        attrs={"operation": "MULTIPLY"},
    )

    main_color = hsv2rgba((0.12132676617720141, 0.8603806232438712, 0.646950198243723))
    colorramp_1 = nw.new_node(
        Nodes.ColorRamp, input_kwargs={"Fac": separate_xyz.outputs["Z"]}
    )
    colorramp_1.color_ramp.interpolation = "B_SPLINE"
    colorramp_1.color_ramp.elements[0].position = 0.3114
    colorramp_1.color_ramp.elements[0].color = main_color
    colorramp_1.color_ramp.elements[1].position = 0.6864
    colorramp_1.color_ramp.elements[1].color = hsv2rgba(
        (0.05366398669287447, 0.983937768886322, 0.6253484093613735)
    )

    principled_bsdf = nw.new_node(
        Nodes.PrincipledBSDF,
        input_kwargs={
            "Base Color": colorramp_1.outputs["Color"],
            "Subsurface Weight": 0.01,
            "Subsurface Radius": (1.0, 1.0, 1.0),
            "Subsurface Color": nw.combine(*([colorramp_1.outputs["Alpha"]] * 3)),
            "Specular IOR Level": 0.0,
            "Roughness": 2.0,
            "Coat Roughness": 0.0,
            "IOR": 1.3,
            "Emission Strength": 0.0,
        },
    )

    translucent_bsdf = nw.new_node(
        Nodes.TranslucentBSDF, input_kwargs={"Color": main_color}
    )

    mix_shader_1 = nw.new_node(
        Nodes.MixShader,
        input_kwargs={"Fac": 0.4, 1: principled_bsdf, 2: translucent_bsdf},
    )

    diffuse_bsdf_1 = nw.new_node(
        Nodes.DiffuseBSDF,
        input_kwargs={"Color": main_color, "Roughness": 0.741536773453283},
    )

    mix_shader_2 = nw.new_node(
        Nodes.MixShader,
        input_kwargs={"Fac": multiply_1, 1: mix_shader_1, 2: diffuse_bsdf_1},
    )

    material_output = nw.new_node(
        Nodes.MaterialOutput, input_kwargs={"Surface": mix_shader_2}
    )


def shader_whitish_green_succulent(nw: NodeWrangler):
    # Code generated using version 2.4.3 of the node_transpiler

    musgrave_texture_1 = nw.new_node(
        Nodes.MusgraveTexture, input_kwargs={"Scale": 5.3567308596615675}
    )

    colorramp_3 = nw.new_node(Nodes.ColorRamp, input_kwargs={"Fac": musgrave_texture_1})
    colorramp_3.color_ramp.elements[0].position = 0.1434194007453063
    colorramp_3.color_ramp.elements[0].color = (0.0, 0.0, 0.0, 1.0)
    colorramp_3.color_ramp.elements[1].position = 0.5273
    colorramp_3.color_ramp.elements[1].color = (1.0, 1.0, 1.0, 1.0)

    texture_coordinate = nw.new_node(Nodes.TextureCoord)

    mapping = nw.new_node(
        Nodes.Mapping, input_kwargs={"Vector": texture_coordinate.outputs["Generated"]}
    )

    separate_xyz = nw.new_node(Nodes.SeparateXYZ, input_kwargs={"Vector": mapping})

    l = 0.9039706083638623
    less_than = nw.new_node(
        Nodes.Math,
        input_kwargs={0: separate_xyz.outputs["Z"], 1: l - 0.05},
        attrs={"operation": "LESS_THAN"},
    )

    multiply = nw.new_node(
        Nodes.Math,
        input_kwargs={0: colorramp_3.outputs["Color"], 1: less_than},
        attrs={"operation": "MULTIPLY"},
    )

    multiply_1 = nw.new_node(
        Nodes.Math,
        input_kwargs={0: multiply, 1: 2.19386080480694},
        attrs={"operation": "MULTIPLY"},
    )

    main_color = hsv2rgba(
        (0.2375114269265709, 0.5949121042959388, 0.22472149622503312)
    )
    colorramp = nw.new_node(
        Nodes.ColorRamp, input_kwargs={"Fac": separate_xyz.outputs["Z"]}
    )
    colorramp.color_ramp.elements[0].position = l - 0.08197571746903712
    colorramp.color_ramp.elements[0].color = hsv2rgba(
        (0.2118502419099142, 0.13100704398561444, 0.6499739143566172)
    )
    colorramp.color_ramp.elements[1].position = l
    colorramp.color_ramp.elements[1].color = main_color

    principled_bsdf = nw.new_node(
        Nodes.PrincipledBSDF,
        input_kwargs={
            "Base Color": colorramp.outputs["Color"],
            "Subsurface Weight": 0.01,
            "Subsurface Radius": (1.0, 1.0, 1.0),
            "Subsurface Color": colorramp.outputs["Color"],
            "Specular IOR Level": 0.0,
            "Roughness": 2.0,
            "Coat Roughness": 0.0,
            "IOR": 1.3,
            "Emission Strength": 0.0,
        },
    )

    translucent_bsdf = nw.new_node(
        Nodes.TranslucentBSDF, input_kwargs={"Color": main_color}
    )

    mix_shader_1 = nw.new_node(
        Nodes.MixShader,
        input_kwargs={"Fac": 0.7, 1: principled_bsdf, 2: translucent_bsdf},
    )
    diffuse = hsv2rgba((0.23122312313091933, 0.4015702010662504, 0.11969039758908548))
    diffuse_bsdf_1 = nw.new_node(
        Nodes.DiffuseBSDF, input_kwargs={"Color": diffuse, "Roughness": 0.5}
    )

    mix_shader_2 = nw.new_node(
        Nodes.MixShader,
        input_kwargs={"Fac": multiply_1, 1: mix_shader_1, 2: diffuse_bsdf_1},
    )

    material_output = nw.new_node(
        Nodes.MaterialOutput, input_kwargs={"Surface": mix_shader_2}
    )


class Succulent:
    def apply(self, obj, selection=None, **kwargs):
        surface.add_material(
            obj, shader_green_transition_succulent, selection=selection
        )
