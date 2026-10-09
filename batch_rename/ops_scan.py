"""Scan all data-block categories using the shared catalog."""
import bpy
from . import reg, data_catalog

class WKNGR_OT_Scan(bpy.types.Operator):
    bl_idname = "wkngr.scan"
    bl_label = "开始查找"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        try:
            count = data_catalog.scan_all(context.scene)
        except (OSError, ValueError, RuntimeError) as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        self.report({"INFO"}, f"找到 {count} 项，共 {len(context.scene.wkngr_categories)} 种数据类型")
        return {"FINISHED"}

_classes = (WKNGR_OT_Scan,)
def register(): reg.register_classes(_classes)
def unregister(): reg.unregister_classes(_classes)
