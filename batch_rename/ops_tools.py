"""Naming utilities and reference lookup operators."""
import bpy
from . import reg,id_handles,scan_cache,data_tools,usage_index,utils,usage_visibility,outliner_focus

def capitalize_all():
    from . import rename_plan
    operations,skipped={},0
    for key in ('objects','collections','materials'):
        for data in getattr(bpy.data,key):
            if data_tools.protected(data):
                skipped+=1;continue
            wanted=data.name[:1].upper()+data.name[1:]
            if wanted!=data.name:
                operations[(data.as_pointer(),'name')]={'owner':data,'target':data,'field':'name',
                    'old':data.name,'desired':wanted,'key':key}
    count,errors,collisions=rename_plan.execute(operations,{},[])
    return count,skipped,errors,collisions

def _scene_contexts(objects):
    # Sync only scenes with actual object readers. Blender 5.2 may leave inactive
    # layers uninitialized or stale; active_layer_collection synchronizes membership.
    wanted={obj.as_pointer():obj for obj in objects};contexts={}
    if not wanted:return contexts
    for scene in bpy.data.scenes:
        readers={obj.as_pointer() for obj in scene.collection.all_objects} & wanted.keys()
        if not readers:continue
        for layer in scene.view_layers:
            active_collection=layer.active_layer_collection  # Native hierarchy sync without geometry evaluation.
            included={obj.as_pointer() for obj in layer.objects}
            for pointer in readers:
                excluded=pointer not in included and any(part.exclude for part in usage_visibility.choose_path(layer,wanted[pointer]))
                contexts.setdefault(pointer,[]).append((scene,layer.name,excluded))
    return contexts


def _collection_contexts(collections):
    wanted={collection.as_pointer() for collection in collections};contexts={}
    if not wanted:return contexts
    for scene in bpy.data.scenes:
        for layer in scene.view_layers:
            active_collection=layer.active_layer_collection
            found={};pending=[(layer.layer_collection,False,())]
            while pending:
                branch,blocked,ancestors=pending.pop();blocked=blocked or branch.exclude
                path=(*ancestors,branch.name);depth=len(path)
                pointer=branch.collection.as_pointer()
                if pointer in wanted:
                    score=(blocked,depth)
                    if pointer not in found or score<found[pointer][0]:found[pointer]=(score,path)
                pending.extend((child,blocked,path) for child in branch.children)
            for pointer,((excluded,depth),path) in found.items():
                contexts.setdefault(pointer,[]).append((scene,layer.name,excluded,' / '.join(path)))
    return contexts


def lookup(scene,target):
    scan_cache.ensure_initialized()
    index=usage_index.UsageIndex();native=bpy.data.user_map()
    hits=index.fast_query(target,native)['other_uses']
    objects=[hit['_owner'] for hit in hits if isinstance(hit['_owner'],bpy.types.Object)]
    collections=[hit['_owner'] for hit in hits if isinstance(hit['_owner'],bpy.types.Collection)]
    contexts=_scene_contexts(objects);contexts.update(_collection_contexts(collections))
    destinations={};unlocated={}
    for hit in hits:
        owner=hit['_owner'];pointer=owner.as_pointer()
        if isinstance(owner,bpy.types.Scene):
            contexts[pointer]=[(owner,layer.name,False) for layer in owner.view_layers]
        placed=False
        for location in contexts.get(pointer,()):
            destination,layer_name,excluded=location[:3]
            hierarchy=location[3] if len(location)>3 else ''
            identity=(destination.session_uid,layer_name,owner.session_uid)
            record=destinations.setdefault(identity,[destination,layer_name,owner,set(),False,excluded,hit['depth'],hit['kind'],hierarchy])
            record[3].add(hit['path']);record[4] |= bool(hit['direct']);placed=True
            record[6:8]=min(tuple(record[6:8]),(hit['depth'],hit['kind']))
        if not placed:unlocated.setdefault((pointer,hit['path']),(owner,hit['path'],bool(hit['direct']),hit['depth'],hit['kind']))
    ordered=[]
    for destination,layer_name,owner,paths,direct,excluded,depth,kind,hierarchy in destinations.values():
        ordered.append(((depth,kind,destination.name,layer_name,owner.name),owner,destination,layer_name,paths,direct,excluded,hierarchy))
    for owner,path,direct,depth,kind in unlocated.values():
        ordered.append(((depth,kind,'','',owner.name),owner,None,'',{path},direct,False,''))
    scene.wkngr_usage_rows.clear()
    for order,owner,destination,layer_name,paths,direct,excluded,hierarchy in sorted(ordered,key=lambda row:row[0]):
        row=scene.wkngr_usage_rows.add();row.owner_uid=id_handles.remember(owner)
        row.reference_depth,row.reference_kind=order[:2]
        row.path='\n'.join(sorted(paths));row.direct=direct;row.excluded=excluded
        if hierarchy:row.path+='\n\u96c6\u5408\u8def\u5f84: '+destination.name+' / '+layer_name+' / '+hierarchy
        if destination:
            row.scene_uid=id_handles.remember(destination);row.view_layer_name=layer_name
            if isinstance(owner,bpy.types.Object):row.object_uid=id_handles.remember(owner)
            elif isinstance(owner,bpy.types.Collection):row.collection_uid=id_handles.remember(owner)
            prefix=owner.bl_rna.name+' / ' if not isinstance(owner,bpy.types.Object) else ''
            row.location_label=prefix+destination.name+' / '+layer_name
            if owner!=destination:row.location_label+=' / '+owner.name
            row.location_label+=' | '+str(len(paths))+' \u6761\u5f15\u7528\u8bb0\u5f55'
        else:row.location_label=owner.bl_rna.name+' / '+usage_index.data_label(owner)
    scene.wkngr_usage_index=0
    scene.wkngr_settings.lookup_summary=('\u76ee\u6807: '+target.name+' | users='+str(target.users)+
        ' | \u5b9a\u4f4d\u5165\u53e3='+str(len(destinations))+' | \u5176\u4ed6\u5f15\u7528='+str(len(unlocated)))
    id_handles.prune()
    return len(scene.wkngr_usage_rows)


def _transfer_lookup(source,destination):
    if source==destination or data_tools.protected(destination):return
    fields=('owner_uid','scene_uid','view_layer_name','object_uid','collection_uid','location_label','path','direct','excluded','reference_depth','reference_kind')
    records=[tuple(getattr(row,field) for field in fields) for row in source.wkngr_usage_rows]
    destination.wkngr_usage_rows.clear()
    for record in records:
        row=destination.wkngr_usage_rows.add()
        for field,value in zip(fields,record):setattr(row,field,value)
    destination.wkngr_usage_index=source.wkngr_usage_index
    for field in ('lookup_kind','lookup_name','lookup_summary'):
        setattr(destination.wkngr_settings,field,getattr(source.wkngr_settings,field))
    destination.wkngr_settings.tool_mode='LOOKUP'
    source.wkngr_usage_rows.clear();source.wkngr_settings.lookup_summary=''
    id_handles.prune()


def locate(context,data,scene=None,view_layer_name=None):
    if not isinstance(data,(bpy.types.Object,bpy.types.Collection,bpy.types.Scene)):
        raise ValueError('\u6b64\u5f15\u7528\u6ca1\u6709\u53ef\u5b9a\u4f4d\u7684\u573a\u666f\u3001\u96c6\u5408\u6216\u7269\u4f53')
    window=context.window
    if window is None:raise ValueError('\u5f53\u524d\u6ca1\u6709\u53ef\u7528\u7a97\u53e3')
    destination=scene or context.scene
    layer=destination.view_layers.get(view_layer_name) if view_layer_name else (context.view_layer if destination==context.scene else None)
    if layer is None:raise ValueError('\u573a\u666f\u6216\u89c6\u56fe\u5c42\u5df2\u53d8\u5316\uff0c\u8bf7\u91cd\u65b0\u67e5\u627e')
    active_collection=layer.active_layer_collection
    if isinstance(data,bpy.types.Scene):
        if data!=destination:raise ValueError('\u573a\u666f\u5b9a\u4f4d\u8bb0\u5f55\u5df2\u53d8\u5316\uff0c\u8bf7\u91cd\u65b0\u67e5\u627e')
        path=(layer.layer_collection,)
    else:path=usage_visibility.choose_path(layer,data)
    excluded=any(part.exclude for part in path)
    if context.mode!='OBJECT':raise ValueError('\u8bf7\u5148\u9000\u51fa\u7f16\u8f91\u6216\u7ed8\u5236\u6a21\u5f0f\u518d\u5b9a\u4f4d')
    areas=[area for area in window.screen.areas if area.type=='OUTLINER']
    if not areas:raise ValueError('\u8bf7\u5148\u6253\u5f00\u5927\u7eb2\u89c6\u56fe')
    source=context.scene
    window.scene=destination;window.view_layer=layer
    if isinstance(data,bpy.types.Object):
        if not excluded:
            usage_visibility.reveal(layer,data,path)
            for obj in layer.objects:
                if obj.select_get(view_layer=layer):obj.select_set(False,view_layer=layer)
            data.select_set(True,view_layer=layer);layer.objects.active=data
    if isinstance(data,bpy.types.Collection) or excluded:
        if excluded:
            first=next(i for i,part in enumerate(path) if part.exclude)
            layer.active_layer_collection=path[max(0,first-1)]
        else:layer.active_layer_collection=path[-1]
    for area in areas:
        space=area.spaces.active;space.display_mode='VIEW_LAYER';space.use_filter_view_layers=False;space.use_sync_select=True;space.filter_text='';space.filter_state='ALL';space.filter_invert=False;space.use_filter_object=True;space.use_filter_collection=True
        type_filter={'MESH':'mesh','ARMATURE':'armature','EMPTY':'empty','LIGHT':'light','CAMERA':'camera','GREASEPENCIL':'grease_pencil'}.get(getattr(data,'type',''),'others')
        if isinstance(data,bpy.types.Object):setattr(space,'use_filter_object_'+type_filter,True)
    focusing=isinstance(data,bpy.types.Object) and not excluded and outliner_focus.request(context,data,destination,layer.name)
    _transfer_lookup(source,destination)
    for row in destination.wkngr_usage_rows:
        if row.scene_uid==str(destination.session_uid) and row.view_layer_name==layer.name and (row.object_uid or row.collection_uid or row.owner_uid)==str(data.session_uid):row.excluded=excluded
    if excluded:
        return '集合已排除，请手动取消排除: '+' / '.join(part.name for part in path)
    if isinstance(data,bpy.types.Scene):return '\u5df2\u5207\u6362\u573a\u666f: '+destination.name+' / '+layer.name
    if isinstance(data,bpy.types.Object):
        prefix='\u5df2\u9009\u62e9\uff0c\u7b49\u5f85\u5927\u7eb2\u7ed8\u5236\u5b8c\u6210: ' if focusing else '\u5df2\u9009\u62e9: '
        return prefix+destination.name+' / '+layer.name+' / '+data.name
    if isinstance(data,bpy.types.Collection):return '\u5df2\u6fc0\u6d3b\u96c6\u5408: '+destination.name+' / '+layer.name+' / '+' / '.join(part.name for part in path)
    return '\u5df2\u5b9a\u4f4d: '+destination.name+' / '+layer.name+' / '+data.name

def _open_excluded_guidance(context,obj,scene,layer_name):
    field='collection_uid' if isinstance(obj,bpy.types.Collection) else 'object_uid'
    return bpy.ops.wkngr.excluded_guidance('INVOKE_DEFAULT',scene_uid=str(scene.session_uid),
        view_layer_name=layer_name,**{field:str(obj.session_uid)})


class WKNGR_OT_ExcludedGuidance(bpy.types.Operator):
    bl_options={'REGISTER','UNDO'}
    bl_idname='wkngr.excluded_guidance'
    bl_label='\u624b\u52a8\u53d6\u6d88\u96c6\u5408\u6392\u9664'
    scene_uid:bpy.props.StringProperty(options={'SKIP_SAVE'})
    object_uid:bpy.props.StringProperty(options={'SKIP_SAVE'})
    collection_uid:bpy.props.StringProperty(options={'SKIP_SAVE'})
    view_layer_name:bpy.props.StringProperty(options={'SKIP_SAVE'})
    def targets(self):
        scene=id_handles.resolve(self.scene_uid);obj=id_handles.resolve(self.object_uid or self.collection_uid)
        layer=scene.view_layers.get(self.view_layer_name) if scene else None
        if obj is None or layer is None:raise ValueError('\u5b9a\u4f4d\u76ee\u6807\u5df2\u53d8\u5316\uff0c\u8bf7\u91cd\u65b0\u67e5\u627e')
        layer.update()
        return scene,layer,obj,usage_visibility.choose_path(layer,obj)
    def invoke(self,context,event):return context.window_manager.invoke_props_dialog(self,width=650)
    def draw(self,context):
        layout=self.layout
        try:scene,layer,obj,path=self.targets()
        except (ValueError,ReferenceError) as exc:layout.label(text=str(exc));return
        layout.label(text=scene.name+' / '+layer.name+' / '+obj.name)
        layout.label(text=' / '.join(part.name for part in path))
        blocked=[part for part in path if part.exclude]
        if blocked:
            layout.label(text='\u8bf7\u624b\u52a8\u53d6\u6d88\u4ee5\u4e0b\u96c6\u5408\u7684\u6392\u9664\u52fe\u9009\uff0c\u7136\u540e\u70b9\u786e\u5b9a')
            for part in blocked:layout.prop(part,'exclude',text=part.name+' / \u6392\u9664')
        else:layout.label(text='\u5df2\u53d6\u6d88\u6392\u9664\uff0c\u70b9\u786e\u5b9a\u5b9a\u4f4d\u76ee\u6807')
    def execute(self,context):
        try:
            scene,layer,obj,path=self.targets()
            if any(part.exclude for part in path):
                self.report({'WARNING'},'\u96c6\u5408\u4ecd\u88ab\u6392\u9664\uff0c\u4fdd\u6301\u539f\u72b6');return {'CANCELLED'}
            message=locate(context,obj,scene,layer.name)
        except (ValueError,RuntimeError,ReferenceError) as exc:self.report({'WARNING'},str(exc));return {'CANCELLED'}
        self.report({'INFO'},message);return {'FINISHED'}

class WKNGR_OT_SyncData(bpy.types.Operator):
    bl_idname='wkngr.sync_data_names'
    bl_label='\u6570\u636e\u540d\u79f0\u540c\u6b65\u4e3a\u7269\u4f53\u540d\u79f0'
    bl_options={'REGISTER','UNDO'}
    def execute(self,context):
        try:stats=data_tools.synchronize()
        except (RuntimeError,ValueError,ReferenceError) as exc:
            self.report({'ERROR'},str(exc));return {'CANCELLED'}
        scan_cache.clear_all()
        self.report({'INFO'},('\u5df2\u6539\u540d {renamed} | \u9501\u5b9a\u8df3\u8fc7 {readonly} | \u5171\u4eab\u51b2\u7a81 {shared} | \u91cd\u540d\u540e\u7f00 {suffix}').format_map(stats))
        return {'FINISHED'}

class WKNGR_OT_Capitalize(bpy.types.Operator):
    bl_idname='wkngr.capitalize_names'
    bl_label='\u7269\u4f53\u3001\u96c6\u5408\u3001\u6750\u8d28\u9996\u5b57\u6bcd\u5927\u5199'
    bl_options={'REGISTER','UNDO'}
    def execute(self,context):
        count,skipped,errors,collisions=capitalize_all()
        if not errors:scan_cache.clear_all()
        self.report({'WARNING'} if errors else {'INFO'},'\u5df2\u6539\u540d '+str(count)+' | \u9501\u5b9a\u8df3\u8fc7 '+str(skipped)+(' | '+errors[0] if errors else ''))
        if collisions:self.report({'WARNING'},'\u91cd\u540d\u540e\u7f00: '+'; '.join(collisions[:5]))
        return {'FINISHED'}

class WKNGR_OT_FindUsage(bpy.types.Operator):
    bl_idname='wkngr.find_usage'
    bl_label='\u67e5\u627e\u5f15\u7528'
    def execute(self,context):
        st=context.scene.wkngr_settings
        matches=[data for data in getattr(bpy.data,st.lookup_kind) if data.name==st.lookup_name]
        if len(matches)>1:
            self.report({'WARNING'},'Ambiguous linked data name; select a unique name');return {'CANCELLED'}
        target=next(iter(matches),None)
        if target is None:
            self.report({'WARNING'},'\u672a\u627e\u5230\u76ee\u6807');return {'CANCELLED'}
        try:count=lookup(context.scene,target)
        except (RuntimeError,ReferenceError,ValueError) as exc:
            self.report({'ERROR'},str(exc));return {'CANCELLED'}
        self.report({'INFO'},'\u627e\u5230 '+str(count)+' \u4e2a\u5f15\u7528\u4f4d\u7f6e')
        return {'FINISHED'}

class WKNGR_OT_LocateUsage(bpy.types.Operator):
    bl_options={'REGISTER','UNDO'}
    bl_idname='wkngr.locate_usage'
    bl_label='\u9009\u62e9 / \u5b9a\u4f4d'
    index:bpy.props.IntProperty(default=-1)
    @classmethod
    def description(cls,context,properties):
        rows=context.scene.wkngr_usage_rows
        return rows[properties.index].path if 0<=properties.index<len(rows) else cls.bl_label
    def execute(self,context):
        rows=context.scene.wkngr_usage_rows
        if not 0<=self.index<len(rows):return {'CANCELLED'}
        row=rows[self.index]
        target=id_handles.resolve(row.object_uid or row.collection_uid or row.owner_uid);destination=id_handles.resolve(row.scene_uid)
        if target is None or destination is None:
            self.report({'WARNING'},'\u6ca1\u6709\u6709\u6548\u7684\u5b9a\u4f4d\u5165\u53e3\uff0c\u8bf7\u91cd\u65b0\u67e5\u627e');return {'CANCELLED'}
        layer_name=row.view_layer_name
        try:message=locate(context,target,destination,layer_name)
        except (ValueError,RuntimeError,ReferenceError) as exc:
            self.report({'WARNING'},str(exc));return {'CANCELLED'}
        layer=destination.view_layers.get(layer_name)
        if layer is not None and isinstance(target,(bpy.types.Object,bpy.types.Collection)) and any(part.exclude for part in usage_visibility.choose_path(layer,target)):_open_excluded_guidance(context,target,destination,layer.name)
        self.report({'INFO'},message);return {'FINISHED'}

class WKNGR_OT_UsageWindow(bpy.types.Operator):
    bl_idname='wkngr.usage_window'
    bl_label='\u5f15\u7528\u67e5\u627e\u7ed3\u679c'
    def invoke(self,context,event):return context.window_manager.invoke_props_dialog(self,width=900)
    def execute(self,context):return {'FINISHED'}
    def draw(self,context):
        draw_usage(self.layout,context.scene)

def draw_usage(layout,scene):
    layout.label(text=scene.wkngr_settings.lookup_summary)
    layout.template_list('WKNGR_UL_Usage','',scene,'wkngr_usage_rows',scene,'wkngr_usage_index',rows=14)
    layout.label(text='\u6309\u6240\u9009\u8bb0\u5f55\u5207\u6362\u573a\u666f\u548c\u89c6\u56fe\u5c42\uff0c\u5b9a\u4f4d\u573a\u666f\u3001\u96c6\u5408\u6216\u7269\u4f53')

_classes=(WKNGR_OT_ExcludedGuidance,WKNGR_OT_SyncData,WKNGR_OT_Capitalize,WKNGR_OT_FindUsage,WKNGR_OT_LocateUsage,WKNGR_OT_UsageWindow)
def register():reg.register_classes(_classes)
def unregister():reg.unregister_classes(_classes)

