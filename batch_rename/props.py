"""属性定义 + Scene 挂载 + 预设枚举项(动态 items 必须在 __init__ 后才可用)."""

import bpy

from . import reg, id_handles

# Keep callback strings alive until unregister (RNA borrows their storage).
PRESET_ITEMS = [("usr", "默认词典", "", 0)]
_preset_item_cache = {"usr": PRESET_ITEMS[0]}


def refresh_preset_enum():
    from . import preset_manager
    names = preset_manager.list_presets()
    PRESET_ITEMS.clear()
    for index, name in enumerate(names):
        cached = _preset_item_cache.get(name)
        if cached is None:
            label = "默认词典" if name == "usr" else name
            cached = (name, label, "", index)
            _preset_item_cache[name] = cached
        PRESET_ITEMS.append((cached[0], cached[1], cached[2], index))
    return PRESET_ITEMS


def _preset_items(self, context):
    return PRESET_ITEMS


def _get_active_preset(self):
    name = self.get("_active_preset_name", "usr")
    return next((i for i, item in enumerate(PRESET_ITEMS) if item[0] == name), 0)


def _set_active_preset(self, value):
    self["_active_preset_name"] = PRESET_ITEMS[value][0]


def _on_active_preset_update(self, context):
    from .ops_preset import sync_scene
    sync_scene(self.id_data, force=True)


class WKNGR_FoundSocket(bpy.types.PropertyGroup):
    node_group_uid: bpy.props.StringProperty(options={"SKIP_SAVE"})
    node_group = id_handles.handle("node_group_uid")
    group_name: bpy.props.StringProperty(name="节点组")
    identifier: bpy.props.StringProperty(name="标识")
    tree_type: bpy.props.StringProperty(name="类型")
    in_out: bpy.props.StringProperty(name="方向")  # INPUT / OUTPUT
    old_name: bpy.props.StringProperty(name="原名")
    new_name: bpy.props.StringProperty(name="新名")


class WKNGR_FoundMaterial(bpy.types.PropertyGroup):
    material_uid: bpy.props.StringProperty(options={"SKIP_SAVE"})
    material = id_handles.handle("material_uid")
    mat_key: bpy.props.StringProperty(name="标识")  # 扫描时的材质名,用于找回
    old_name: bpy.props.StringProperty(name="原名")
    new_name: bpy.props.StringProperty(name="新名")


class WKNGR_UsageRow(bpy.types.PropertyGroup):
    reference_depth: bpy.props.IntProperty(options={'SKIP_SAVE'})
    reference_kind: bpy.props.IntProperty(options={'SKIP_SAVE'})
    excluded: bpy.props.BoolProperty(options={'SKIP_SAVE'})
    scene_uid: bpy.props.StringProperty(options={'SKIP_SAVE'})
    view_layer_name: bpy.props.StringProperty(options={'SKIP_SAVE'})
    object_uid: bpy.props.StringProperty(options={'SKIP_SAVE'})
    collection_uid: bpy.props.StringProperty(options={'SKIP_SAVE'})
    location_label: bpy.props.StringProperty(options={'SKIP_SAVE'})
    owner_uid: bpy.props.StringProperty(options={'SKIP_SAVE'})
    path: bpy.props.StringProperty()
    direct: bpy.props.BoolProperty(default=True)

class WKNGR_DataItem(bpy.types.PropertyGroup):
    target_uid: bpy.props.StringProperty(options={"SKIP_SAVE"})
    target = id_handles.handle("target_uid")
    identifier: bpy.props.StringProperty(name="接口标识")
    old_name: bpy.props.StringProperty(name="原名")
    new_name: bpy.props.StringProperty(name="新名")
    cache_key: bpy.props.StringProperty(options={"SKIP_SAVE"})
    field: bpy.props.StringProperty(default="name")
    context_label: bpy.props.StringProperty(name="所属数据")
    read_only: bpy.props.BoolProperty(name="只读")


class WKNGR_DataCategory(bpy.types.PropertyGroup):
    key: bpy.props.StringProperty()
    label: bpy.props.StringProperty(name="数据类型")
    entries: bpy.props.CollectionProperty(type=WKNGR_DataItem)
    item_index: bpy.props.IntProperty(default=0)


class WKNGR_PresetWord(bpy.types.PropertyGroup):
    cn: bpy.props.StringProperty(name="原文")
    en: bpy.props.StringProperty(name="译文")


class WKNGR_CustomToken(bpy.types.PropertyGroup):
    value: bpy.props.StringProperty(name="字符")


SCAN_TARGET_ITEMS = (
    ("BOTH", "节点组和材质", "节点组和材质都查"),
    ("SOCKET", "节点组", "只查节点组"),
    ("MATERIAL", "材质", "只查材质"),
)


TREE_FILTER_ITEMS = (
    ("ALL", "全部", ""),
    ("GEOMETRY", "几何", ""),
    ("SHADER", "着色", ""),
    ("COMPOSITING", "合成", ""),
    ("OTHER", "其他", ""),
)


DISPLAY_MODE_ITEMS = (
    ("SOCKET", "节点组", "", 1),
    ("MATERIAL", "材质", "", 2),
)


def _get_display_mode(self):
    value = self.get("display_mode", 1)
    return value if value in (1, 2) else 1


def _set_display_mode(self, value):
    self["display_mode"] = value


REPLACE_SCOPE_ITEMS = (
    ("ALL", "全部", ""),
    ("SOCKET", "节点组", ""),
    ("MATERIAL", "材质", ""),
)


class WKNGR_Settings(bpy.types.PropertyGroup):
    tool_mode: bpy.props.EnumProperty(name='\u529f\u80fd',items=(
        ('RENAME','\u6279\u91cf\u6539\u4e2d\u6587',''),
        ('SYNC','\u6570\u636e\u540d\u79f0\u540c\u6b65',''),
        ('CAPITAL','\u9996\u5b57\u6bcd\u5927\u5199',''),
        ('LOOKUP','\u5f15\u7528\u67e5\u627e','')),default='RENAME')
    lookup_kind: bpy.props.EnumProperty(name='\u6570\u636e\u7c7b\u578b',items=(
        ('objects','\u7269\u4f53',''),('collections','\u96c6\u5408',''),
        ('materials','\u6750\u8d28',''),('node_groups','\u8282\u70b9\u7ec4','')),default='objects')
    lookup_name: bpy.props.StringProperty(name='\u540d\u79f0')
    lookup_summary: bpy.props.StringProperty(options={'SKIP_SAVE'})
    scan_target: bpy.props.EnumProperty(
        name="扫描目标", items=SCAN_TARGET_ITEMS, default="BOTH",
    )
    tree_filter: bpy.props.EnumProperty(
        name="节点类型", items=TREE_FILTER_ITEMS, default="ALL",
    )
    display_mode: bpy.props.EnumProperty(
        name="分组", items=DISPLAY_MODE_ITEMS, default="SOCKET",
        get=_get_display_mode, set=_set_display_mode,
    )
    custom_enable: bpy.props.BoolProperty(name="启用附加字符", default=True)
    custom_quick: bpy.props.StringProperty(
        name="附加字符",
        description="用英文分号 ; 分隔多个字符串，名称内的逗号和空格保留。例：_tmp;旧版",
        default="",
    )
    replace_from: bpy.props.StringProperty(name="查找", default="")
    replace_to: bpy.props.StringProperty(name="替换为", default="")
    replace_scope: bpy.props.EnumProperty(
        name="范围", items=REPLACE_SCOPE_ITEMS, default="ALL",
    )
    active_preset: bpy.props.EnumProperty(
        name="预设文件", items=_preset_items, get=_get_active_preset, set=_set_active_preset,
        update=_on_active_preset_update,
    )
    original_text: bpy.props.StringProperty(name="原文", default="")
    translate_text: bpy.props.StringProperty(name="译文", default="")
    new_token_text: bpy.props.StringProperty(name="字符", default="")


_classes = (
    WKNGR_UsageRow, WKNGR_DataItem, WKNGR_DataCategory,
    WKNGR_FoundSocket,
    WKNGR_FoundMaterial,
    WKNGR_PresetWord,
    WKNGR_CustomToken,
    WKNGR_Settings,
)

_SCENE_ATTRS = (
    "wkngr_usage_rows", "wkngr_usage_index",
    "wkngr_categories", "wkngr_category_index",
    "wkngr_sockets", "wkngr_socket_index",
    "wkngr_materials", "wkngr_material_index",
    "wkngr_words", "wkngr_word_index",
    "wkngr_tokens", "wkngr_token_index",
    "wkngr_settings",
)


def register():
    reg.register_classes(_classes)
    bpy.types.Scene.wkngr_usage_rows = bpy.props.CollectionProperty(type=WKNGR_UsageRow)
    bpy.types.Scene.wkngr_usage_index = bpy.props.IntProperty(default=0)
    bpy.types.Scene.wkngr_categories = bpy.props.CollectionProperty(type=WKNGR_DataCategory)
    bpy.types.Scene.wkngr_category_index = bpy.props.IntProperty(default=0)
    bpy.types.Scene.wkngr_sockets = bpy.props.CollectionProperty(type=WKNGR_FoundSocket)
    bpy.types.Scene.wkngr_socket_index = bpy.props.IntProperty(default=0)
    bpy.types.Scene.wkngr_materials = bpy.props.CollectionProperty(type=WKNGR_FoundMaterial)
    bpy.types.Scene.wkngr_material_index = bpy.props.IntProperty(default=0)
    bpy.types.Scene.wkngr_words = bpy.props.CollectionProperty(type=WKNGR_PresetWord)
    bpy.types.Scene.wkngr_word_index = bpy.props.IntProperty(default=0)
    bpy.types.Scene.wkngr_tokens = bpy.props.CollectionProperty(type=WKNGR_CustomToken)
    bpy.types.Scene.wkngr_token_index = bpy.props.IntProperty(default=0)
    bpy.types.Scene.wkngr_settings = bpy.props.PointerProperty(type=WKNGR_Settings)


def unregister():
    for attr in _SCENE_ATTRS:
        if hasattr(bpy.types.Scene, attr):
            delattr(bpy.types.Scene, attr)
    reg.unregister_classes(_classes)
    PRESET_ITEMS[:] = [("usr", "默认词典", "", 0)]
    _preset_item_cache.clear()
