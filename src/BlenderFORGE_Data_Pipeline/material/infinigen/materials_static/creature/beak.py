# Copyright (C) 2023, Princeton University.
# This source code is licensed under the BSD 3-Clause license found in the LICENSE file in the root directory of this source tree.

# Authors: Yihan Wang


from numpy.random import randint, uniform

from infinigen.core import surface
from infinigen.core.nodes.node_wrangler import Nodes, NodeWrangler


def orange():
    r = uniform(205 / 255, 1)
    g = uniform(0, 150 / 255)
    b = 0
    return (r, g, b)


def white():
    return (0.03488353200956194, 0.0022617033932806176, 0.028693301839458348)


def black():
    return (1 - 0.04550080073495199, 1 - 0.0267098984130362, 1 - 0.034029456628112825)


def rand_color():
    op = randint(0, 2)
    return orange(), orange()


def shader_beak(nw: NodeWrangler):
    # Code generated using version 2.4.3 of the node_transpiler

    texture_coordinate = nw.new_node(Nodes.TextureCoord)

    separate_xyz = nw.new_node(
        Nodes.SeparateXYZ, input_kwargs={"Vector": texture_coordinate.outputs["UV"]}
    )

    noise_texture_1 = nw.new_node(
        Nodes.NoiseTexture,
        input_kwargs={
            "Scale": 4.3 + 1.2126768355084379,
            "Roughness": 0.4167 + 0.11519058960630815,
        },
    )

    multiply = nw.new_node(
        Nodes.Math,
        input_kwargs={0: noise_texture_1.outputs["Fac"], 1: 0.2},
        attrs={"operation": "MULTIPLY"},
    )

    add = nw.new_node(
        Nodes.Math, input_kwargs={0: separate_xyz.outputs["Y"], 1: multiply}
    )

    colorramp = nw.new_node(Nodes.ColorRamp, input_kwargs={"Fac": add})
    colorramp.color_ramp.interpolation = "EASE"
    col0, col1 = rand_color()
    colorramp.color_ramp.elements[0].position = 0.33 + -0.9466064106755896 * 0.2
    colorramp.color_ramp.elements[0].color = (col0[0], col0[1], col0[2], 1.0)
    colorramp.color_ramp.elements[1].position = 0.66 + 0.26999981982291654 * 0.2
    colorramp.color_ramp.elements[1].color = (col1[0], col1[1], col1[2], 1.0)

    principled_bsdf = nw.new_node(
        Nodes.PrincipledBSDF,
        input_kwargs={
            "Base Color": colorramp.outputs["Color"],
            "Roughness": 0.2434 + 0.03912094093228269,
        },
    )

    glass_bsdf = nw.new_node("ShaderNodeBsdfGlass")

    mix_shader = nw.new_node(
        Nodes.MixShader,
        input_kwargs={
            "Fac": 0.5667 + 0.018506997016759376,
            1: principled_bsdf,
            2: glass_bsdf,
        },
    )

    material_output = nw.new_node(
        Nodes.MaterialOutput, input_kwargs={"Surface": mix_shader}
    )


class Beak:
    shader = shader_beak

    def apply(self, obj, selection=None, **kwargs):
        surface.add_material(obj, shader_beak, selection=selection)
