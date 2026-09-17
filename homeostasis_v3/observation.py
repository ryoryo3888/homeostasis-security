"""Read-only TURN-end measurement. No Agent, world mutation, policy or I/O.

Records are measurements, not research claims. Offline checkpoints cannot be
promoted to formal research by changing an artifact_class label.
"""
from collections import Counter, deque
from copy import deepcopy
from fractions import Fraction

from .choices import ensure, check
from .contracts import digest, ID, HASH, UINT, obj, enum
from .turn import validate_checkpoint, totals, Snapshot
from .metric_definitions import DEFINITIONS, DEFINITIONS_DIGEST

STATUSES = {'measured', 'unknown', 'not_applicable', 'not_measured'}
CATEGORIES = ('world_metrics','state_metrics','resource_metrics','network_metrics','transaction_metrics','propagation_metrics')
# formal_experiment is reserved in the data contract. This offline source
# adapter deliberately rejects it until a formal runner/provenance gate exists.
OBSERVATION_SCHEMA = obj({
    'observation_schema_version': enum(1), 'version': enum('v3'),
    'artifact_class': enum('test_fixture','validation_run','formal_experiment'),
    'experiment_id': {'anyOf':[ID,{'type':'null'}]}, 'provisional_reference': ID,
    'worldline_id': ID, 'turn': UINT, 'checkpoint_digest': HASH,
    'observation_input_digest': HASH, 'measured_at_phase': enum('TURN_CLOSE'),
    'metric_definitions_digest': HASH,
    **{key:{'type':'object'} for key in CATEGORIES},
    'provenance': {'type':'object'}, 'research_eligible': {'type':'boolean'},
    'publication_status': enum('withheld'), 'observation_digest': HASH})



def unknown(reason, status='unknown'):
    return {'status': status, 'value': None, 'reason': reason}


def ratio(numerator, denominator):
    return float(Fraction(numerator, denominator)) if denominator else unknown('zero denominator', 'not_applicable')


def hhi(weights):
    total = sum(weights.values())
    return float(sum((Fraction(x,total)**2 for x in weights.values()), Fraction(0))) if total else unknown('empty support', 'not_applicable')


def resolve(data, path):
    if path == '': return data
    ensure(type(path) is str and path.startswith('/'), 'INVALID_EVIDENCE_POINTER')
    try:
        for part in path[1:].split('/'):
            part = part.replace('~1','/').replace('~0','~')
            data = data[int(part)] if isinstance(data,list) else data[part]
        return data
    except (KeyError, IndexError, ValueError, TypeError):
        ensure(False, 'BROKEN_EVIDENCE_POINTER')


def metric_cells(record):
    def walk(value):
        if isinstance(value, dict):
            if 'metric_id' in value:
                yield value
            else:
                for v in value.values(): yield from walk(v)
        elif isinstance(value, list):
            for v in value: yield from walk(v)
    for category in CATEGORIES: yield from walk(record[category])


def _series(checkpoint, previous, reference):
    validate_checkpoint(checkpoint)
    ensure(checkpoint['turn'] > 0, 'TURN_END_REQUIRED')
    series = sorted([*previous, checkpoint], key=lambda c:c['turn'])
    ensure(len({c['turn'] for c in series}) == len(series), 'DUPLICATE_OBSERVATION_TURN')
    for c in series:
        validate_checkpoint(c)
        ensure(c['context_id'] == checkpoint['context_id'] and c['config_hash'] == checkpoint['config_hash'], 'MIXED_WORLDLINE')
        ensure(0 < c['turn'] <= checkpoint['turn'], 'INVALID_HISTORY_TURN')
        ensure(c['history'] == checkpoint['history'][:c['turn']], 'HISTORY_FORK')
    for a,b in zip(series,series[1:]):
        if b['turn'] == a['turn']+1:
            ensure(b['input']['opening'] == a['checkpoint_digest'], 'CHECKPOINT_CHAIN_MISMATCH')
    if reference is not None:
        validate_checkpoint(reference)
        ensure(reference['config_hash'] == checkpoint['config_hash'] and reference['turn'] <= checkpoint['turn'], 'INCOMPATIBLE_REFERENCE')
        if reference['turn']:
            ensure(reference['history'] == checkpoint['history'][:reference['turn']], 'REFERENCE_FORK')
        if reference['turn'] == 0 and series[0]['turn'] == 1:
            ensure(series[0]['input']['opening'] == reference['checkpoint_digest'], 'REFERENCE_CHAIN_MISMATCH')
    complete = [c['turn'] for c in series] == list(range(1,checkpoint['turn']+1))
    return series, complete


def _paths(world, limit):
    ensure(type(limit) is int and limit > 0, 'INVALID_PATH_LIMIT')
    n = world['network']; b = world['physical']['world']
    groups = {g['group_id']:g['capacity'] for g in n['shared_capacities']}
    transport = {c['owner']:c['available'] for c in b['capacities'] if c['category']=='transport'}
    costs = {c['resource_id']:c['transport_units_per_stock_unit'] for c in n['transport_costs']}
    output = []; count = 0
    for resource,cost in sorted(costs.items()):
        routes = sorted([r for r in n['routes'] if resource in r['resource_types'] and r['availability'] and
                         min(r['capacity'],groups[r['shared_capacity_group']],transport[r['source']]) >= cost], key=lambda r:r['route_id'])
        for source in sorted(transport):
            stack = [(source, {source}, [])]
            while stack:
                node, visited, path = stack.pop()
                for r in routes:
                    if r['source'] != node or r['destination'] in visited: continue
                    chain = path+[r['route_id']]; count += 1
                    ensure(count <= limit, 'OBSERVATION_PATH_BUDGET_EXCEEDED')
                    output.append({'source':source,'destination':r['destination'],'resource':resource,'routes':chain})
                    stack.append((r['destination'],visited|{r['destination']},chain))
    return sorted(output, key=lambda p:(p['source'],p['destination'],p['resource'],p['routes']))


def observe(checkpoint, *, worldline_id, provisional_reference, previous=(), reference=None,
            artifact_class='test_fixture', path_limit=10000):
    check(ID, worldline_id); check(ID, provisional_reference)
    ensure(artifact_class in ('test_fixture','validation_run'), 'OFFLINE_CHECKPOINT_NOT_FORMAL_RESEARCH')
    cp = deepcopy(checkpoint); previous = deepcopy(list(previous)); reference = deepcopy(reference)
    series, complete = _series(cp, previous, reference)
    sources = {c['checkpoint_digest']:c for c in series}
    if reference is not None: sources[reference['checkpoint_digest']] = reference
    def evidence(path, source=cp):
        value = resolve(source,path)
        return {'checkpoint_digest':source['checkpoint_digest'], 'pointer':path, 'value_digest':digest(value)}
    def m(mid, value, paths, *, status='measured', reason=None, extra=()):
        return {'metric_id':mid, 'definition_digest':digest(DEFINITIONS[mid]), 'status':status,
                'value':value, 'reason':reason, 'unit':DEFINITIONS[mid]['unit'],
                'evidence':[evidence(p) for p in paths]+list(extra)}
    w = cp['world_state']; b = w['physical']['world']; n = w['network']
    conservation = cp['audit']['CONSERVATION']
    ensure(conservation['closing'] == totals(w), 'CLOSING_TOTAL_EVIDENCE_MISMATCH')
    ensure(all(conservation['closing'][r] == conservation['opening'][r] - conservation['loss'][r] - conservation['consumed'][r] - conservation['production_inputs'][r] + conservation['production_outputs'][r] for r in conservation['closing']), 'CONSERVATION_EVIDENCE_MISMATCH')
    ensure(cp['audit']['TURN_CLOSE']['world_hash'] == cp['output_digest'], 'TURN_CLOSE_EVIDENCE_MISMATCH')
    sid_list = sorted(c['state_id'] for c in b['countries']); rid_list = sorted(r['resource_id'] for r in b['resources'])
    accounts = {(a['owner'],a['resource_id']):a['balance'] for a in b['accounts']}
    ledger = {(r['owner'],r['resource']):r for r in cp['ledger']}
    ensure(set(ledger) == {(s,r) for s in sid_list for r in rid_list} and len(ledger)==len(cp['ledger']), 'INCOMPLETE_OBSERVATION_LEDGER')
    for row in cp['ledger']:
        ensure(all(type(row[k]) is int and row[k]>=0 for k in ('required','consumed','shortage')) and row['required']==row['consumed']+row['shortage'], 'INVALID_SHORTAGE_LEDGER')
    paths = _paths(w,path_limit)
    routes = {r['route_id']:r for r in n['routes']}
    costs = {c['resource_id']:c['transport_units_per_stock_unit'] for c in n['transport_costs']}
    audit_path = f'/history/{cp["turn"]-1}/settlement'
    audit = cp['history'][-1]['settlement']
    ensure(cp['audit']['JOINT_SETTLEMENT'] == audit, 'SETTLEMENT_EVIDENCE_MISMATCH')
    ensure(cp['audit']['CONSUMPTION'] == cp['ledger'], 'LEDGER_EVIDENCE_MISMATCH')
    audit_choices = audit['choices']
    history_evidence = [evidence('/ledger', c) for c in series if c is not cp and c['checkpoint_digest'] != cp['checkpoint_digest']]
    def rows(s,r): return [(c['turn'], next(x for x in c['ledger'] if (x['owner'],x['resource'])==(s,r))) for c in series]
    def shortage(sids,r):
        demand = sum(ledger[s,r]['required'] for s in sids); served = sum(ledger[s,r]['consumed'] for s in sids)
        return {'demand':demand,'fulfilled':served,'shortage':demand-served,'fulfillment_rate':ratio(served,demand),
                'cumulative_shortage':sum(row['shortage'] for s in sids for _,row in rows(s,r)) if complete else unknown('incomplete checkpoint history')}
    state_metrics = {}; resource_metrics = {}; world_metrics = {}
    for s in sid_list:
        selected = [c for c in audit_choices if c['intent']['actor_state_id']==s]
        autonomy = {'submitted_choices':len(selected), 'conditional_choices':sum(bool(c['intent']['conditions']) for c in selected),
                    'individually_feasible_submitted':sum(c['individual']['feasible_amount']>0 for c in selected),
                    'catalogue_options':sum(t['actor_state_id']==s for t in cp['input']['catalogue']),
                    'explicit_refusals':sum(v is False for v in cp['input']['consents'].get(s,{}).values()),
                    'consent_required_by_applied_policy':audit['policy']['consent_required'],
                    'coordinator_proposal_present':cp['input']['proposal'] is not None,
                    'self_submission_boundary':'actor-bound signed choice; coordinator cannot submit on behalf of country',
                    'conditional_participation_supported':True,'refusal_supported':True,
                    'feasible_unselected_options':unknown('unselected alternatives not evaluated'),
                    'coercion_outside_contract':unknown('not measured from software trace')}
        entry = {'autonomy':m('autonomy',autonomy,[audit_path+'/choices','/input/catalogue','/input/consents','/input/proposal']), 'resources':{}}
        for r in rid_list:
            series_rows = rows(s,r); positive = [(t,x['shortage']) for t,x in series_rows if x['shortage']>0]
            values = [x['shortage'] for _,x in series_rows]
            onset = positive[0][0] if positive and complete else unknown('no shortage observed' if not positive and complete else 'incomplete history', 'not_applicable' if not positive and complete else 'unknown')
            decreases = [t for (pt,prev),(t,now) in zip(series_rows,series_rows[1:]) if t==pt+1 and prev['shortage']>now['shortage']]
            zero = next((t for t,row in series_rows if isinstance(onset,int) and t>onset and row['shortage']==0), None)
            resilience = {'history_complete':complete,'first_shortage_turn':onset,
                          'maximum_shortage':max(values) if complete else unknown('incomplete history'),
                          'cumulative_shortage':sum(values) if complete else unknown('incomplete history'),
                          'first_shortage_decrease_turn':decreases[0] if decreases and complete else unknown('not observed or incomplete history'),
                          'first_zero_after_shortage':zero if zero is not None else unknown('not observed'),
                          'turns_to_zero':zero-onset if zero is not None else unknown('not observed'),
                          'recovery_mechanism':unknown('recovery law undefined')}
            incoming_paths = [p for p in paths if p['destination']==s and p['resource']==r]
            suppliers = sorted({p['source'] for p in incoming_paths})
            actual = [x for x in w['shipments'] if x['target']==s and x['resource']==r and x['arrival_turn']==cp['turn']]
            capacity = sum(c['available'] for c in b['capacities'] if c['owner']==s and c['category']=='production' and
                           next(p['resource_id'] for p in w['physical']['capacity_profiles'] if p['capacity_id']==c['capacity_id'])==r)
            demand = ledger[s,r]['required']; stock = accounts[s,r]
            self_reliance = {'domestic_stock':stock,'essential_demand':demand,'domestic_production_capacity':capacity,
                            'reserve_buffer':max(0,stock-demand),'reserve_only_full_turns':stock//demand if demand else unknown('zero demand','not_applicable'),
                            'external_received_this_turn':sum(x['arrived_amount'] for x in actual),
                            'observed_supplier_count':len({x['source'] for x in actual}),
                            'potential_supplier_ids':suppliers,'potential_supplier_count':len(suppliers),
                            'additional_supplier_options':max(0,len(suppliers)-1),
                            'potential_paths':len(incoming_paths),
                            'additional_paths_per_supplier':{p:max(0,sum(x['source']==p for x in incoming_paths)-1) for p in suppliers},
                            'supply_required_to_avoid_shortage':unknown('counterfactual external dependency not evaluated')}
            ref_value = None
            ref_ev = []
            if reference is not None:
                ref_stock = next(a['balance'] for a in reference['world_state']['physical']['world']['accounts'] if (a['owner'],a['resource_id'])==(s,r))
                ref_value=stock-ref_stock;ref_ev=[evidence('/world_state/physical/world/accounts',reference)]
            entry['resources'][r] = {
                'shortage':m('shortage',shortage([s],r),['/ledger'],extra=history_evidence),
                'self_reliance':m('self_reliance',self_reliance,['/world_state','/ledger']),
                'resilience':m('resilience',resilience,['/ledger'],extra=history_evidence),
                'reference_deviation':m('reference_deviation',ref_value,['/world_state/physical/world/accounts'],status='measured' if reference else 'unknown',reason=None if reference else 'explicit reference not supplied',extra=ref_ev)}
        state_metrics[s] = entry
    for r in rid_list:
        stock_distribution = {s:accounts[s,r] for s in sid_list}
        resource_metrics[r] = {
            'total':m('resource_total',{'total':totals(w)[r], 'domestic':sum(stock_distribution.values()), 'pool':w['pool'][r],
                'in_transit':sum(s['dispatched_amount'] for s in w['shipments'] if s['resource']==r and s['arrival_turn'] is None),
                'production_pending':sum(p['quantity'] for p in w['production_pending'] if p['resource']==r)},['/world_state']),
            'distribution':m('resource_distribution',{'stock':stock_distribution,'demand':{s:ledger[s,r]['required'] for s in sid_list},
                'shortage':{s:ledger[s,r]['shortage'] for s in sid_list}},['/world_state/physical/world/accounts','/ledger'])}
    world_metrics['homeostasis_components'] = {'essential_fulfillment':{r:m('shortage',shortage(sid_list,r),['/ledger'],extra=history_evidence) for r in rid_list},
        'reference_deviation':'see state_metrics.*.resources.*.reference_deviation',
        'recovery_process':'see state_metrics.*.resources.*.resilience'}
    profiles = {p['capacity_id']:p for p in w['physical']['capacity_profiles']}
    world_metrics['capacity_damage'] = m('capacity_damage',[{'capacity_id':c['capacity_id'],'owner':c['owner'],'unit':c['unit_id'],
        'available':c['available'],'maximum_operating':profiles[c['capacity_id']]['maximum_capacity']*profiles[c['capacity_id']]['utilization_ppm']//1000000,
        'deficit':profiles[c['capacity_id']]['maximum_capacity']*profiles[c['capacity_id']]['utilization_ppm']//1000000-c['available']} for c in b['capacities']],['/world_state/physical'])
    for mid in ('conflict_load','overreaction','underreaction'):
        world_metrics[mid] = m(mid,None,[],status='unknown' if mid=='conflict_load' else 'not_measured',reason=DEFINITIONS[mid]['known_limits'])
    network_metrics = {'reachability':m('network_reachability',paths,['/world_state/network','/world_state/physical/world/capacities']), 'routes':{},'shared_groups':{},'concentration':{}}
    def load_record(route_ids, capacity, load):
        dispatches = [s for s in w['shipments'] if s['route'] in route_ids and s['dispatch_turn']==cp['turn']]
        outstanding = [s for s in w['shipments'] if s['route'] in route_ids and s['arrival_turn'] is None]
        calculated = sum(s['dispatched_amount']*costs[s['resource']] for s in dispatches)
        ensure(calculated==load and load<=capacity, 'NETWORK_LOAD_EVIDENCE_MISMATCH')
        return {'used':load,'capacity':capacity,'utilization':ratio(load,capacity),
                'by_resource':{r:{'dispatch_load':sum(s['dispatched_amount']*costs[r] for s in dispatches if s['resource']==r),
                                  'shared_capacity_denominator':capacity,
                                  'in_transit':sum(s['dispatched_amount'] for s in outstanding if s['resource']==r)} for r in rid_list},
                'waiting':unknown('no queue model')}
    for rid,r in sorted(routes.items()):
        value=load_record({rid},r['capacity'],audit['joint_reservations']['route_load'].get(rid,0))
        value['available']=r['availability']
        network_metrics['routes'][rid]=m('route_load',value,['/world_state/network/routes','/world_state/shipments',audit_path+'/joint_reservations'])
    for g in n['shared_capacities']:
        value=load_record({rid for rid,r in routes.items() if r['shared_capacity_group']==g['group_id']},g['capacity'],audit['joint_reservations']['shared_load'].get(g['group_id'],0))
        network_metrics['shared_groups'][g['group_id']]=m('shared_load',value,['/world_state/network','/world_state/shipments',audit_path+'/joint_reservations'])
    for s in sid_list:
        network_metrics['concentration'][s]={}
        for resource in rid_list:
            inbound=[r for r in routes.values() if r['destination']==s and resource in r['resource_types'] and any(p['routes']==[r['route_id']] for p in paths if p['resource']==resource)]
            observed=[x for x in w['shipments'] if x['target']==s and x['resource']==resource and x['arrival_turn']==cp['turn']]
            structural={name:Counter(r[key] for r in inbound) for name,key in [('supplier','source'),('route','route_id'),('shared_group','shared_capacity_group')]}
            realized={name:Counter() for name in structural}
            for x in observed:
                realized['supplier'][x['source']]+=x['arrived_amount']
                realized['route'][x['route'] or 'local_pool']+=x['arrived_amount']
                realized['shared_group'][routes[x['route']]['shared_capacity_group'] if x['route'] else 'local_pool']+=x['arrived_amount']
            value={basis:{k:{'weights':dict(sorted(v.items())),'hhi':hhi(v)} for k,v in weights.items()} for basis,weights in [('structural_route_counts',structural),('observed_receipt_amounts',realized)]}
            network_metrics['concentration'][s][resource]=m('dependency_concentration',value,['/world_state/network','/world_state/shipments'])
    transactions=[]; summary=Counter(); reasons=Counter()
    for i,a in enumerate(audit_choices):
        requested=a['intent']['requested_amount']; settled=a['settled_amount']
        status='not_established' if settled==0 else ('full' if settled==requested else 'partial')
        summary[status]+=1;reasons.update(a['reason_codes'])
        arrived=sum(s['arrived_amount'] for s in w['shipments'] if s['choice_id']==a['choice_id'])
        transactions.append(m('transaction',{'choice_id':a['choice_id'],'actor':a['intent']['actor_state_id'], 'resource':a['intent']['resource'],
            'requested':requested,'individually_feasible':a['individual']['feasible_amount'],'settled':settled,
            'dispatched':a['dispatched_amount'],'arrived_as_of_turn_end':arrived,'fulfillment':status,'reason_codes':a['reason_codes']},[audit_path+f'/choices/{i}','/world_state/shipments']))
    transaction_metrics={'choices':transactions,'summary':m('transaction_summary',{'counts':{s:summary[s] for s in ('full','partial','not_established')},'reason_codes':dict(sorted(reasons.items()))},[audit_path+'/choices']),
                         'receipts_this_turn':m('transaction',{'receipts':[s for s in w['shipments'] if s['arrival_turn']==cp['turn']]},['/world_state/shipments'])}
    propagation=_propagation(cp,series)
    record={'observation_schema_version':1,'version':'v3','artifact_class':artifact_class,'experiment_id':None,
            'provisional_reference':provisional_reference,'worldline_id':worldline_id,'turn':cp['turn'],
            'checkpoint_digest':cp['checkpoint_digest'],'observation_input_digest':cp['output_digest'],'measured_at_phase':'TURN_CLOSE',
            'metric_definitions_digest':DEFINITIONS_DIGEST,'world_metrics':world_metrics,'state_metrics':state_metrics,
            'resource_metrics':resource_metrics,'network_metrics':network_metrics,'transaction_metrics':transaction_metrics,
            'propagation_metrics':m('propagation',propagation,['/history','/world_state/network','/ledger'],extra=history_evidence),
            'provenance':{'source_kind':cp['kind'],'context_id':cp['context_id'],'configuration_hash':cp['config_hash'],
                'source_checkpoints':sorted(sources),'history_checkpoints':[c['checkpoint_digest'] for c in series],
                'history_complete':complete,'path_limit':path_limit,
                'reference_checkpoint':None if reference is None else reference['checkpoint_digest']},
            'research_eligible':False,'publication_status':'withheld'}
    record['observation_digest']=digest(record)
    validate_observation(record,sources)
    return record


def _propagation(cp,series):
    w=cp['world_state']; b=w['physical']['world']; n=w['network']; edges=[]
    for r in n['routes']:
        for resource in r['resource_types']:
            edges.append(((r['source'],resource),(r['destination'],resource),r['route_id'],'transport',r['availability']))
    for d in n['production_dependencies']:
        edges.append(((d['producer_state'],d['input_resource']),(d['producer_state'],d['output_resource']),d['dependency_id'],'production_input',True))
    edges.sort(key=lambda e:(e[2],e[0],e[1])); output=[]
    accounts={a['account_id']:(a['owner'],a['resource_id']) for a in b['accounts']}
    profiles={p['capacity_id']:p for p in w['physical']['capacity_profiles']}
    for hi,h in enumerate(cp['history']):
        for ei,event in enumerate(h['events']):
            origins=[]
            if event['kind']=='resource_loss': origins=[accounts[event['target']]]
            elif event['kind']=='demand_change': origins=[(event['target'],event['resource'])]
            elif event['kind']=='route_stop':
                route=next(r for r in n['routes'] if r['route_id']==event['target'])
                origins=[(route['source'],r) for r in route['resource_types']]
            else:
                cap=next(c for c in b['capacities'] if c['capacity_id']==event['target']); resource=profiles[cap['capacity_id']]['resource_id']
                if cap['category']=='recovery':
                    output.append({'origin':{'event_id':event['event_id'],'turn':h['turn'],'node':[cap['owner'],None],
                        'evidence_pointer':f'/history/{hi}/events/{ei}'},'affected_state':cap['owner'],'resource':None,
                        'first_affected_turn':unknown('recovery effect undefined'),'dependency_path':[],
                        'effect_type':'capacity_loss_without_defined_resource_effect','evidence_strength':'unknown','causal_claim':False})
                    continue
                origins=[(cap['owner'],resource)] if resource else [(cap['owner'],r['resource_id']) for r in b['resources']]
            for origin in sorted(origins):
                queue=deque([(origin,[])]); visited={origin}
                while queue:
                    node,path=queue.popleft(); changed=[]
                    for prev,now in zip(series,series[1:]):
                        if now['turn']!=prev['turn']+1 or now['turn']<h['turn']:continue
                        a=next(x for x in prev['ledger'] if (x['owner'],x['resource'])==node)
                        z=next(x for x in now['ledger'] if (x['owner'],x['resource'])==node)
                        if z['shortage']>a['shortage']:changed.append(now['turn'])
                    output.append({'origin':{'event_id':event['event_id'],'turn':h['turn'],'node':list(origin),
                        'evidence_pointer':f'/history/{hi}/events/{ei}'}, 'affected_state':node[0],'resource':node[1],
                        'first_affected_turn':changed[0] if changed else unknown('no observed adjacent shortage increase'),
                        'dependency_path':path,'effect_type':'shortage_increase' if changed else 'structural_exposure',
                        'evidence_strength':'change_along_dependency_path' if changed else 'structurally_possible',
                        'causal_claim':False})
                    for a,z,eid,kind,available in edges:
                        if a==node and z not in visited:
                            visited.add(z);queue.append((z,path+[{'edge_id':eid,'kind':kind,'available_at_measurement':available}]))
    return output


def validate_observation(record, sources):
    check(OBSERVATION_SCHEMA,record)
    raw=deepcopy(record); checksum=raw.pop('observation_digest',None)
    ensure(digest(raw)==checksum,'OBSERVATION_DIGEST_MISMATCH')
    ensure(record['observation_schema_version']==1 and record['metric_definitions_digest']==DEFINITIONS_DIGEST,'METRIC_DEFINITION_MISMATCH')
    ensure(record['measured_at_phase']=='TURN_CLOSE','MEASUREMENT_PHASE_MISMATCH')
    ensure(record['artifact_class'] in ('test_fixture','validation_run') and record['experiment_id'] is None and
           record['research_eligible'] is False and record['publication_status']=='withheld','FIXTURE_PROMOTION_FORBIDDEN')
    ensure(set(record['provenance']['source_checkpoints'])==set(sources),'SOURCE_SET_MISMATCH')
    for h,c in sources.items():
        validate_checkpoint(c)
        ensure(c['checkpoint_digest']==h,'SOURCE_DIGEST_MISMATCH')
    cp=sources[record['checkpoint_digest']];validate_checkpoint(cp)
    ensure(cp['output_digest']==record['observation_input_digest'] and cp['turn']==record['turn'] and cp['context_id']==record['provenance']['context_id'],'OBSERVATION_INPUT_MISMATCH')
    for cell in metric_cells(record):
        ensure(cell['metric_id'] in DEFINITIONS and cell['definition_digest']==digest(DEFINITIONS[cell['metric_id']]),'UNKNOWN_METRIC_DEFINITION')
        ensure(cell['status'] in STATUSES and cell['unit']==DEFINITIONS[cell['metric_id']]['unit'],'INVALID_METRIC_STATUS_OR_UNIT')
        ensure((cell['status']=='measured' and cell['value'] is not None and bool(cell['evidence'])) or
               (cell['status']!='measured' and cell['value'] is None and bool(cell['reason'])),'UNKNOWN_IS_NOT_ZERO')
        for ref in cell['evidence']:
            ensure(ref['checkpoint_digest'] in sources,'MISSING_EVIDENCE_CHECKPOINT')
            ensure(digest(resolve(sources[ref['checkpoint_digest']],ref['pointer']))==ref['value_digest'],'EVIDENCE_DIGEST_MISMATCH')
    return record


def comparison_contract(a,b):
    keys=('version','observation_schema_version','metric_definitions_digest','measured_at_phase','artifact_class')
    ensure(all(a[k]==b[k] for k in keys),'INCOMPARABLE_OBSERVATIONS')
    return {'measurement_compatible':True,'same_configuration':a['provenance']['configuration_hash']==b['provenance']['configuration_hash'],
            'causal_comparison_established':False,'requires_review':['initial conditions','policy','events','history coverage','reference state']}


def interpretation(record, *, text, evidence_paths, kind='interpretation'):
    """Evaluator commentary is a separate artifact, never a metric mutation."""
    ensure(kind in ('interpretation','commentary','value_judgment'),'INVALID_INTERPRETATION_KIND')
    ensure(type(text) is str and bool(text.strip()) and bool(evidence_paths),'INTERPRETATION_EVIDENCE_REQUIRED')
    for path in evidence_paths:resolve(record,path)
    return {'kind':kind,'observation_digest':record['observation_digest'],'text':text,
            'evidence_paths':list(evidence_paths),'changes_measurements':False,'classifies_worldline':False}


def evaluator_view(record):
    return Snapshot.of(record)


def verify_observation(record, sources):
    """Recompute every metric; a rehashed edited value is not trusted evidence."""
    validate_observation(record,sources)
    current=sources[record['checkpoint_digest']]
    reference_id=record['provenance']['reference_checkpoint']
    previous=[sources[h] for h in record['provenance']['history_checkpoints'] if h!=record['checkpoint_digest']]
    # A reference can also be one of the historical observations.
    expected=observe(current,worldline_id=record['worldline_id'],provisional_reference=record['provisional_reference'],
        previous=previous, reference=sources[reference_id] if reference_id else None,
        artifact_class=record['artifact_class'],path_limit=record['provenance']['path_limit'])
    ensure(record==expected,'OBSERVATION_RECOMPUTATION_MISMATCH')
    return record
