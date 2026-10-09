"""Transactional updates for UV/vertex-group names and their typed references."""
import bpy
from . import utils, nested_data, name_safety, geometry_contracts, node_names


ID_FIELD = '@id:'


def read(target, field):
    return target.get(field[len(ID_FIELD):], '') if field.startswith(ID_FIELD) else getattr(target, field)


def write(target, field, value):
    if field.startswith(ID_FIELD):
        target[field[len(ID_FIELD):]] = value
    else:
        setattr(target, field, value)


def readonly(target, field):
    return False if field.startswith(ID_FIELD) else target.is_property_readonly(field)


def modifier_attributes(modifier):
    if modifier.type != 'NODES' or modifier.node_group is None:
        return
    props = getattr(modifier, 'properties', None)
    for socket in modifier.node_group.interface.items_tree:
        if socket.item_type != 'SOCKET':
            continue
        if props is not None:
            container = props.inputs if socket.in_out == 'INPUT' else props.outputs
            value = getattr(container, socket.identifier, None)
            if value is not None and hasattr(value, 'attribute_name'):
                yield value, 'attribute_name'
        else:
            key = socket.identifier + '_attribute_name'
            if key in modifier:
                yield modifier, ID_FIELD + key


def _settings_strings(target, uv):
    for prop in target.bl_rna.properties:
        if prop.type == 'STRING':
            matches = prop.identifier in {'uv_layer','uv_map','uv_layer_stencil'} if uv else 'vertex_group' in prop.identifier
            if matches:
                yield target, prop.identifier
    for name in ('settings','collision_settings'):
        child = getattr(target, name, None)
        if child is not None and hasattr(child, 'bl_rna'):
            for prop in child.bl_rna.properties:
                if prop.type == 'STRING' and 'vertex_group' in prop.identifier and not uv:
                    yield child, prop.identifier


def references(uv, old_names, attribute=False):
    """Collect name consumers with all actual local/external source namespaces."""
    found, tree_cache = {}, {}
    known_owners = set()
    candidate_namespaces = {obj.data if uv or attribute else obj for obj in bpy.data.objects
                            if obj.data is not None}
    def has_name(namespace, old):
        if namespace is None:
            return False
        if not uv and not attribute:
            return namespace.vertex_groups.get(old) is not None
        if uv:
            return getattr(namespace, 'uv_layers', {}).get(old) is not None
        return getattr(namespace, 'attributes', {}).get(old) is not None
    def add(target, field, owner, namespaces, unknown=False):
        value = read(target, field)
        if value not in old_names:
            return
        users = {namespace.as_pointer() for namespace in namespaces if has_name(namespace, value)}
        if unknown:
            users.update(namespace.as_pointer() for namespace in candidate_namespaces if has_name(namespace, value))
            users.add(0)
        if not users:
            return
        key = (target.as_pointer(), field)
        record = found.setdefault(key, [target, field, owner, set(), value])
        record[3].update(users)
    def walk(tree, owner, namespaces, visited, unknown=False, values=None):
        values = values or {}
        context_key = (tree.as_pointer(),tuple(sorted((key,repr(value)) for key,value in values.items()))) if tree is not None else None
        if tree is None or context_key in visited:
            return
        visited.add(context_key)
        known_owners.add(owner);known_owners.add(tree)
        root = owner if tree.is_embedded_data else tree
        cached = tree_cache.get(tree.as_pointer())
        if cached is None:
            fields, children, name_sockets = [], [], []
            for node in tree.nodes:
                fields.extend(node_names.reference_fields(node,uv=uv,attribute=attribute))
                name_sockets.extend(node_names.name_sockets(node))
                child = getattr(node, 'node_tree', None)
                if child is not None:
                    children.append(node)
            for interface,direction in utils.iter_interface_sockets(tree):
                fields.append((interface,'default_attribute_name'))
            cached = fields, children, name_sockets
            tree_cache[tree.as_pointer()] = cached
        for target, field in cached[0]:
            add(target, field, root, namespaces, unknown)
        dynamic = False
        for socket in cached[2]:
            source = geometry_contracts.name_source(socket,values)
            if source is None:
                dynamic = True
                continue
            target,field = source
            source_owner = getattr(target,'id_data',root)
            if getattr(source_owner,'is_embedded_data',False):source_owner=root
            add(target,field,source_owner,namespaces,unknown)
        if dynamic:
            for old in old_names:
                users = {namespace.as_pointer() for namespace in namespaces if has_name(namespace, old)}
                if unknown:
                    users.update(namespace.as_pointer() for namespace in candidate_namespaces if has_name(namespace, old))
                if users:
                    record = found.setdefault((tree.as_pointer(), '@dynamic:' + old), [None, '', root, set(), old])
                    record[3].update(users);record[3].add(0)
        for node in cached[1]:
            child = node.node_tree
            inputs = geometry_contracts.child_values(node,values,None)
            walk(child,child,namespaces,visited,unknown,inputs)
    for obj in bpy.data.objects:
        known_owners.add(obj)
        namespace = obj.data if uv or attribute else obj
        if namespace is None or (uv and not isinstance(namespace, bpy.types.Mesh)):
            continue
        for modifier in obj.modifiers:
            if not attribute:
                for target, field in _settings_strings(modifier, uv):
                    add(target, field, obj, {namespace})
            for target, field in modifier_attributes(modifier):
                add(target, field, obj, {namespace})
        if not uv and not attribute:
            keys = getattr(obj.data, 'shape_keys', None)
            if keys:
                for block in keys.key_blocks:
                    add(block, 'vertex_group', keys, {namespace})
            for target in obj.particle_systems:
                for candidate, field in _settings_strings(target, False):
                    add(candidate, field, obj, {namespace})
        for slot in obj.material_slots:
            if slot.material and slot.material.node_tree:
                walk(slot.material.node_tree, slot.material, {namespace}, set())
        for modifier in obj.modifiers:
            tree = getattr(modifier, 'node_group', None)
            if modifier.type != 'NODES' or tree is None:
                continue
            sources, unknown = {obj}, False
            for context, values in geometry_contracts.contexts(tree, geometry_contracts.modifier_values(modifier), obj):
                for node in context.nodes:
                    if node.bl_idname not in geometry_contracts.EXTERNAL:
                        continue
                    value = geometry_contracts.external_value(node, values, obj)
                    if value is geometry_contracts.UNKNOWN:
                        unknown = True
                    elif value is not None:
                        if node.bl_idname == 'GeometryNodeCollectionInfo':
                            sources.update(value.all_objects)
                        else:
                            sources.add(value)
            namespaces = {source.data if uv or attribute else source for source in sources
                          if source.data is not None}
            walk(tree,tree,namespaces,set(),unknown,geometry_contracts.modifier_values(modifier))
    if not uv and not attribute:
        for obj in bpy.data.objects:
            constraints = list(obj.constraints)
            if obj.pose:
                constraints.extend(c for bone in obj.pose.bones for c in bone.constraints)
            for constraint in constraints:
                target = getattr(constraint, 'target', None)
                if target is not None and hasattr(constraint, 'subtarget') and target.type != 'ARMATURE':
                    add(constraint, 'subtarget', obj, {target})
    tree_owners = {record[2] for record in found.values() if isinstance(record[2], bpy.types.NodeTree) and not record[2].is_embedded_data}
    native = bpy.data.user_map(subset=tree_owners) if tree_owners else {}
    for record in found.values():
        if native.get(record[2], set()) - known_owners:
            record[3].add(0)
    return list(found.values())


def prepare(category, safety=None, validate_refs=True):
    uv = category.key == '__uv_layers__'
    attribute = category.key in ('__attributes__', '__color_attributes__')
    members = nested_data.live_members(category.key, category.entries)
    plans, errors, collisions = {}, [], []
    safety = safety or name_safety.Preflight()
    for item in category.entries:
        requested = item.new_name.strip()
        if not requested or requested == item.old_name:
            continue
        if utils.contains_chinese(requested):
            errors.append(item.old_name + ': 新名仍含中文，已保留原名')
            continue
        owner, target = item.target, nested_data.resolve(item.cache_key)
        if owner is None or target is None or item.read_only or not utils.is_editable(owner):
            errors.append(item.old_name + ': 数据已删除或只读')
            continue
        if (owner.as_pointer(),target.as_pointer(),'name') not in members or target.name != item.old_name:
            errors.append(item.old_name + ': 数据已变化，已刷新')
            continue
        reason = safety.reason(category.key, owner, item.old_name, requested)
        if reason:
            errors.append(item.old_name + ': ' + reason)
            continue
        plans[(owner.as_pointer(),item.old_name)] = (owner,target,item.old_name,requested)
    reference_names = ({key[1] for key in plans} if validate_refs else
                       {item.old_name for item in category.entries if item.new_name.strip() and item.new_name.strip() != item.old_name})
    refs = references(uv, reference_names, attribute=attribute) if reference_names else []
    if category.key == '__vertex_groups__':
        blocked = set()
        for key, (owner, target, old, requested) in plans.items():
            peers = [obj for obj in bpy.data.objects if obj.data == owner.data and obj.vertex_groups.get(old)]
            peer_keys = {(obj.as_pointer(), old) for obj in peers}
            if not peer_keys <= plans.keys() or any(plans[peer][3] != requested for peer in peer_keys):
                blocked.update(peer_keys & plans.keys())
        for key in blocked:
            owner, target, old, requested = plans.pop(key)
            errors.append(owner.name + ' / ' + old + ': \u5171\u4eab\u7f51\u683c\u7684\u9876\u70b9\u7ec4\u5fc5\u987b\u4e00\u81f4\u6539\u540d')
    if not validate_refs:
        return plans, refs, errors
    # Shared nodes can only be updated when every user agrees on the same rename.
    while True:
        blocked = set()
        for target, field, owner, users, old in refs:
            keys = {(user,old) for user in users}
            affected = keys & plans.keys()
            if not affected:
                continue
            if not keys <= plans.keys() or len({plans[key][3] for key in keys}) != 1 or not utils.is_editable(owner) or target is None or readonly(target, field):
                blocked.update(affected)
        if not blocked:
            break
        for key in blocked:
            owner, target, old, requested = plans.pop(key)
            errors.append(owner.name + ' / ' + old + ': 共享引用无法一致更新，已保留原名')
    return plans, refs, errors


def apply(category):
    from . import rename_plan
    return rename_plan.apply([category])
