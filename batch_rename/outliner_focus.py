"""One-shot Outliner focus after its destination tree has actually been drawn.

The draw hook only acknowledges readiness. Native UI operations run in the modal
operator on the next window event, never from drawing and never from a timer.
"""
import bpy
from bpy.app.handlers import persistent
from . import reg,id_handles

# A package reload must dispose the old native draw hooks before replacing state.
for _previous in tuple(globals().get('_jobs',{}).values()):
    _previous.close()
_jobs={}


def _native_focus(window,scene,layer,area):
    region=next((r for r in area.regions if r.type=='WINDOW'),None)
    if region is None:return {'CANCELLED'}
    with bpy.context.temp_override(window=window,scene=scene,view_layer=layer,area=area,region=region):
        if not bpy.ops.outliner.show_active.poll():return {'CANCELLED'}
        return bpy.ops.outliner.show_active()


class FocusJob:
    def __init__(self,window,scene,obj,layer_name):
        self.window=window;self.window_pointer=window.as_pointer()
        self.scene_uid=str(scene.session_uid);self.object_uid=str(obj.session_uid);self.layer_name=layer_name
        self.areas={area.as_pointer() for area in window.screen.areas if area.type=='OUTLINER' and any(r.type=='WINDOW' for r in area.regions)}
        self.ready=set();self.done=set();self.hook=None;self.closed=False
    def targets(self):
        scene=id_handles.resolve(self.scene_uid);obj=id_handles.resolve(self.object_uid)
        if scene is None or obj is None:return None
        try:
            layer=scene.view_layers.get(self.layer_name)
            if layer is None or self.window.scene!=scene or self.window.view_layer!=layer or layer.objects.active!=obj:return None
            areas={area.as_pointer():area for area in self.window.screen.areas if area.type=='OUTLINER'}
            if not self.areas.issubset(areas):return None
        except ReferenceError:return None
        return scene,layer,areas
    def mark_drawn(self,window_pointer,area_pointer,scene_uid,layer_name):
        if not self.closed and window_pointer==self.window_pointer and area_pointer in self.areas and str(scene_uid)==self.scene_uid and layer_name==self.layer_name:
            self.ready.add(area_pointer)
    def draw_ack(self):
        context=bpy.context
        if context.window is None or context.area is None or context.region is None or context.region.type!='WINDOW':return
        self.mark_drawn(context.window.as_pointer(),context.area.as_pointer(),context.scene.session_uid,context.view_layer.name)
    def arm(self):
        self.hook=bpy.types.SpaceOutliner.draw_handler_add(self.draw_ack,(),'WINDOW','POST_PIXEL')
        for area in self.window.screen.areas:
            if area.as_pointer() in self.areas:area.tag_redraw()
    def advance(self):
        if self.closed:return 'STALE'
        targets=self.targets()
        if targets is None:self.close();return 'STALE'
        scene,layer,areas=targets
        for pointer in self.ready-self.done:
            try:result=_native_focus(self.window,scene,layer,areas[pointer])
            except (RuntimeError,ReferenceError,ValueError):
                self.close();return 'FAILED'
            if result!={'FINISHED'}:
                self.close();return 'FAILED'
            self.done.add(pointer);areas[pointer].tag_redraw()
        if self.done==self.areas:
            self.close();return 'DONE'
        return 'WAIT'
    def close(self):
        if self.closed:return
        self.closed=True
        if self.hook is not None:
            bpy.types.SpaceOutliner.draw_handler_remove(self.hook,'WINDOW');self.hook=None
        self.ready.clear()
        if _jobs.get(self.window_pointer) is self:_jobs.pop(self.window_pointer,None)


@persistent
def _cancel_focus_jobs(_unused=None):
    for job in tuple(_jobs.values()):job.close()


class WKNGR_OT_FocusOutliner(bpy.types.Operator):
    bl_idname='wkngr.focus_outliner'
    bl_label='\u5c55\u5f00\u5e76\u5b9a\u4f4d\u5927\u7eb2\u7269\u4f53'
    bl_options={'INTERNAL'}
    scene_uid:bpy.props.StringProperty(options={'SKIP_SAVE'})
    object_uid:bpy.props.StringProperty(options={'SKIP_SAVE'})
    layer_name:bpy.props.StringProperty(options={'SKIP_SAVE'})
    def invoke(self,context,event):
        scene=id_handles.resolve(self.scene_uid);obj=id_handles.resolve(self.object_uid)
        if context.window is None or scene is None or obj is None:return {'CANCELLED'}
        job=FocusJob(context.window,scene,obj,self.layer_name)
        if not job.areas or job.targets() is None:return {'CANCELLED'}
        previous=_jobs.get(job.window_pointer)
        if previous is not None:previous.close()
        try:
            job.arm();context.window_manager.modal_handler_add(self)
        except Exception:
            job.close();raise
        self.job=job;_jobs[job.window_pointer]=job
        return {'RUNNING_MODAL'}
    def modal(self,context,event):
        if event.type=='ESC':self.job.close();return {'CANCELLED'}
        state=self.job.advance()
        if state=='WAIT':return {'PASS_THROUGH'}
        if state=='DONE':
            self.report({'INFO'},'\u5df2\u5c55\u5f00\u5e76\u5b9a\u4f4d\u5927\u7eb2\u4e2d\u7684\u7269\u4f53');return {'FINISHED'}
        if state=='FAILED':
            self.report({'WARNING'},'\u7269\u4f53\u5df2\u9009\u4e2d\uff0c\u4f46\u5927\u7eb2\u5b9a\u4f4d\u5931\u8d25');return {'CANCELLED'}
        return {'CANCELLED'}
    def cancel(self,context):
        job=getattr(self,'job',None)
        if job is not None:job.close()


def request(context,obj,scene,layer_name):
    if bpy.app.background:return False
    result=bpy.ops.wkngr.focus_outliner('INVOKE_DEFAULT',object_uid=str(obj.session_uid),scene_uid=str(scene.session_uid),layer_name=layer_name)
    return result=={'RUNNING_MODAL'}


_classes=(WKNGR_OT_FocusOutliner,)
def register():
    reg.register_classes(_classes)
    for handlers in (bpy.app.handlers.load_pre,bpy.app.handlers.undo_pre,bpy.app.handlers.redo_pre):
        if _cancel_focus_jobs not in handlers:handlers.append(_cancel_focus_jobs)
def unregister():
    _cancel_focus_jobs()
    for handlers in (bpy.app.handlers.load_pre,bpy.app.handlers.undo_pre,bpy.app.handlers.redo_pre):
        if _cancel_focus_jobs in handlers:handlers.remove(_cancel_focus_jobs)
    reg.unregister_classes(_classes)
