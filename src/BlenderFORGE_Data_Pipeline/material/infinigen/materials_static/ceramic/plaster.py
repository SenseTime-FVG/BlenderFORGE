# Copyright (C) 2023, Princeton University.
# This source code is licensed under the BSD 3-Clause license found in the LICENSE file in the root directory of this source tree.

# Authors: Lingjie Mei

from typing import Iterable


from infinigen.assets.materials.utils import common
from infinigen.assets.utils.uv import unwrap_normal
from infinigen.core import surface
from infinigen.core.nodes.node_info import Nodes
from infinigen.core.nodes.node_utils import build_color_ramp
from infinigen.core.nodes.node_wrangler import NodeWrangler
from infinigen.core.util.color import hsv2rgba


def shader_plaster(nw: NodeWrangler, plaster_colored, **kwargs):
    hue = 0.32520436274739006
    front_value = 0.9141299866804113
    back_value = front_value * 0.6764268366009563
    if plaster_colored:
        front_color = hsv2rgba(hue, 0.4135021481241344, front_value)
        back_color = hsv2rgba(hue + -0.010406085712885926, 0.34772318572304406, back_value)
    else:
        front_color = hsv2rgba(hue, 0, front_value)
        back_color = hsv2rgba(hue + -0.08391083628949292, 0, back_value)
    uv_map = nw.new_node(Nodes.UVMap)
    musgrave = nw.new_node(
        Nodes.MusgraveTexture,
        [uv_map],
        input_kwargs={"Detail": 18.725666969281786, "Dimension": 0},
    )
    noise = nw.new_node(
        Nodes.NoiseTexture,
        [uv_map],
        input_kwargs={"Detail": 21.33028353888467, "Distortion": 7.636088505190796},
    )
    noise = build_color_ramp(
        nw, noise, [0, 0.49350805005802867], [(0, 0, 0, 1), (1, 1, 1, 1)]
    )
    difference = nw.new_node(
        Nodes.MixRGB, [musgrave, noise], attrs={"blend_type": "DIFFERENCE"}
    )
    base_color = build_color_ramp(
        nw, difference, [0.280317946927987, 1], [back_color, front_color]
    )

    displacement = nw.new_node(
        Nodes.Displacement,
        input_kwargs={
            "Scale": 0.00011272852286872071,
            "Height": nw.new_node(
                Nodes.MusgraveTexture, input_kwargs={"Scale": 1814.466863291336}
            ),
        },
    )

    principled_bsdf = nw.new_node(
        Nodes.PrincipledBSDF,
        input_kwargs={
            "Base Color": base_color,
            "Roughness": 0.7551267246090552,
        },
    )

    nw.new_node(
        Nodes.MaterialOutput,
        input_kwargs={"Surface": principled_bsdf, "Displacement": displacement},
    )


class Plaster:
    shader = shader_plaster

    def apply(self, obj, selection=None, plaster_colored=None, **kwargs):
        if plaster_colored is None:
            plaster_colored = 0.7065614098668896 < 0.4
        for o in obj if isinstance(obj, Iterable) else [obj]:
            unwrap_normal(o, selection)
        common.apply(
            obj, shader_plaster, selection, plaster_colored=plaster_colored, **kwargs
        )

    def generate(self, plaster_colored=None, **kwargs):
        if plaster_colored is None:
            plaster_colored = 0.5474409113284238 < 0.4
        return surface.shaderfunc_to_material(shader_plaster, plaster_colored, **kwargs)

    # def apply(self, obj, selection=None, plaster_colored=None):
    #     return surface.add_material(obj, shader_plaster, selection, plaster_colored=plaster_colored)

    __call__ = generate
