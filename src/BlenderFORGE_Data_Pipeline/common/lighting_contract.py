"""Lighting-specific scope, identity and edit checks for v1 samples."""
from common.contract import require, vector


def check_lighting_states(metadata, start, goal):
    names = metadata['editable']['object_names']
    require(names and len(names) == len(set(names)), 'Missing/duplicate light candidates')
    config = metadata['generator']['config']['light_modification']
    properties = [key for key in ('energy', 'color') if config['modify_'+key]]
    require(properties and metadata['editable']['properties'] == ['light.'+p for p in properties],
            'Editable light properties disagree with config')
    require(start['objects'].keys() == goal['objects'].keys(), 'Entity set changed')
    require(start['scene'] == goal['scene'] and start['materials'] == goal['materials'], 'Non-lighting scene/material edit')
    cameras = [v['camera_name'] for v in start['views']]
    require(cameras == [v['camera_name'] for v in goal['views']], 'Camera set/order changed')
    for state in (start, goal):
        objects = state['objects']
        require(set(names) == {name for name,obj in objects.items() if obj['editable']}, 'Editable scope mismatch')
        scope = set(names) | set(cameras)
        for name in tuple(scope):
            seen = {name}
            parent = objects[name]['parent_id']
            while parent is not None:
                require(parent not in seen, 'Parent cycle')
                seen.add(parent)
                scope.add(parent)
                parent = objects[parent]['parent_id']
        require(set(objects) == scope, 'Unrelated objects in lighting state')
        for name in names:
            obj = objects[name]
            require(obj['object_type'] == 'LIGHT', 'Lighting candidate must be a light')
            light = obj['light']
            vector([light['energy']], 1, name+'.energy')
            vector(light['color'], 3, name+'.color')
            require(light['energy'] >= 0 and all(0 <= c <= 1 for c in light['color']), 'Invalid light energy/color')
        materials = {slot for obj in objects.values() for slot in obj['material_slots'] if slot is not None}
        require(set(state['materials']) == materials, 'Unrelated materials')
        require(all('nodes' not in m for m in state['materials'].values()), 'Lighting state must omit material shader graphs')
    changed = []
    for name, obj in start['objects'].items():
        other = goal['objects'][name]
        if name not in names:
            require(obj == other, f'Non-light edit: {name}')
            continue
        require(obj.keys() == other.keys() and all(obj[k] == other[k] for k in obj if k != 'light'),
                f'Non-light-property edit: {name}')
        light, target = obj['light'], other['light']
        require(light.keys() == target.keys(), 'Light schema changed')
        require(all(light[k] == target[k] for k in light if k not in properties), f'Unrequested light edit: {name}')
        if any(light[k] != target[k] for k in properties):
            changed.append(name)
    edits = metadata['edit_summary']
    require(set(edits['object_names']) == set(changed) and len(edits['object_names']) == len(changed), 'Changed light summary mismatch')
    require(1 <= len(changed) == edits['actual_changed'] <= edits['requested_max'], 'Invalid up-to-N light count')
    require(edits['requested_max'] == config['max_lights_to_modify'], 'Requested light count mismatch')
