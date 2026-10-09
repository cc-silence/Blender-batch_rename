"""Explicit nested-name coverage and bounded live RNA references."""
from contextlib import contextmanager
import itertools
import uuid
import bpy
from bpy.app.handlers import persistent
from . import utils, node_names

LABELS = {
'__node_other_names__':'其他节点名称（仅检查）',
'__node_interfaces__':'节点组接口（输入/输出名称）',
'__name_references__':'名称引用字符串',
'__color_attributes__':'顶点色',
'__attributes__':'几何属性',
'__custom_properties__':'自定义属性（仅检查）',
'__node_items__':'节点自定义条目',
'__action_layers__':'动作图层','__action_slots__':'动作槽位','__action_groups__':'动画通道组','__pose_markers__':'动作标记',
'__sequence_strips__':'序列片段','__sequence_channels__':'序列通道','__strip_modifiers__':'序列修改器','__annotation_layers__':'注释图层',
'__nodes__':'节点名称','__node_labels__':'节点标签',
'__frames__':'框架名称','__frame_labels__':'框架标签',
'__interface_panels__':'接口面板名称','__interface_descriptions__':'接口说明',
'__modifiers__':'修改器','__constraints__':'物体约束','__pose_constraints__':'骨骼约束',
'__bones__':'骨骼','__bone_collections__':'骨骼集合','__vertex_groups__':'顶点组',
'__shape_blocks__':'形态键条目','__uv_layers__':'纹理坐标层',
'__view_layers__':'视图层','__timeline_markers__':'时间线标记',
'__grease_layers__':'蜡笔图层','__nla_tracks__':'非线性动画轨道','__nla_strips__':'非线性动画片段',
}
NODE_ITEM_COLLECTIONS = node_names.NODE_ITEM_COLLECTIONS
SPECS = {
'__action_layers__':('actions','layers'), '__pose_markers__':('actions','pose_markers'),
'__modifiers__':('objects','modifiers'), '__constraints__':('objects','constraints'),
'__bones__':('armatures','bones'), '__bone_collections__':('armatures','collections_all'),
'__vertex_groups__':('objects','vertex_groups'), '__shape_blocks__':('shape_keys','key_blocks'),
'__uv_layers__':('meshes','uv_layers'), '__view_layers__':('scenes','view_layers'),
'__timeline_markers__':('scenes','timeline_markers'), '__grease_layers__':('grease_pencils','layers'),
}
_tree_fields = {}
_scan_trees = None
_validation_nodes = None
_validation_parts = None
_part_types = None
_refs = {}
_epoch = uuid.uuid4().hex
_counter = itertools.count()


def _node_part_types():
    global _part_types
    if _part_types is None:
        _part_types=set()
        for name in dir(bpy.types):
            cls=getattr(bpy.types,name)
            if not isinstance(cls,type) or not issubclass(cls,bpy.types.Node):continue
            for field in NODE_ITEM_COLLECTIONS:
                prop=cls.bl_rna.properties.get(field)
                if prop is not None:_part_types.add(prop.fixed_type.identifier)
    return _part_types


def _part_index():
    parts={}
    for _,tree,_ in node_trees():
        interface=getattr(tree,'interface',None)
        if interface:
            for item in interface.items_tree:parts[item.as_pointer()]=(item,None)
        for node in tree.nodes:
            for socket in (*node.inputs,*node.outputs):parts[socket.as_pointer()]=(socket,node)
            for field in NODE_ITEM_COLLECTIONS:
                for item in getattr(node,field,()):parts[item.as_pointer()]=(item,node)
    for obj in bpy.data.objects:
        for modifier in obj.modifiers:
            if modifier.type!='NODES' or modifier.node_group is None:continue
            props=getattr(modifier,'properties',None)
            if props is None:continue
            for socket,direction in utils.iter_interface_sockets(modifier.node_group):
                container=props.inputs if direction=='INPUT' else props.outputs
                item=getattr(container,socket.identifier,None)
                if item is not None:
                    _node_part_types().add(item.bl_rna.identifier)
                    parts[item.as_pointer()]=(item,modifier)
    return parts


def remember(target, scene):
    token = _epoch + ':' + str(next(_counter))
    identity = None
    pointer=target.as_pointer()
    if isinstance(target,bpy.types.NodeSocket) or isinstance(target,bpy.types.NodeTreeInterfaceItem) or target.bl_rna.identifier in _node_part_types():
        part,parent=(_validation_parts if _validation_parts is not None else _part_index()).get(pointer,(None,None))
        if part is None:raise ValueError('Node part is no longer live')
        marker=None
        if isinstance(parent,bpy.types.Node) and utils.is_editable(parent.id_data):
            marker='_wkngr_identity_'+uuid.uuid4().hex;parent[marker]=token
        identifier=getattr(target,'identifier',None)
        identity=('part',parent.as_pointer() if parent else 0,marker,identifier,getattr(parent,'persistent_uid',None))
        # Keep primitive identity only. Freed sockets/items must never be dereferenced.
        _refs[token]=(scene.session_uid,None,identity,pointer)
        return token
    if isinstance(target, bpy.types.Node) and utils.is_editable(target.id_data):
        identity = '_wkngr_identity_' + uuid.uuid4().hex
        target[identity] = token
    elif hasattr(target, 'persistent_uid'):
        identity = ('persistent_uid', target.persistent_uid)
    _refs[token] = (scene.session_uid, target, identity, pointer)
    return token


def resolve(token):
    record = _refs.get(token)
    if record is None:return None
    target,identity,pointer=record[1:]
    if isinstance(identity,tuple) and identity[0]=='part':
        target,parent=(_validation_parts if _validation_parts is not None else _part_index()).get(pointer,(None,None))
        if target is None:return None
        _,parent_pointer,marker,identifier,generation=identity
        if parent_pointer and (parent is None or parent.as_pointer()!=parent_pointer):return None
        if generation is not None and getattr(parent,'persistent_uid',None)!=generation:return None
        if marker and parent.get(marker)!=token:return None
        if identifier is not None and getattr(target,'identifier',None)!=identifier:return None
        return target
    if isinstance(identity, str):
        target = (_validation_nodes if _validation_nodes is not None else _node_index()).get(pointer)
        return target if target is not None and target.get(identity) == token else None
    if target is not None:
        try:
            target.as_pointer()
            target.bl_rna
            if isinstance(identity, tuple) and getattr(target, identity[0]) != identity[1]:return None
        except ReferenceError:return None
    return target


def _node_marker(record):
    identity=record[2]
    if isinstance(identity,str):return record[3],identity
    if isinstance(identity,tuple) and identity[0]=='part' and identity[2]:return identity[1],identity[2]
    return None


def _node_index():
    return {node.as_pointer(): node for _, tree, _ in node_trees() for node in tree.nodes}


@contextmanager
def validation_session():
    global _validation_nodes,_validation_parts
    previous,previous_parts=_validation_nodes,_validation_parts
    try:
        if _validation_nodes is None:_validation_nodes=_node_index()
        if _validation_parts is None:_validation_parts=_part_index()
        yield
    finally:
        _validation_nodes,_validation_parts=previous,previous_parts


def _forget(token, nodes):
    record=_refs.pop(token,None)
    marker=_node_marker(record) if record else None
    if marker:
        target=nodes.get(marker[0])
        if target is not None and target.get(marker[1])==token:del target[marker[1]]


def clear_references():
    nodes=_node_index() if any(_node_marker(r) for r in _refs.values()) else {}
    for token in tuple(_refs):_forget(token,nodes)


def release(entries):
    tokens=[item.cache_key for item in entries if item.cache_key]
    if not tokens:return
    nodes=_node_index() if any(_node_marker(_refs[t]) for t in tokens if t in _refs) else {}
    for token in tokens:_forget(token,nodes)


def id_owners():
    for prop in bpy.data.bl_rna.properties:
        if prop.type != 'COLLECTION':
            continue
        cls = getattr(bpy.types, prop.fixed_type.identifier, None)
        if cls is not None and cls is not bpy.types.ID and issubclass(cls, bpy.types.ID):
            yield from getattr(bpy.data, prop.identifier)


def prune():
    live = {scene.session_uid for scene in bpy.data.scenes}
    nodes = _node_index() if _refs else {}
    for token, (scene_uid, target, identity, pointer) in tuple(_refs.items()):
        if scene_uid not in live:
            _forget(token, nodes)


def _iter_node_trees():
    seen = set()
    for tree in bpy.data.node_groups:
        seen.add(tree.as_pointer())
        yield tree, tree, tree.name
    for owner in id_owners():
        if isinstance(owner, bpy.types.NodeTree):
            continue
        type_name = owner.bl_rna.identifier
        fields = _tree_fields.get(type_name)
        if fields is None:
            fields = []
            for prop in owner.bl_rna.properties:
                if prop.type == 'POINTER':
                    cls = getattr(bpy.types, prop.fixed_type.identifier, None)
                    if cls is not None and issubclass(cls, bpy.types.NodeTree):
                        fields.append(prop.identifier)
            _tree_fields[type_name] = fields
        for field in fields:
            tree = getattr(owner, field, None)
            if tree is not None and tree.as_pointer() not in seen:
                seen.add(tree.as_pointer())
                yield owner, tree, owner.name


def node_trees():
    yield from _scan_trees if _scan_trees is not None else _iter_node_trees()


@contextmanager
def scan_session():
    global _scan_trees,_validation_parts
    prune()
    previous = _scan_trees
    previous_parts = _validation_parts
    try:
        _scan_trees = tuple(_iter_node_trees())
        _validation_parts = _part_index()
        yield
    finally:
        _scan_trees = previous
        _validation_parts = previous_parts


def all_candidates(key):
    if key == '__custom_properties__':
        for owner in id_owners():
            targets = [owner]
            if isinstance(owner, bpy.types.Object):
                targets.extend(owner.modifiers)
                if owner.pose:
                    targets.extend(owner.pose.bones)
            if isinstance(owner, bpy.types.Armature):
                targets.extend(owner.bones)
            if isinstance(owner, bpy.types.NodeTree):
                targets.extend(owner.nodes)
            for target in targets:
                try:
                    names = target.keys()
                except TypeError:
                    continue
                for name in names:
                    if not name.startswith(('wkngr_', '_wkngr_')) and name not in target.bl_rna.properties:
                        yield owner, target, '__custom__' + name, owner.name + ' / ' + getattr(target, 'name', '')
    elif key == '__node_interfaces__':
        for owner,tree,label in node_trees():
            for target,direction in utils.iter_interface_sockets(tree):
                yield owner,target,'name',label+' / '+direction
    elif key == '__node_other_names__':
        yield from node_names.inspection_candidates()
    elif key == '__name_references__':
        yield from node_names.reference_candidates()
    elif key in ('__color_attributes__', '__attributes__'):
        for owner in id_owners():
            colors = getattr(owner, 'color_attributes', ())
            color_names = {item.name for item in colors}
            uv_names = {item.name for item in getattr(owner, 'uv_layers', ())}
            for target in colors if key == '__color_attributes__' else getattr(owner, 'attributes', ()):
                if key == '__attributes__' and (target.name in color_names or target.name in uv_names):
                    continue
                yield owner, target, 'name', owner.name
    elif key in SPECS:
        owners, collection = SPECS[key]
        for owner in getattr(bpy.data, owners, ()):
            for target in getattr(owner, collection, ()):
                yield owner, target, 'name', owner.name
    elif key == '__annotation_layers__':
        for owner in getattr(bpy.data, 'annotations', ()):
            for target in owner.layers:
                yield owner, target, 'info', owner.name
    elif key == '__action_slots__':
        for owner in bpy.data.actions:
            for target in owner.slots:
                yield owner, target, 'name_display', owner.name
    elif key == '__action_groups__':
        for owner in bpy.data.actions:
            for layer in owner.layers:
                for strip in layer.strips:
                    for bag in getattr(strip, 'channelbags', ()):
                        for target in bag.groups:
                            yield owner, target, 'name', owner.name + ' / ' + layer.name
    elif key in ('__sequence_strips__','__sequence_channels__','__strip_modifiers__'):
        for owner in bpy.data.scenes:
            editor = owner.sequence_editor
            if editor is None:
                continue
            if key == '__sequence_channels__':
                for target in editor.channels:
                    yield owner, target, 'name', owner.name
            else:
                for strip in editor.strips_all:
                    if key == '__sequence_strips__':
                        yield owner, strip, 'name', owner.name
                    else:
                        for target in strip.modifiers:
                            yield owner, target, 'name', owner.name + ' / ' + strip.name
    elif key == '__node_items__':
        for owner, tree, label in node_trees():
            for node in tree.nodes:
                for collection in NODE_ITEM_COLLECTIONS:
                    if collection=='sample_attribute_items':continue  # A lookup into external geometry, not a socket display name.
                    for target in getattr(node, collection, ()):
                        if hasattr(target, 'name'):
                            yield owner, target, 'name', label + ' / ' + node.name
    elif key == '__pose_constraints__':
        for owner in bpy.data.objects:
            if owner.pose:
                for bone in owner.pose.bones:
                    for target in bone.constraints:
                        yield owner, target, 'name', owner.name + ' / ' + bone.name
    elif key in ('__nla_tracks__', '__nla_strips__'):
        for owner in id_owners():
            animation = getattr(owner, 'animation_data', None)
            if animation:
                for track in animation.nla_tracks:
                    if key == '__nla_tracks__':
                        yield owner, track, 'name', owner.name
                    else:
                        for target in track.strips:
                            yield owner, target, 'name', owner.name + ' / ' + track.name
    else:
        for owner, tree, label in node_trees():
            if key in ('__interface_panels__','__interface_descriptions__'):
                interface = getattr(tree, 'interface', None)
                if interface:
                    for target in interface.items_tree:
                        if key == '__interface_panels__' and target.item_type == 'PANEL':
                            yield owner, target, 'name', label
                        elif key == '__interface_descriptions__' and hasattr(target, 'description'):
                            yield owner, target, 'description', label + ' / ' + target.name
            else:
                frames = key in ('__frames__','__frame_labels__')
                field = 'label' if key in ('__node_labels__','__frame_labels__') else 'name'
                for target in tree.nodes:
                    if (target.bl_idname == 'NodeFrame') == frames:
                        yield owner, target, field, label + ' / ' + target.name


def matches(key, tokens, custom):
    for owner, target, field, context in all_candidates(key):
        value = field[len('__custom__'):] if field.startswith('__custom__') else (target.get(field[4:],'') if field.startswith('@id:') else getattr(target, field))
        if not utils.should_show(value, tokens, custom):
            continue
        readonly = key in {'__custom_properties__','__node_other_names__'} or getattr(target, 'is_internal', False) or getattr(target, 'is_required', False) or not utils.is_editable(owner) or (not field.startswith('@id:') and target.is_property_readonly(field))
        if (field=='attribute_name' and isinstance(target,bpy.types.ShaderNodeAttribute)
                and target.attribute_type!='GEOMETRY'):
            readonly = True  # These fields refer to custom-property keys, currently inspection-only.
        if key in ('__bones__','__bone_collections__') and getattr(owner, 'is_editmode', False):
            readonly = True
        yield owner, value, str(target.identifier) if key=='__node_interfaces__' else '', readonly, target, field, context


def live_members(key, entries):
    requested = set()
    for item in entries:
        target = resolve(item.cache_key)
        if target is not None and item.target is not None:
            requested.add((item.target.as_pointer(), target.as_pointer(), item.field))
    found = set()
    for owner, target, field, _ in all_candidates(key):
        value = (owner.as_pointer(), target.as_pointer(), field)
        if value in requested:
            found.add(value)
    return found


@persistent
def _refresh_nested_history(_unused):
    """RNA addresses are invalidated by load/undo; rebuild nested previews safely."""
    # Loading and undo free old RNA: discard wrappers without dereferencing them.
    _refs.clear()
    for node in _node_index().values():
        if utils.is_editable(node.id_data):
            for name in list(node.keys()):
                if name.startswith('_wkngr_identity_'):
                    del node[name]
    from . import data_catalog
    for scene in bpy.data.scenes:
        if scene.library or not hasattr(scene, 'wkngr_categories'):
            continue
        selected = data_catalog.active_category(scene)
        selected_key = selected.key if selected else ''
        keys = [category.key for category in scene.wkngr_categories if category.key in LABELS]
        if not keys:
            continue
        try:
            filters = data_catalog.filters(scene)
            for key in keys:
                data_catalog.refresh_category(scene, key, filters)
            for index, category in enumerate(scene.wkngr_categories):
                if category.key == selected_key:
                    scene.wkngr_category_index = index
                    break
        except (OSError, ValueError, RuntimeError, ReferenceError) as exc:
            print('batch_rename nested refresh:', exc)


def ensure_scene(scene):
    """Re-enable may restore persisted rows, but never their old RNA addresses."""
    from . import data_catalog
    keys = [c.key for c in scene.wkngr_categories if c.key in LABELS and
            any(resolve(row.cache_key) is None for row in c.entries)]
    if keys:
        filters = data_catalog.filters(scene)
        selected = data_catalog.active_category(scene)
        selected_key = selected.key if selected else ''
        for key in keys:
            data_catalog.refresh_category(scene, key, filters)
        for index, category in enumerate(scene.wkngr_categories):
            if category.key == selected_key:
                scene.wkngr_category_index = index
                break


@persistent
def _before_save(_unused):
    nodes=_node_index()
    for token,record in tuple(_refs.items()):
        marker=_node_marker(record)
        if not marker:continue
        target=nodes.get(marker[0])
        if target is not None and target.get(marker[1])==token:del target[marker[1]]


@persistent
def _after_save(_unused):
    nodes=_node_index()
    for token,record in tuple(_refs.items()):
        marker=_node_marker(record)
        if not marker:continue
        target=nodes.get(marker[0])
        if target is not None:target[marker[1]]=token


def register():
    for handlers, callback in ((bpy.app.handlers.save_pre, _before_save), (bpy.app.handlers.save_post, _after_save), (bpy.app.handlers.save_post_fail, _after_save)):
        if callback not in handlers:
            handlers.append(callback)
    for handlers in (bpy.app.handlers.load_post, bpy.app.handlers.undo_post, bpy.app.handlers.redo_post):
        if _refresh_nested_history not in handlers:
            handlers.append(_refresh_nested_history)


def unregister():
    for handlers, callback in ((bpy.app.handlers.save_pre, _before_save), (bpy.app.handlers.save_post, _after_save), (bpy.app.handlers.save_post_fail, _after_save)):
        if callback in handlers:
            handlers.remove(callback)
    _tree_fields.clear()
    for handlers in (bpy.app.handlers.load_post, bpy.app.handlers.undo_post, bpy.app.handlers.redo_post):
        if _refresh_nested_history in handlers:
            handlers.remove(_refresh_nested_history)
    if hasattr(bpy.data, 'scenes'):
        clear_references()
    else:
        _refs.clear()
