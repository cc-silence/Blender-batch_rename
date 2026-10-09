"""RNA registration transactions and recovery from interrupted installations."""

import bpy

_registered = {}


def is_registered(cls):
    # Blender sets bl_rna BEFORE deferred property registration can fail.
    # Check the class itself, never a bl_rna inherited from a built-in base.
    return "bl_rna" in cls.__dict__


def _rollback(classes):
    errors = []
    for cls in reversed(tuple(classes)):
        try:
            if is_registered(cls):
                bpy.utils.unregister_class(cls)
            _registered.pop(cls.__name__, None)
        except Exception as exc:
            errors.append(exc)
    if errors:
        raise RuntimeError("Failed to unregister add-on RNA classes") from errors[0]


def register_classes(classes):
    attempted = []
    try:
        for cls in classes:
            if _registered.get(cls.__name__) is cls and is_registered(cls):
                continue
            if is_registered(cls):
                raise RuntimeError("Stale RNA class was not cleaned: " + cls.__name__)
            attempted.append(cls)
            bpy.utils.register_class(cls)
            _registered[cls.__name__] = cls
    except Exception as error:
        try:
            _rollback(attempted)
        except Exception as cleanup_error:
            raise cleanup_error from error
        raise


def unregister_classes(classes):
    _rollback(cls for cls in classes if _registered.get(cls.__name__) is cls)


def _same_addon(module_name):
    owner = module_name.rpartition(".")[0]
    return (owner == __package__ or owner == "batch_rename_cn"
            or (owner.startswith("bl_ext.") and owner.endswith(".batch_rename_cn")))


def cleanup_stale(modules, scene_attrs):
    """Recover actual old class objects, including ones absent from our ledger."""
    declared = [cls for module in modules for cls in getattr(module, "_classes", ())]
    names = {cls.__name__ for cls in declared}
    bases = {base for cls in declared for base in cls.__bases__}
    found = {name: [] for name in names}
    for base in bases:
        for cls in base.__subclasses__():
            if cls.__name__ in names and is_registered(cls):
                if not _same_addon(cls.__module__):
                    raise RuntimeError("RNA name belongs to another add-on: " + cls.__module__ + "." + cls.__name__)
                found[cls.__name__].append(cls)
    # Stop old callbacks before detaching RNA properties. Only known callbacks qualify.
    for handlers in (bpy.app.handlers.load_pre, bpy.app.handlers.undo_pre, bpy.app.handlers.redo_pre, bpy.app.handlers.load_post, bpy.app.handlers.depsgraph_update_post,
                     bpy.app.handlers.undo_post, bpy.app.handlers.redo_post,
                     bpy.app.handlers.save_pre, bpy.app.handlers.save_post, bpy.app.handlers.save_post_fail):
        for callback in tuple(handlers):
            callback_name = getattr(callback, "__name__", "")
            callback_module = getattr(callback, "__module__", "")
            known = ((callback_name == "_cancel_focus_jobs" and callback_module.endswith(".outliner_focus"))
                     or (callback_name == "_invalidate" and callback_module.endswith(".id_handles"))
                     or (callback_name in {"_on_load", "_before_save", "_after_save", "_on_scene_update"} and callback_module.endswith(".scan_cache"))
                     or (callback_name in {"_on_load", "_on_scene_update", "_on_history"} and callback_module.endswith(".ops_preset"))
                     or (callback_name in {"_refresh_nested_history", "_before_save", "_after_save"} and callback_module.endswith(".nested_data")))
            if known and _same_addon(callback_module):
                handlers.remove(callback)
    for attr in scene_attrs:
        if hasattr(bpy.types.Scene, attr):
            delattr(bpy.types.Scene, attr)
    old_classes = [old for cls in declared for old in found[cls.__name__]]
    _rollback(old_classes)
    _registered.clear()


def reset_state():
    if _registered:
        raise RuntimeError("RNA classes remain registered")
