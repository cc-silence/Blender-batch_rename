"""Temporary scan state: excluded from saves, cleared on load and disable."""
import bpy
from bpy.app.handlers import persistent
from . import nested_data, reg

FIELDS = ('wkngr_categories', 'wkngr_sockets', 'wkngr_materials','wkngr_usage_rows')
INDICES = ('wkngr_category_index', 'wkngr_socket_index', 'wkngr_material_index','wkngr_usage_index')
_pending = []
_needs_initial_cleanup = False


def _scenes():
    return [s for s in bpy.data.scenes if s.library is None and s.override_library is None and s.is_editable]


def _pack(row):
    result = {}
    for prop in row.bl_rna.properties:
        name = prop.identifier
        if name == 'rna_type' or prop.is_readonly and prop.type != 'COLLECTION':
            continue
        value = getattr(row, name)
        result[name] = [_pack(item) for item in value] if prop.type == 'COLLECTION' else value
    return result


def _unpack(row, values):
    for name, value in values.items():
        if isinstance(value, list):
            collection = getattr(row, name)
            for item in value:
                _unpack(collection.add(), item)
        else:
            setattr(row, name, value)


def clear_all():
    """Only scan rows; dictionary words, filters and settings are retained."""
    global _needs_initial_cleanup
    if _pending:
        raise RuntimeError('Cannot clear scan results during a save')
    count = 0
    for scene in _scenes():
        for category in scene.wkngr_categories:
            count += len(category.entries)
            nested_data.release(category.entries)
        count += len(scene.wkngr_sockets) + len(scene.wkngr_materials)
        for name in FIELDS:
            getattr(scene, name).clear()
        for name in INDICES:
            setattr(scene, name, 0)
        scene.wkngr_settings.lookup_summary = ''
    from . import id_handles
    id_handles._invalidate()
    _needs_initial_cleanup = False
    return count


def ensure_initialized():
    if _needs_initial_cleanup:
        clear_all()


@persistent
def _on_scene_update(_scene, _depsgraph):
    ensure_initialized()


@persistent
def _before_save(_filepath):
    ensure_initialized()
    if _pending:
        raise RuntimeError('Nested scan-cache save transaction')
    # Snapshot everything before mutation; Python ID wrappers do not add ID users.
    snapshots = [(scene, {name: [_pack(row) for row in getattr(scene, name)] for name in FIELDS},
                  {name: getattr(scene, name) for name in INDICES}) for scene in _scenes()]
    _pending.extend(snapshots)
    try:
        for scene, values, indices in snapshots:
            for name in FIELDS:
                getattr(scene, name).clear()
            for name in INDICES:
                setattr(scene, name, 0)
    except Exception:
        _after_save(_filepath)
        raise


@persistent
def _after_save(_filepath):
    try:
        for scene, values, indices in _pending:
            for name, rows in values.items():
                collection = getattr(scene, name)
                collection.clear()
                for row in rows:
                    _unpack(collection.add(), row)
            for name, value in indices.items():
                setattr(scene, name, value)
    finally:
        _pending.clear()


@persistent
def _on_load(_filepath):
    _pending.clear()
    clear_all()


class WKNGR_OT_ClearScan(bpy.types.Operator):
    bl_idname = 'wkngr.clear_scan'
    bl_label = '\u6e05\u7a7a batch_rename \u626b\u63cf\u8bb0\u5f55'
    bl_description = '\u6e05\u7a7a\u6240\u6709\u672c\u5730\u573a\u666f\u7684\u626b\u63cf\u7ed3\u679c\u548c\u672a\u5e94\u7528\u9884\u89c8'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        count = clear_all()
        self.report({'INFO'}, '\u5df2\u6e05\u9664 ' + str(count) + ' \u6761\u626b\u63cf\u8bb0\u5f55')
        return {'FINISHED'}


_classes = (WKNGR_OT_ClearScan,)

def _handlers():
    return ((bpy.app.handlers.save_pre, _before_save),
            (bpy.app.handlers.save_post, _after_save),
            (bpy.app.handlers.save_post_fail, _after_save),
            (bpy.app.handlers.load_post, _on_load),
            (bpy.app.handlers.depsgraph_update_post, _on_scene_update))


def register():
    global _needs_initial_cleanup
    _needs_initial_cleanup = True
    reg.register_classes(_classes)
    for handlers, callback in _handlers():
        if callback not in handlers:
            handlers.append(callback)


def unregister():
    global _needs_initial_cleanup
    for handlers, callback in _handlers():
        if callback in handlers:
            handlers.remove(callback)
    if hasattr(bpy.data, 'scenes'):
        if _pending:
            _after_save('')
        clear_all()
    else:
        _pending.clear()
    _needs_initial_cleanup = False
    reg.unregister_classes(_classes)
