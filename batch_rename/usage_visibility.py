"""Exact object collection paths and minimal viewport-only visibility changes."""
import bpy


def object_paths(layer,obj):
    paths=[];pending=[(layer.layer_collection,())]
    while pending:
        branch,ancestors=pending.pop();path=(*ancestors,branch)
        if any(value==obj for value in branch.collection.objects):paths.append(path)
        pending.extend((child,path) for child in branch.children)
    return paths


def collection_paths(layer,collection):
    paths=[];pending=[(layer.layer_collection,())]
    while pending:
        branch,ancestors=pending.pop();path=(*ancestors,branch)
        if branch.collection==collection:paths.append(path)
        pending.extend((child,path) for child in branch.children)
    return paths


def choose_path(layer,obj):
    paths=collection_paths(layer,obj) if isinstance(obj,bpy.types.Collection) else object_paths(layer,obj)
    if not paths:raise ValueError('物体已移出该场景，请重新查找')
    def score(path):
        return (sum(part.exclude for part in path),
                sum(bool(part.hide_viewport)+bool(part.collection.hide_viewport)+bool(part.collection.hide_select) for part in path),
                len(path),tuple(part.name for part in path))
    return min(paths,key=score)


def reveal(layer,obj,path):
    if any(part.exclude for part in path):raise ValueError('集合已排除，请手动取消排除')
    writes=[];seen=set()
    def add(target,field):
        identity=(target.as_pointer(),field)
        if identity in seen:return
        seen.add(identity)
        if not getattr(target,field):return
        if target.is_property_readonly(field):raise ValueError('可见性设置只读，无法解锁: '+target.name+' / '+field)
        writes.append((target,field,True))
    add(obj,'hide_viewport');add(obj,'hide_select')
    for part in path:
        add(part,'hide_viewport');add(part.collection,'hide_viewport');add(part.collection,'hide_select')
    # No hide_render, exclude, holdout, indirect_only or ViewLayer.use write belongs here.
    changed=[];hidden=None
    try:
        for target,field,old in writes:
            changed.append((target,field,old));setattr(target,field,False)
        layer.update()
        hidden=obj.hide_get(view_layer=layer)
        if hidden:obj.hide_set(False,view_layer=layer)
        layer.update()
        if not obj.visible_get(view_layer=layer):raise ValueError('物体仍不可见，请检查可见性驱动')
    except (RuntimeError,ValueError,ReferenceError):
        if hidden is not None:obj.hide_set(hidden,view_layer=layer)
        for target,field,old in reversed(changed):setattr(target,field,old)
        layer.update()
        raise
