bl_info = {
    "name": "batch_rename",
    "author": "WiKey",
    "version": (1, 7, 7),
    "blender": (5, 1, 0),
    "location": "节点编辑器 / 3D 视图 > 侧栏 > batch_rename",
    "description": "检查所有数据块类型，使用字典局部翻译，按全部类型预览和应用重命名",
    "category": "Node",
}

import importlib
import sys

_needs_reload = __name__ + ".props" in sys.modules
_modules = []
_registered = False


def _load_modules():
    global _modules
    from . import (reg, id_handles, props, preset_manager, utils,
                   scan_cache, node_names, nested_data, geometry_contracts, name_safety, name_references, rename_plan, data_tools, usage_index, usage_visibility, outliner_focus, data_catalog, ops_scan, ops_rename, ops_tools, ops_preset, ui_main, ui_preset)
    _modules = [reg, id_handles, props, preset_manager, utils,
                scan_cache, node_names, nested_data, geometry_contracts, name_safety, name_references, rename_plan, data_tools, usage_index, usage_visibility, outliner_focus, data_catalog, ops_scan, ops_rename, ops_tools, ops_preset, ui_main, ui_preset]


def register():
    global _registered, _needs_reload
    if _registered:
        return
    _load_modules()
    from . import reg, props
    if _needs_reload:
        importlib.reload(reg)
    reg.cleanup_stale(_modules, props._SCENE_ATTRS)
    if _needs_reload:
        # Blender may reload only the package while retaining old submodules.
        # Remove old RNA and callbacks before creating replacement Python classes.
        for module in _modules:
            if module is not reg:
                importlib.reload(module)
        _needs_reload = False
    done = []
    try:
        for m in _modules:
            done.append(m)
            if hasattr(m, "register"):
                m.register()
        _registered = True
    except Exception:
        # 回滚已注册的模块,避免"注册一半"的脏状态。
        # 否则之后 unregister 会去 unregister 根本没注册上的类,报一堆无关错误。
        for m in reversed(done):
            try:
                if hasattr(m, "unregister"):
                    m.unregister()
            except Exception:
                import traceback
                traceback.print_exc()
        raise


def unregister():
    global _registered
    _registered = False
    errors = []
    for module in reversed(_modules):
        if hasattr(module, "unregister"):
            try:
                module.unregister()
            except Exception as exc:
                errors.append(exc)
    from . import reg
    try:
        reg.reset_state()
    except Exception as exc:
        errors.append(exc)
    if errors:
        raise RuntimeError("Add-on cleanup failed; see the original error") from errors[0]
