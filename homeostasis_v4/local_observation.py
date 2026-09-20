"""Local-only V4 pilot; unchanged dialogue/world, no repairs or retries.

Ollama 0.34.2 is pinned because its generate API supports truncate=false and
shift=false. This adapter never starts servers, pulls models or loads secrets.
"""
import base64
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import platform
import re
import subprocess
import time
import uuid

import httpx

from homeostasis_core.execution_lock import exclusive_execution
from homeostasis_v3.agent_adapter import ExchangeBudget
from homeostasis_v3.choices import ensure
from homeostasis_v3.contracts import canonical, digest
from homeostasis_v3.network import load_network
from homeostasis_v3.physical import load_baseline
from homeostasis_v3.turn import TurnRunner
from homeostasis_v4.dialogue import DialogueRunner, SYSTEM_INSTRUCTION, REPLY
from homeostasis_v4.evidence import EvidenceRun, FORMAT, read_record, timestamp, verify
from homeostasis_v4.observation_run import sources
from model_response_json import load_response_object

ROOT = Path(__file__).resolve().parents[1]
ENDPOINT = 'http://127.0.0.1:11434'
SERVER_VERSION = '0.34.2'
SOURCE = 'Local Ollama V4 exploratory pilot'


def source_hashes():
    result = sources()
    path = ROOT / 'tools/run_v4_local.py'
    result[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def runner():
    baseline = load_baseline(ROOT / 'scenarios/v3/synthetic_baseline.json')
    network = load_network(ROOT / 'scenarios/v3/synthetic_network.json', baseline)
    return DialogueRunner(TurnRunner(baseline, network, pool_location='MIL',
        context_id='v4-free-dialogue-observation', search_budget=1000000), source=SOURCE)


def get_json(client, method, path, **kwargs):
    response = client.request(method, ENDPOINT + path, **kwargs)
    response.raise_for_status()
    return load_response_object(response.text)


def identity(client, model):
    ensure(re.fullmatch(r'[a-z0-9_.-]+:[a-z0-9_.-]+', model) is not None
           and 'cloud' not in model, 'LOCAL_MODEL_NAME_REQUIRED')
    version = get_json(client, 'GET', '/api/version')
    ensure(version.get('version') == SERVER_VERSION, 'UNVERIFIED_OLLAMA_VERSION')
    cloud = get_json(client, 'GET', '/api/status')
    ensure(cloud.get('cloud', {}).get('disabled') is True, 'OLLAMA_CLOUD_MUST_BE_DISABLED')
    models = get_json(client, 'GET', '/api/tags')['models']
    selected = [m for m in models if m.get('name') == model or m.get('model') == model]
    ensure(len(selected) == 1, 'LOCAL_MODEL_NOT_INSTALLED')
    tag = selected[0]
    show = get_json(client, 'POST', '/api/show', json={'model': model})
    ensure(not any(v.get('remote_host') or v.get('remote_model') for v in (tag, show)), 'REMOTE_MODEL_FORBIDDEN')
    ensure(not show.get('system') and not show.get('messages'), 'EMBEDDED_MODEL_INSTRUCTIONS_FORBIDDEN')
    ensure(re.fullmatch(r'(sha256:)?[0-9a-f]{64}', tag.get('digest', '')) is not None, 'MODEL_DIGEST_REQUIRED')
    # Exclude generated Modelfile: it contains a machine-specific absolute path.
    fields = ('details', 'model_info', 'parameters', 'template', 'capabilities',
              'renderer', 'parser', 'license', 'requires')
    return {'version': version, 'cloud': cloud,
            'model': model, 'digest': tag['digest'], 'size': tag['size'],
            'details': {k: show[k] for k in fields if k in show},
            'metadata_scope': 'selected API fields; generated Modelfile and local paths excluded'}


def same_identity(actual, expected):
    """Ignore parameter-key display order, preserving values and repeated order."""
    def normalized(value):
        result = deepcopy(value)
        parameters = result.get('details', {}).get('parameters')
        if isinstance(parameters, str):
            groups = {}
            for line in parameters.splitlines():
                if not line.strip():
                    continue
                parts = line.strip().split(None, 1)
                if len(parts) != 2:
                    return result  # Unknown representation: compare it exactly.
                key, argument = parts
                groups.setdefault(key, []).append(argument)
            result['details']['parameters'] = groups
        return result
    return normalized(actual) == normalized(expected)


def memory_sample(client, model):
    result = {'timestamp': timestamp(), 'measurements': {},
              'scope': 'samples, not continuous peak measurement; RSS excludes some shared GPU accounting'}
    for label, command in (
        ('vm_stat', ['/usr/bin/vm_stat']),
        ('swap_usage', ['/usr/sbin/sysctl', 'vm.swapusage']),
    ):
        try:
            p = subprocess.run(command, capture_output=True, text=True, timeout=5)
            result['measurements'][label] = p.stdout.strip() if p.returncode == 0 else None
        except (OSError, subprocess.TimeoutExpired):
            result['measurements'][label] = None
    try:
        p = subprocess.run(['/bin/ps', '-axo', 'rss=,comm='], capture_output=True, text=True, timeout=5)
        rss = [int(line.split(None, 1)[0]) * 1024 for line in p.stdout.splitlines()
               if len(line.split(None, 1)) == 2 and Path(line.split(None, 1)[1]).name in ('ollama', 'ollama_llama_server')]
        result['measurements']['ollama_rss_bytes_sum'] = sum(rss) if p.returncode == 0 else None
    except (OSError, ValueError, subprocess.TimeoutExpired):
        result['measurements']['ollama_rss_bytes_sum'] = None
    try:
        result['measurements']['model_allocation'] = [m for m in get_json(client, 'GET', '/api/ps')['models']
            if m.get('name') == model or m.get('model') == model]
    except (httpx.HTTPError, ValueError, KeyError):
        result['measurements']['model_allocation'] = None
    return result


def hardware():
    result = {'system': platform.system(), 'machine': platform.machine(),
              'python': platform.python_version()}
    for key in ('hw.memsize', 'hw.model', 'machdep.cpu.brand_string'):
        try:
            p = subprocess.run(['/usr/sbin/sysctl', '-n', key], capture_output=True, text=True, timeout=5)
            result[key] = p.stdout.strip() if p.returncode == 0 else None
        except (OSError, subprocess.TimeoutExpired):
            result[key] = None
    return result


def prepare(client, *, model, seed, turns, num_ctx=16384, num_predict=2048, synthetic=False,
            structured_output=False):
    ensure(type(seed) is int and 0 <= seed < 2**31 - 800, 'INVALID_SEED')
    ensure(type(turns) is int and 1 <= turns <= 8, 'PILOT_TURN_LIMIT')
    ensure(type(num_ctx) is int and 4096 <= num_ctx <= 32768, 'PILOT_CONTEXT_LIMIT')
    ensure(type(num_predict) is int and 1 <= num_predict <= 8192, 'PILOT_OUTPUT_LIMIT')
    ensure(type(structured_output) is bool, 'INVALID_STRUCTURED_OUTPUT_OPTION')
    model_identity = identity(client, model)
    world = runner()
    return {'kind': 'local_v4_pilot', 'model_identity': model_identity,
            'evidence_origin': 'injected_transport_test' if synthetic else 'local_model',
            'hardware': hardware(),
            'seed': seed, 'seed_scope': 'Ollama generation seed = run seed + zero-based request sequence; deterministic world has no RNG',
            'generation_config': {'model': model,
                'format': deepcopy(REPLY) if structured_output else 'json', 'stream': False,
                'think': False, 'truncate': False, 'shift': False, 'keep_alive': '5m',
                'options': {'num_ctx': num_ctx, 'num_predict': num_predict}},
            'unspecified_sampling': 'Use recorded model parameters and pinned server defaults; not assumed equal to Gemini',
            'turns': turns, 'participants': world.states, 'max_generations': turns * len(world.states),
            'request_timeout_seconds': 180, 'run_deadline_seconds': 1200,
            'source_hashes': source_hashes(), 'world_config': world.config,
            'external_shocks': [], 'automatic_retries': False, 'observer_feedback': False,
            'formal_research_eligibility': False}


class LocalExchange:
    def __init__(self, client, evidence, settings, telemetry=memory_sample):
        self.client = client; self.evidence = evidence; self.settings = settings
        self.telemetry = telemetry; self.sequence = 0; self.started = time.monotonic()

    def __call__(self, raw):
        s = self.settings
        ensure(source_hashes() == s['source_hashes'], 'LOCAL_SOURCE_CHANGED')
        ensure(time.monotonic() - self.started < s['run_deadline_seconds'], 'PILOT_DEADLINE_REACHED')
        ensure(self.sequence < s['max_generations'], 'PILOT_CALL_LIMIT')
        ensure(same_identity(identity(self.client, s['model_identity']['model']), s['model_identity']), 'LOCAL_MODEL_CHANGED')
        index = self.sequence; self.sequence += 1
        body = {**s['generation_config'], 'system': SYSTEM_INSTRUCTION, 'prompt': raw,
                'options': {**s['generation_config']['options'], 'seed': s['seed'] + index}}
        self.evidence.write(f'call-{index:03d}.request.json', {'timestamp': timestamp(), 'body': body})
        response = None; chunks = []; started = time.monotonic(); error = None
        try:
            request = self.client.build_request('POST', ENDPOINT + '/api/generate', json=body)
            response = self.client.send(request, stream=True)
            for chunk in response.iter_bytes():
                chunks.append(chunk)
            response.raise_for_status()
        except BaseException as exc:
            error = type(exc).__name__
            raise
        finally:
            if response is not None:
                response.close()
            self.evidence.write(f'call-{index:03d}.wire.json', {
                'timestamp': timestamp(), 'duration_seconds': time.monotonic() - started,
                'status_code': response.status_code if response is not None else None,
                'body_base64': base64.b64encode(b''.join(chunks)).decode(), 'error_type': error})
        self.evidence.write(f'call-{index:03d}.memory.json', self.telemetry(self.client, body['model']))
        data = load_response_object(b''.join(chunks).decode('utf-8'))
        ensure(not data.get('remote_host') and not data.get('remote_model'), 'REMOTE_RESPONSE_FORBIDDEN')
        ensure(data.get('model') == body['model'] and data.get('done') is True
               and data.get('done_reason') == 'stop', 'INCOMPLETE_LOCAL_RESPONSE')
        ensure(isinstance(data.get('response'), str), 'LOCAL_RESPONSE_TEXT_REQUIRED')
        print(f'Local response {index + 1}/{s["max_generations"]} saved.', flush=True)
        return data['response']


def execute(directory, settings, *, protocol_digest, client, telemetry=memory_sample):
    ensure(digest(settings) == protocol_digest, 'PREPARED_LOCAL_PROTOCOL_CHANGED')
    ensure(source_hashes() == settings['source_hashes'], 'LOCAL_SOURCE_CHANGED')
    world = runner()
    ensure(world.config == settings['world_config'], 'LOCAL_WORLD_CHANGED')
    try:
        commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        commit = None
    manifest = {'format': FORMAT, 'run_id': 'local-' + str(uuid.uuid4()), 'started_at': timestamp(),
        'seed': settings['seed'], 'seed_scope': settings['seed_scope'],
        'provider': 'synthetic-transport' if settings['evidence_origin'] == 'injected_transport_test' else 'ollama-local',
        'model': settings['model_identity']['model'],
        'model_version_or_digest': settings['model_identity']['digest'],
        'generation_config': settings['generation_config'],
        'experiment_config': settings, 'world_config': world.config,
        'provenance': {'source_hashes': settings['source_hashes'], 'source_commit': commit,
            'runtime': {**settings['hardware'], 'ollama': SERVER_VERSION},
            'parent_evidence_hash': None, 'purpose': 'local feasibility pilot, not formal research'}}
    directory = Path(directory)
    with exclusive_execution(directory):
        evidence = EvidenceRun(directory, manifest)
        checkpoint = world.genesis(); exchange = LocalExchange(client, evidence, settings, telemetry)
        evidence.write('turn-000.json', checkpoint)
        evidence.write('memory-before.json', telemetry(client, manifest['model']))
        status = 'success'; error = None
        try:
            ensure(same_identity(identity(client, manifest['model']), settings['model_identity']), 'LOCAL_MODEL_CHANGED')
            budget = ExchangeBudget(settings['max_generations'])
            for turn in range(1, settings['turns'] + 1):
                candidate = world.run(checkpoint, exchange=exchange, budget=budget)
                world.replay(checkpoint, candidate)
                evidence.write(f'turn-{turn:03d}.json', candidate)
                checkpoint = candidate
                print(f'Local TURN {turn}/{settings["turns"]} verified and saved.', flush=True)
            ensure(same_identity(identity(client, manifest['model']), settings['model_identity']), 'LOCAL_MODEL_CHANGED')
        except BaseException as exc:
            status = 'interrupted' if isinstance(exc, (KeyboardInterrupt, SystemExit)) else 'failure'
            error = {'exception_type': type(exc).__name__, 'code': getattr(exc, 'code', None),
                     'turn_failure': getattr(exc, 'record', None), 'not_an_agent_decision': True}
            evidence.write('failure.json', {'timestamp': timestamp(), **error})
        evidence.write('memory-after.json', telemetry(client, manifest['model']))
        elapsed = time.monotonic() - exchange.started
        evidence.write('execution-end.json', {'timestamp': timestamp(), 'elapsed_seconds': elapsed,
                                             'generation_attempts': exchange.sequence})
        result = evidence.finish(status, completed_turns=checkpoint['dialogue']['turn'], error=error)
        evidence.derive('execution-summary.json', {
            'generation_attempts': exchange.sequence,
            'completed_turns': checkpoint['dialogue']['turn'],
            'elapsed_seconds': elapsed,
            'final_checkpoint_digest': checkpoint['checkpoint_digest'],
            'paid_api_calls': 0, 'automatic_retries': 0,
            'raw_bytes': sum(p.stat().st_size for p in (directory / 'RAW').iterdir()),
            'model_mode': 'local; think=false; defaults recorded; no seed reproducibility guarantee'})
        return result


def replay(directory):
    """Rebuild in chronological order, including insertion-ordered offer views."""
    directory = Path(directory)
    integrity = verify(directory)
    world = runner()
    manifest = read_record(directory / 'manifest.json')
    settings = manifest['experiment_config']
    ensure(world.config == manifest['world_config'], 'LOCAL_REPLAY_CONFIG_CHANGED')
    checkpoint = world.genesis()
    ensure(checkpoint == read_record(directory / 'RAW/turn-000.json'), 'LOCAL_GENESIS_MISMATCH')
    for path in sorted((directory / 'RAW').glob('turn-*.json')):
        if path.name == 'turn-000.json':
            continue
        candidate = read_record(path)
        for offset, actor in enumerate(world.states):
            index = checkpoint['dialogue']['turn'] * len(world.states) + offset
            request = read_record(directory / f'RAW/call-{index:03d}.request.json')['body']
            expected = {**settings['generation_config'], 'system': SYSTEM_INSTRUCTION,
                'prompt': canonical(candidate['input']['requests'][actor]),
                'options': {**settings['generation_config']['options'], 'seed': settings['seed'] + index}}
            ensure(request == expected, 'LOCAL_WIRE_REQUEST_MISMATCH')
            wire = read_record(directory / f'RAW/call-{index:03d}.wire.json')
            response = load_response_object(base64.b64decode(wire['body_base64']).decode())
            ensure(wire['status_code'] == 200 and wire['error_type'] is None
                   and response.get('response') == candidate['input']['raw_replies'][actor]
                   and response.get('done') is True and response.get('done_reason') == 'stop',
                   'LOCAL_WIRE_RESPONSE_MISMATCH')
        checkpoint = world.replay(checkpoint, candidate)
    terminal = read_record(directory / 'terminal.json')
    ensure(checkpoint['dialogue']['turn'] == terminal['completed_turns'], 'LOCAL_TURN_COUNT_MISMATCH')
    return {**integrity, 'replayed_turns': checkpoint['dialogue']['turn']}
