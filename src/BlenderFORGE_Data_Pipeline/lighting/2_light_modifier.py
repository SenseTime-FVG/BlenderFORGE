#!/usr/bin/env python3
"""
Light Modifier - Module 2
Infinigen Lighting Dataset Generation Pipeline

Purpose:
- Modify light properties (energy and color) to create GOAL state variations
- Support multiple modification strategies (random_range, temperature, etc.)
- Validate modified values are physically plausible
- Return the GOAL values for the generator to apply after rendering START

Called by 6_generate.py inside Blender.
"""

import random
import numpy as np
from typing import Dict, List, Tuple, Optional


class LightModifier:
    """Modify light properties for dataset generation"""

    def __init__(self, config: Optional[Dict] = None):
        """
        Initialize light modifier

        Args:
            config: Configuration dict with:
                - modify_energy: Whether to modify energy (default: True)
                - modify_color: Whether to modify color (default: True)
                - energy_strategy: 'random_range' (default)
                - energy_change_ratio_range: [min, max] ratio (default: [2.0, 4.0])
                - energy_bidirectional: Allow dimming (default: True)
                - energy_absolute_min: Min energy value (default: 0.1)
                - energy_absolute_max: Max energy value (default: 10000.0)
                - color_strategy: 'direct_rgb' (default)
                - color_change_per_channel: Max change per channel (default: 0.3)
                - modify_all_lights: Modify all lights vs random selection (default: True)
        """
        self.config = config or {}

        self.modify_energy = self.config.get('modify_energy', True)
        self.modify_color = self.config.get('modify_color', True)
        self.modify_all_lights = self.config.get('modify_all_lights', True)

        self.energy_strategy = self.config.get('energy_strategy', 'random_range')
        self.energy_ratio_range = self.config.get('energy_change_ratio_range', [2.0, 4.0])
        self.energy_bidirectional = self.config.get('energy_bidirectional', True)
        self.energy_min = self.config.get('energy_absolute_min', 0.1)
        self.energy_max = self.config.get('energy_absolute_max', 10000.0)

        self.color_strategy = self.config.get('color_strategy', 'direct_rgb')
        self.color_change_max = self.config.get('color_change_per_channel', 0.3)

        self.min_color_sum = 0.05  # Prevent pure black

    def modify_lights(
        self,
        light_objects: List[Dict]
    ) -> List[Dict]:
        """Sample GOAL values without changing the scene or consuming extra RNG draws."""
        modifications = []

        if self.modify_all_lights:
            max_to_modify = self.config.get('max_lights_to_modify', len(light_objects))
            num_to_modify = min(max_to_modify, len(light_objects))

            lights_to_modify = set(random.sample(range(len(light_objects)), num_to_modify))
        else:
            # Random selection (50% chance per light, but respect max limit)
            max_to_modify = self.config.get('max_lights_to_modify', len(light_objects))

            candidates = [i for i in range(len(light_objects)) if random.random() < 0.5]

            if len(candidates) > max_to_modify:
                lights_to_modify = set(random.sample(candidates, max_to_modify))
            else:
                lights_to_modify = set(candidates)

            # Ensure at least 1 light is modified (if possible)
            if not lights_to_modify and light_objects:
                lights_to_modify = {random.randint(0, len(light_objects) - 1)}

        print(f"ℹ️  Will modify {len(lights_to_modify)} out of {len(light_objects)} lights")

        for i, light in enumerate(light_objects):
            light_name = light['name']
            original_energy = light['energy']
            original_color = tuple(light['color'])

            should_modify = i in lights_to_modify

            if not should_modify:
                modifications.append({
                    'light_name': light_name,
                    'new_energy': original_energy,
                    'new_color': original_color,
                    'modified': False
                })
                continue

            if self.modify_energy:
                new_energy = self.generate_energy_variation(
                    original_energy,
                    strategy=self.energy_strategy
                )
            else:
                new_energy = original_energy

            if self.modify_color:
                new_color = self.generate_color_variation(
                    original_color,
                    strategy=self.color_strategy
                )
            else:
                new_color = original_color

            is_valid, error_msg = self.validate_light_properties(new_energy, new_color)
            if not is_valid:
                print(f"WARNING: Invalid modification for {light_name}: {error_msg}")
                print(f"  Keeping original values")
                new_energy = original_energy
                new_color = original_color

            modifications.append({
                'light_name': light_name,
                'new_energy': new_energy,
                'new_color': new_color,
                'modified': True
            })

        return modifications

    def generate_energy_variation(
        self,
        current_energy: float,
        strategy: str = 'random_range'
    ) -> float:
        """
        Generate new energy value

        Args:
            current_energy: Current energy value
            strategy: Modification strategy (default: 'random_range')

        Returns:
            New energy value

        Strategy 'random_range':
            - Defines ratio = new_energy / old_energy
            - If bidirectional=True: ratio in [min, max] OR [1/max, 1/min]
              Example: [2.0, 4.0] means 2-4x brighter OR 2-4x dimmer
            - If bidirectional=False: ratio only in [min, max]
              Example: [2.0, 4.0] means always 2-4x brighter
        """
        if strategy == 'random_range':
            min_ratio, max_ratio = self.energy_ratio_range

            if self.energy_bidirectional and random.random() < 0.5:
                # Dimming: use inverse ratio
                # If ratio_range=[2, 4], this gives [1/4, 1/2] = [0.25, 0.5]
                ratio = 1.0 / random.uniform(min_ratio, max_ratio)
            else:
                ratio = random.uniform(min_ratio, max_ratio)

            new_energy = current_energy * ratio

            new_energy = np.clip(new_energy, self.energy_min, self.energy_max)

            return float(new_energy)

        else:
            raise ValueError(f"Unknown energy modification strategy: {strategy}")

    def generate_color_variation(
        self,
        current_color: Tuple[float, float, float],
        strategy: str = 'direct_rgb'
    ) -> Tuple[float, float, float]:
        """
        Generate new color value

        Args:
            current_color: Current RGB color (R, G, B) in [0, 1]
            strategy: Modification strategy (default: 'direct_rgb')

        Returns:
            New RGB color tuple

        Strategy 'direct_rgb':
            - Directly modify RGB channels independently
            - Each channel: new = old ± random_change
            - random_change ~ Uniform(-max_change, +max_change)
            - Clamped to [0, 1]

        Strategy 'dramatic_shift':
            - Create strong color temperature shifts
            - Presets: warm (red/orange), cool (blue/cyan), magenta, green, etc.
            - More visually striking changes
        """
        if strategy == 'direct_rgb':
            new_color = []

            for channel in current_color:
                delta = random.uniform(-self.color_change_max, self.color_change_max)

                new_channel = np.clip(channel + delta, 0.0, 1.0)
                new_color.append(new_channel)

            return tuple(new_color)

        elif strategy == 'dramatic_shift':
            color_presets = [
                (1.0, 0.3, 0.1),   # Warm orange/red
                (1.0, 0.5, 0.2),   # Orange
                (1.0, 0.7, 0.3),   # Warm yellow-orange
                (0.2, 0.5, 1.0),   # Cool blue
                (0.3, 0.7, 1.0),   # Sky blue
                (0.1, 0.3, 1.0),   # Deep blue
                (1.0, 0.2, 0.8),   # Magenta
                (0.8, 0.2, 1.0),   # Purple
                (0.3, 1.0, 0.5),   # Green-cyan
                (1.0, 0.9, 0.6),   # Warm white
                (0.6, 0.8, 1.0),   # Cool white
            ]

            target_color = random.choice(color_presets)

            # Blend 60%-100% of the selected preset with the original color.
            blend_factor = random.uniform(0.6, 1.0)
            new_color = tuple(
                blend_factor * target_color[i] + (1 - blend_factor) * current_color[i]
                for i in range(3)
            )

            return new_color

        elif strategy == 'pure_colors':
            pure_color_presets = [
                (1.0, 0.0, 0.0),   # Pure RED
                (0.0, 1.0, 0.0),   # Pure GREEN
                (0.0, 0.0, 1.0),   # Pure BLUE

                (1.0, 1.0, 0.0),   # Pure YELLOW (R+G)
                (0.0, 1.0, 1.0),   # Pure CYAN (G+B)
                (1.0, 0.0, 1.0),   # Pure MAGENTA (R+B)

                (1.0, 0.5, 0.0),   # ORANGE
                (0.5, 0.0, 1.0),   # PURPLE
                (1.0, 0.0, 0.5),   # PINK-RED
                (0.0, 1.0, 0.5),   # SPRING GREEN
                (0.5, 1.0, 0.0),   # LIME GREEN
                (0.0, 0.5, 1.0),   # SKY BLUE

                (1.0, 0.2, 0.0),   # HOT RED-ORANGE (fire)
                (0.2, 0.5, 1.0),   # COLD BLUE (ice)
                (1.0, 0.3, 0.9),   # HOT MAGENTA
            ]

            new_color = random.choice(pure_color_presets)

            # Optional: Add slight variation (±5%) to avoid exact duplicates
            if random.random() < 0.3:  # 30% chance to add variation
                variation = [random.uniform(-0.05, 0.05) for _ in range(3)]
                new_color = tuple(
                    np.clip(new_color[i] + variation[i], 0.0, 1.0)
                    for i in range(3)
                )

            return new_color

        else:
            raise ValueError(f"Unknown color modification strategy: {strategy}")

    def validate_light_properties(
        self,
        energy: float,
        color: Tuple[float, float, float]
    ) -> Tuple[bool, str]:
        """
        Ensure modified values are physically plausible

        Args:
            energy: Energy value to validate
            color: RGB color tuple to validate

        Returns:
            (is_valid, error_message)

        Checks:
            - Energy > 0 and within [min, max] bounds
            - Color components all in [0, 1]
            - Color is not pure black (sum > threshold)
        """
        if energy < self.energy_min:
            return False, f"Energy {energy} below minimum {self.energy_min}"

        if energy > self.energy_max:
            return False, f"Energy {energy} above maximum {self.energy_max}"

        for i, channel in enumerate(color):
            if channel < 0.0 or channel > 1.0:
                return False, f"Color channel {i} ({channel}) out of range [0, 1]"

        color_sum = sum(color)
        if color_sum < self.min_color_sum:
            return False, f"Color too dark (sum={color_sum:.3f} < {self.min_color_sum})"

        return True, ""
