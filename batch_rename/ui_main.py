"""上面板:查询 + 双堆栈列表 + 批量替换.

所有 icon 都走 utils.ui_icon() 校验,避免 Blender 版本枚举差异导致 draw 崩溃.
"""

import bpy

from . import reg

from . import utils, data_catalog


class WKNGR_UL_Sockets(bpy.types.UIList):
    bl_idname = "WKNGR_UL_Sockets"

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)
        tt = {"GEOMETRY": "几何", "SHADER": "着色", "COMPOSITING": "合成"}.get(item.tree_type, "其他")
        io = "输入" if item.in_out == "INPUT" else "输出"
        row.label(text=f"{tt}|{io}", icon=utils.ui_icon("NODETREE"))
        row.label(text=f"{item.group_name} : {item.old_name}")
        row.prop(item, "new_name", text="")


class WKNGR_UL_Materials(bpy.types.UIList):
    bl_idname = "WKNGR_UL_Materials"

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)
        row.label(text="", icon=utils.ui_icon("MATERIAL"))
        row.label(text=item.old_name)
        row.prop(item, "new_name", text="")


class WKNGR_UL_Categories(bpy.types.UIList):
    bl_idname = "WKNGR_UL_Categories"

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)
        row.label(text=item.label)
        row.label(text=str(len(item.entries)))


class WKNGR_UL_Data(bpy.types.UIList):
    bl_idname = "WKNGR_UL_Data"

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)
        label = item.old_name
        if item.context_label:
            label = item.context_label + " : " + label
        elif item.identifier and item.target:
            label = item.target.name + " : " + label
        row.label(text=label, icon=utils.ui_icon("LOCKED" if item.read_only else "NONE"))
        field = row.row(align=True)
        field.enabled = not item.read_only
        field.prop(item, "new_name", text="")


def draw_rename(layout, scene):
    st = scene.wkngr_settings
    box = layout.box()
    box.label(text="自定义字符过滤（用 ; 分隔）", icon=utils.ui_icon("SORTALPHA"))
    row = box.row(align=True)
    row.prop(st, "custom_quick", text="")
    row.prop(st, "custom_enable", text="启用")
    layout.operator("wkngr.scan", icon=utils.ui_icon("VIEWZOOM"))

    split = layout.split(factor=0.32)
    left, right = split.column(), split.column()
    left.label(text="数据类型 / 数量")
    left.template_list("WKNGR_UL_Categories", "", scene, "wkngr_categories", scene, "wkngr_category_index", rows=10)
    category = data_catalog.active_category(scene)
    if category:
        right.label(text=f"{category.label} ({len(category.entries)})")
        right.template_list("WKNGR_UL_Data", "", category, "entries", category, "item_index", rows=10)
    else:
        right.label(text="没有符合条件的数据")

    box = layout.box()
    box.label(text="批量替换（全部已扫描类型）", icon=utils.ui_icon("SETTINGS"))
    row = box.row(align=True)
    row.prop(st, "replace_from", text="查找")
    row.prop(st, "replace_to", text="替换为")
    row = layout.row(align=True)
    row.enabled = category is not None
    row.operator("wkngr.preview_replace", icon=utils.ui_icon("AUTOMERGE_ON"))
    row.operator("wkngr.auto_fill", icon=utils.ui_icon("AUTO"))
    row.operator("wkngr.apply", icon=utils.ui_icon("CHECKMARK"))


class WKNGR_UL_Usage(bpy.types.UIList):
    bl_idname='WKNGR_UL_Usage'
    def draw_item(self,context,layout,data,item,icon,active_data,active_propname,index):
        row=layout.row(align=True)
        row.label(text=(item.location_label or item.path)+(' | 集合已排除' if item.excluded else ''))
        action=row.row(align=True);action.enabled=bool(item.scene_uid and (item.object_uid or item.collection_uid or item.owner_uid))
        button=action.operator('wkngr.locate_usage',text='\u9009\u62e9 / \u5b9a\u4f4d',icon=utils.ui_icon('VIEWZOOM'))
        button.index=index

def draw_main(layout,scene):
    from . import ops_tools
    st=scene.wkngr_settings
    layout.prop(st,'tool_mode',text='\u529f\u80fd')
    if st.tool_mode=='RENAME':
        layout.label(text='\u6279\u91cf\u6539\u4e2d\u6587')
        draw_rename(layout,scene)
    elif st.tool_mode=='SYNC':
        layout.label(text='\u6574\u4e2a\u6587\u4ef6\uff1a\u7269\u4f53\u6570\u636e\u540d\u79f0\u540c\u6b65')
        layout.label(text='\u81ea\u52a8\u8df3\u8fc7\u5173\u8054\u3001\u9501\u5b9a\u548c\u5171\u4eab\u51b2\u7a81')
        layout.operator('wkngr.sync_data_names',icon=utils.ui_icon('SORTALPHA'))
    elif st.tool_mode=='CAPITAL':
        layout.label(text='\u6574\u4e2a\u6587\u4ef6\uff1a\u7269\u4f53 / \u96c6\u5408 / \u6750\u8d28')
        layout.label(text='\u4fdd\u7559\u540d\u79f0\u5176\u4f59\u90e8\u5206\uff0c\u81ea\u52a8\u8df3\u8fc7\u9501\u5b9a\u6570\u636e')
        layout.operator('wkngr.capitalize_names',icon=utils.ui_icon('SORTALPHA'))
    else:
        layout.prop(st,'lookup_kind',text='\u7c7b\u578b')
        layout.prop_search(st,'lookup_name',bpy.data,st.lookup_kind,text='\u76ee\u6807')
        row=layout.row(align=True)
        row.operator('wkngr.find_usage',icon=utils.ui_icon('VIEWZOOM'))
        row.operator('wkngr.usage_window',text='\u7a97\u53e3\u663e\u793a',icon=utils.ui_icon('WINDOW'))
        ops_tools.draw_usage(layout,scene)

class WKNGR_PT_Main_Node(bpy.types.Panel):
    bl_label = "数据工具"
    bl_idname = "WKNGR_PT_Main_Node"
    bl_space_type = "NODE_EDITOR"
    bl_region_type = "UI"
    bl_category = "batch_rename"

    def draw(self, context):
        draw_main(self.layout, context.scene)


class WKNGR_PT_Main_View3D(bpy.types.Panel):
    bl_label = "数据工具"
    bl_idname = "WKNGR_PT_Main_View3D"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "batch_rename"

    def draw(self, context):
        draw_main(self.layout, context.scene)


_classes = (WKNGR_UL_Usage, WKNGR_UL_Categories, WKNGR_UL_Data, WKNGR_UL_Sockets, WKNGR_UL_Materials, WKNGR_PT_Main_Node, WKNGR_PT_Main_View3D)


def register():
    reg.register_classes(_classes)


def unregister():
    reg.unregister_classes(_classes)
