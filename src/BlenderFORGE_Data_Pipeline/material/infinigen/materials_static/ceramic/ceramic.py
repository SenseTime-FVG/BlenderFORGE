# Copyright (C) 2023, Princeton University.
# This source code is licensed under the BSD 3-Clause license found in the LICENSE file in the root directory of this source tree.

# Authors: Lingjie Mei

from infinigen.assets.materials.utils import common
from infinigen.core import surface
from infinigen.core.nodes.node_info import Nodes
from infinigen.core.nodes.node_wrangler import NodeWrangler
from infinigen.core.util.color import hsv2rgba


def shader_ceramic(
    nw: NodeWrangler, clear=False, roughness_min=0, roughness_max=0.8, **kwargs
):
    if 0.8102172359965896 < 0.8 and not clear:
        color = hsv2rgba(0.9021659504395827, 0.2620295138638665, 0.49753370012333453)
    else:
        color = hsv2rgba(0, 0, 0.5593691885218914)

    roughness = nw.build_float_curve(
        nw.musgrave(32.131402003272136), [(0, roughness_min), (1, roughness_max)]
    )
    clearcoat_roughness = nw.build_float_curve(
        nw.musgrave(27.743363698485478), [(0, roughness_min), (1, roughness_max)]
    )

    principled_bsdf = nw.new_node(
        Nodes.PrincipledBSDF,
        input_kwargs={
            "Roughness": roughness,
            "Coat Weight": 1,
            "Coat Roughness": clearcoat_roughness,
            "Specular IOR Level": 1,
            "Base Color": color,
            "Subsurface Weight": 0.023021036242050975,
            "Subsurface Radius": (0.02, 0.02, 0.02),
        },
    )

    displacement = nw.new_node(
        "ShaderNodeDisplacement",
        input_kwargs={
            "Height": nw.scalar_multiply(
                0.0020112825687687392,
                nw.new_node(
                    Nodes.NoiseTexture, input_kwargs={"Scale": 30.543956928529983}
                ),
            ),
            "Midlevel": 0.0000,
        },
    )

    nw.new_node(
        Nodes.MaterialOutput,
        input_kwargs={"Surface": principled_bsdf, "Displacement": displacement},
    )


class Ceramic:
    shader = shader_ceramic

    def generate(self):
        return surface.shaderfunc_to_material(shader_ceramic)

    @staticmethod
    def apply(obj, selection=None, clear=False, **kwargs):
        common.apply(obj, shader_ceramic, selection, clear, **kwargs)

    __call__ = generate
