"""预设文件 + 词语 + 自定义字符 管理."""

import functools

import bpy
from bpy.app.handlers import persistent

from . import reg

from . import preset_manager


_scene_versions = {}
_syncing = False


def _fill_words(scene, data):
    scene.wkngr_words.clear()
    for original in sorted(data):
        item = scene.wkngr_words.add()
        item.cn, item.en = original, data[original]
    scene.wkngr_word_index = min(scene.wkngr_word_index, max(0, len(data) - 1))


def _fill_tokens(scene, tokens):
    scene.wkngr_tokens.clear()
    for value in tokens:
        scene.wkngr_tokens.add().value = value
    scene.wkngr_token_index = min(scene.wkngr_token_index, max(0, len(tokens) - 1))


def refresh_preset_words(context):
    scene = context.scene
    data = preset_manager.load_preset(scene.wkngr_settings.active_preset)
    _fill_words(scene, data)
    return data


def refresh_tokens(context):
    _fill_tokens(context.scene, preset_manager.load_custom_tokens())


def sync_scene(scene, force=False):
    global _syncing
    if _syncing or not hasattr(scene, "wkngr_settings") or scene.library is not None:
        return
    key = scene.session_uid
    signature = (scene.wkngr_settings.active_preset, preset_manager._revision)
    if not force and _scene_versions.get(key) == signature:
        return
    _syncing = True
    try:
        if key not in _scene_versions:
            from . import nested_data
            nested_data.ensure_scene(scene)
        data = preset_manager.load_preset(signature[0])
        tokens = preset_manager.load_custom_tokens()
        _fill_words(scene, data)
        _fill_tokens(scene, tokens)
    except (OSError, ValueError) as exc:
        # Do not repeatedly hit a corrupt file on every dependency graph update.
        print("WKNGR preset sync:", exc)
    finally:
        _scene_versions[key] = signature
        _syncing = False


@persistent
def _on_load(_dummy):
    from . import props
    _scene_versions.clear()
    preset_manager.invalidate_cache()
    try:
        props.refresh_preset_enum()
    except (OSError, ValueError) as exc:
        print("WKNGR preset list:", exc)
    for scene in bpy.data.scenes:
        sync_scene(scene)


@persistent
def _on_history(_dummy):
    # Undo restores Scene collections, but it does not undo dictionary files.
    _scene_versions.clear()
    for scene in bpy.data.scenes:
        sync_scene(scene)


@persistent
def _on_scene_update(scene, depsgraph):
    if scene.session_uid not in _scene_versions:
        live = {item.session_uid for item in bpy.data.scenes}
        for key in tuple(_scene_versions):
            if key not in live:
                del _scene_versions[key]
    sync_scene(scene)


def _file_operation(method):
    @functools.wraps(method)
    def execute(self, context):
        try:
            result = method(self, context)
            if result == {"FINISHED"}:
                for scene in bpy.data.scenes:
                    sync_scene(scene)
            return result
        except (OSError, ValueError) as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
    return execute


def _remap_preset_users(old, new):
    # Selection is per scene, but dictionary files are shared by all scenes.
    for scene in bpy.data.scenes:
        if scene.library is None and hasattr(scene, "wkngr_settings"):
            settings = scene.wkngr_settings
            if settings.get("_active_preset_name", "usr") == old:
                settings["_active_preset_name"] = new


class WKNGR_OT_PresetNew(bpy.types.Operator):
    bl_idname = "wkngr.preset_new"
    bl_label = "新建预设"
    bl_options = {"REGISTER"}  # 动文件,不给 UNDO
    preset_name: bpy.props.StringProperty(name="预设名", default="新预设")

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    @_file_operation
    def execute(self, context):
        from . import props
        name = preset_manager._safe_name(self.preset_name)
        if not name:
            self.report({"WARNING"}, "预设名为空")
            return {"CANCELLED"}
        if not preset_manager.create_preset(name):
            self.report({"WARNING"}, f"已存在: {name}")
            return {"CANCELLED"}
        props.refresh_preset_enum()  # 先刷枚举项,再赋值
        context.scene.wkngr_settings.active_preset = name
        refresh_preset_words(context)
        return {"FINISHED"}


class WKNGR_OT_PresetRemove(bpy.types.Operator):
    bl_idname = "wkngr.preset_remove"
    bl_label = "删除预设"
    bl_options = {"REGISTER"}  # 动文件,不给 UNDO(撤销回不到磁盘)

    def invoke(self, context, event):
        # 删除预设会清空词典内容,必须确认(usr 只清空不删文件)
        return context.window_manager.invoke_confirm(self, event)

    @_file_operation
    def execute(self, context):
        from . import props
        st = context.scene.wkngr_settings
        old = st.active_preset
        if not preset_manager.delete_preset(old):
            self.report({"WARNING"}, "删除失败")
            return {"CANCELLED"}
        _remap_preset_users(old, preset_manager.DEFAULT_PRESET)
        props.refresh_preset_enum()  # 先刷枚举项,再赋值,否则设不进新值
        names = preset_manager.list_presets()
        st.active_preset = names[0] if names else preset_manager.DEFAULT_PRESET
        refresh_preset_words(context)
        return {"FINISHED"}


class WKNGR_OT_PresetRename(bpy.types.Operator):
    bl_idname = "wkngr.preset_rename"
    bl_label = "重命名预设"
    bl_options = {"REGISTER"}  # 动文件,不给 UNDO
    preset_name: bpy.props.StringProperty(name="新名称", default="")

    def invoke(self, context, event):
        self.preset_name = context.scene.wkngr_settings.active_preset.rsplit("/", 1)[-1]
        return context.window_manager.invoke_props_dialog(self)

    @_file_operation
    def execute(self, context):
        from . import props
        st = context.scene.wkngr_settings
        old = st.active_preset
        new = preset_manager._safe_name(self.preset_name)
        if new and "/" in old:
            new = old.rsplit("/", 1)[0] + "/" + new
        if not preset_manager.rename_preset(old, new):
            self.report({"WARNING"}, "重命名失败(重名或不存在)")
            return {"CANCELLED"}
        props.refresh_preset_enum()  # 先刷枚举项,再赋值
        _remap_preset_users(old, new)
        st.active_preset = new
        return {"FINISHED"}


class WKNGR_OT_PresetReload(bpy.types.Operator):
    bl_idname = "wkngr.preset_reload"
    bl_label = "加载字典"
    bl_description = "重新读取当前选中的字典，在下方显示词条"
    bl_options = {"REGISTER"}

    @_file_operation
    def execute(self, context):
        from . import props
        errors = preset_manager.refresh_external_presets()
        props.refresh_preset_enum()
        refresh_preset_words(context)
        for error in errors:
            self.report({"WARNING"}, error)
        self.report({"INFO"}, "已刷新预设列表和当前字典词条")
        return {"FINISHED"}


class WKNGR_OT_PresetImport(bpy.types.Operator):
    bl_idname = "wkngr.preset_import"
    bl_label = "导入字典"
    bl_options = {"REGISTER"}
    filepath: bpy.props.StringProperty(name="文件路径", subtype="FILE_PATH")
    filter_glob: bpy.props.StringProperty(default="*.json", options={"HIDDEN"})

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    @_file_operation
    def execute(self, context):
        from . import props
        name = preset_manager.import_preset(self.filepath) if self.filepath else None
        preset_manager.invalidate_cache()
        props.refresh_preset_enum()
        if name:
            context.scene.wkngr_settings.active_preset = name
        refresh_preset_words(context)
        refresh_tokens(context)
        self.report({"INFO"}, "字典已加载")
        return {"FINISHED"}


class WKNGR_OT_PresetExport(bpy.types.Operator):
    bl_idname = "wkngr.preset_export"
    bl_label = "导出字典"
    bl_options = {"REGISTER"}
    filepath: bpy.props.StringProperty(name="文件路径", subtype="FILE_PATH")
    filter_glob: bpy.props.StringProperty(default="*.json", options={"HIDDEN"})
    check_existing: bpy.props.BoolProperty(default=True, options={"HIDDEN"})

    def check(self, context):
        if self.filepath and not self.filepath.lower().endswith(".json"):
            self.filepath += ".json"
            return True
        return False

    def invoke(self, context, event):
        self.filepath = context.scene.wkngr_settings.active_preset.rsplit("/", 1)[-1] + ".json"
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    @_file_operation
    def execute(self, context):
        if not self.filepath:
            self.report({"ERROR"}, "请选择导出路径")
            return {"CANCELLED"}
        preset_manager.export_preset(context.scene.wkngr_settings.active_preset, self.filepath)
        self.report({"INFO"}, "字典已导出")
        return {"FINISHED"}


class WKNGR_OT_WordAdd(bpy.types.Operator):
    bl_idname = "wkngr.word_add"
    bl_label = "添加词条"
    bl_options = {"REGISTER"}  # 动文件,不给 UNDO

    @_file_operation
    def execute(self, context):
        scene = context.scene
        st = scene.wkngr_settings
        cn, en = st.original_text.strip(), st.translate_text.strip()
        if not cn or not en:
            self.report({"WARNING"}, "原文和译文 都要填")
            return {"CANCELLED"}
        d = preset_manager.load_preset(st.active_preset)
        d[cn] = en
        preset_manager.save_preset(st.active_preset, d)
        refresh_preset_words(context)
        return {"FINISHED"}


class WKNGR_OT_WordRemove(bpy.types.Operator):
    bl_idname = "wkngr.word_remove"
    bl_label = "移除词条"
    bl_options = {"REGISTER"}  # 动文件,不给 UNDO

    @_file_operation
    def execute(self, context):
        scene = context.scene
        st = scene.wkngr_settings
        idx = scene.wkngr_word_index
        if 0 <= idx < len(scene.wkngr_words):
            cn = scene.wkngr_words[idx].cn
            d = preset_manager.load_preset(st.active_preset)
            d.pop(cn, None)
            preset_manager.save_preset(st.active_preset, d)
            refresh_preset_words(context)
            scene.wkngr_word_index = max(0, min(idx, len(scene.wkngr_words) - 1))
        return {"FINISHED"}


class WKNGR_OT_WordSave(bpy.types.Operator):
    bl_idname = "wkngr.word_save"
    bl_label = "保存词典"
    bl_description = "把词语列表存回 json(以磁盘为准回写,不会误删词典)"
    bl_options = {"REGISTER"}  # 动文件,不给 UNDO(撤销回不到磁盘)

    @_file_operation
    def execute(self, context):
        scene = context.scene
        st = scene.wkngr_settings
        # 关键:wkngr_words 是 per-Scene 集合,可能为空(换了场景/还没开过预设面板)。
        # 拿它直接覆盖文件会把整个词典清空,而且撤销也救不回来。
        # 所以这里以磁盘内容为准回写,只做安全落盘。
        d = preset_manager.load_preset(st.active_preset)
        preset_manager.save_preset(st.active_preset, d)
        refresh_preset_words(context)
        self.report({"INFO"}, f"已保存 {len(d)} 条到 {st.active_preset}.json")
        return {"FINISHED"}


class WKNGR_OT_TokenAdd(bpy.types.Operator):
    bl_idname = "wkngr.token_add"
    bl_label = "添加字符"
    bl_options = {"REGISTER"}  # 动文件,不给 UNDO

    @_file_operation
    def execute(self, context):
        scene = context.scene
        st = scene.wkngr_settings
        t = st.new_token_text.strip()
        if not t:
            self.report({"WARNING"}, "字符为空")
            return {"CANCELLED"}
        toks = preset_manager.load_custom_tokens()
        if t not in toks:
            toks.append(t)
            preset_manager.save_custom_tokens(toks)
        refresh_tokens(context)
        st.new_token_text = ""
        return {"FINISHED"}


class WKNGR_OT_TokenRemove(bpy.types.Operator):
    bl_idname = "wkngr.token_remove"
    bl_label = "删除字符"
    bl_options = {"REGISTER"}  # 动文件,不给 UNDO

    @_file_operation
    def execute(self, context):
        scene = context.scene
        idx = scene.wkngr_token_index
        toks = preset_manager.load_custom_tokens()
        if 0 <= idx < len(scene.wkngr_tokens):
            v = scene.wkngr_tokens[idx].value
            toks = [x for x in toks if x != v]
            preset_manager.save_custom_tokens(toks)
            refresh_tokens(context)
        return {"FINISHED"}


_classes = (
    WKNGR_OT_PresetNew, WKNGR_OT_PresetRemove, WKNGR_OT_PresetRename, WKNGR_OT_PresetReload,
    WKNGR_OT_PresetImport, WKNGR_OT_PresetExport, WKNGR_OT_WordAdd, WKNGR_OT_WordRemove, WKNGR_OT_WordSave,
    WKNGR_OT_TokenAdd, WKNGR_OT_TokenRemove,
)


def register():
    from . import props
    reg.register_classes(_classes)
    try:
        preset_manager.ensure_defaults()
        props.refresh_preset_enum()
    except (OSError, ValueError) as exc:
        print("WKNGR preset initialization:", exc)
    for handlers, callback in (
        (bpy.app.handlers.load_post, _on_load),
        (bpy.app.handlers.depsgraph_update_post, _on_scene_update),
        (bpy.app.handlers.undo_post, _on_history),
        (bpy.app.handlers.redo_post, _on_history),
    ):
        if callback not in handlers:
            handlers.append(callback)
    # Enabling an extension uses _RestrictData; initialize at the next scene event.
    for scene in getattr(bpy.data, "scenes", ()):
        sync_scene(scene)


def unregister():
    for handlers, callback in (
        (bpy.app.handlers.load_post, _on_load),
        (bpy.app.handlers.depsgraph_update_post, _on_scene_update),
        (bpy.app.handlers.undo_post, _on_history),
        (bpy.app.handlers.redo_post, _on_history),
    ):
        if callback in handlers:
            handlers.remove(callback)
    _scene_versions.clear()
    reg.unregister_classes(_classes)
