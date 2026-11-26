"""Material construction, native state export and portable sample snapshots."""
import hashlib
import importlib
import inspect
import json
from pathlib import Path
import sys

import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from common.blender_state import apply_render_config, capture_render_config, export_state, pack_resources, plain
from common.contract import compare_values, publish_success, read_json, require, write_json

PROVENANCE_KEY = 'blenderforge_material'


def reset_material(obj, material_name):
    """Rebuild only the owned material and release its unused procedural groups."""
    old = bpy.data.materials.get(material_name)
    groups = []
    def collect(tree):
        for node in tree.nodes:
            group = getattr(node, 'node_tree', None)
            if group and group not in groups:
                groups.append(group)
                collect(group)
    if old:
        other_users = [o.name for o in bpy.data.objects if o != obj and any(s.material == old for s in o.material_slots)]
        if other_users:
            raise ValueError(f'Shared editable material: {other_users}')
        if old.node_tree:
            collect(old.node_tree)
        obj.data.materials.clear()
        if old.users:
            raise ValueError(f'Material has unsupported users: {material_name}')
        bpy.data.materials.remove(old)
        pending = list(groups)
        while pending:
            unused = [g for g in pending if g.users == 0]
            if not unused:
                break
            for group in unused:
                pending.remove(group)
                bpy.data.node_groups.remove(group)
    else:
        obj.data.materials.clear()
    mat = bpy.data.materials.new(name=material_name)
    mat.use_nodes = True
    obj.data.materials.append(mat)
    obj.active_material = mat
    return mat


def make_script(backend, config, parameters, shader=None):
    obj_name = config['scene']['target_object']
    mat_name = config['scene']['target_material']
    if backend == 'principled_bsdf':
        return importlib.import_module('material.basic.2_script').generate_script(parameters,obj_name,mat_name)
    lines = ['import bpy', '', inspect.getsource(reset_material),
             f'obj = bpy.data.objects[{obj_name!r}]', f'mat = reset_material(obj, {mat_name!r})']
    module = importlib.import_module(shader['module_path'])
    package = importlib.import_module('infinigen')
    source = Path(inspect.getsourcefile(module))
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    provenance = {'module':shader['module_path'], 'function':shader['shader_name'],
                  'source_sha256':digest, 'seed':config['random_seed'], 'package_version':package.__version__}
    lines += ['import hashlib', 'import importlib', 'import inspect', 'import json', 'import random',
                  'from pathlib import Path', 'import numpy as np', 'import infinigen',
                  'from infinigen.core.nodes.node_wrangler import NodeWrangler',
                  f'shader = {provenance!r}', "module = importlib.import_module(shader['module'])",
                  "source = Path(inspect.getsourcefile(module))",
                  "if hashlib.sha256(source.read_bytes()).hexdigest() != shader['source_sha256']:",
                  "    raise RuntimeError('Infinigen shader source differs from the sample dependency')",
                  "if infinigen.__version__ != shader['package_version']:",
                  "    raise RuntimeError('Infinigen version differs from the sample dependency')",
                  "random.seed(shader['seed'])", "np.random.seed(shader['seed'])",
                  f'params = {parameters!r}', "nw = NodeWrangler(mat.node_tree)",
                  "surface_shader = getattr(module, shader['function'])(nw=nw, **params)",
                  "if hasattr(surface_shader, 'outputs'):",
                  "    output = next(n for n in mat.node_tree.nodes if n.type == 'OUTPUT_MATERIAL')",
                  "    mat.node_tree.links.new(surface_shader.outputs[0], output.inputs['Surface'])",
                  f"mat[{PROVENANCE_KEY!r}] = json.dumps({{'shader':shader, 'parameters':params}}, allow_nan=False)"]
    lines.append('bpy.context.view_layer.update()')
    return '\n'.join(lines)+'\n'


def parameter_type(value):
    if value is None:
        return 'null'
    if isinstance(value, bool):
        return 'boolean'
    if isinstance(value, int):
        return 'integer'
    if isinstance(value, float):
        return 'float'
    if isinstance(value, str):
        return 'string'
    if isinstance(value, list):
        return 'vector'
    raise ValueError(f'Unsupported shader argument type: {type(value).__name__}')


def export_material_state(sample_id, state, config, backend):
    name, camera = [config['scene'][key] for key in ('target_object','target_camera')]
    obj = bpy.context.scene.objects[name]
    require(len(obj.material_slots) == 1, 'Material profile requires one target material slot')
    mat = obj.material_slots[0].material
    require(mat is not None and mat.name == config['scene']['target_material'], 'Incorrect target material binding')
    require(not mat.animation_data and not mat.node_tree.animation_data, 'Animated/driven editable material')
    scope = {name,camera}
    for key in tuple(scope):
        parent = bpy.data.objects[key].parent
        while parent:
            scope.add(parent.name)
            parent = parent.parent
    info = export_state(sample_id,state,[camera],[name],object_names=scope,include_material_nodes=True)
    material = info['materials'][mat.name]
    material['backend'] = backend
    parameters = {}
    if backend == 'principled_bsdf':
        bsdfs = [n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED']
        require(len(bsdfs) == 1, 'Expected one Principled BSDF node')
        node = bsdfs[0]
        material['shader'] = {'node_type':node.bl_idname, 'node_name':node.name}
        for param, definition in config['material_modification']['parameters'].items():
            socket = node.inputs[param]
            require(not socket.is_linked, f'Editable socket is linked: {param}')
            parameters[param] = {'value':plain(socket.default_value), 'type':definition['type'],
                'minimum':definition['min'], 'maximum':definition['max'], 'editable':True,
                'binding':{'kind':'node_input', 'node_name':node.name, 'input_index':list(node.inputs).index(socket),
                           'socket_identifier':socket.identifier}}
    else:
        provenance = json.loads(mat[PROVENANCE_KEY])
        material['shader'] = provenance['shader']
        for param,value in provenance['parameters'].items():
            parameters[param] = {'value':value, 'type':parameter_type(value), 'minimum':None, 'maximum':None,
                                 'editable':True, 'binding':{'kind':'shader_argument','name':param}}
    material['parameters'] = parameters
    return info


def check_supported_scene(config):
    require(not bpy.data.libraries, 'Linked libraries must be localized')
    obj = bpy.context.scene.objects[config['scene']['target_object']]
    require(obj.type == 'MESH' and obj.data.users == 1, 'Target must be an independent mesh')
    require(len(obj.material_slots) <= 1, 'Multiple target slots are unsupported by the original material task')
    editable = bpy.data.materials.get(config['scene']['target_material'])
    require(not editable or not any(o != obj and any(s.material == editable for s in o.material_slots) for o in bpy.data.objects),
            'Shared editable material')
    for material in bpy.data.materials:
        require(not material.animation_data and (not material.node_tree or not material.node_tree.animation_data),
                f'Animated/driven material: {material.name}')
    for item in bpy.context.scene.objects:
        require(not item.animation_data and not item.constraints, f'Dynamic object: {item.name}')
        if item.data:
            require(not item.data.animation_data, f'Dynamic datablock: {item.name}')
    camera = bpy.context.scene.objects[config['scene']['target_camera']]
    require(camera.type == 'CAMERA', 'Target camera is not a camera')
    require(not any(c in camera.name for c in '/\\\x00') and camera.name not in ('.','..'), 'Unsafe camera name')
    pack_resources(allow_static_geometry_nodes=True)


def save_state(root, state, sample_id, config, backend):
    root = Path(root)
    camera = config['scene']['target_camera']
    bpy.context.scene.camera = bpy.data.objects[camera]
    bpy.context.scene.render.filepath = f'//{state}_views/{camera}.png'
    pack_resources(allow_static_geometry_nodes=True)
    info = export_material_state(sample_id,state,config,backend)
    version = bpy.context.preferences.filepaths.save_version
    try:
        bpy.context.preferences.filepaths.save_version = 0
        bpy.ops.wm.save_as_mainfile(filepath=str(root/f'{state}.blend'),copy=True)
    finally:
        bpy.context.preferences.filepaths.save_version = version
    write_json(root/f'{state}_info.json',info)
    requested = config['render_config']
    effective = capture_render_config(requested.get('scene'),requested.get('view_layer'))
    if state == 'start':
        write_json(root/'render_config.json',{'schema_version':'1.0','sample_id':sample_id,'requested':requested,'effective':effective})
    else:
        compare_values(effective,read_json(root/'render_config.json')['effective'])


def replay_checks(root, config, backend, sample_id, rendering):
    root = Path(root)
    render = read_json(root/'render_config.json')
    checks = []
    replay_dir = root/'.replay'
    for route,snapshot,scripts,state in (('start_replay','start',('start',),'start'),
        ('goal_replay','start',('start','goal'),'goal'), ('goal_snapshot','goal',(),'goal')):
        bpy.ops.wm.open_mainfile(filepath=str(root/f'{snapshot}.blend'))
        for script in scripts:
            path = root/f'{script}.py'
            exec(compile(path.read_text(),str(path),'exec'),{'__name__':'__main__'})
        apply_render_config(render)
        error = compare_values(export_material_state(sample_id,state,config,backend),read_json(root/f'{state}_info.json'))
        effective = render['effective']
        compare_values(capture_render_config(effective.get('configured_scene'),effective.get('configured_view_layer')),effective)
        output = replay_dir/f'{route}.png'
        rendering.render_view(output,config['scene']['target_camera'])
        loss = rendering.rgb_l1(output,root/f'{state}_views'/f"{config['scene']['target_camera']}.png")
        require(loss <= config['replay_image_tolerance'], f'Render replay differs: {route}: {loss}')
        checks.append({'name':route,'executed':True,'passed':True,'metrics':{'max_absolute_numeric_error':error,'image_rgb_l1':loss},
                       'tolerance':{'state':1e-6,'image_rgb_l1':config['replay_image_tolerance']},'reason':None})
    import shutil
    shutil.rmtree(replay_dir)
    return checks


def finalize(root, config, source, backend, sample_id, quality, rendering):
    root,source = Path(root),Path(source)
    start,goal = [read_json(root/f'{s}_info.json') for s in ('start','goal')]
    name,mat_name = [config['scene'][key] for key in ('target_object','target_material')]
    parameters = start['materials'][mat_name]['parameters']
    changed = [{'material_name':mat_name,'parameter':key} for key in parameters
               if parameters[key]['value'] != goal['materials'][mat_name]['parameters'][key]['value']]
    with source.open('rb') as stream:
        digest = hashlib.file_digest(stream,'sha256').hexdigest()
    dependencies = {'external_files':[],'resources_packed':True,'python_modules_for_replay':['bpy']}
    if backend == 'infinigen':
        dependencies['python_modules_for_replay'] += ['numpy','infinigen']
        dependencies['shader'] = start['materials'][mat_name]['shader']
    metadata = {'schema_version':'1.0','sample_id':sample_id,'task':'material','backend':backend,
        'source':{'asset_id':source.stem,'filename':source.name,'sha256':digest},
        'generator':{'name':'material','config':config,'seed':config['random_seed'],'seed_scope':'invocation','blender_version':bpy.app.version_string},
        'dependencies':dependencies,'num_views':1,
        'editable':{'object_names':[name],'properties':['materials.parameters'],
            'material_bindings':[{'object_name':name,'slot_index':0,'material_name':mat_name}],
            'parameters':[{'material_name':mat_name,'parameter':key} for key in parameters]},
        'edit_summary':{'actual_changed':len(changed),'parameters':changed,'object_names':[name]}}
    write_json(root/'metadata.json',metadata)
    checks = [{'name':'quality','executed':True,'passed':True,'metrics':quality,
               'tolerance':config['validation']['min_photometric_diff'],'reason':None}]
    checks.extend(replay_checks(root,config,backend,sample_id,rendering))
    publish_success(root,checks)
    return checks
