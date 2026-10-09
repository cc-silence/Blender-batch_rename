"""Validated, atomic preset storage outside the installed extension."""

import hashlib
import json
import os
import re
import shutil
import tempfile

import bpy

CUSTOM_FILTER_FILENAME = "custom_filter.json"
DEFAULT_PRESET = "usr"
_dir = ""
_preset_cache = None
_token_cache = None
_revision = 0


def _addon_preset_dir():
    return os.path.join(os.path.dirname(__file__), "presets")


def get_preset_dir():
    global _dir
    if _dir:
        return _dir
    legacy = bpy.utils.user_resource("SCRIPTS", path="wkngr_presets", create=False)
    if __package__.startswith("bl_ext."):
        directory = bpy.utils.extension_path_user(__package__, path="presets", create=True)
    else:
        directory = bpy.utils.user_resource("SCRIPTS", path="wkngr_presets", create=True)
    if not directory:
        raise OSError("Cannot create the user preset directory")
    os.makedirs(directory, exist_ok=True)
    marker = os.path.join(directory, ".migration_v1")
    if not os.path.exists(marker):
        for source in (legacy, _addon_preset_dir()):
            if not source or os.path.abspath(source) == os.path.abspath(directory):
                continue
            if os.path.isdir(source):
                for name, source_path in _iter_preset_files(source):
                    destination = os.path.join(directory, *name.split('/')) + '.json'
                    if not os.path.exists(destination):
                        os.makedirs(os.path.dirname(destination), exist_ok=True)
                        shutil.copy2(source_path, destination)
                source_filter = os.path.join(source, CUSTOM_FILTER_FILENAME)
                destination_filter = os.path.join(directory, CUSTOM_FILTER_FILENAME)
                if os.path.isfile(source_filter) and not os.path.exists(destination_filter):
                    shutil.copy2(source_filter, destination_filter)
        _write_json(marker, {"version": 1})
    _dir = directory
    return _dir


def _safe_name(name):
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', str(name).strip()).rstrip(' .')
    if not name or name.startswith(".") or name.casefold() == "custom_filter":
        return ""
    stem = name.split('.')[0].upper()
    if stem in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}:
        return ""
    return name


def _relative_name(name):
    if not isinstance(name, str):
        raise ValueError("Invalid preset name")
    parts = name.replace('\\', '/').split('/')
    if any(not part or _safe_name(part) != part or part in ('.', '..') for part in parts):
        raise ValueError("Invalid or reserved preset name: " + repr(name))
    return '/'.join(parts)


def _preset_path(name):
    name = _relative_name(name)
    path = os.path.join(get_preset_dir(), *name.split('/')) + '.json'
    if not os.path.exists(path):
        parent, filename = os.path.split(path)
        if os.path.isdir(parent):
            for entry in os.scandir(parent):
                stem, ext = os.path.splitext(entry.name)
                if stem == filename[:-5] and ext.lower() == '.json' and entry.is_file():
                    return entry.path
    return path


def _iter_preset_files(directory):
    if not os.path.isdir(directory):
        return
    for folder, subdirs, files in os.walk(directory, followlinks=False):
        subdirs[:] = sorted(d for d in subdirs if _safe_name(d) == d and not d.startswith('.') and not os.path.islink(os.path.join(folder, d)))
        for filename in sorted(files):
            stem, ext = os.path.splitext(filename)
            if ext.lower() != '.json' or not stem or stem.startswith('.') or _safe_name(stem) != stem:
                continue
            path = os.path.join(folder, filename)
            relative = os.path.relpath(path, directory).replace(os.sep, '/')[:-5]
            yield relative, path


def _hidden_preset(name):
    return any(part.casefold() == 'default' for part in name.split('/')[:-1])


def invalidate_cache():
    global _preset_cache, _token_cache, _revision
    _preset_cache = _token_cache = None
    _revision += 1


def ensure_defaults():
    os.makedirs(os.path.join(get_preset_dir(), "default"), exist_ok=True)
    for filename, value in (("usr.json", {}), (CUSTOM_FILTER_FILENAME, [])):
        path = os.path.join(get_preset_dir(), filename)
        if not os.path.exists(path):
            _write_json(path, value)


def list_presets():
    global _preset_cache
    if _preset_cache is None:
        ensure_defaults()
        names = {name for name, _ in _iter_preset_files(get_preset_dir()) if name != DEFAULT_PRESET and not _hidden_preset(name)}
        _preset_cache = [DEFAULT_PRESET] + sorted(names)
    return list(_preset_cache)


def list_translation_presets():
    ensure_defaults()
    names = {name for name, _ in _iter_preset_files(get_preset_dir())}
    rest = names - {DEFAULT_PRESET}
    return [DEFAULT_PRESET] + sorted(name for name in rest if not _hidden_preset(name)) + sorted(name for name in rest if _hidden_preset(name))


def _read_json(path, expected):
    # A malformed dictionary must never be treated as an empty one and overwritten.
    with open(path, 'r', encoding='utf-8-sig') as stream:
        data = json.load(stream)
    if not isinstance(data, expected):
        raise ValueError("Invalid JSON structure: " + path)
    if isinstance(data, dict) and any(not isinstance(k, str) or not isinstance(v, str) for k, v in data.items()):
        raise ValueError("Dictionary entries must be strings: " + path)
    if isinstance(data, list) and any(not isinstance(v, str) for v in data):
        raise ValueError("Filter entries must be strings: " + path)
    return data


def load_preset(name):
    ensure_defaults()
    return _read_json(_preset_path(name or DEFAULT_PRESET), dict)


def _write_json(path, data):
    fd, temporary = tempfile.mkstemp(prefix='.wkngr-', suffix='.tmp', dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.remove(temporary)


def save_preset(name, data):
    if not isinstance(data, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in data.items()):
        raise ValueError("Dictionary entries must be strings")
    ensure_defaults()
    path = _preset_path(name or DEFAULT_PRESET)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    _write_json(path, data)
    invalidate_cache()


def create_preset(name):
    name = _safe_name(name)
    if not name:
        return False
    ensure_defaults()
    path = _preset_path(name)
    if os.path.exists(path):
        return False
    _write_json(path, {})
    invalidate_cache()
    return True


def delete_preset(name):
    path = _preset_path(name)
    if name == DEFAULT_PRESET:
        save_preset(name, {})
        return True
    if not os.path.exists(path):
        return False
    _remember_removed_source(name)
    os.remove(path)
    invalidate_cache()
    return True


def rename_preset(old, new):
    try:
        new = _relative_name(new)
    except ValueError:
        return False
    if not new or old == new:
        return False
    source, destination = _preset_path(old), _preset_path(new)
    if not os.path.exists(source) or os.path.exists(destination):
        return False
    _remember_removed_source(old)
    os.rename(source, destination)
    invalidate_cache()
    return True


def load_custom_tokens():
    global _token_cache
    if _token_cache is None:
        ensure_defaults()
        data = _read_json(os.path.join(get_preset_dir(), CUSTOM_FILTER_FILENAME), list)
        _token_cache = list(dict.fromkeys(t.strip() for t in data if t.strip()))
    return list(_token_cache)


def save_custom_tokens(tokens):
    ensure_defaults()
    clean = list(dict.fromkeys(str(t).strip() for t in tokens if str(t).strip()))
    _write_json(os.path.join(get_preset_dir(), CUSTOM_FILTER_FILENAME), clean)
    invalidate_cache()


def unregister():
    global _dir
    _dir = ""
    invalidate_cache()


def import_preset(filepath, relative_name=None):
    data = _read_json(os.fspath(filepath), dict)
    base = _relative_name(relative_name) if relative_name else _safe_name(os.path.splitext(os.path.basename(filepath))[0])
    if not base:
        raise ValueError("字典文件名无效或为保留名称")
    ensure_defaults()
    name, index = base, 0
    while os.path.exists(_preset_path(name)):
        if _read_json(_preset_path(name), dict) == data:
            return name
        index += 1
        name = f"{base}.{index:03d}"
    save_preset(name, data)
    return name


def export_preset(name, filepath):
    data = load_preset(name)
    path = os.path.abspath(os.fspath(filepath))
    if not path.lower().endswith('.json'):
        path += '.json'
    internal = os.path.normcase(os.path.abspath(get_preset_dir()))
    try:
        inside = os.path.commonpath((internal, os.path.normcase(path))) == internal
    except ValueError:
        inside = False
    if inside:
        raise ValueError("请导出到插件字典目录以外的位置")
    _write_json(path, data)
    return path


def load_translation_dictionary(preferred):
    """Merge once per fill: selected preset first, then stable list order."""
    invalidate_cache()
    names = list_translation_presets()
    if preferred in names:
        names.remove(preferred)
        names.insert(0, preferred)
    merged = {}
    for name in names:
        try:
            data = _read_json(_preset_path(name), dict)
        except (OSError, ValueError) as exc:
            raise ValueError(f"{name}.json: {exc}") from exc
        for original, translated in data.items():
            if translated:
                merged.setdefault(original, translated)
    return merged


def _source_ledger():
    path = os.path.join(get_preset_dir(), '.sources_v1')
    return path, _read_json(path, dict) if os.path.exists(path) else {}


def _source_signature(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest()


def refresh_external_presets():
    """Discover manually added files; preserve user edits and remembered removals."""
    ensure_defaults()
    source = _addon_preset_dir()
    destination = get_preset_dir()
    errors = []
    if os.path.normcase(os.path.abspath(source)) == os.path.normcase(os.path.abspath(destination)) or not os.path.isdir(source):
        invalidate_cache()
        return errors
    ledger_path, ledger = _source_ledger()
    before = dict(ledger)
    for name, path in _iter_preset_files(source):
        if name == DEFAULT_PRESET:
            continue
        filename = os.path.relpath(path, source)
        key = os.path.normcase(os.path.abspath(path))
        try:
            data = _read_json(path, dict)
            signature = _source_signature(data)
            if ledger.get(key) != signature:
                previous = ledger.get('target:' + key)
                target = _preset_path(previous) if previous else None
                if target and os.path.isfile(target) and _source_signature(_read_json(target, dict)) == ledger.get('saved:' + key):
                    save_preset(previous, data)
                    imported = previous
                else:
                    imported = import_preset(path, relative_name=name)
                ledger[key] = signature
                ledger['target:' + key] = imported
                ledger['saved:' + key] = signature
        except (OSError, ValueError) as exc:
            errors.append(f"{filename}: {exc}")
    if ledger != before:
        _write_json(ledger_path, ledger)
    invalidate_cache()
    return errors


def _remember_removed_source(name):
    """An unchanged source file must not resurrect a removed/renamed preset."""
    source = _addon_preset_dir()
    if not os.path.isdir(source):
        return
    ledger_path, ledger = _source_ledger()
    changed = False
    for relative, path in _iter_preset_files(source):
        if relative != name:
            continue
        try:
            signature = _source_signature(_read_json(path, dict))
        except ValueError:
            continue
        ledger[os.path.normcase(os.path.abspath(path))] = signature
        changed = True
    if changed:
        _write_json(ledger_path, ledger)
