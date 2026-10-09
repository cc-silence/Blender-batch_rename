"""Preview all scanned categories and apply one global rename plan."""
import bpy
from . import reg, preset_manager, utils, data_catalog

class WKNGR_OT_AutoFill(bpy.types.Operator):
    bl_idname = "wkngr.auto_fill"
    bl_label = "用预设自动填充"
    bl_description = "用所有字典局部翻译全部已扫描数据类型，仅生成预览"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        categories = list(context.scene.wkngr_categories)
        if not categories: return {"CANCELLED"}
        try:
            translate = utils.make_partial_translator(preset_manager.load_translation_dictionary(context.scene.wkngr_settings.active_preset))
        except (OSError, ValueError) as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        count = 0
        for category in categories:
            for item in category.entries:
                if item.read_only: continue
                translated, matches = translate(item.old_name)
                if matches:
                    item.new_name = translated
                    count += 1
        self.report({"INFO"}, f"已填充 {count} 项")
        return {"FINISHED"}

class WKNGR_OT_PreviewReplace(bpy.types.Operator):
    bl_idname = "wkngr.preview_replace"
    bl_label = "预览替换"
    bl_description = "仅替换全部已扫描数据类型的预览名称"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        categories = context.scene.wkngr_categories
        settings = context.scene.wkngr_settings
        if not categories or not settings.replace_from: return {"CANCELLED"}
        for category in categories:
            for item in category.entries:
                if not item.read_only:
                    item.new_name = item.new_name.replace(settings.replace_from, settings.replace_to)
        return {"FINISHED"}

class WKNGR_OT_Reset(bpy.types.Operator):
    bl_idname = "wkngr.reset"
    bl_label = "重置为原名"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        category = data_catalog.active_category(context.scene)
        if category is None: return {"CANCELLED"}
        for item in category.entries: item.new_name = item.old_name
        return {"FINISHED"}

class WKNGR_OT_Apply(bpy.types.Operator):
    bl_idname = "wkngr.apply"
    bl_label = "应用修改"
    bl_description = "统一应用全部已扫描类型，同步名称引用并刷新"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        if not context.scene.wkngr_categories: return {"CANCELLED"}
        try:
            count, errors, collisions = data_catalog.apply_all(context.scene)
        except (OSError, ValueError) as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        for error in errors[:5]: self.report({"WARNING"}, error)
        if collisions: self.report({"WARNING"}, "重名已自动加后缀: " + '; '.join(collisions[:5]))
        if errors:
            self.report({"WARNING"}, f"\u5df2\u5e94\u7528 {count} \u9879\uff0c{len(errors)} \u9879\u672a\u5e94\u7528\uff1a{errors[0]}")
        elif count == 0:
            self.report({"WARNING"}, "\u6ca1\u6709\u53ef\u5e94\u7528\u7684\u65b0\u540d\u79f0\uff0c\u8bf7\u786e\u8ba4\u5168\u90e8\u7c7b\u578b\u7684\u65b0\u540d\u4e0e\u539f\u540d\u4e0d\u540c")
        else:
            self.report({"INFO"}, f"\u5df2\u5e94\u7528 {count} \u9879\uff0c\u5168\u90e8\u7c7b\u578b\u5df2\u5237\u65b0")
        return {"FINISHED"}

_classes = (WKNGR_OT_AutoFill, WKNGR_OT_PreviewReplace, WKNGR_OT_Reset, WKNGR_OT_Apply)
def register(): reg.register_classes(_classes)
def unregister(): reg.unregister_classes(_classes)
