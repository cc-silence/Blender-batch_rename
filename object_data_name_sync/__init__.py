"""Rename object data without changing ownership, geometry or object names."""
import bpy
import uuid
from collections import Counter

bl_info = {
    'name': '\u7269\u4f53\u6570\u636e\u540c\u540d',
    'author': 'CC', 'version': (1, 0, 0), 'blender': (5, 1, 0),
    'category': 'Object',
}


def protected(item):
    return (item.library is not None or item.override_library is not None
            or not item.is_editable or item.is_property_readonly('name'))


def synchronize():
    stats = Counter()
    owners = {}
    for obj in bpy.data.objects:
        data = obj.data
        if data is None:
            stats['no_data'] += 1
            continue
        owners.setdefault(data, []).append(obj)
    plan = []
    for data, objects in owners.items():
        if protected(data) or any(protected(obj) for obj in objects):
            stats['readonly'] += 1
        elif len({obj.name for obj in objects}) != 1:
            stats['shared'] += 1
        elif data.name == objects[0].name:
            stats['unchanged'] += 1
        else:
            plan.append((data, data.name, objects[0].name))
    # Stage all candidates to resolve cycles (A -> B and B -> A) correctly.
    prefix = '__data_name_sync_' + uuid.uuid4().hex + '_'
    touched = []
    try:
        for index, (data, old, wanted) in enumerate(plan):
            touched.append((data, old))
            data.rename(prefix + str(index), mode='NEVER')
        for data, old, wanted in plan:
            data.rename(wanted, mode='NEVER')
            stats['renamed'] += 1
            if data.name != wanted:
                stats['suffix'] += 1
    except Exception:
        # Restore original names without stealing any unrelated data-block name.
        for index, (data, old) in enumerate(touched):
            data.rename(prefix + 'rollback_' + str(index), mode='NEVER')
        for data, old in touched:
            data.rename(old, mode='NEVER')
        raise
    return stats


class ODNS_OT_Synchronize(bpy.types.Operator):
    bl_idname = 'object.sync_all_data_names'
    bl_label = '\u6240\u6709\u7269\u4f53\uff1a\u6570\u636e\u540d\u79f0\u540c\u6b65\u4e3a\u7269\u4f53\u540d\u79f0'
    bl_description = '\u5904\u7406\u6574\u4e2a\u6587\u4ef6\uff1b\u8df3\u8fc7\u5173\u8054\u3001\u5e93\u8986\u76d6\u548c\u5171\u4eab\u6570\u636e\u51b2\u7a81\uff1b\u652f\u6301\u64a4\u9500'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            stats = synchronize()
        except (RuntimeError, TypeError, ReferenceError) as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        message = ('\u5df2\u6539\u540d {renamed}\uff1b\u5df2\u540c\u540d {unchanged}\uff1b'
                   '\u8df3\u8fc7\u53ea\u8bfb/\u5e93\u8986\u76d6 {readonly}\uff1b'
                   '\u8df3\u8fc7\u5171\u4eab\u51b2\u7a81 {shared}\uff1b'
                   '\u65e0\u6570\u636e\u7269\u4f53 {no_data}\uff1b\u91cd\u540d\u540e\u7f00 {suffix}').format_map(stats)
        self.report({'INFO'}, message)
        return {'FINISHED'}


class ODNS_PT_Panel(bpy.types.Panel):
    bl_label = '\u7269\u4f53\u6570\u636e\u540c\u540d'
    bl_idname = 'ODNS_PT_panel'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = '\u6570\u636e\u540c\u540d'

    def draw(self, context):
        self.layout.label(text='\u8303\u56f4\uff1a\u5f53\u524d\u6587\u4ef6\u5168\u90e8\u7269\u4f53')
        self.layout.operator(ODNS_OT_Synchronize.bl_idname, text='\u540c\u6b65\u6570\u636e\u540d\u79f0', icon='SORTALPHA')
        self.layout.label(text='\u81ea\u52a8\u8df3\u8fc7\u53ea\u8bfb\u548c\u5171\u4eab\u51b2\u7a81')


def menu_entry(self, context):
    self.layout.operator(ODNS_OT_Synchronize.bl_idname)


_CLASSES = (ODNS_OT_Synchronize, ODNS_PT_Panel)


def register():
    done = []
    try:
        for cls in _CLASSES:
            bpy.utils.register_class(cls)
            done.append(cls)
        bpy.types.VIEW3D_MT_object.append(menu_entry)
    except Exception:
        for cls in reversed(done):
            bpy.utils.unregister_class(cls)
        raise


def unregister():
    bpy.types.VIEW3D_MT_object.remove(menu_entry)
    for cls in reversed(_CLASSES):
        if 'bl_rna' in cls.__dict__:
            bpy.utils.unregister_class(cls)
