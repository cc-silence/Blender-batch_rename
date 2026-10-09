"""小工具函数:非英文判断 / interface 兼容遍历 / 类型标签 / 图标防崩."""

import re

import bpy

_NON_ASCII_RE = re.compile(r"[^\x00-\x7F]")

_HAN_RE = re.compile(r"[㐀-䶿一-鿿豈-﫿𠀀-𲎯]")

def contains_chinese(name):
    return bool(_HAN_RE.search(name or ''))


# ---------------------------------------------------------------------------
# 图标安全网
# Blender 各版本 icon 枚举差异很大(5.x 删了一批,例如 FIND_REPLACE/PREVIEW_RANGE)。
# 直接写死 icon="XXX" 一旦该版本没有,draw() 每次重绘都会抛
#   TypeError: UILayout.label(): error with keyword argument "icon"
# 导致整个面板画不出来。这里统一走 ui_icon(): 从 RNA 读取当前版本真实枚举,
# 校验通过才用,不通过退回 'NONE',永远不会因为图标把面板搞崩。
# ---------------------------------------------------------------------------
_ICON_CACHE = None


def valid_icons() -> set:
    """当前 Blender 版本真实存在的 icon 标识符集合(读一次后缓存)."""
    global _ICON_CACHE
    if _ICON_CACHE is None:
        names = {"NONE"}
        try:
            param = bpy.types.UILayout.bl_rna.functions["label"].parameters["icon"]
            for item in param.enum_items:
                if item.identifier:
                    names.add(item.identifier)
        except Exception:
            pass
        _ICON_CACHE = names
    return _ICON_CACHE


def ui_icon(name: str, fallback: str = "NONE") -> str:
    """安全取图标:合法返回原名,非法返回 fallback,任何异常都吞掉."""
    try:
        ok = valid_icons()
        if name and name in ok:
            return name
        if fallback in ok:
            return fallback
        return "NONE"
    except Exception:
        return "NONE"


def clear_icon_cache():
    """版本切换/重载时清缓存."""
    global _ICON_CACHE
    _ICON_CACHE = None


def is_non_english(name: str) -> bool:
    """含任何非 ASCII 字符即算命中(中文/全角/特殊符号)."""
    if not name:
        return False
    return bool(_NON_ASCII_RE.search(name))


def match_custom(name: str, tokens: list[str]) -> bool:
    """自定义字符:字面子串匹配,任一命中即 True."""
    if not name or not tokens:
        return False
    for t in tokens:
        if t and t in name:
            return True
    return False


def should_show(name: str, tokens: list[str], custom_enable: bool) -> bool:
    """查找逻辑: 非英文 OR (启用时命中自定义字符)."""
    if is_non_english(name):
        return True
    if custom_enable and match_custom(name, tokens):
        return True
    return False


def parse_quick_tokens(quick: str) -> list[str]:
    """Split only on ASCII semicolons; preserve commas and spaces within names."""
    return [token for part in (quick or "").split(";") if (token := part.strip())]



def tree_type_label(ng) -> str:
    """返回 GEOMETRY / SHADER / COMPOSITING / OTHER.

    NodeTree.type 已废弃,bl_idname 才是真实类型标识:
    GeometryNodeTree / ShaderNodeTree / CompositorNodeTree.
    """
    bid = str(getattr(ng, "bl_idname", "") or "")
    if "GeometryNodeTree" in bid:
        return "GEOMETRY"
    if "ShaderNodeTree" in bid:
        return "SHADER"
    if "CompositorNodeTree" in bid or "Compositor" in bid:
        return "COMPOSITING"
    # 兜底:旧版 type 枚举
    t = str(getattr(ng, "type", "") or "").upper()
    if t == "GEOMETRY":
        return "GEOMETRY"
    if t == "SHADER":
        return "SHADER"
    if t in ("COMPOSITING", "COMPOSITE"):
        return "COMPOSITING"
    return "OTHER"


def iter_interface_sockets(ng):
    """版本兼容:优先 interface.items_tree,失败回退 inputs/outputs.

    yields: (socket_item, in_out_str)

    注意:必须先把 items_tree 整体取成 list 再 yield。
    如果在 yield 循环里 try/except,迭代到一半抛错会退到 legacy 分支,
    结果是"半截 items_tree + 完整 inputs/outputs"混在一起,同一个 socket 会出现两次。
    """
    iface = getattr(ng, "interface", None)
    if iface is not None and hasattr(iface, "items_tree"):
        items = None
        try:
            items = list(iface.items_tree)
        except Exception:
            items = None
        if items is not None:
            for item in items:
                # Blender 5.x: item.item_type in {'SOCKET','PANEL'}
                if getattr(item, "item_type", "SOCKET") != "SOCKET":
                    continue
                yield item, str(getattr(item, "in_out", "INPUT"))
            return  # interface 可用就不再走 legacy
    # 老版本回退(没有 interface,或 items_tree 完全读不了)
    for s in getattr(ng, "inputs", []) or []:
        yield s, "INPUT"
    for s in getattr(ng, "outputs", []) or []:
        yield s, "OUTPUT"


def is_editable(data):
    return (data is not None and data.library is None
            and data.is_editable and data.override_library is None)


def socket_index(ng):
    return {str(item.identifier): item for item, _ in iter_interface_sockets(ng)}


def find_socket_by_identifier(ng, identifier, fallback_name=""):
    # Never substitute a namesake for a deleted socket.
    return socket_index(ng).get(identifier) if identifier else None


def touch_inner_nodes(ng):
    ng.update_tag()


def unregister():
    clear_icon_cache()


def make_partial_translator(dictionary):
    """Compile once; longest literal match wins, translated output is not rescanned."""
    terms = sorted((key for key, value in dictionary.items() if key and value), key=lambda key: (-len(key), key))
    if not terms:
        return lambda text: (text, 0)
    pattern = re.compile('|'.join(re.escape(key) for key in terms))
    return lambda text: pattern.subn(lambda match: dictionary[match.group(0)], text)
