"""
Module 2: Material Modifier
Handles material shader selection and parameter modification planning.

This module plans START → GOAL material parameter changes by:
- Selecting Infinigen shaders from the catalog
- Generating START state parameters
- Modifying parameters to create GOAL state
- Validating parameter bounds and change magnitude

NO silent failures - all errors must propagate.
"""

import json

import random

from pathlib import Path

from typing import Dict, List, Optional, Any

import colorsys

class MaterialModifier:
    """Plan material modifications for dataset generation"""

    BOOL_PARAMS = {
        'vertical', 'clear', 'is_window', 'enable_scatter', 'is_rock',
        'layered_mountain', 'snowy', 'spherical', 'tail', 'wet',
        'plaster_colored', 'snake_crack'
    }

    HSV3_PARAMS = {
        'hsv', 'color_hsv', 'base_color_hsv', 'color_1_hsv', 'color_2_hsv'
    }

    INT_PARAMS = {
        'seed', 'random_seed', 'selection'
    }

    RANGE2_PARAMS = {
        'wet_part', 'preset_zrange'
    }

    ENUM_PARAM_OPTIONS = {
        'kind': ['duck', 'goose', 'swan', 'parrot'],
        'coord': ['X', 'Y', 'Z'],
        '_map': ['UV', 'Object', 'Generated'],
        'alternating': [True, False],
    }

    CONTEXTUAL_PARAMS = {
        'obj', 'base_shader', 'original_bsdf', 'original_displacement', 'geo_params'
    }

    PARAMETER_BOUNDS = {
        'color': {
            'min': [0.0, 0.0, 0.0, 1.0],
            'max': [1.0, 1.0, 1.0, 1.0]
        },
        'base_color': {
            'min': [0.0, 0.0, 0.0, 1.0],
            'max': [1.0, 1.0, 1.0, 1.0]
        },
        'roughness': {'min': 0.0, 'max': 1.0},
        'roughness_min': {'min': 0.0, 'max': 1.0},
        'roughness_max': {'min': 0.0, 'max': 1.0},
        'shader_roughness': {'min': 0.0, 'max': 1.0},
        'metallic': {'min': 0.0, 'max': 1.0},
        'w': {'min': 0.0, 'max': 1.0},
        'ior': {'min': 1.0, 'max': 3.0},
        'scale': {'min': 0.1, 'max': 10.0},
        'hscale': {'min': 0.5, 'max': 2.0},
        'vscale': {'min': 0.5, 'max': 2.0},
        'vertical_scale': {'min': 0.5, 'max': 2.0},
        'specular': {'min': 0.0, 'max': 1.0},
        'height': {'min': 0.01, 'max': 0.3},  # Brick/tile height in meters
        'density': {'min': 0.1, 'max': 2.0},
        'strength': {'min': 0.0, 'max': 2.0},
        'anisotropy': {'min': 0.0, 'max': 1.0},
        'crack_amount': {'min': 0.0, 'max': 1.0},
        'crack_scale': {'min': 0.5, 'max': 5.0},
        'weave_scale': {'min': 0.5, 'max': 5.0},
        'rotation': {'min': 0.0, 'max': 6.28318},  # 0 to 2*PI radians
        'rand': {'min': 0.0, 'max': 1.0},  # Random seed/noise parameter
        'color_scale': {'min': 0.0, 'max': 2.0},
        'hue_diff': {'min': 0.0, 'max': 1.0},
        'max_sat': {'min': 0.0, 'max': 1.0},  # Maximum saturation
        'max_val': {'min': 0.0, 'max': 1.0},  # Maximum value/brightness
        'n': {'min': 1, 'max': 20},  # Tile repetition count (integer)
        'num_layers': {'min': 1, 'max': 10},
        'offset': {'min': -1.0, 'max': 1.0},
        'prob_arranged_layers': {'min': 0.0, 'max': 1.0},

        # Fabric-specific parameters (with underscore prefix)
        '_pattern_mixer': {'min': 0.0, 'max': 1.0},
        '_pattern_density': {'min': 0.05, 'max': 0.5},
        '_brick_knit': {'min': 0.0, 'max': 1.0},
        '_knit_resolution': {'min': 1.0, 'max': 10.0},
        '_brick_resolution': {'min': 10, 'max': 100},
        '_crease_resolution': {'min': 50, 'max': 500},
        '_smoothness': {'min': 0.0, 'max': 1.0},
        '_color_shader_frac': {'min': 0.0, 'max': 0.1},
        '_roughness': {'min': 0.0, 'max': 1.0},
        '_thread_density_x': {'min': 50, 'max': 500},
        '_relative_density_y': {'min': 0.5, 'max': 2.0},
        '_displacement_scale': {'min': 0.001, 'max': 0.02},
        '_hue': {'min': 0.0, 'max': 1.0},
        '_saturation': {'min': 0.0, 'max': 1.0},
        '_line_density': {'min': 5, 'max': 30},

        # Edge wear parameters
        '_edge_base_color_hue': {'min': 0.0, 'max': 1.0},
        '_edge_base_color_whiteness': {'min': 0.0, 'max': 1.0},
        '_scratch_density': {'min': 1.0, 'max': 20.0},
        '_scratch_mask_randomness': {'min': 0.0, 'max': 1.0},
        '_scratch_opacity': {'min': 0.0, 'max': 1.0},
        '_scratch_radius': {'min': 0.001, 'max': 0.05},
        '_worn_off_mask_randomness': {'min': 0.0, 'max': 5.0},
        '_worn_off_opacity': {'min': 0.0, 'max': 1.0},
        '_worn_off_radius': {'min': 0.005, 'max': 0.05},
    }

    # Minimum change thresholds to ensure visual difference
    MIN_CHANGE_THRESHOLDS = {
        'color': 0.3,          # RGB distance
        'base_color': 0.3,     # RGB distance
        'roughness': 0.2,
        'roughness_min': 0.2,
        'roughness_max': 0.2,
        'shader_roughness': 0.2,
        'metallic': 0.3,
        'w': 0.2,              # Weight parameter
        'ior': 0.2,            # Refractive index
        'scale': 0.5,
        'hscale': 0.3,
        'vscale': 0.3,
        'vertical_scale': 0.3,
        'specular': 0.2,
        'height': 0.05,        # Height parameter (meters)
        'density': 0.3,
        'strength': 0.3,
        'anisotropy': 0.2,
        'crack_amount': 0.2,
        'crack_scale': 0.5,
        'weave_scale': 0.5,
        'rotation': 0.785,     # ~45 degrees (PI/4)
        'rand': 0.2,
        'color_scale': 0.3,
        'hue_diff': 0.2,
        'max_sat': 0.2,
        'max_val': 0.2,
        'n': 2,                # Tile count (at least 2 tiles difference)
        'num_layers': 1,       # Layer count (at least 1 layer difference)
        'offset': 0.3,
        'prob_arranged_layers': 0.2,

        # Fabric-specific thresholds
        '_pattern_mixer': 0.2,
        '_pattern_density': 0.1,
        '_brick_knit': 0.2,
        '_knit_resolution': 2.0,
        '_brick_resolution': 20,
        '_crease_resolution': 100,
        '_smoothness': 0.2,
        '_color_shader_frac': 0.02,
        '_roughness': 0.2,
        '_thread_density_x': 100,
        '_relative_density_y': 0.3,
        '_displacement_scale': 0.005,
        '_hue': 0.2,
        '_saturation': 0.2,
        '_line_density': 5,

        # Edge wear thresholds
        '_edge_base_color_hue': 0.2,
        '_edge_base_color_whiteness': 0.2,
        '_scratch_density': 3.0,
        '_scratch_mask_randomness': 0.2,
        '_scratch_opacity': 0.2,
        '_scratch_radius': 0.01,
        '_worn_off_mask_randomness': 1.0,
        '_worn_off_opacity': 0.2,
        '_worn_off_radius': 0.01,
    }

    def __init__(self, material_catalog_path: str, config: Optional[Dict] = None):
        """
        Initialize Material Modifier

        Args:
            material_catalog_path: Path to material_catalog.json
            config: Optional configuration dict

        Raises:
            FileNotFoundError: If catalog file doesn't exist
            ValueError: If catalog is invalid JSON
        """
        catalog_path = Path(material_catalog_path)
        assert catalog_path.exists(), f"Material catalog not found: {material_catalog_path}"

        with open(catalog_path, 'r') as f:
            catalog_data = json.load(f)

        self.catalog = catalog_data

        self.catalog_params = set()
        self.param_defaults = {}
        for top_data in self.catalog.values():
            for module_data in top_data.values():
                for shader_data in module_data.get('shaders', []):
                    defaults = shader_data.get('defaults', {})
                    for param_name in shader_data.get('params', []):
                        self.catalog_params.add(param_name)
                        if param_name not in self.param_defaults:
                            self.param_defaults[param_name] = defaults.get(param_name)

        self.config = config or {}
        self.random_seed = self.config.get('random_seed', None)
        if self.random_seed is not None:
            random.seed(self.random_seed)

    def list_all_shaders(self, modifiable_only: bool = False) -> List[Dict]:
        """
        List all available shaders with metadata

        Args:
            modifiable_only: If True, only return shaders with adjustable parameters

        Returns:
            List of shader info dicts with keys:
                - top_category: Top-level category (e.g., 'root', 'wood', 'ceramic')
                - module_name: Sub-category name (e.g., 'hardwood_floor')
                - module_path: Import path
                - shader_name: Function name
                - params: List of parameter names
                - defaults: Default values
        """
        shaders = []
        for top_category, top_data in self.catalog.items():
            for module_name, module_data in top_data.items():
                for shader_data in module_data.get('shaders', []):
                    params = shader_data.get('params', [])

                    if modifiable_only:
                        modifiable_count = sum(1 for p in params
                                              if self._is_modifiable_param(p))
                        if modifiable_count == 0:
                            continue

                    shaders.append({
                        'top_category': top_category,
                        'module_name': module_name,
                        'module_path': module_data['import_path'],
                        'file_path': module_data['file_path'],
                        'shader_name': shader_data['name'],
                        'params': params,
                        'defaults': shader_data.get('defaults', {})
                    })
        return shaders


    def select_shader(self,
                      category: Optional[str] = None,
                      shader_name: Optional[str] = None,
                      modifiable_only: bool = True) -> Dict:
        """
        Select shader from catalog

        Args:
            category: Optional category filter - can be:
                     - Top-level category: 'root', 'wood', 'ceramic', etc.
                     - Sub-category: 'hardwood_floor', 'plywood', etc.
            shader_name: Optional specific shader name
            modifiable_only: If True, only select shaders with parameters (default: True)

        Returns:
            Shader info dict with keys:
                - top_category
                - module_name
                - module_path
                - shader_name
                - params
                - defaults

        Raises:
            ValueError: If no matching shader found or multiple matches
        """
        all_shaders = self.list_all_shaders(modifiable_only=modifiable_only)

        if category:
            # Try matching as top-level category first
            filtered = [s for s in all_shaders if s['top_category'] == category]

            # If no match, try as sub-category (module_name)
            if not filtered:
                filtered = [s for s in all_shaders if s['module_name'] == category]

            assert len(filtered) > 0, f"No shaders found for category: {category}"
            all_shaders = filtered

        if shader_name:
            all_shaders = [s for s in all_shaders if s['shader_name'] == shader_name]
            assert len(all_shaders) > 0, f"No shader found with name: {shader_name}"

        # If multiple matches, prefer shaders with adjustable parameters
        if len(all_shaders) > 1:
            parametric_shaders = [s for s in all_shaders if len(s['params']) > 0]
            if parametric_shaders:
                return random.choice(parametric_shaders)
            else:
                return random.choice(all_shaders)

        assert len(all_shaders) > 0, "No matching shaders found"
        return all_shaders[0]

    def generate_parameter_set(self,
                              shader_info: Dict,
                              strategy: str = 'random') -> Dict:
        """
        Generate parameter values for a shader

        Args:
            shader_info: Shader metadata from select_shader()
            strategy: 'random', 'preset', or 'default'

        Returns:
            Dict of parameter_name -> value

        Raises:
            ValueError: If strategy is unknown
        """
        params = shader_info['params']
        defaults = shader_info['defaults']

        if strategy == 'default':
            return {param_name: defaults.get(param_name) for param_name in params}

        elif strategy == 'random':
            param_values = {}
            for param_name in params:
                default_val = defaults.get(param_name)

                param_values[param_name] = self._generate_random_parameter_value(
                    param_name,
                    default_val
                )

            return param_values

        elif strategy == 'preset':
            return self._get_preset_parameters(shader_info)

        else:
            raise ValueError(f"Unknown strategy: {strategy}")

    def _get_preset_parameters(self, shader_info: Dict) -> Dict:
        """Get preset parameters for common material types"""
        top_category = shader_info.get('top_category', '')
        module_name = shader_info['module_name']
        shader_name = shader_info['shader_name']

        if top_category == 'wood' and shader_name == 'shader_wood':
            presets = [
                {'color': (0.75, 0.65, 0.45, 1.0), 'w': 0.3, 'vertical': False},  # Light oak
                {'color': (0.6, 0.4, 0.2, 1.0), 'w': 0.5, 'vertical': False},      # Medium brown
                {'color': (0.15, 0.08, 0.03, 1.0), 'w': 0.7, 'vertical': False},   # Dark walnut
                {'color': (0.6, 0.3, 0.2, 1.0), 'w': 0.4, 'vertical': True},       # Reddish vertical
            ]
            return random.choice(presets)

        return self.generate_parameter_set(shader_info, strategy='random')

    def modify_parameters(self,
                         start_params: Dict,
                         shader_info: Dict,
                         modification_type: str = 'single_param') -> Dict:
        """
        Modify parameters to create GOAL state

        Args:
            start_params: START state parameters
            shader_info: Shader metadata
            modification_type: 'single_param', 'multi_param', or 'preset_change'

        Returns:
            Dict with keys:
                - modified_params: New parameter values
                - changed_params: List of parameter names that changed
                - change_summary: Dict describing changes

        Raises:
            ValueError: If modification type is unknown or no valid modification found
        """
        params = shader_info['params']

        if modification_type == 'single_param':
            modifiable_params = self._get_modifiable_params(params, start_params)
            assert len(modifiable_params) > 0, f"No modifiable parameters found in {params}"

            param_to_modify = random.choice(modifiable_params)
            goal_params = dict(start_params)

            new_value = self._modify_single_parameter(
                param_to_modify,
                start_params[param_to_modify]
            )
            goal_params[param_to_modify] = new_value

            return {
                'modified_params': goal_params,
                'changed_params': [param_to_modify],
                'change_summary': {
                    'type': 'single_param',
                    'param': param_to_modify,
                    'start_value': start_params[param_to_modify],
                    'goal_value': new_value,
                    'magnitude': self._compute_change_magnitude(
                        param_to_modify,
                        start_params[param_to_modify],
                        new_value
                    )
                }
            }

        elif modification_type == 'multi_param':
            modifiable_params = self._get_modifiable_params(params, start_params)
            assert len(modifiable_params) >= 2, "Need at least 2 modifiable parameters for multi_param"

            num_to_modify = min(3, random.randint(2, len(modifiable_params)))
            params_to_modify = random.sample(modifiable_params, num_to_modify)

            goal_params = dict(start_params)
            changes = []

            for param_name in params_to_modify:
                new_value = self._modify_single_parameter(
                    param_name,
                    start_params[param_name]
                )
                goal_params[param_name] = new_value
                changes.append({
                    'param': param_name,
                    'start': start_params[param_name],
                    'goal': new_value
                })

            return {
                'modified_params': goal_params,
                'changed_params': params_to_modify,
                'change_summary': {
                    'type': 'multi_param',
                    'changes': changes
                }
            }

        elif modification_type == 'preset_change':
            goal_params = self._get_preset_parameters(shader_info)

            changed_params = [k for k in goal_params.keys()
                            if goal_params[k] != start_params.get(k)]

            return {
                'modified_params': goal_params,
                'changed_params': changed_params,
                'change_summary': {
                    'type': 'preset_change',
                    'num_changed': len(changed_params)
                }
            }

        else:
            raise ValueError(f"Unknown modification type: {modification_type}")

    def _get_modifiable_params(self, all_params: List[str], param_values: Dict) -> List[str]:
        """Get list of parameters that can be modified"""
        modifiable = []
        for param in all_params:
            if self._is_modifiable_param(param):
                modifiable.append(param)
        return modifiable

    def _is_modifiable_param(self, param_name: str) -> bool:
        """Check whether a parameter is considered modifiable."""
        return (
            param_name in self.PARAMETER_BOUNDS or
            param_name in self.catalog_params or
            param_name in ['color', 'base_color', '_color', 'vertical', 'clear']
        )

    def _generate_random_parameter_value(self, param_name: str, default_val: Any) -> Any:
        """Generate a random but plausible value for a parameter."""
        if param_name == 'color' or param_name == 'base_color':
            h = random.random()
            s = random.uniform(0.3, 0.9)
            v = random.uniform(0.3, 0.9)
            r, g, b = colorsys.hsv_to_rgb(h, s, v)
            return (r, g, b, 1.0)

        if param_name == '_color':
            if isinstance(default_val, list) and len(default_val) == 3:
                if all(isinstance(x, (int, float)) and x <= 1.0 for x in default_val):
                    return [random.uniform(0.1, 0.9) for _ in range(3)]
                return [
                    random.uniform(0, 10),
                    random.uniform(5, 15),
                    random.uniform(5, 15)
                ]
            return [random.uniform(0.1, 0.9) for _ in range(3)]

        if param_name in self.BOOL_PARAMS:
            return random.choice([True, False])

        if param_name in self.HSV3_PARAMS:
            return [
                random.uniform(0.0, 1.0),
                random.uniform(0.2, 1.0),
                random.uniform(0.2, 1.0)
            ]

        if param_name in self.INT_PARAMS:
            return random.randint(0, 9999)

        if param_name in self.ENUM_PARAM_OPTIONS:
            return random.choice(self.ENUM_PARAM_OPTIONS[param_name])

        if param_name in self.RANGE2_PARAMS:
            lo = random.uniform(0.0, 0.6)
            hi = random.uniform(lo + 0.05, min(1.0, lo + 0.4))
            return [lo, hi]

        if param_name in self.CONTEXTUAL_PARAMS:
            return {'auto': param_name}

        if param_name in self.PARAMETER_BOUNDS:
            bounds = self.PARAMETER_BOUNDS[param_name]
            min_val = bounds['min']
            max_val = bounds['max']
            if isinstance(min_val, int) and isinstance(max_val, int):
                return random.randint(min_val, max_val)
            return random.uniform(min_val, max_val)

        # Fallback by default value type
        if isinstance(default_val, bool):
            return random.choice([True, False])
        if isinstance(default_val, int):
            return random.randint(max(0, default_val - 10), default_val + 10)
        if isinstance(default_val, float):
            return max(0.0, default_val + random.uniform(-0.5, 0.5))
        if isinstance(default_val, str):
            return f"{default_val}_alt"
        if isinstance(default_val, list):
            out = []
            for value in default_val:
                if isinstance(value, bool):
                    out.append(not value)
                elif isinstance(value, int):
                    out.append(value + random.randint(-3, 3))
                elif isinstance(value, float):
                    out.append(value + random.uniform(-0.2, 0.2))
                else:
                    out.append(value)
            return out

        # None/unknown fallback
        if 'seed' in param_name:
            return random.randint(0, 9999)
        if 'color' in param_name or 'hsv' in param_name:
            return [
                random.uniform(0.0, 1.0),
                random.uniform(0.2, 1.0),
                random.uniform(0.2, 1.0)
            ]
        if param_name.startswith('is_') or param_name.startswith('enable_'):
            return random.choice([True, False])
        if 'scale' in param_name or 'roughness' in param_name:
            return random.uniform(0.1, 2.0)

        return random.uniform(0.0, 1.0)

    def _modify_single_parameter(self, param_name: str, current_value: Any) -> Any:
        """
        Modify a single parameter value

        Ensures change magnitude exceeds minimum threshold.
        """
        if param_name == 'color' or param_name == 'base_color':
            r, g, b, a = current_value

            # Convert to HSV for better control
            h, s, v = colorsys.rgb_to_hsv(r, g, b)

            h_shift = random.uniform(0.3, 0.7)
            new_h = (h + h_shift) % 1.0

            new_s = max(0.3, min(0.9, s + random.uniform(-0.2, 0.2)))
            new_v = max(0.3, min(0.9, v + random.uniform(-0.2, 0.2)))

            new_r, new_g, new_b = colorsys.hsv_to_rgb(new_h, new_s, new_v)
            return (new_r, new_g, new_b, a)

        elif param_name == '_color':
            # Special handling for _color parameter (list format)
            # The format can vary: [h, s, v] with different scales
            if isinstance(current_value, list) and len(current_value) == 3:
                if all(isinstance(x, (int, float)) and x <= 1.0 for x in current_value):
                    # Normalized RGB format [0-1, 0-1, 0-1]
                    new_values = []
                    for val in current_value:
                        direction = 1 if random.random() > 0.5 else -1
                        shift = random.uniform(0.3, 0.7)
                        new_val = val + direction * shift
                        new_val = max(0.1, min(0.9, new_val))
                        new_values.append(new_val)
                    return new_values
                else:
                    # Scaled format like [5, 10.0, 10.0]
                    return [
                        random.uniform(0, 10),   # Hue-like
                        random.uniform(5, 15),   # Saturation-like
                        random.uniform(5, 15)    # Value-like
                    ]
            return current_value

        elif param_name in self.HSV3_PARAMS:
            if isinstance(current_value, list) and len(current_value) == 3:
                hue_shift = random.uniform(0.25, 0.75)
                return [
                    (float(current_value[0]) + hue_shift) % 1.0,
                    max(0.2, min(1.0, float(current_value[1]) + random.uniform(-0.3, 0.3))),
                    max(0.2, min(1.0, float(current_value[2]) + random.uniform(-0.3, 0.3))),
                ]
            return self._generate_random_parameter_value(param_name, current_value)

        elif param_name == 'vertical':
            return not current_value

        elif param_name == 'clear':
            return not current_value

        elif param_name in self.BOOL_PARAMS:
            return not bool(current_value)

        elif param_name in self.ENUM_PARAM_OPTIONS:
            choices = self.ENUM_PARAM_OPTIONS[param_name]
            alternatives = [choice for choice in choices if choice != current_value]
            if alternatives:
                return random.choice(alternatives)
            return current_value

        elif param_name in self.RANGE2_PARAMS:
            if isinstance(current_value, list) and len(current_value) == 2:
                current_lo = float(current_value[0])
                current_hi = float(current_value[1])
                shift = random.uniform(0.1, 0.3)
                new_lo = max(0.0, min(1.0, current_lo + shift if random.random() > 0.5 else current_lo - shift))
                new_hi = max(new_lo + 0.05, min(1.0, current_hi + shift if random.random() > 0.5 else current_hi - shift))
                return [new_lo, new_hi]
            return self._generate_random_parameter_value(param_name, current_value)

        elif param_name in self.CONTEXTUAL_PARAMS:
            # Keep contextual placeholders JSON-safe and clearly changed
            if isinstance(current_value, dict):
                new_value = dict(current_value)
                new_value['variant'] = random.randint(1, 1000)
                return new_value
            return {'auto': param_name, 'variant': random.randint(1, 1000)}

        elif current_value is None:
            # Support parameters with null defaults by synthesizing a valid value
            return self._generate_random_parameter_value(
                param_name,
                self.param_defaults.get(param_name)
            )

        elif param_name in self.PARAMETER_BOUNDS:
            bounds = self.PARAMETER_BOUNDS[param_name]
            min_val = bounds['min']
            max_val = bounds['max']
            threshold = self.MIN_CHANGE_THRESHOLDS.get(param_name, 0.2)

            is_integer = isinstance(min_val, int) and isinstance(max_val, int)
            current_num = int(current_value) if is_integer else float(current_value)

            attempts = 0
            while attempts < 10:
                new_value = random.randint(min_val, max_val) if is_integer else random.uniform(min_val, max_val)
                if abs(new_value - current_num) >= threshold:
                    return new_value
                attempts += 1

            # Force a threshold-exceeding change
            direction = 1 if random.random() > 0.5 else -1
            delta = max(1, int(round(threshold * 1.5))) if is_integer else threshold * 1.5
            new_value = current_num + direction * delta
            new_value = max(min_val, min(max_val, new_value))
            if is_integer:
                new_value = int(new_value)
            return new_value

        elif isinstance(current_value, bool):
            return not current_value

        elif isinstance(current_value, int):
            delta = random.randint(1, 10)
            return current_value + delta if random.random() > 0.5 else current_value - delta

        elif isinstance(current_value, float):
            delta = random.uniform(0.2, 1.0)
            return current_value + delta if random.random() > 0.5 else current_value - delta

        elif isinstance(current_value, str):
            return f"{current_value}_alt"

        elif isinstance(current_value, list):
            if len(current_value) == 3 and all(isinstance(x, (int, float)) for x in current_value):
                return [
                    max(0.0, min(1.0, float(current_value[0]) + random.uniform(0.2, 0.6) * (1 if random.random() > 0.5 else -1))),
                    max(0.0, min(1.0, float(current_value[1]) + random.uniform(0.2, 0.6) * (1 if random.random() > 0.5 else -1))),
                    max(0.0, min(1.0, float(current_value[2]) + random.uniform(0.2, 0.6) * (1 if random.random() > 0.5 else -1))),
                ]
            return self._generate_random_parameter_value(param_name, current_value)

        else:
            return self._generate_random_parameter_value(param_name, current_value)


    def _compute_change_magnitude(self, param_name: str, start_val: Any, goal_val: Any) -> float:
        """Compute the sampled parameter change magnitude."""
        if param_name in ['color', 'base_color']:
            r1, g1, b1, _ = start_val
            r2, g2, b2, _ = goal_val
            return ((r2-r1)**2 + (g2-g1)**2 + (b2-b1)**2)**0.5
        elif isinstance(start_val, bool):
            return 1.0 if start_val != goal_val else 0.0
        elif isinstance(start_val, (int, float)):
            return abs(goal_val - start_val)
        return 0.0

    def plan_modification(self,
                         shader_category: Optional[str] = None,
                         shader_name: Optional[str] = None,
                         modification_type: str = 'single_param',
                         param_strategy: str = 'random') -> Dict:
        """
        Complete modification planning workflow

        Args:
            shader_category: Optional category filter
            shader_name: Optional specific shader
            modification_type: Type of modification to plan
            param_strategy: Parameter generation strategy

        Returns:
            Complete modification plan (modification_plan.json format)
        """
        # If shader_name is specified, allow non-modifiable shaders to be found
        # We'll validate parameters afterwards
        shader_info = self.select_shader(
            category=shader_category,
            shader_name=shader_name,
            modifiable_only=False if shader_name else True
        )

        start_params = self.generate_parameter_set(
            shader_info,
            strategy=param_strategy
        )

        modification_result = self.modify_parameters(
            start_params,
            shader_info,
            modification_type=modification_type
        )

        plan = {
            'shader': {
                'module_path': shader_info['module_path'],
                'shader_name': shader_info['shader_name'],
            },
            'start_params': start_params,
            'goal_params': modification_result['modified_params'],
        }

        return plan
