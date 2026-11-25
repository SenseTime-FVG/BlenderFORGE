# Copyright (C) 2023, Princeton University.
# This source code is licensed under the BSD 3-Clause license found in the LICENSE file in the root directory of this source tree.

# Authors: Alexander Raistrick


import numpy as np
from numpy.random import normal

from infinigen.core import surface
from infinigen.core.nodes.node_wrangler import Nodes
from infinigen.core.util.color import hsv2rgba


def shader_basic_bsdf(nw, hsv=None):
    if hsv is None:
        hsv = [0.06119268694638296, 0.7174169396695972, 0.35232489902611447]

    color = nw.new_node(Nodes.RGB)
    color.outputs[0].default_value = hsv2rgba(hsv)

    principled_bsdf = nw.new_node(
        Nodes.PrincipledBSDF,
        input_kwargs={
            "Base Color": color,
            "Roughness": np.clip(normal(0.6, 0.3), 0.05, 0.95),
            "Metallic": 0.04569649356841665 if 0.24013040782635398 < 0.3 else 0,
            "Subsurface Weight": 0 if 0.9531293398277989 < 0.8 else 0.05617663284366965,
        },
        attrs={"subsurface_method": "BURLEY"},
    )

    material_output = nw.new_node(
        Nodes.MaterialOutput, input_kwargs={"Surface": principled_bsdf}
    )

    return principled_bsdf


class BasicBSDF:
    shader = shader_basic_bsdf

    def apply(obj, selection=None, **kwargs):
        surface.add_material(obj, shader_basic_bsdf, reuse=False)

    def generate(self, hsv=None):
        return surface.shaderfunc_to_material(shader_basic_bsdf, hsv=hsv)

    __call__ = generate
