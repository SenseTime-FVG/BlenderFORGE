"""Material identity, public parameter bindings and edit invariants."""
import copy
import math
from common.contract import require


def parameter_pairs(items):
    return [(item['material_name'],item['parameter']) for item in items]


def validate_parameter(item):
    value,kind = item['value'],item['type']
    valid = ((kind == 'null' and value is None) or
             (kind == 'boolean' and type(value) is bool) or
             (kind == 'integer' and type(value) is int) or
             (kind == 'float' and type(value) in (int,float)) or
             (kind == 'string' and isinstance(value,str)) or
             (kind in ('vector','color') and isinstance(value,list)))
    require(valid and type(item['editable']) is bool,'Invalid parameter type/flag')
    if kind in ('float','integer','vector','color'):
        values = value if isinstance(value,list) else [value]
        require(values and all(type(v) in (int,float) and math.isfinite(v) for v in values),'Invalid numeric parameter')
        for field,sign in (('minimum',1),('maximum',-1)):
            bound = item[field]
            if bound is not None:
                bounds = bound if isinstance(bound,list) else [bound]
                require(len(values) == len(bounds) and all(sign*(v-b) >= -1e-6 for v,b in zip(values,bounds)),f'Parameter exceeds {field}')


def check_material_states(metadata, start, goal):
    bindings = metadata['editable']['material_bindings']
    require(len(bindings) == 1, 'Expected one material binding')
    binding = bindings[0]
    name,mat_name = binding['object_name'],binding['material_name']
    require(binding['slot_index'] == 0 and metadata['editable']['object_names'] == [name], 'Invalid target object/slot')
    pairs = parameter_pairs(metadata['editable']['parameters'])
    require(pairs and len(pairs) == len(set(pairs)), 'Missing/duplicate editable parameters')
    require(start['scene'] == goal['scene'] and start['objects'] == goal['objects'], 'Material task changed geometry/cameras/bindings')
    require([v['camera_name'] for v in start['views']] == [v['camera_name'] for v in goal['views']], 'Camera set/order changed')
    for state in (start,goal):
        objects = state['objects']
        require(objects[name]['object_type'] == 'MESH' and objects[name]['material_slots'] == [mat_name], 'Actual material binding disagrees with metadata')
        require({n for n,obj in objects.items() if obj['editable']} == {name}, 'Editable object scope mismatch')
        scope = {name} | {v['camera_name'] for v in state['views']}
        for key in tuple(scope):
            seen = {key}
            parent = objects[key]['parent_id']
            while parent is not None:
                require(parent not in seen, 'Parent cycle')
                seen.add(parent)
                scope.add(parent)
                parent = objects[parent]['parent_id']
        require(set(objects) == scope, 'Unrelated material-task objects')
        referenced = {slot for obj in objects.values() for slot in obj['material_slots'] if slot is not None}
        require(set(state['materials']) == referenced, 'Unrelated materials')
        mat = state['materials'][mat_name]
        require(mat['backend'] == metadata['backend'] and mat['use_nodes'], 'Material backend/node mode mismatch')
        params = mat['parameters']
        require(set(pairs) == {(mat_name,p) for p,x in params.items() if x['editable']}, 'Editable parameter scope mismatch')
        for param,item in params.items():
            require(set(item) == {'value','type','minimum','maximum','editable','binding'}, 'Incomplete parameter definition')
            validate_parameter(item)
            b = item['binding']
            if metadata['backend'] == 'principled_bsdf':
                require(b['kind'] == 'node_input', 'Expected a socket binding')
                node = mat['nodes']['nodes'][b['node_name']]
                require(node['type'] == 'ShaderNodeBsdfPrincipled', 'Expected Principled BSDF node')
                socket = node['inputs'][b['input_index']]
                require(socket['identifier'] == b['socket_identifier'] and socket['name'] == param and not socket['linked'], 'Wrong/linked parameter socket')
                require(socket['value'] == item['value'], 'Parameter value disagrees with native socket')
            else:
                require(b == {'kind':'shader_argument','name':param}, 'Invalid shader argument binding')
        if metadata['backend'] == 'infinigen':
            require(mat['shader'] == metadata['dependencies']['shader'], 'Shader dependency mismatch')
            require(all(k in mat['shader'] for k in ('module','function','source_sha256','seed','package_version')),'Incomplete shader dependency')
        else:
            require(mat['shader']['node_type'] == 'ShaderNodeBsdfPrincipled' and
                    mat['shader']['node_name'] in mat['nodes']['nodes'],'Invalid Principled shader identity')
    require(start['materials'].keys() == goal['materials'].keys(), 'Material identities changed')
    a,b = [s['materials'][mat_name] for s in (start,goal)]
    require(a.keys() == b.keys() and all(a[k] == b[k] for k in a if k not in ('nodes','parameters')),'Material settings changed')
    require(a['shader'] == b['shader'] and a['parameters'].keys() == b['parameters'].keys(), 'Shader or parameter identities changed')
    changed = set()
    for key,item in a['parameters'].items():
        other = b['parameters'][key]
        require(all(item[k] == other[k] for k in item if k != 'value'), 'Parameter definitions changed')
        if item['value'] != other['value']:
            changed.add((mat_name,key))
    summary = metadata['edit_summary']
    listed = parameter_pairs(summary['parameters'])
    require(changed and changed == set(listed) and len(listed) == summary['actual_changed'] == len(changed), 'Invalid changed parameter summary')
    require(summary['object_names'] == [name], 'Changed object summary mismatch')
    if metadata['backend'] == 'principled_bsdf':
        graphs = [copy.deepcopy(mat['nodes']) for mat in (a,b)]
        for graph in graphs:
            for item in a['parameters'].values():
                binding = item['binding']
                graph['nodes'][binding['node_name']]['inputs'][binding['input_index']]['value'] = None
        require(graphs[0] == graphs[1],'Changed a non-editable node/socket')
    for material,value in start['materials'].items():
        if material != mat_name:
            require(value == goal['materials'][material], 'Unrelated material changed')
