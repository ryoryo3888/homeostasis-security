/** Pure, read-only projection of published evidence. No simulator imports. */
export const METRICS = Object.freeze({
  global_homeostasis: {label: 'Homeostasis', color: '#dfc69c'},
  international_trust: {label: 'Trust', color: '#8bbfba'},
  conflict_load: {label: 'Conflict', color: '#e19a83'},
  economy: {label: 'Economy', color: '#bcc5e3'},
  food: {label: 'Food', color: '#b2c88c'},
  energy: {label: 'Energy', color: '#cab5d6'},
  environment: {label: 'Environment', color: '#a5c0cf'},
});
export const RESOURCE_LABELS = Object.freeze({food:'食料', logistics:'物流', funds_economy:'資金', fossil_fuel:'化石燃料', renewable_energy:'再生可能エネルギー', nuclear:'原子力', grid_storage_resilience:'電力網・蓄電'});
const EPSILON = 1e-8;
const number = value => typeof value === 'number' && Number.isFinite(value);
const need = (condition, message) => { if (!condition) throw new Error(message); };
const total = (items, key) => items.reduce((sum, item) => sum + item[key], 0);
export const format = value => value == null ? '—' : new Intl.NumberFormat('ja-JP', {maximumFractionDigits: 3}).format(value);

export function projectWorldline(data, source) {
  need(data.timeline_version === 1 && Array.isArray(data.turns) && data.turns.length > 0, 'Unsupported timeline');
  need(data.run?.run_id === data.run_id && data.run.turns_completed === data.turns.length, 'Run identity mismatch');
  need(data.validation?.research_eligible === true && data.run.status === 'success', 'Not an admitted research worldline');
  const ids = Object.keys(data.initial_country_states).sort();
  const resources = Object.keys(data.initial_country_states[ids[0]].resources);
  const turns = data.turns.map((row, index) => {
    need(row.turn === index + 1 && row.decisions.length === ids.length, 'Incomplete turn');
    const state = row.executed_state;
    for (const key of Object.keys(METRICS)) need(number(state.true_world[key]) && state.true_world[key] >= 0 && state.true_world[key] <= 100, 'Invalid world metric');
    for (const resource of resources) need(number(state.world_pool[resource]) && state.world_pool[resource] >= 0 && state.world_pool[resource] <= 100 + EPSILON, 'Invalid pool');
    for (const key of ['before','after','recovered','domestic_recovery','external_support']) need(number(state.reconstruction[key]) && state.reconstruction[key] >= 0, 'Invalid reconstruction');
    const pointer = `/turns/${index}`;
    const evidence = (path, callId = null) => ({runId: data.run_id, turn: row.turn, pointer: pointer + path, callId, source});
    const flows = state.atomic_settlements.map((flow, i) => {
      for (const key of ['requested','realized','unmet']) need(number(flow[key]) && flow[key] >= -EPSILON, 'Invalid flow');
      need(flow.realized <= flow.requested + EPSILON && Math.abs(flow.requested - flow.realized - flow.unmet) < EPSILON, 'Flow does not reconcile');
      need(ids.includes(flow.agent_id) && resources.includes(flow.resource), 'Unknown flow identity');
      return {...flow, target: flow.target_country ?? 'world_pool', evidence: evidence(`/executed_state/atomic_settlements/${i}`)};
    });
    const seen = new Set();
    const agents = row.decisions.map((decision, i) => {
      need(decision.run_id === data.run_id && decision.turn === row.turn && ids.includes(decision.agent_id) && !seen.has(decision.agent_id), 'Invalid decision identity');
      seen.add(decision.agent_id);
      need(decision.validation_status === 'PASS', 'Unvalidated decision');
      const response = decision.model_response;
      const action = decision.materialized_action;
      need(response.choice_id === decision.choice_response.choice_id && response.amount === action.parameters.amount && response.reason === decision.choice_response.reason, 'Choice trace mismatch');
      const choice = decision.public_observation_payload.action_choices.find(c => c.choice_id === response.choice_id);
      need(choice && choice.action_id === action.action_id && number(response.amount) && response.amount >= 0 && response.amount <= choice.maximum_amount + EPSILON, 'Invalid catalog choice');
      for (const key of ['recipient_type','target_country','resource']) need(choice[key] === action.parameters[key], 'Catalog tuple mismatch');
      return {id: decision.agent_id, archetype: data.initial_country_states[decision.agent_id].archetype,
        response, action, participates: state.participants.includes(decision.agent_id),
        checks: row.derived.condition_checks[decision.agent_id], flows: flows.filter(flow => flow.agent_id === decision.agent_id),
        evidence: evidence(`/decisions/${i}`, decision.call_id)};
    }).sort((a,b) => a.id.localeCompare(b.id));
    const edges = row.derived.condition_edges.map((edge, i) => {
      need(ids.includes(edge.dependent) && ids.includes(edge.required), 'Unknown dependency');
      return {...edge, evidence: evidence(`/derived/condition_edges/${i}`)};
    });
    return {number: row.turn, event: row.snapshot.event, world: {...state.true_world}, sovereignty: state.research_metrics.national_sovereignty,
      agents, flows, edges, resources, pool: {...state.world_pool}, openingPool: {...row.snapshot.world_pool},
      reconstruction: {...state.reconstruction}, proposal: row.proposal, evaluator: row.evaluator_commentary,
      derivation: row.event_derivation, resourceDelta: row.derived.resource_delta,
      evidence: evidence(''), evaluatorInputHash: row.evaluator_input_sha256};
  });
  return {runId: data.run_id, turns, ids, resources, source, sourceHashes: {...data.source_hashes},
    sourceCommit: data.runtime.source_commit, calls: data.run.api_calls, retry: data.run.retry_count,
    initialDamage: turns[0].reconstruction.before};
}

export function summarizeFlows(turn, resource) {
  const flows = turn.flows.filter(flow => flow.resource === resource);
  return {flows, requested: total(flows, 'requested'), realized: total(flows, 'realized'), unmet: total(flows, 'unmet')};
}

/** Discover moments from observed predicates, never turn-number special cases. */
export function discoverMoments(model) {
  let convergence = null;
  for (const turn of model.turns) {
    const groups = new Map();
    for (const flow of turn.flows.filter(flow => flow.action_id === 'DRAW_WORLD_POOL')) {
      const key = `${flow.target}/${flow.resource}`;
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(flow);
    }
    for (const flows of groups.values()) {
      const agents = new Set(flows.map(flow => flow.agent_id)).size;
      if (agents > 1 && (!convergence || total(flows,'requested') > convergence.requested))
        convergence = {kind:'convergence', turn:turn.number, title:'同じ支援先へ', agents, resource:flows[0].resource, target:flows[0].target,
          requested:total(flows,'requested'), realized:total(flows,'realized'), unmet:total(flows,'unmet'), agent:flows[0].agent_id};
    }
  }
  const boundaryTurn = model.turns.find(turn => turn.agents.some(a => a.response.response_id === 'CONDITIONAL' && !a.participates));
  const boundaryAgent = boundaryTurn?.agents.find(a => a.response.response_id === 'CONDITIONAL' && !a.participates);
  const donors = new Set();
  const transitions = [];
  for (const turn of model.turns) {
    for (const flow of turn.flows) {
      if (flow.action_id === 'DRAW_WORLD_POOL' && flow.target === flow.agent_id && donors.has(`${flow.agent_id}/${flow.resource}`))
        transitions.push({kind:'self', turn:turn.number, agent:flow.agent_id, resource:flow.resource, title:'供与から引出しへ'});
    }
    for (const flow of turn.flows) if (flow.source !== 'world_pool' && flow.realized > 0)
      donors.add(`${flow.agent_id}/${flow.resource}`);
  }
  return [convergence, boundaryAgent && {kind:'boundary', title:'条件の境界', turn:boundaryTurn.number, agent:boundaryAgent.id}, transitions.at(-1)].filter(Boolean);
}

export function resolvePointer(data, pointer) {
  return pointer.split('/').slice(1).reduce((node,key) => node[key.replaceAll('~1','/').replaceAll('~0','~')], data);
}
