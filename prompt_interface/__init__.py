"""Exact private text loading. No defaults, interpolation engine, or provider calls."""
import hashlib
import json
import os
from pathlib import Path


_PINNED = {}

def _bundle():
    value = os.environ.get('HOMEOSTASIS_PRIVATE_CONFIG')
    if not value:
        raise RuntimeError('HOMEOSTASIS_PRIVATE_CONFIG_REQUIRED')
    path = Path(value).resolve()
    root = Path(__file__).resolve().parents[1]
    if path.is_relative_to(root) and not path.is_relative_to(root / 'private_config'):
        raise RuntimeError('PRIVATE_CONFIG_MUST_NOT_BE_PUBLIC')
    raw = path.read_bytes()
    checksum = hashlib.sha256(raw).hexdigest()
    if path in _PINNED and _PINNED[path] != checksum:
        raise RuntimeError('PRIVATE_CONFIG_CHANGED_DURING_PROCESS')
    data = json.loads(raw)
    _PINNED[path] = checksum
    if data.get('format') != 'homeostasis-private-text-v1':
        raise RuntimeError('PRIVATE_CONFIG_FORMAT_MISMATCH')
    return data


def private_text(key):
    item = _bundle()['texts'][key]
    text = item['text']
    if not isinstance(text, str) or hashlib.sha256(text.encode('utf-8')).hexdigest() != item['sha256']:
        raise RuntimeError('PRIVATE_TEXT_DIGEST_MISMATCH')
    return text


def private_file(relative):
    """Resolve an immutable former repository file from a private mirror."""
    value = os.environ.get('HOMEOSTASIS_PRIVATE_FILES')
    if not value:
        raise RuntimeError('HOMEOSTASIS_PRIVATE_FILES_REQUIRED')
    root = Path(value).resolve()
    public_root = Path(__file__).resolve().parents[1]
    if root.is_relative_to(public_root) and not root.is_relative_to(public_root / 'private_config'):
        raise RuntimeError('PRIVATE_FILES_MUST_NOT_BE_PUBLIC')
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise RuntimeError('PRIVATE_FILE_PATH_INVALID')
    return path


def prompt_identity():
    data = _bundle()
    raw = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
    return {'prompt_version': data['version'], 'private_configuration_sha256': hashlib.sha256(raw).hexdigest()}


def private_function(name, *args):
    """Load only explicitly configured, hash-verified researcher-owned code."""
    import importlib.util
    data = _bundle()['private_modules'][name]
    root = Path(os.environ['HOMEOSTASIS_PRIVATE_CONFIG']).resolve().parent
    path = (root / data['file']).resolve()
    if not path.is_relative_to(root) or hashlib.sha256(path.read_bytes()).hexdigest() != data['sha256']:
        raise RuntimeError('PRIVATE_MODULE_DIGEST_MISMATCH')
    spec = importlib.util.spec_from_file_location('_homeostasis_private_' + name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, name)(*args)


def private_value(key):
    item = _bundle()['values'][key]
    value = item['value']
    raw = json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    if hashlib.sha256(raw).hexdigest() != item['sha256']:
        raise RuntimeError('PRIVATE_VALUE_DIGEST_MISMATCH')
    return value


def configuration_path(path):
    """Redirect only the explicitly separated experiment configuration files."""
    root = Path(__file__).resolve().parents[1]
    p = Path(path).resolve()
    if p.is_relative_to(root):
        name = str(p.relative_to(root))
        if name in ('config/country_archetypes.json','config/country_types.json','config/information_policies.json'):
            return private_file(name)
    return Path(path)


def original_file(relative):
    """Read-only reference to a hash-verified privately retained original."""
    path = private_file(relative)
    root = Path(os.environ['HOMEOSTASIS_PRIVATE_FILES']).resolve()
    manifest = json.loads((root.parent / 'baseline-sha256.json').read_text())
    key = str(path.relative_to(root))
    if key not in manifest or hashlib.sha256(path.read_bytes()).hexdigest() != manifest[key]:
        raise RuntimeError('PRIVATE_ORIGINAL_DIGEST_MISMATCH')
    return path
