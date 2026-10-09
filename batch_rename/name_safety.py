"""Preflight only for explicit name lookups that native setters cannot maintain."""
import ast
import bpy
from . import geometry_contracts, node_names

NAME_COLLECTIONS = {
    '__uv_layers__': ('uv_layers',),
    '__vertex_groups__': ('vertex_groups',),
    '__attributes__': ('attributes',),
    '__color_attributes__': ('color_attributes', 'attributes'),
    '__bones__': ('bones', 'edit_bones'),
    '__bone_collections__': ('collections', 'collections_all'),
    '__shape_blocks__': ('key_blocks',),
    '__nodes__': ('nodes',),
    '__frames__': ('nodes',),
    '__modifiers__': ('modifiers',),
    '__constraints__': ('constraints',),
    '__pose_constraints__': ('constraints',),
    '__node_items__': node_names.NODE_ITEM_COLLECTIONS,
    '__interface_panels__': ('items_tree',),
    '__node_interfaces__': ('items_tree','inputs','outputs'),
}
_NESTED_COLLECTIONS = {name for names in NAME_COLLECTIONS.values() for name in names}

def name_lookups(source, require_bpy=True):
    """Index literal collection lookups, never comments or arbitrary strings."""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError, RecursionError):
        return set()
    result = set()
    for node in ast.walk(tree):
        receiver = value = None
        if isinstance(node, ast.Subscript):
            receiver, value = node.value, node.slice
        elif (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
              and node.func.attr == 'get' and node.args):
            receiver, value = node.func.value, node.args[0]
        if not (isinstance(receiver, ast.Attribute) and isinstance(value, ast.Constant)
                and isinstance(value.value, str)):
            continue
        parent = receiver.value
        is_data = (isinstance(parent, ast.Attribute) and parent.attr == 'data'
                   and isinstance(parent.value, ast.Name) and parent.value.id == 'bpy')
        if not is_data and receiver.attr not in _NESTED_COLLECTIONS:
            continue
        if require_bpy and not any(isinstance(n, ast.Name) and n.id == 'bpy'
                                   for n in ast.walk(receiver)):
            continue
        result.add((receiver.attr, value.value))
    return result

def _action_paths(action):
    for layer in action.layers:
        for strip in layer.strips:
            for bag in getattr(strip, 'channelbags', ()):
                for curve in bag.fcurves:
                    yield curve.data_path

class Preflight:
    def __init__(self):
        self.geometry_reasons = {}
        self.data_users = None
        self._lookups = None
        self._shared = {}

    def _lookup_index(self):
        if self._lookups is None:
            index = {}
            for text in bpy.data.texts:
                for lookup in name_lookups(text.as_string()):
                    index.setdefault(lookup, 'Script: ' + text.name)
            from . import nested_data
            for owner in nested_data.id_owners():
                animation = getattr(owner, 'animation_data', None)
                if animation is not None:
                    for curve in animation.drivers:
                        for lookup in name_lookups(curve.driver.expression):
                            index.setdefault(lookup, 'Driver: ' + owner.name + ' / ' + curve.data_path)
            self._lookups = index
        return self._lookups

    def _ensure_geometry(self):
        if self.data_users is None:
            self.data_users = {}
            for obj in bpy.data.objects:
                if obj.data is not None:
                    self.data_users.setdefault(obj.data.as_pointer(), []).append(obj)

    def _shared_reason(self, key, owner, old):
        collections = NAME_COLLECTIONS.get(key, ())
        if not collections:
            return ''
        pointer = owner.as_pointer()
        if pointer not in self._shared:
            lookups = {}
            animation = getattr(owner, 'animation_data', None)
            if animation is not None:
                actions = set()
                if animation.action is not None:
                    actions.add(animation.action)
                for track in animation.nla_tracks:
                    actions.update(strip.action for strip in track.strips if strip.action is not None)
                for action in actions:
                    if action.users > 1:
                        for path in _action_paths(action):
                            for lookup in name_lookups('owner.' + path, require_bpy=False):
                                lookups.setdefault(lookup, action.name + ' / ' + path)
            self._shared[pointer] = lookups
        for collection in collections:
            where = self._shared[pointer].get((collection, old))
            if where:
                return '\u5171\u4eab\u52a8\u4f5c\u5b58\u5728\u660e\u786e\u7684\u6309\u540d\u5f15\u7528: ' + where
        return ''

    def reason(self, key, owner, old, requested, field='name'):
        if field in ('label', 'description'):
            return ''
        collections = NAME_COLLECTIONS.get(key, (key,))
        index = self._lookup_index()
        for collection in collections:
            where = index.get((collection, old))
            if where:
                return '\u5b58\u5728\u660e\u786e\u7684\u6309\u540d\u67e5\u627e\uff0c\u9700\u6838\u5bf9\u5b57\u7b26\u4e32\u5f15\u7528: ' + where
        reason = self._shared_reason(key, owner, old)
        if reason:
            return reason
        if key == '__vertex_groups__':
            data = owner.data
            if any(getattr(mod, 'type', '') == 'ARMATURE' and mod.object and
                   (mod.object.data.bones.get(old) or mod.object.data.bones.get(requested))
                   for mod in owner.modifiers):
                return '\u9876\u70b9\u7ec4\u4e0e\u53d8\u5f62\u9aa8\u9abc\u540c\u540d\u5173\u8054\uff0c\u5df2\u4fdd\u7559\u539f\u540d'
            attributes = getattr(data, 'attributes', ())
            if hasattr(attributes, 'get') and (attributes.get(old) or attributes.get(requested)):
                return '\u9876\u70b9\u7ec4\u4e0e\u51e0\u4f55\u5c5e\u6027\u540d\u79f0\u51b2\u7a81\uff0c\u5df2\u4fdd\u7559\u539f\u540d'
        if key in ('__uv_layers__', '__vertex_groups__', '__attributes__', '__color_attributes__'):
            self._ensure_geometry()
            from . import nested_data
            for _, tree, _ in nested_data.node_trees():
                for node in tree.nodes:
                    if node.bl_idname == 'ShaderNodeUVMap' and node.from_instancer and node.uv_map == old:
                        return '\u5b9e\u4f8b\u7236\u7ea7\u7eb9\u7406\u5750\u6807\u5f15\u7528\u9700\u624b\u52a8\u6838\u5bf9\uff0c\u5df2\u4fdd\u7559\u539f\u540d'
            users = self.data_users.get(owner.as_pointer(), []) if key != '__vertex_groups__' else [owner]
            scope = tuple(obj.as_pointer() for obj in users)
            if scope not in self.geometry_reasons:
                self.geometry_reasons[scope] = geometry_contracts.reason(users, old)
            problem = self.geometry_reasons[scope]
            if problem:
                return problem
            if key == '__uv_layers__' and any(obj.particle_systems for obj in users):
                return '\u7c92\u5b50\u7cfb\u7edf\u7eb9\u7406\u5750\u6807\u5f15\u7528\u9700\u6838\u5bf9'
            if key in ('__attributes__', '__color_attributes__'):
                if any(obj.vertex_groups.get(old) or obj.vertex_groups.get(requested) for obj in users):
                    return '\u5c5e\u6027\u4e0e\u9876\u70b9\u7ec4\u540c\u540d\uff0c\u65e0\u6cd5\u786e\u5b9a\u540d\u79f0\u67e5\u627e\u7684\u5b9e\u9645\u76ee\u6807'
        if key == '__bones__':
            rigs = {obj.as_pointer() for obj in bpy.data.objects if obj.data == owner}
            for obj in bpy.data.objects:
                if any(mod.type == 'ARMATURE' and mod.object and mod.object.as_pointer() in rigs for mod in obj.modifiers):
                    if obj.vertex_groups.get(old) or obj.vertex_groups.get(requested):
                        return '\u9aa8\u9abc\u4e0e\u9876\u70b9\u7ec4\u5173\u8054\uff0c\u9700\u6210\u5957\u6539\u540d\uff0c\u5df2\u4fdd\u7559\u539f\u540d'
        return ''
