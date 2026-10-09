"""Runtime discovery and typed scan results for all Blender ID collections."""
import bpy
from . import utils, preset_manager, nested_data, name_references, name_safety

SOCKETS = '__node_interfaces__'
LABELS = {
'actions':'动作','annotations':'注释','armatures':'骨架','brushes':'笔刷','cache_files':'缓存文件',
'cameras':'相机','collections':'集合','curves':'曲线','fonts':'字体','grease_pencils':'蜡笔','hair_curves':'毛发曲线',
'images':'图像','lattices':'晶格','libraries':'链接库','lightprobes':'光照探头','lights':'灯光','linestyles':'线条样式',
'masks':'遮罩','materials':'材质','meshes':'网格','metaballs':'融球','movieclips':'影片片段','node_groups':'节点组',
'objects':'物体','paint_curves':'绘制曲线','palettes':'调色板','particles':'粒子设置','pointclouds':'点云',
'scenes':'场景','screens':'屏幕布局','shape_keys':'形态键数据','sounds':'声音','speakers':'扬声器','texts':'文本',
'textures':'纹理','volumes':'体积','window_managers':'窗口管理器','workspaces':'工作区','worlds':'世界',
SOCKETS:'节点组接口',
}


def data_types():
    result = {}
    for prop in bpy.data.bl_rna.properties:
        if prop.type == 'COLLECTION':
            cls = getattr(bpy.types, prop.fixed_type.identifier, None)
            if cls is not None and cls is not bpy.types.ID and issubclass(cls, bpy.types.ID):
                result[prop.identifier] = LABELS.get(prop.identifier, bpy.app.translations.pgettext_iface(prop.name))
    result[SOCKETS] = LABELS[SOCKETS]
    result.update(nested_data.LABELS)
    return result


def active_category(scene):
    index = scene.wkngr_category_index
    return scene.wkngr_categories[index] if 0 <= index < len(scene.wkngr_categories) else None


def filters(scene):
    settings = scene.wkngr_settings
    tokens = preset_manager.load_custom_tokens() + utils.parse_quick_tokens(settings.custom_quick) if settings.custom_enable else []
    return list(dict.fromkeys(tokens)), settings.custom_enable


def editable(target):
    try:
        return utils.is_editable(target) and not target.is_property_readonly('name')
    except (ReferenceError, AttributeError):
        return False


def matches_for(key, tokens, custom):
    if key in nested_data.LABELS:
        yield from nested_data.matches(key, tokens, custom)
    elif key == SOCKETS:
        for owner in bpy.data.node_groups:
            for socket, direction in utils.iter_interface_sockets(owner):
                if utils.should_show(socket.name, tokens, custom):
                    yield owner, socket.name, str(socket.identifier), not editable(owner)
    else:
        for target in getattr(bpy.data, key, ()):
            if utils.should_show(target.name, tokens, custom):
                yield target, target.name, '', not editable(target)


def fill_category(category, entries):
    nested_data.release(category.entries)
    category.entries.clear()
    category.item_index = 0
    for record in entries:
        target, name, identifier, readonly = record[:4]
        item = category.entries.add()
        item.target = target
        item.identifier = identifier
        item.old_name = item.new_name = name
        item.read_only = readonly
        if len(record) > 4:
            item.cache_key = nested_data.remember(record[4], category.id_data)
            item.field = record[5]
            item.context_label = record[6]


def scan_all(scene):
    from . import scan_cache
    scan_cache.ensure_initialized()
    tokens, custom = filters(scene)
    selected = active_category(scene)
    old_key = selected.key if selected else ''
    for category in scene.wkngr_categories:
        nested_data.release(category.entries)
    scene.wkngr_categories.clear()
    scene.wkngr_sockets.clear()
    scene.wkngr_materials.clear()
    with nested_data.scan_session():
        for key, label in sorted(data_types().items()):
            entries = iter(matches_for(key, tokens, custom))
            first = next(entries, None)
            if first is None:
                continue
            category = scene.wkngr_categories.add()
            category.key, category.label = key, label
            from itertools import chain
            fill_category(category, chain((first,), entries))
    scene.wkngr_category_index = next((i for i, c in enumerate(scene.wkngr_categories) if c.key == old_key), 0)
    from . import id_handles
    id_handles.prune()
    return sum(len(c.entries) for c in scene.wkngr_categories)


def _preview_identity(row):
    owner = row.target
    if owner is None:
        return None
    target = nested_data.resolve(row.cache_key) if row.cache_key else None
    if row.cache_key and target is None:
        return None
    return (owner.session_uid, target.as_pointer() if target is not None else 0,
            row.identifier, row.field, row.old_name)


def refresh_category(scene, key, filter_values=None, drafts=None):
    tokens, custom = filter_values if filter_values is not None else filters(scene)
    for index, category in enumerate(scene.wkngr_categories):
        if category.key != key:
            continue
        with nested_data.scan_session():
            fill_category(category, matches_for(key, tokens, custom))
        if drafts:
            for row in category.entries:
                identity = _preview_identity(row)
                if identity in drafts:
                    row.new_name = drafts[identity]
        if not category.entries:
            scene.wkngr_categories.remove(index)
            scene.wkngr_category_index = min(index, max(0, len(scene.wkngr_categories) - 1))
        return


def apply_category(scene):
    """Internal single-category entrypoint uses the same global planner."""
    from . import rename_plan
    category = active_category(scene)
    if category is None:
        return 0, [], []
    key = category.key
    with nested_data.validation_session():
        drafts = {identity: row.new_name for row in category.entries
                  if row.new_name != row.old_name and (identity := _preview_identity(row)) is not None}
    result = rename_plan.apply([category])
    refresh_category(scene,key,drafts=drafts)
    return result


def apply_all(scene):
    """Plan every category against one snapshot, then refresh once."""
    from . import rename_plan
    with nested_data.validation_session():
        drafts = {(category.key,identity): row.new_name
                  for category in scene.wkngr_categories for row in category.entries
                  if row.new_name != row.old_name and (identity := _preview_identity(row)) is not None}
    result = rename_plan.apply(list(scene.wkngr_categories))
    scan_all(scene)
    with nested_data.validation_session():
        for category in scene.wkngr_categories:
            for row in category.entries:
                identity = (category.key,_preview_identity(row))
                if identity in drafts:
                    row.new_name = drafts[identity]
    return result
