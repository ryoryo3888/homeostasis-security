"""Private evidence and explicit public audit projection; no provider execution."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import uuid

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_FIELDS = ('run', 'turn', 'agent_id', 'agent_type', 'model', 'schema_version',
                 'timestamp', 'seed', 'commit_sha', 'prompt_version', 'private_configuration_sha256', 'attempt',
                 'token_usage', 'response_status', 'failure_type', 'provider_status_code',
                 'automatic_regeneration', 'snapshot_id', 'response_sha256',
                 'request_contents_sha256', 'request_config_sha256', 'working_tree_dirty')
PROMPT_KEYS = ('role', 'decision_instruction', 'action_instruction', 'proposal_instruction',
               'response_contract', 'recipient_rules', 'response_options', 'system_instruction', 'systemInstruction')
OBSERVATION_KEYS = ('turn_start_observation', 'observable_world', 'executed_true_state', 'observation')


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()


def input_fingerprints(payload):
    if not isinstance(payload, dict):
        return {'request_sha256': fingerprint(payload), 'prompt_sha256': None, 'observation_sha256': None}
    prompt = {k: payload[k] for k in PROMPT_KEYS if k in payload}
    observation = {k: payload[k] for k in OBSERVATION_KEYS if k in payload}
    return {'request_sha256': fingerprint(payload),
            'prompt_sha256': fingerprint(prompt) if prompt else None,
            'observation_sha256': fingerprint(observation) if observation else None}


def public_audit(record):
    out = {k: record.get(k) for k in PUBLIC_FIELDS}
    payload = record.get('public_observation_payload')
    out.update(input_fingerprints(payload) if payload is not None else
               {k: record.get(k) for k in ('request_sha256','prompt_sha256','observation_sha256')})
    out['fingerprint_format'] = 'sha256-json-utf8-sorted-compact-v1'
    out['retry_count'] = max(0, record['attempt'] - 1) if type(record.get('attempt')) is int else None
    out['validation_success'] = True if record.get('response_status') == 'validated' else False if record.get('response_status') == 'validation_failed' else None
    # Research outputs live in the existing result tree, not a duplicate raw SDK record.
    return out


def public_result(value):
    if isinstance(value, list):
        return [public_result(v) for v in value]
    if isinstance(value, dict):
        return {k: [public_audit(v) for v in child] if k == 'call_audit' else public_result(child)
                for k, child in value.items()}
    return value


def private_root():
    p = Path(os.environ.get('HOMEOSTASIS_PRIVATE_RUNS', str(ROOT / 'private_runs'))).resolve()
    if p.is_relative_to(ROOT) and not p.is_relative_to(ROOT / 'private_runs'):
        raise ValueError('PRIVATE_RUNS_MUST_NOT_BE_PUBLIC')
    p.mkdir(parents=True, exist_ok=True, mode=0o700)
    return p


def require_private_path(path):
    p = Path(path).resolve()
    if p.is_relative_to(ROOT) and not any(p.is_relative_to(ROOT / folder) for folder in ('private_runs', '.artifacts')):
        raise ValueError('RAW_DESTINATION_IS_PUBLIC_USE_PRIVATE_RUNS')
    return p


def private_checkpoint(output):
    ident = hashlib.sha256(str(Path(output).resolve()).encode()).hexdigest()
    return private_root() / 'checkpoints' / (ident + '.json')


def preserve(value, category='raw'):
    directory = private_root() / category
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = directory / (uuid.uuid4().hex + '.json')
    data = json.dumps(value, ensure_ascii=False, allow_nan=False).encode('utf-8')
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(data); stream.flush(); os.fsync(stream.fileno())
    return {'sha256': hashlib.sha256(data).hexdigest(), 'id': path.stem}


def new_metadata():
    p = subprocess.run(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], capture_output=True, text=True)
    dirty = subprocess.run(['git', '-C', str(ROOT), 'status', '--porcelain'], capture_output=True, text=True)
    return {'working_tree_dirty': bool(dirty.stdout) if dirty.returncode == 0 else None,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'commit_sha': p.stdout.strip() if p.returncode == 0 else None}


def reject_legacy_checkpoint(output):
    """Never reinterpret a legacy checkpoint as a fresh run or migrate it."""
    legacy = Path(output).with_suffix(Path(output).suffix + '.checkpoint')
    if os.path.lexists(legacy):
        raise ValueError('旧形式checkpointのため再開停止 (LEGACY_CHECKPOINT_RESTART_BLOCKED)')


def private_receipts(output):
    ident = hashlib.sha256(str(Path(output).resolve()).encode()).hexdigest()
    return private_root() / 'response-receipts' / ident
