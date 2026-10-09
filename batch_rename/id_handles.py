"""Non-owning ID handles: only session identity strings enter scene RNA."""
import bpy
from bpy.app.handlers import persistent
_live = {}
_missing = set()


def _ids():
    for prop in bpy.data.bl_rna.properties:
        if prop.type == 'COLLECTION':
            cls = getattr(bpy.types, prop.fixed_type.identifier, None)
            if cls is not None and issubclass(cls, bpy.types.ID):
                yield from getattr(bpy.data, prop.identifier)


def remember(data):
    if data is None:
        return ''
    key = str(data.session_uid)
    _live[key] = data
    _missing.discard(key)
    return key


def resolve(key):
    if not key or key in _missing:
        return None
    data = _live.get(key)
    if data is not None:
        try:
            if str(data.session_uid) == key:
                return data
        except ReferenceError:
            pass
        _live.pop(key, None)
    _live.update((str(data.session_uid), data) for data in _ids())
    data = _live.get(key)
    if data is not None:
        return data
    _missing.add(key)
    return None


def handle(field):
    def get(row):
        return resolve(getattr(row, field))
    def set(row, data):
        setattr(row, field, remember(data))
    return property(get, set)


@persistent
def _invalidate(_unused=None):
    _live.clear()
    _missing.clear()


def register():
    for handlers in (bpy.app.handlers.load_pre, bpy.app.handlers.undo_pre, bpy.app.handlers.redo_pre):
        if _invalidate not in handlers:
            handlers.append(_invalidate)


def unregister():
    for handlers in (bpy.app.handlers.load_pre, bpy.app.handlers.undo_pre, bpy.app.handlers.redo_pre):
        if _invalidate in handlers:
            handlers.remove(_invalidate)
    _invalidate()


def prune():
    live = set()
    for scene in bpy.data.scenes:
        for category in scene.wkngr_categories:
            live.update(row.target_uid for row in category.entries)
        live.update(row.node_group_uid for row in scene.wkngr_sockets)
        live.update(row.material_uid for row in scene.wkngr_materials)
        for row in scene.wkngr_usage_rows:
            live.update((row.owner_uid,row.scene_uid,row.object_uid,row.collection_uid))
    for key in tuple(_live):
        if key not in live:
            del _live[key]
    _missing.intersection_update(live)
