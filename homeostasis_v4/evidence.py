"""Evidence Format 1: immutable conditions/RAW, separately derived reports.

Integrity is not provider authentication. An absent terminal record is an
unfinalized attempt, never a successful run. No model or network is used here.
"""
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import re

from jsonschema import Draft202012Validator
from homeostasis_v3.contracts import canonical, digest, obj, TEXT, HASH, UINT
from model_response_json import load_response_object
from v2_autonomous import Journal

FORMAT = 'homeostasis-evidence-1'
MANIFEST = obj({
    'format': {'const': FORMAT}, 'run_id': TEXT, 'started_at': TEXT,
    'seed': {'type': ['integer', 'null']}, 'seed_scope': TEXT,
    'provider': TEXT, 'model': TEXT,
    'model_version_or_digest': {'type': ['string', 'null']},
    'generation_config': {'type': 'object'},
    'experiment_config': {'type': 'object'}, 'world_config': {'type': 'object'},
    'provenance': obj({'source_hashes': {'type': 'object', 'minProperties': 1,
                                      'additionalProperties': HASH},
                       'source_commit': {'type': ['string', 'null']},
                       'runtime': {'type': 'object'},
                       'parent_evidence_hash': {'anyOf': [HASH, {'type': 'null'}]},
                       'purpose': TEXT}),
})
TERMINAL = obj({
    'format': {'const': FORMAT}, 'run_id': TEXT,
    'status': {'enum': ['success', 'failure', 'interrupted']},
    'ended_at': TEXT, 'completed_turns': UINT,
    'error': {'type': ['object', 'null']},
    'manifest_sha256': HASH, 'raw_evidence_hash': HASH,
    'raw_files': {'type': 'object', 'additionalProperties': HASH},
})


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def _time(value):
    result = datetime.fromisoformat(value)
    if result.tzinfo is None:
        raise ValueError('TIMESTAMP_TIMEZONE_REQUIRED')
    return result


def _hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_record(path):
    """Public copies may have normal Git permissions; symlinks are not records."""
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError('REGULAR_EVIDENCE_FILE_REQUIRED')
    value = load_response_object(path.read_text(encoding='utf-8'))
    if set(value) != {'sha256', 'payload'} or digest(value['payload']) != value['sha256']:
        raise ValueError('EVIDENCE_DIGEST_MISMATCH')
    return value['payload']


def _inventory(root):
    raw = root / 'RAW'
    if raw.is_symlink() or not raw.is_dir():
        raise ValueError('RAW_DIRECTORY_REQUIRED')
    result = {}
    for path in sorted(raw.iterdir()):
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*\.json', path.name):
            raise ValueError('UNRECOGNIZED_RAW_FILE')
        read_record(path)
        result['RAW/' + path.name] = _hash(path)
    return result


def verify(directory, *, expected_evidence_hash=None):
    root = Path(directory)
    if root.is_symlink() or not root.is_dir():
        raise ValueError('EVIDENCE_DIRECTORY_REQUIRED')
    if any(p.name not in {'manifest.json', 'terminal.json', 'RAW', 'DERIVED'}
           for p in root.iterdir()):
        raise ValueError('UNRECOGNIZED_EVIDENCE_FILE')
    manifest = read_record(root / 'manifest.json')
    Draft202012Validator(MANIFEST).validate(manifest)
    _time(manifest['started_at'])
    files = _inventory(root)
    raw_hash = digest(files)
    terminal_path = root / 'terminal.json'
    terminal = read_record(terminal_path) if terminal_path.exists() or terminal_path.is_symlink() else None
    if terminal is not None:
        Draft202012Validator(TERMINAL).validate(terminal)
        if (terminal['run_id'] != manifest['run_id'] or terminal['raw_files'] != files
                or terminal['raw_evidence_hash'] != raw_hash
                or terminal['manifest_sha256'] != _hash(root / 'manifest.json')
                or _time(terminal['ended_at']) < _time(manifest['started_at'])):
            raise ValueError('TERMINAL_EVIDENCE_MISMATCH')
        if terminal['status'] == 'success' and (terminal['error'] is not None or not files):
            raise ValueError('SUCCESS_WITH_ERROR_OR_NO_EVIDENCE')
    derived = root / 'DERIVED'
    if derived.is_symlink() or not derived.is_dir():
        raise ValueError('DERIVED_DIRECTORY_REQUIRED')
    for path in derived.iterdir():
        report = read_record(path)
        if report.get('raw_evidence_hash') != raw_hash:
            raise ValueError('DERIVED_SOURCE_MISMATCH')
    evidence_hash = digest({'manifest_sha256': _hash(root / 'manifest.json'),
                            'raw_evidence_hash': raw_hash,
                            'terminal_sha256': _hash(terminal_path) if terminal else None})
    if expected_evidence_hash is not None and evidence_hash != expected_evidence_hash:
        raise ValueError('PINNED_EVIDENCE_MISMATCH')
    return {'run_id': manifest['run_id'],
            'status': terminal['status'] if terminal else 'unfinalized',
            'ended_at': terminal['ended_at'] if terminal else None,
            'completion_record_present': terminal is not None,
            'raw_files': len(files), 'raw_evidence_hash': raw_hash,
            'evidence_hash': evidence_hash}


class EvidenceRun:
    """New attempts only. A failure cannot overwrite or resume an earlier run."""
    def __init__(self, directory, manifest):
        Draft202012Validator(MANIFEST).validate(manifest)
        _time(manifest['started_at'])
        self.root = Path(directory)
        self.root.mkdir(mode=0o700)
        (self.root / 'RAW').mkdir(mode=0o700)
        (self.root / 'DERIVED').mkdir(mode=0o700)
        Journal(self.root).write('manifest.json', manifest)

    def write(self, name, payload):
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*\.json', name):
            raise ValueError('INVALID_RAW_NAME')
        if (self.root / 'terminal.json').exists():
            raise ValueError('EVIDENCE_ALREADY_FINALIZED')
        Journal(self.root / 'RAW').write(name, payload)

    def finish(self, status, *, completed_turns, error=None):
        manifest = read_record(self.root / 'manifest.json')
        files = _inventory(self.root)
        terminal = {'format': FORMAT, 'run_id': manifest['run_id'], 'status': status,
                    'ended_at': timestamp(), 'completed_turns': completed_turns, 'error': error,
                    'manifest_sha256': _hash(self.root / 'manifest.json'),
                    'raw_evidence_hash': digest(files), 'raw_files': files}
        Draft202012Validator(TERMINAL).validate(terminal)
        if status == 'success' and (error is not None or not files):
            raise ValueError('SUCCESS_WITH_ERROR_OR_NO_EVIDENCE')
        Journal(self.root).write('terminal.json', terminal)
        return verify(self.root)

    def derive(self, name, report):
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*\.json', name):
            raise ValueError('INVALID_DERIVED_NAME')
        result = verify(self.root)
        if not result['completion_record_present']:
            raise ValueError('FINALIZE_BEFORE_DERIVING')
        Journal(self.root / 'DERIVED').write(name, {
            'raw_evidence_hash': result['raw_evidence_hash'], 'report': report})
