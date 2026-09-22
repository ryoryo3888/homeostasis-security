from __future__ import annotations

import base64
from datetime import date
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import platform
import subprocess
from typing import Any
import uuid

import httpx

from homeostasis_core.execution_lock import exclusive_execution
from homeostasis_v3.contracts import digest
from homeostasis_v4.evidence import EvidenceRun, FORMAT, read_record, timestamp, verify
from homeostasis_v5.life_first_generation import wire_bytes
from homeostasis_v5.paired_diplomacy_experiment import (
    COMMUNICATION_BUDGET_CHARS,
    CONDITIONS,
    DOCUMENT_TYPE,
    NORMAL,
    NO_DIPLOMACY,
    TURN_MAX,
    TURN_MIN,
    VERSION as CONTRACT_VERSION,
    build_turn_snapshot,
    decision_schema,
    validate_decision,
)
from homeostasis_v5.persona_generation import GenerationError, account_usage, ensure, price, _extract_persona
from homeostasis_v5.world_law_settlement import (
    VERSION as WORLD_LAW_VERSION,
    WorldLawState,
    apply_dispatch_if_scheduled,
    process_arrivals,
    settlement_funnel,
    summarize_world_state,
)
from model_response_json import load_response_object
from tools.prepare_v5_paired_diplomacy_preregistration import load_base, stable_hash
from v2_autonomous import Journal

ROOT = Path(__file__).resolve().parents[1]
PREPARE_DIR = ROOT / 'results/v5-generated-nations/paired-diplomacy-prepare-only-20260922'
MODEL = 'gemini-3.6-flash'
ENDPOINT = 'https://generativelanguage.googleapis.com/v1beta/models/' + MODEL
VERSION = 'v5-paired-diplomacy-20run-execution-1'
MAX_INPUT = 48000
MAX_OUTPUT = 8192
CALLS_PER_RUN = (TURN_MAX - TURN_MIN + 1) * 12
STOP_LIMIT_PER_RUN = Decimal('8.5000000000')
CONFIG = {
    'responseMimeType': 'application/json',
    'temperature': 1.0,
    'candidateCount': 1,
    'maxOutputTokens': MAX_OUTPUT,
    'thinkingConfig': {'thinkingLevel': 'LOW', 'includeThoughts': False},
}


def _runtime() -> dict[str, str]:
    return {'python': platform.python_version()}


def source_hashes() -> dict[str, str]:
    names = (
        'homeostasis_v5/paired_diplomacy_generation.py',
        'homeostasis_v5/paired_diplomacy_experiment.py',
        'homeostasis_v5/world_law_settlement.py',
        'tools/run_v5_paired_diplomacy_20runs.py',
        'tools/prepare_v5_paired_diplomacy_preregistration.py',
        'homeostasis_v5/persona_generation.py',
        'homeostasis_v4/evidence.py',
        'model_response_json.py',
    )
    return {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in names if (ROOT / name).exists()}


def _load_manifests(prepare_dir: Path = PREPARE_DIR) -> list[dict[str, Any]]:
    manifests = []
    for path in sorted((prepare_dir / 'manifests').glob('*.json')):
        manifest = json.loads(path.read_text(encoding='utf-8'))
        ensure(manifest['api_executed'] is False, 'MANIFEST_ALREADY_EXECUTED_FLAG_CHANGED')
        ensure(manifest['turns'] == {'start': 1, 'end': 36, 'turn_count': 36, 'turn_length_days': 30}, 'MANIFEST_TURN_SCOPE_CHANGED')
        ensure(manifest['condition'] in CONDITIONS, 'MANIFEST_CONDITION_UNKNOWN')
        manifests.append(manifest)
    ensure(len(manifests) == 20, 'MANIFEST_COUNT_NOT_20')
    return manifests


def _manifest_by_run_id(manifests: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result = {m['run_id']: m for m in manifests}
    ensure(len(result) == len(manifests), 'DUPLICATE_RUN_ID')
    return result


def _initial_world_law_state(world_id: str) -> WorldLawState:
    return WorldLawState(
        world_id=world_id,
        turn=TURN_MIN,
        unmet_need={
            'vegetable_fresh_produce_supply': 0,
            'communications_stability': 0,
            'clean_water_public_health': 0,
            'medical_logistics': 0,
        },
        transport_capacity={},
        route_eligibility={},
    )


def _state_to_payload(state: WorldLawState) -> dict[str, Any]:
    return {
        'world_id': state.world_id,
        'turn': state.turn,
        'unmet_need': dict(state.unmet_need),
        'transport_capacity': dict(state.transport_capacity),
        'route_eligibility': dict(state.route_eligibility),
        'dispatched': list(state.dispatched),
        'arrivals': list(state.arrivals),
        'world_state_mutations': list(state.world_state_mutations),
    }


def _state_from_payload(payload: dict[str, Any]) -> WorldLawState:
    return WorldLawState(
        world_id=payload['world_id'],
        turn=payload['turn'],
        unmet_need=dict(payload.get('unmet_need', {})),
        transport_capacity=dict(payload.get('transport_capacity', {})),
        route_eligibility=dict(payload.get('route_eligibility', {})),
        dispatched=list(payload.get('dispatched', [])),
        arrivals=list(payload.get('arrivals', [])),
        world_state_mutations=list(payload.get('world_state_mutations', [])),
    )


def _history_message(source_world: dict[str, Any], output: dict[str, Any], msg: dict[str, Any]) -> dict[str, Any]:
    leader_index = int(output['leader_id'].split('-')[1]) - 1
    intro = source_world['leaders'][leader_index].get('presentation', {}).get('self_introduction')
    attached = intro if msg.get('attach_self_introduction') else None
    return {
        'turn': output['turn'],
        'from_nation_id': output['nation_id'],
        'from_leader_id': output['leader_id'],
        'to_nation_ids': msg['to_nation_ids'],
        'body': msg['body'],
        'attach_self_introduction': msg.get('attach_self_introduction', False),
        'attached_self_introduction': attached,
        'message_id': msg['message_id'],
    }


def _acceptance_candidates(messages: list[dict[str, Any]], decisions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    words = ('承諾', '受け入れ', '受け容れ', '合意', '同意', 'accept', 'accepted', 'agree', 'agreed')
    acceptances = []
    for msg in messages:
        body = (msg.get('body') or '').lower()
        if any(word.lower() in body for word in words):
            acceptances.append({
                'from_nation_id': msg['from_nation_id'],
                'to_nation_ids': msg.get('to_nation_ids', []),
                'source': 'message_text',
                'source_id': msg.get('message_id'),
            })
    for decision in decisions:
        for proposal in decision.get('proposals', []):
            body = (proposal.get('body') or '').lower()
            if any(word.lower() in body for word in words):
                acceptances.append({
                    'from_nation_id': decision['nation_id'],
                    'to_nation_ids': proposal.get('to_nation_ids', []),
                    'source': 'proposal_text',
                    'source_id': proposal.get('proposal_id'),
                })
    return acceptances


def _settle_turn(state: WorldLawState, decisions: list[dict[str, Any]], messages: list[dict[str, Any]]) -> dict[str, Any]:
    state.turn = decisions[0]['turn'] if decisions else state.turn
    arrivals = process_arrivals(state, turn=state.turn)
    acceptances = _acceptance_candidates(messages, decisions)
    funnels = []
    for decision in decisions:
        for proposal in decision.get('proposals', []):
            funnel = settlement_funnel(proposal, source_nation_id=decision['nation_id'], acceptances=acceptances, state=state)
            applied = apply_dispatch_if_scheduled(funnel, state)
            funnels.append(applied)
    return {
        'version': WORLD_LAW_VERSION,
        'turn': state.turn,
        'arrivals_processed': arrivals,
        'acceptance_candidates': acceptances,
        'proposal_funnels': funnels,
        'world_state_summary': summarize_world_state(state),
        'world_state': _state_to_payload(state),
    }


def _body(snapshot: dict[str, Any], *, condition: str, seed_value: int) -> dict[str, Any]:
    if condition == NORMAL:
        instruction = (
            'あなたはHOMEOSTASIS SECURITY V5 Emergent Societyの国家Leaderです。'
            '固定済みの36ターン比較実験です。与えられたturn開始snapshotだけを見て、外交通信・提案・国内判断を自律的に決めてください。'
            '固定ペア、専用仲介役、全員へ必ず連絡する規則はありません。'
            '発言だけで物理世界を変更できません。物資到着・復旧・被害変化は別の物理成立判定でのみ扱われます。'
            'JSON schemaに従い、世界状態を直接変更しないことを明示してください。'
        )
    else:
        instruction = (
            'あなたはHOMEOSTASIS SECURITY V5 Emergent Societyの国家Leaderです。'
            '固定済みの36ターン比較実験です。この条件では外交通信、他国宛メッセージ、他国宛提案、他国への資源提供、交渉、明示的な外交上の承諾・拒否は使えません。'
            '公開された世界状況は見えますが、他国と直接連絡する経路はありません。国内観察・国内配分・国内対策だけを自律的に決めてください。'
            '発言だけで物理世界を変更できません。物資到着・復旧・被害変化は別の物理成立判定でのみ扱われます。'
            'JSON schemaに従い、世界状態を直接変更しないことを明示してください。'
        )
    config = {**CONFIG, 'seed': seed_value, 'responseJsonSchema': decision_schema(condition)}
    return {'contents': [{'role': 'user', 'parts': [
        {'text': instruction},
        {'text': json.dumps(snapshot, ensure_ascii=False, separators=(',', ':'))},
    ]}], 'generationConfig': config}


def prepare(directory: Path, *, prepare_dir: Path = PREPARE_DIR) -> dict[str, Any]:
    ensure(date.today() <= date(2026, 12, 31), 'PRICE_WINDOW_EXPIRED')
    directory = Path(directory)
    manifests = _load_manifests(prepare_dir)
    base_plan, source_world = load_base()
    ensure(stable_hash(source_world) == manifests[0]['world']['source_world_sha256'], 'SOURCE_WORLD_HASH_MISMATCH')
    with exclusive_execution(directory):
        ensure(not directory.exists() and not directory.is_symlink(), 'NEW_BATCH_REQUIRED')
        directory.mkdir(mode=0o700, parents=True)
        plan = {
            'version': VERSION,
            'batch_id': 'v5-paired-diplomacy-20run-' + uuid.uuid4().hex,
            'created_at': timestamp(),
            'model': MODEL,
            'prepare_directory': str(prepare_dir),
            'source_world': source_world,
            'source_world_sha256': stable_hash(source_world),
            'base_plan_sha256': digest(base_plan),
            'manifests': manifests,
            'manifest_sha256_by_run_id': {m['run_id']: m['manifest_sha256'] for m in manifests},
            'max_generation_calls_per_run': CALLS_PER_RUN,
            'max_generation_calls_total': CALLS_PER_RUN * len(manifests),
            'max_count_calls_total': CALLS_PER_RUN * len(manifests),
            'max_input_tokens': MAX_INPUT,
            'max_output_tokens_including_thoughts': MAX_OUTPUT,
            'usd_stop_limit_per_run': str(STOP_LIMIT_PER_RUN),
            'per_attempt_reservation_usd': str(price(MAX_INPUT, MAX_OUTPUT)),
            'retry_count': 0,
            'concurrency': 1,
            'turns': {'start': TURN_MIN, 'end': TURN_MAX, 'turn_count': TURN_MAX - TURN_MIN + 1},
            'world_law_version': WORLD_LAW_VERSION,
            'contract_version': CONTRACT_VERSION,
            'source_hashes': source_hashes(),
            'runtime': _runtime(),
            'source_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
            'publication': 'private_unpublished',
            'physical_settlement_executed': True,
            'result_before_snapshot_commit': '5078251dece19e141bec3d960f71494162ca533a',
        }
        Journal(directory).write('plan.json', plan)
        return {'status': 'prepared', 'runs': len(manifests), 'calls_total': CALLS_PER_RUN * len(manifests), 'plan_sha256': digest(plan)}


def _plan(directory: Path) -> dict[str, Any]:
    directory = Path(directory)
    ensure(directory.is_dir() and not directory.is_symlink() and not directory.stat().st_mode & 0o077, 'PRIVATE_BATCH_REQUIRED')
    plan = Journal(directory).read('plan.json')
    ensure(plan['version'] == VERSION and plan['model'] == MODEL, 'PLAN_VERSION_CHANGED')
    ensure(plan['turns'] == {'start': TURN_MIN, 'end': TURN_MAX, 'turn_count': TURN_MAX - TURN_MIN + 1}, 'PLAN_TURN_SCOPE_CHANGED')
    ensure(plan['source_hashes'] == source_hashes() and plan['runtime'] == _runtime(), 'SOURCE_OR_RUNTIME_CHANGED')
    return plan


def _run_dir(directory: Path, run_id: str) -> Path:
    return Path(directory) / run_id


def _run_state_paths(directory: Path, run_id: str) -> list[Path]:
    return sorted(_run_dir(directory, run_id).glob('run-state-*.json'))


def _latest_run_state_path(directory: Path, run_id: str) -> Path | None:
    paths = _run_state_paths(directory, run_id)
    return paths[-1] if paths else None


def _initial_run_state(plan: dict[str, Any], manifest: dict[str, Any]) -> dict[str, Any]:
    world_state = _initial_world_law_state(plan['source_world']['world_id'])
    return {
        'run_id': manifest['run_id'],
        'condition': manifest['condition'],
        'seed_label': manifest['seed_label'],
        'seed_value': manifest['seed_value_fixed_before_execution'],
        'next_index': 1,
        'message_history': [],
        'turn_decisions': [],
        'settlement_by_turn': [],
        'world_law_state': _state_to_payload(world_state),
        'complete': False,
    }


def _load_run_state(directory: Path, plan: dict[str, Any], manifest: dict[str, Any]) -> dict[str, Any]:
    run_dir = _run_dir(directory, manifest['run_id'])
    run_dir.mkdir(mode=0o700, exist_ok=True)
    path = _latest_run_state_path(directory, manifest['run_id'])
    if path is None:
        state = _initial_run_state(plan, manifest)
        Journal(run_dir).write('run-state-000.json', state)
        return state
    return read_record(path)


def _save_run_state(directory: Path, run_id: str, state: dict[str, Any]) -> None:
    completed = len(state.get('turn_decisions', []))
    Journal(_run_dir(directory, run_id)).write(f'run-state-{completed:03d}.json', state)


def _next_manifest(directory: Path, plan: dict[str, Any], requested_run_id: str | None = None) -> dict[str, Any]:
    manifests = plan['manifests']
    if requested_run_id:
        by_id = _manifest_by_run_id(manifests)
        ensure(requested_run_id in by_id, 'REQUESTED_RUN_ID_UNKNOWN')
        return by_id[requested_run_id]
    for manifest in manifests:
        path = _latest_run_state_path(directory, manifest['run_id'])
        if path is None:
            return manifest
        state = read_record(path)
        if not state.get('complete'):
            return manifest
    return manifests[-1]


def _attempt_root(directory: Path, run_id: str, index: int) -> Path:
    return _run_dir(directory, run_id) / f'attempt-{index:03d}'


def _existing_attempts(directory: Path, run_id: str) -> list[Path]:
    run_dir = _run_dir(directory, run_id)
    return sorted(run_dir.glob('attempt-*'), key=lambda p: int(p.name.split('-')[-1]))


def _current_actor(index: int) -> tuple[int, int]:
    turn = TURN_MIN + (index - 1) // 12
    actor_index = (index - 1) % 12
    return turn, actor_index


def _validate_history(directory: Path, plan: dict[str, Any], manifest: dict[str, Any], state: dict[str, Any]) -> None:
    attempts = _existing_attempts(directory, manifest['run_id'])
    ensure(len(attempts) == state['next_index'] - 1, 'RUN_STATE_ATTEMPT_COUNT_MISMATCH')
    for i, root in enumerate(attempts, 1):
        checked = verify(root)
        ensure(checked['status'] == 'success', 'PRIOR_ATTEMPT_NOT_SUCCESSFUL')
        output = read_record(root / 'DERIVED/output.json')['report']['output']
        ensure(output == state['turn_decisions'][i - 1], 'RUN_STATE_DECISION_MISMATCH')


def _error(exc: Exception) -> str:
    if isinstance(exc, GenerationError):
        return str(exc)
    if isinstance(exc, httpx.TimeoutException):
        return 'TRANSPORT_TIMEOUT'
    if isinstance(exc, httpx.HTTPError):
        return 'TRANSPORT_ERROR'
    if isinstance(exc, KeyboardInterrupt):
        return 'INTERRUPTED'
    if isinstance(exc, OSError):
        return 'LOCAL_IO_ERROR'
    return 'VALIDATION_OR_RUNTIME_ERROR'


def _failure_record(directory: Path, run_id: str, index: int, error: dict[str, Any]) -> None:
    Journal(_run_dir(directory, run_id)).write(f'blocked-{index:03d}.json', error)


def generate_next(directory: Path, *, credential: str, transport, run_id: str | None = None) -> dict[str, Any]:
    directory = Path(directory)
    ensure(isinstance(credential, str) and credential.strip(), 'CREDENTIAL_REQUIRED')
    with exclusive_execution(directory):
        plan = _plan(directory)
        manifest = _next_manifest(directory, plan, run_id)
        state = _load_run_state(directory, plan, manifest)
        if state.get('complete'):
            return {'status': 'complete', 'run_id': manifest['run_id'], 'completed_calls': CALLS_PER_RUN}
        _validate_history(directory, plan, manifest, state)
        index = state['next_index']
        ensure(index <= CALLS_PER_RUN, 'RUN_COMPLETE')
        turn, actor_index = _current_actor(index)
        world_state = _state_from_payload(state['world_law_state'])
        world_observation = summarize_world_state(world_state)
        snapshot = build_turn_snapshot(
            source_world=plan['source_world'], condition=manifest['condition'], run_id=manifest['run_id'],
            seed_label=manifest['seed_label'], turn=turn, actor_index=actor_index,
            message_history=state['message_history'], world_state=world_observation,
        )
        body = _body(snapshot, condition=manifest['condition'], seed_value=manifest['seed_value_fixed_before_execution'])
        maximum = price(MAX_INPUT, MAX_OUTPUT)
        reserved = sum((Decimal(read_record(p)['usd']) for p in _run_dir(directory, manifest['run_id']).glob('reservation-*.json')), Decimal(0))
        ensure(reserved + maximum <= STOP_LIMIT_PER_RUN, 'BUDGET_EXHAUSTED')
        evidence_manifest = {
            'format': FORMAT,
            'run_id': f"{manifest['run_id']}-{index:03d}",
            'started_at': timestamp(),
            'seed': manifest['seed_value_fixed_before_execution'],
            'seed_scope': 'Fixed preregistered seed reused for the paired condition run.',
            'provider': 'google-gemini-api',
            'model': MODEL,
            'model_version_or_digest': None,
            'generation_config': body['generationConfig'],
            'experiment_config': {
                'method': VERSION,
                'manifest_run_id': manifest['run_id'],
                'condition': manifest['condition'],
                'index': index,
                'turn': turn,
                'nation_id': snapshot['actor_nation_id'],
                'leader_id': snapshot['actor_leader_id'],
                'manifest_sha256': manifest['manifest_sha256'],
                'plan_sha256': digest(plan),
                'request_sha256': digest(body),
            },
            'world_config': {
                'number_of_worlds': 1,
                'nation_count': 12,
                'simulation_turns_planned': 36,
                'world_law_settlement_executed': True,
            },
            'provenance': {
                'source_hashes': plan['source_hashes'],
                'source_commit': plan['source_commit'],
                'runtime': plan['runtime'],
                'parent_evidence_hash': manifest['manifest_sha256'],
                'purpose': 'Collect one preregistered paired-diplomacy leader turn decision and preserve evidence.',
            },
        }
        run = EvidenceRun(_attempt_root(directory, manifest['run_id'], index), evidence_manifest)
        stage, attempted, actual = 'save_request', False, None
        try:
            count_body = {'generateContentRequest': {'model': 'models/' + MODEL, **body}}
            run.write('snapshot.json', snapshot)
            run.write('run-manifest.json', manifest)
            for name, payload in [('generation', body), ('count', count_body)]:
                raw = wire_bytes(payload)
                run.write(name + '.request.json', payload)
                run.write(name + '.wire.json', {'body_base64': base64.b64encode(raw).decode(), 'body_sha256': hashlib.sha256(raw).hexdigest()})
            ensure(digest(_plan(directory)) == digest(plan), 'PLAN_CHANGED_BEFORE_API')
            with httpx.Client(transport=transport, trust_env=False, follow_redirects=False, timeout=httpx.Timeout(180, connect=30, write=30, pool=30)) as client:
                def send(method: str, payload: dict[str, Any]) -> dict[str, Any]:
                    response = client.post(ENDPOINT + ':' + method, content=wire_bytes(payload), headers={'x-goog-api-key': credential, 'content-type': 'application/json'})
                    raw = response.content
                    run.write(('count' if method == 'countTokens' else 'generation') + '.response.json', {'status': response.status_code, 'received_at': timestamp(), 'body_base64': base64.b64encode(raw).decode(), 'body_sha256': hashlib.sha256(raw).hexdigest()})
                    ensure(response.status_code == 200, 'COUNT_HTTP_ERROR' if method == 'countTokens' else 'GENERATION_HTTP_ERROR')
                    return load_response_object(raw.decode('utf-8'))
                stage = 'count_tokens'
                count = send('countTokens', count_body).get('totalTokens')
                ensure(type(count) is int and 0 < count <= MAX_INPUT, 'INPUT_COUNT_INVALID_OR_OVER_LIMIT')
                stage = 'reserve_generation'
                Journal(_run_dir(directory, manifest['run_id'])).write(f'reservation-{index:03d}.json', {'usd': str(maximum), 'index': index, 'request_sha256': digest(body), 'counted_input_tokens': count, 'reserved_at': timestamp()})
                stage = 'generate_content'; attempted = True
                response = send('generateContent', body)
            ensure(digest(_plan(directory)) == digest(plan), 'PLAN_CHANGED_AFTER_API')
            stage = 'account_usage'
            accounting = account_usage(response.get('usageMetadata'))
            actual = accounting['estimated_cost_usd']
            run.write('receipt.json', {'usage_metadata': response.get('usageMetadata'), 'accounting': accounting, 'billing_verified': False, 'model_version': response.get('modelVersion'), 'response_id': response.get('responseId'), 'reservation_usd': str(maximum)})
            ensure(accounting['input_tokens'] <= MAX_INPUT and accounting['generated_tokens_including_thoughts'] <= MAX_OUTPUT and Decimal(actual) <= maximum, 'USAGE_OVER_RESERVATION')
            stage = 'validate_output'
            output = _extract_persona(response)
            validation = validate_decision(
                output, condition=manifest['condition'], world_id=plan['source_world']['world_id'],
                run_id=manifest['run_id'], seed_label=manifest['seed_label'], turn=turn,
                leader_id=snapshot['actor_leader_id'], nation_id=snapshot['actor_nation_id'],
                nation_ids=plan['source_world']['nation_ids'], turn_start_snapshot=snapshot,
                communication_budget_chars=COMMUNICATION_BUDGET_CHARS,
            )
            terminal = run.finish('success', completed_turns=turn)
            run.derive('output.json', {'output': output, 'raw_response_path': 'RAW/generation.response.json'})
            run.derive('validation.json', validation)
            state['turn_decisions'].append(output)
            for msg in output['outgoing_messages']:
                state['message_history'].append(_history_message(plan['source_world'], output, msg))
            if actor_index == 11:
                turn_decisions = [d for d in state['turn_decisions'] if d['turn'] == turn]
                settlement = _settle_turn(world_state, turn_decisions, state['message_history'])
                state['settlement_by_turn'].append(settlement)
                state['world_law_state'] = settlement['world_state']
            else:
                state['world_law_state'] = _state_to_payload(world_state)
            state['next_index'] = index + 1
            if state['next_index'] > CALLS_PER_RUN:
                state['complete'] = True
                Journal(_run_dir(directory, manifest['run_id'])).write('run-summary.json', summarize_run_state(state))
            _save_run_state(directory, manifest['run_id'], state)
            return {**terminal, 'manifest_run_id': manifest['run_id'], 'index': index, 'turn': turn, 'nation_id': snapshot['actor_nation_id'], 'leader_id': snapshot['actor_leader_id'], 'estimated_cost_usd': actual, 'run_complete': state['complete']}
        except (Exception, KeyboardInterrupt) as exc:
            error = {'code': _error(exc), 'exception_type': type(exc).__name__, 'stage': stage, 'generation_attempted': attempted}
            if not (run.root / 'terminal.json').exists():
                run.write('error.json', error)
                run.finish('interrupted' if isinstance(exc, KeyboardInterrupt) else 'failure', completed_turns=0, error=error)
            _failure_record(directory, manifest['run_id'], index, error)
            return {'status': 'failure', 'manifest_run_id': manifest['run_id'], 'index': index, 'error': error, 'estimated_cost_usd': actual}


def summarize_run_state(state: dict[str, Any]) -> dict[str, Any]:
    decisions = state.get('turn_decisions', [])
    messages = sum(len(d.get('outgoing_messages', [])) for d in decisions)
    proposals = sum(len(d.get('proposals', [])) for d in decisions)
    contacted = sorted({target for d in decisions for item in d.get('outgoing_messages', []) + d.get('proposals', []) for target in item.get('to_nation_ids', [])})
    funnels = [f for s in state.get('settlement_by_turn', []) for f in s.get('proposal_funnels', [])]
    dispatches = [f for f in funnels if f.get('status') == 'dispatch_scheduled']
    final_world = state.get('world_law_state', {})
    return {
        'document_type': 'v5-paired-diplomacy-run-summary-1',
        'run_id': state['run_id'],
        'condition': state['condition'],
        'seed_label': state['seed_label'],
        'turns_completed': sorted(set(d['turn'] for d in decisions)),
        'decision_count': len(decisions),
        'message_count': messages,
        'proposal_count': proposals,
        'contacted_nation_ids': contacted,
        'settlement_turns': len(state.get('settlement_by_turn', [])),
        'dispatch_scheduled_count': len(dispatches),
        'arrival_count': len(final_world.get('arrivals', [])),
        'world_state_mutation_count': len(final_world.get('world_state_mutations', [])),
        'complete': state.get('complete', False),
        'summary_sha256': stable_hash({'run_id': state['run_id'], 'decisions': decisions, 'settlement': state.get('settlement_by_turn', [])}),
    }


def dry_run_validate(directory: Path, *, prepare_dir: Path = PREPARE_DIR) -> dict[str, Any]:
    manifests = _load_manifests(prepare_dir)
    _, source_world = load_base()
    by_seed = {}
    invariant_failures = []
    for manifest in manifests:
        for turn in range(TURN_MIN, TURN_MAX + 1):
            for actor_index in range(12):
                snapshot = build_turn_snapshot(
                    source_world=source_world,
                    condition=manifest['condition'],
                    run_id=manifest['run_id'],
                    seed_label=manifest['seed_label'],
                    turn=turn,
                    actor_index=actor_index,
                    message_history=[],
                    world_state=summarize_world_state(_initial_world_law_state(source_world['world_id'])),
                )
                _body(snapshot, condition=manifest['condition'], seed_value=manifest['seed_value_fixed_before_execution'])
                by_seed.setdefault(manifest['seed_label'], {})[manifest['condition']] = manifest['seed_value_fixed_before_execution']
    for seed_label, values in by_seed.items():
        if set(values) != set(CONDITIONS) or len(set(values.values())) != 1:
            invariant_failures.append(seed_label)
    return {
        'status': 'pass' if not invariant_failures else 'failure',
        'manifest_count': len(manifests),
        'turns_checked_per_run': TURN_MAX,
        'leader_calls_checked_per_run': CALLS_PER_RUN,
        'total_calls_checked': CALLS_PER_RUN * len(manifests),
        'paired_seed_invariant_failures': invariant_failures,
        'api_executed': False,
    }
