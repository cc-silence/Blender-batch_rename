"""下面板:Translate Setting 预设字典 + 自定义字符管理.

所有 icon 都走 utils.ui_icon() 校验,避免 Blender 版本枚举差异导致 draw 崩溃.
"""

import bpy

from . import reg

from . import utils


class WKNGR_UL_Words(bpy.types.UIList):
    bl_idname = "WKNGR_UL_Words"

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)
        row.label(text=item.cn)
        row.label(text="->", icon=utils.ui_icon("FORWARD"))
        row.label(text=item.en)


class WKNGR_UL_Tokens(bpy.types.UIList):
    bl_idname = "WKNGR_UL_Tokens"

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        layout.label(text=item.value, icon=utils.ui_icon("FONT_DATA"))


def draw_preset(layout, context):
    scene = context.scene
    st = scene.wkngr_settings

    layout.prop(st, "active_preset", text="翻译字典")

    row = layout.row(align=True)
    row.operator("wkngr.preset_new", icon=utils.ui_icon("ADD"), text="添加预设")
    row.operator("wkngr.preset_remove", icon=utils.ui_icon("REMOVE"), text="移除")
    row.operator("wkngr.preset_rename", icon=utils.ui_icon("GREASEPENCIL"), text="重命名")
    row.operator("wkngr.preset_reload", icon=utils.ui_icon("FILE_REFRESH"), text="加载")

    layout.prop(st, "original_text", text="原文")
    layout.prop(st, "translate_text", text="译文")
    row = layout.row(align=True)
    row.operator("wkngr.word_add", text="添加词条")
    row.operator("wkngr.word_remove", text="移除词条")
    row.operator("wkngr.word_save", text="保存词典")
    row.operator("wkngr.preset_export", text="导出字典")

    layout.template_list("WKNGR_UL_Words", "", scene, "wkngr_words", scene, "wkngr_word_index", rows=6)

    box = layout.box()
    box.label(text="自定义字符 (命中即显示)", icon=utils.ui_icon("SORTALPHA"))
    box.template_list("WKNGR_UL_Tokens", "", scene, "wkngr_tokens", scene, "wkngr_token_index", rows=3)
    row = box.row(align=True)
    row.prop(st, "new_token_text", text="")
    row.operator("wkngr.token_add", text="", icon=utils.ui_icon("ADD"))
    row.operator("wkngr.token_remove", text="", icon=utils.ui_icon("REMOVE"))


class WKNGR_PT_Preset_Node(bpy.types.Panel):
    bl_label = "翻译设置"
    bl_idname = "WKNGR_PT_Preset_Node"
    bl_space_type = "NODE_EDITOR"
    bl_region_type = "UI"
    bl_category = "batch_rename"
    bl_parent_id = "WKNGR_PT_Main_Node"
    bl_options = {"DEFAULT_CLOSED"}

    @classmethod
    def poll(cls,context):
        return getattr(getattr(context.scene,'wkngr_settings',None),'tool_mode','RENAME')=='RENAME'

    def draw(self, context):
        draw_preset(self.layout, context)


class WKNGR_PT_Preset_View3D(bpy.types.Panel):
    bl_label = "翻译设置"
    bl_idname = "WKNGR_PT_Preset_View3D"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "batch_rename"
    bl_parent_id = "WKNGR_PT_Main_View3D"
    bl_options = {"DEFAULT_CLOSED"}

    @classmethod
    def poll(cls,context):
        return getattr(getattr(context.scene,'wkngr_settings',None),'tool_mode','RENAME')=='RENAME'

    def draw(self, context):
        draw_preset(self.layout, context)


_classes = (WKNGR_UL_Words, WKNGR_UL_Tokens, WKNGR_PT_Preset_Node, WKNGR_PT_Preset_View3D)


def register():
    reg.register_classes(_classes)


def unregister():
    reg.unregister_classes(_classes)
