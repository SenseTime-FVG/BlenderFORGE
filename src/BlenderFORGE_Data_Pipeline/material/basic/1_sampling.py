
import random


from typing import Dict, List, Tuple, Any

class BSDFModifier:
    """Plan material modifications for Principled BSDF dataset generation"""

    def __init__(self, config: Dict):
        self.config = config
        self.parameters = config.get('material_modification', {}).get('parameters', {})

    def sample_parameters(self) -> Dict[str, Any]:
        """Sample a full set of parameters for the start state."""
        params = {}
        for param_name, param_info in self.parameters.items():
            param_type = param_info.get('type', 'float')
            min_val = param_info.get('min')
            max_val = param_info.get('max')

            if param_type == 'float':
                params[param_name] = random.uniform(min_val, max_val)
            elif param_type == 'color':
                # Sample RGB, keep Alpha at 1.0
                r = random.uniform(min_val[0], max_val[0])
                g = random.uniform(min_val[1], max_val[1])
                b = random.uniform(min_val[2], max_val[2])
                params[param_name] = [r, g, b, 1.0]
        return params

    def mutate_parameters(self, start_params: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
        """Mutate 1 to N parameters for the goal state."""
        mod_config = self.config.get('material_modification', {})
        mod_type = mod_config.get('modification_type', 'single_param')

        if mod_type == 'single_param':
            num_to_mutate = 1
        else:
            multi_config = mod_config.get('multi_param', {})
            min_params = multi_config.get('min_params', 2)
            max_params = multi_config.get('max_params', 3)
            num_to_mutate = random.randint(min_params, max_params)

        available_params = list(self.parameters.keys())
        params_to_mutate = random.sample(available_params, min(num_to_mutate, len(available_params)))

        goal_params = start_params.copy()

        for param_name in params_to_mutate:
            param_info = self.parameters[param_name]
            param_type = param_info.get('type', 'float')
            min_val = param_info.get('min')
            max_val = param_info.get('max')

            min_change_pct = mod_config.get('min_change_percentage', 0.45)

            if param_type == 'float':
                current_val = start_params[param_name]
                range_span = max_val - min_val
                min_change = range_span * min_change_pct

                new_val = current_val
                attempts = 0
                while abs(new_val - current_val) < min_change and attempts < 100:
                    new_val = random.uniform(min_val, max_val)
                    attempts += 1
                goal_params[param_name] = new_val

            elif param_type == 'color':
                current_val = start_params[param_name]
                new_val = current_val.copy()
                attempts = 0
                # For color, we want the sum of absolute differences across RGB to be significant
                # Max possible difference is 3.0 (1.0 for each channel)
                min_color_change = 3.0 * min_change_pct
                while sum(abs(n - c) for n, c in zip(new_val[:3], current_val[:3])) < min_color_change and attempts < 100:
                    new_val[0] = random.uniform(min_val[0], max_val[0])
                    new_val[1] = random.uniform(min_val[1], max_val[1])
                    new_val[2] = random.uniform(min_val[2], max_val[2])
                    attempts += 1
                goal_params[param_name] = new_val

        return goal_params, params_to_mutate
