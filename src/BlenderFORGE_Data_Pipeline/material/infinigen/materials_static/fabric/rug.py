# Copyright (C) 2023, Princeton University.
# This source code is licensed under the BSD 3-Clause license found in the LICENSE file in the root directory of this source tree.

# Authors: Lingjie Mei

from infinigen.core import surface
from infinigen.core.nodes import Nodes, NodeWrangler
from infinigen.core.util.color import hsv2rgba


def shader_rug(nw: NodeWrangler, strength=0.01, **kwargs):
    coord = nw.new_node(
        Nodes.Mapping, [nw.new_node(Nodes.TextureCoord).outputs["Object"]]
    )
    vec = nw.new_node(
        Nodes.MixRGB,
        [0.8812414932363759, nw.new_node(Nodes.NoiseTexture, [coord]), coord],
    )
    height = 0, 0, 0, 1
    base_scale = 422.0496892927538
    for scale, thresh in zip([1, 0.75, 0.5], [1, 0.5, 0.33]):
        voronoi = nw.new_node(
            Nodes.VoronoiTexture, [vec], input_kwargs={"Scale": scale * base_scale}
        ).outputs[0]
        height = nw.new_node(
            Nodes.MixRGB, [nw.math("GREATER_THAN", voronoi, thresh), voronoi, height]
        )

    displacement = nw.new_node(
        Nodes.Displacement, input_kwargs={"Scale": strength, "Height": height}
    )

    base_hue = 0.8838751542487009
    base_value = 0.348374801112586
    if 0.31205824641687296 < 0.2:
        base_saturation = 0.03067786244830439
        front_color = hsv2rgba(base_hue, base_saturation, base_value)
        back_color = hsv2rgba(
            base_hue + 0.009988407189106608,
            base_saturation * 1.0266177519836601,
            base_value * 0.9166934100351459,
        )
    else:
        base_saturation = 0.35041046396181624
        front_color = hsv2rgba(base_hue, base_saturation, base_value)
        back_color = hsv2rgba(
            base_hue + 0.004511087109226248,
            base_saturation * 1.0973642960410257,
            base_value * 0.9803633644425087,
        )
    color = nw.new_node(
        Nodes.MixRGB,
        [
            nw.build_float_curve(
                nw.musgrave(40.35545015725905), [(0, 1), (0.3316177137221342, 0), (1, 0)]
            ),
            front_color,
            back_color,
        ],
    )
    roughness = nw.build_float_curve(
        nw.musgrave(25.64003882152484), [(0.5, 0.9), (1, 0.8)]
    )
    principled_bsdf = nw.new_node(
        Nodes.PrincipledBSDF, input_kwargs={"Base Color": color, "Roughness": roughness}
    )
    nw.new_node(
        Nodes.MaterialOutput,
        input_kwargs={"Surface": principled_bsdf, "Displacement": displacement},
    )


class Rug:
    shader = shader_rug

    def generate(self):
        strength = 0.018340288477175625
        return surface.shaderfunc_to_material(shader_rug, strength=strength)

    __call__ = generate
