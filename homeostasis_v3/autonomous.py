"""Country-authored terms compiled into the existing reviewed transfer law.

Opportunities describe topology, not recommended actions or promised outcomes.
All countries plan from one frozen observation without seeing earlier plans.
New-law requests are recorded, never interpreted as executable world patches.
"""
from copy import deepcopy
import json

from .agent_adapter import _object, RESPONSE
from .choices import check, ensure, CONDITION, materialize_choice, TEMPLATE
from .contracts import ID, HASH, POS, TEXT, obj, arr, digest, canonical
from .turn import CountryInput

INITIATIVE = obj({'opportunity_id': ID, 'requested_amount': POS,
                  'minimum_amount': POS, 'allow_partial': {'type':'boolean'},
                  'conditions': arr(CONDITION), 'public_reason': TEXT})
INITIATIVE_RESPONSE = obj({'request_digest': HASH, 'state_id': ID,
                           'initiatives': arr(INITIATIVE), 'extension_requests': arr(TEXT)})


def opportunities(observation, maximum_amount):
    """All defined one-hop resource routes, including unavailable ones.

    Quantities are protocol bounds, not a feasibility filter. Scarce resources,
    stopped routes and competition remain visible and may fail in settlement.
    Multi-hop delivery requires later independent choices by intermediate states.
    """
    ensure(type(maximum_amount) is int and maximum_amount > 0, 'INVALID_AMOUNT_BOUND')
    view=observation.read(); snapshot=view['settlement_snapshot']
    result=[]
    for route in sorted(view['world_state']['network']['routes'], key=lambda r:r['route_id']):
        for resource in sorted(route['resource_types']):
            key={'turn':view['turn'],'route':route['route_id'],'resource':resource,
                 'actor':route['source'],'snapshot_hash':digest(snapshot)}
            result.append({'choice_id':'offer-'+digest(key)[:32],
                           'actor_state_id':route['source'], 'turn':view['turn'],
                           'snapshot_hash':digest(snapshot), 'action_type':'transfer',
                           'resource':resource, 'maximum_amount':maximum_amount,
                           'target':route['destination'], 'route_preference':route['route_id'],
                           'conditions':[], 'allow_partial':True, 'minimum_amount':1})
    ensure(len({c['choice_id'] for c in result})==len(result), 'OPPORTUNITY_ID_COLLISION')
    for template in result: check(TEMPLATE,template)
    return result


class AutonomousRound:
    """One TURN's host; it becomes unusable after an incomplete planning round.

    max_initiatives and maximum_amount are explicit protocol limits, not a
    permanent action menu. No coordinator or pool authority is fabricated.
    """
    def __init__(self, state_ids, *, exchange, budget, maximum_amount,
                 max_initiatives, source):
        ensure(type(max_initiatives) is int and max_initiatives > 0,'INVALID_INITIATIVE_LIMIT')
        ensure(type(maximum_amount) is int and maximum_amount > 0,'INVALID_AMOUNT_BOUND')
        self.state_ids=tuple(sorted(state_ids))
        ensure(len(set(self.state_ids))==len(self.state_ids),'DUPLICATE_STATE')
        for sid in self.state_ids: check(ID,sid)
        check(TEXT,source)
        self.exchange,self.budget,self.source=exchange,budget,source
        self.maximum_amount,self.max_initiatives=maximum_amount,max_initiatives
        self.observation_hash=None; self.complete=False; self.failed=False
        self._catalogue=[]; self._selections={}; self._extensions={}; self._consented=set()
        self._exchange,self._budget=exchange,budget
        self._configuration_hash=digest(self._configuration())

    def _configuration(self):
        return {'state_ids':list(self.state_ids), 'maximum_amount':self.maximum_amount,
                'max_initiatives':self.max_initiatives, 'source':self.source,
                'budget_limit':getattr(self.budget,'limit',None),
                'schemas':digest([INITIATIVE_RESPONSE,RESPONSE])}

    def _check_configuration(self):
        ensure(not self.failed,'PLANNING_ROUND_FAILED')
        try:
            ensure(self.exchange is self._exchange and self.budget is self._budget and
                   digest(self._configuration())==self._configuration_hash,
                   'PLANNING_CONFIGURATION_CHANGED')
        except Exception:
            self.failed=True
            raise

    def _ask(self, phase, sid, observation, payload, schema):
        self._check_configuration()
        request={'version':'v3','phase':phase,'state_id':sid,
                 'observation_digest':observation.hash,'observation':observation.read(),
                 'payload':payload}
        key=self.budget.reserve(request)
        self._check_configuration()
        raw=self.exchange(canonical({**request,'request_digest':key}))
        self._check_configuration()
        ensure(type(raw) is str and len(raw.encode('utf-8'))<=65536,'INVALID_RESPONSE_SIZE')
        try: answer=json.loads(raw,object_pairs_hook=_object)
        except (ValueError,TypeError):
            ensure(False,'INVALID_JSON_RESPONSE')
        check(schema,answer)
        ensure(answer['state_id']==sid,'RESPONSE_ACTOR_MISMATCH')
        ensure(answer['request_digest']==key,'RESPONSE_SNAPSHOT_MISMATCH')
        return answer

    def catalogue(self, observation):
        self._check_configuration()
        if self.complete:
            ensure(observation.hash==self.observation_hash,'ROUND_OBSERVATION_CHANGED')
            return deepcopy(self._catalogue)
        ensure(self.observation_hash is None,'PLANNING_REENTRY_FORBIDDEN')
        self.observation_hash=observation.hash
        try:
            actual=sorted(c['state_id'] for c in observation.read()['world_state']['physical']['world']['countries'])
            ensure(list(self.state_ids)==actual,'COMPLETE_STATE_SET_REQUIRED')
            available=opportunities(observation,self.maximum_amount)
            by_id={t['choice_id']:t for t in available}
            historical=set(observation.read()['world_state']['seen_choice_ids'])
            for sid in self.state_ids:
                answer=self._ask('initiative',sid,observation,
                    {'opportunities':available,'max_initiatives':self.max_initiatives,
                     'maximum_amount':self.maximum_amount,'proposal':None,
                     'extension_policy':'Record unimplemented law requests; never execute them.'},INITIATIVE_RESPONSE)
                ensure(len(answer['initiatives'])<=self.max_initiatives,'INITIATIVE_LIMIT_EXCEEDED')
                self._selections[sid]=[]; self._extensions[sid]=answer['extension_requests']
                ensure(len({i['opportunity_id'] for i in answer['initiatives']})==len(answer['initiatives']),
                       'DUPLICATE_INITIATIVE')
                for initiative in answer['initiatives']:
                    template=deepcopy(by_id.get(initiative['opportunity_id']))
                    ensure(template is not None,'UNKNOWN_OPPORTUNITY')
                    ensure(template['actor_state_id']==sid,'ACTOR_AUTHORITY_REQUIRED')
                    template.update(conditions=initiative['conditions'],
                                    minimum_amount=initiative['minimum_amount'],
                                    allow_partial=initiative['allow_partial'])
                    for condition in template['conditions']:
                        allowed=historical if condition['kind']=='arrived_amount' else by_id
                        ensure(condition['choice_id'] in allowed,'UNKNOWN_CONDITION_REFERENCE')
                    selection={'choice_id':template['choice_id'],
                               'requested_amount':initiative['requested_amount'],
                               'provenance':{'source':self.source,'public_reason':initiative['public_reason']}}
                    materialize_choice(selection,[template])
                    by_id[template['choice_id']]=template; self._selections[sid].append(selection)
            # Retain known but unselected opportunities as reference evidence.
            # They are never turned into selections, consent or state changes.
            self._catalogue=[by_id[cid] for cid in sorted(by_id)]
            self.complete=True
            return deepcopy(self._catalogue)
        except Exception:
            self.failed=True
            raise

    def _choose(self,sid,observation,proposal):
        self._check_configuration()
        ensure(self.complete and not self.failed and observation.hash==self.observation_hash,'ROUND_NOT_READY')
        ensure(proposal.read() is None,'COORDINATOR_PROTOCOL_NOT_CONFIGURED')
        return deepcopy(self._selections[sid])

    def _consent(self,sid,observation,choices):
        self._check_configuration()
        ensure(self.complete and not self.failed and observation.hash==self.observation_hash,'ROUND_NOT_READY')
        ensure(sid not in self._consented,'DUPLICATE_CONSENT_REQUEST')
        self._consented.add(sid)
        if not choices.read(): return {}
        try:
            answer=self._ask('consent',sid,observation,{'choices':choices.read()},RESPONSE)
            ensure(not answer['decisions'],'LATE_DECISION_FORBIDDEN')
            ensure(set(answer['consents']) <= {c['choice_id'] for c in choices.read()},'INVALID_CONSENT_REFERENCE')
            return answer['consents']
        except Exception:
            self.failed=True
            raise

    def countries(self):
        self._check_configuration()
        return {sid:CountryInput(lambda view,proposal,sid=sid:self._choose(sid,view,proposal),
                                 lambda view,choices,sid=sid:self._consent(sid,view,choices))
                for sid in self.state_ids}

    def record(self):
        self._check_configuration()
        ensure(self.complete and not self.failed,'ROUND_NOT_READY')
        return {'observation_digest':self.observation_hash,
                'source':self.source,'maximum_amount':self.maximum_amount,
                'max_initiatives':self.max_initiatives,
                'extension_requests':deepcopy(self._extensions),
                'extension_status':'unimplemented_not_executed',
                'decision_scope':{
                    'executable_action_types':['transfer'],
                    'route_scope':'existing_one_hop_routes',
                    'agent_authored_terms':['requested_amount','minimum_amount','allow_partial','conditions'],
                    'multi_hop_delivery':'requires_later_independent_intermediate_choices',
                    'extension_requests':'recorded_only_not_executable',
                    'coordinator_protocol':'not_configured',
                    'general_action_execution':False,
                },
                'catalogue_digest':digest(self._catalogue)}
