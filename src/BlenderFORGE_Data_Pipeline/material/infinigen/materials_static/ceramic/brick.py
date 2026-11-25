# Copyright (C) 2023, Princeton University.
# This source code is licensed under the BSD 3-Clause license found in the LICENSE file in the root directory of this source tree.

# Authors: Lingjie Mei

import numpy as np

from infinigen.assets.utils.object import new_plane
from infinigen.core import surface
from infinigen.core.nodes.node_info import Nodes
from infinigen.core.nodes.node_wrangler import NodeWrangler
from infinigen.core.util import blender as butil
from infinigen.core.util.color import hsv2rgba


def shader_brick(nw: NodeWrangler, height=None, **kwargs):
    if height is None:
        height = 0.11034763108248023
    uv_map = nw.new_node(Nodes.UVMap)

    front_color, back_color = [
        hsv2rgba(0.015165636303946373, 0.8953193908304712, 0.13078655157315486)
        for _ in range(2)
    ]
    mortar_color = hsv2rgba(0.037897720147015125, 0.3261714742492535, 0.05197926837741244)
    dark_color = hsv2rgba(0.025563736068430428, 0.880986827490083, 0.014820531407285308)
    noise = nw.new_node(
        Nodes.NoiseTexture,
        [uv_map],
        input_kwargs={"Scale": 42.81837844399704, "Detail": 18.779021020786118},
    )
    color = nw.new_node(
        Nodes.BrickTexture,
        [uv_map, front_color, back_color, mortar_color],
        input_kwargs={
            "Scale": 1,
            "Row Height": height,
            "Brick Width": height * 2.3397574398647314,
            "Mortar Size": height * 0.07905109661048791,
            "Mortar Smooth": noise,
        },
    ).outputs["Color"]
    noise = nw.new_node(
        Nodes.MusgraveTexture, [uv_map], input_kwargs={"Scale": 3.8551069900259947}
    )
    color = nw.new_node(
        Nodes.MixRGB,
        [nw.scalar_multiply(0.5948122815952354, noise), color, dark_color],
        attrs={"blend_type": "DARKEN"},
    )

    roughness = nw.build_float_curve(
        nw.new_node(Nodes.NoiseTexture, input_kwargs={"Scale": 50}),
        [(0, 0.5), (1, 1.0)],
    )

    offset = nw.scalar_add(
        nw.scalar_multiply(color, 0.037243386555860056),
        nw.scalar_multiply(
            nw.new_node(Nodes.MusgraveTexture, [uv_map], input_kwargs={"Scale": 50}),
            0.005046868558173902,
        ),
    )
    principled_bsdf = nw.new_node(
        Nodes.PrincipledBSDF,
        input_kwargs={"Roughness": roughness, "Base Color": color},
    )
    displacement = nw.new_node(
        Nodes.Displacement, input_kwargs={"Height": offset, "Scale": 0.05}
    )
    nw.new_node(
        Nodes.MaterialOutput,
        input_kwargs={"Surface": principled_bsdf, "Displacement": displacement},
    )


class Brick:
    shader = shader_brick

    def generate(self):
        return surface.shaderfunc_to_material(shader_brick)

    __call__ = generate


def make_sphere():
    obj = new_plane()
    obj.rotation_euler[0] = np.pi / 2
    butil.apply_transform(obj, True)
    return obj
