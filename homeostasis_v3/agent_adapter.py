"""JSON-only country boundary. No SDK, credentials, network or model is created.

The host supplies the exchange and catalogue. Tests use explicit synthetic
replies; supplying a live exchange requires a separate experiment protocol.
Only public reasons survive into core provenance, never raw provider objects.
"""
import json

from .choices import ensure, check, materialize_choice
from .contracts import ID, HASH, POS, TEXT, obj, arr, digest, canonical
from .turn import CountryInput

DECISION = obj({'choice_id': ID, 'requested_amount': POS, 'public_reason': TEXT})
RESPONSE = obj({'request_digest': HASH, 'state_id': ID,
                'decisions': arr(DECISION),
                'consents': {'type': 'object', 'additionalProperties': {'type': 'boolean'}}})


class ExchangeBudget:
    """Sequential host budget; reserve before dispatch, never retry an attempt."""
    def __init__(self, limit):
        ensure(type(limit) is int and limit >= 0, 'INVALID_EXCHANGE_LIMIT')
        self.limit = limit
        self.attempts = []

    def reserve(self, request):
        key = digest(request)
        ensure(key not in self.attempts, 'DUPLICATE_EXCHANGE_FORBIDDEN')
        ensure(len(self.attempts) < self.limit, 'EXCHANGE_BUDGET_EXHAUSTED')
        self.attempts.append(key)
        return key


def _object(pairs):
    result = {}
    for key, value in pairs:
        ensure(key not in result, 'DUPLICATE_RESPONSE_KEY')
        result[key] = value
    return result


class JsonCountryAdapter:
    def __init__(self, state_id, *, catalogue, exchange, budget, source):
        check(ID, state_id); check(TEXT, source)
        self.state_id, self.catalogue = state_id, catalogue
        self.exchange, self.budget, self.source = exchange, budget, source
        self._catalogue, self._exchange, self._budget = catalogue, exchange, budget
        self._configuration_failed = False
        self._configuration_hash = digest(self._configuration())

    def _configuration(self):
        return {'state_id': self.state_id, 'source': self.source,
                'budget_limit': getattr(self.budget, 'limit', None),
                'response_schema': RESPONSE}

    def _check_configuration(self):
        ensure(not self._configuration_failed, 'ADAPTER_CONFIGURATION_FAILED')
        try:
            ensure(self.catalogue is self._catalogue and self.exchange is self._exchange
                   and self.budget is self._budget
                   and digest(self._configuration()) == self._configuration_hash,
                   'ADAPTER_CONFIGURATION_CHANGED')
        except Exception:
            self._configuration_failed = True
            raise

    def _request(self, phase, observation, payload):
        self._check_configuration()
        request = {'version': 'v3', 'phase': phase, 'state_id': self.state_id,
                   'observation_digest': observation.hash,
                   'observation': observation.read(), 'payload': payload}
        key = self.budget.reserve(request)
        self._check_configuration()
        # Serialized JSON prevents a provider from mutating host input objects.
        raw = self.exchange(canonical({**request, 'request_digest': key}))
        self._check_configuration()
        ensure(type(raw) is str and len(raw.encode('utf-8')) <= 65536, 'INVALID_RESPONSE_SIZE')
        try:
            answer = json.loads(raw, object_pairs_hook=_object)
        except (ValueError, TypeError):
            ensure(False, 'INVALID_JSON_RESPONSE')
        check(RESPONSE, answer)
        ensure(answer['state_id'] == self.state_id, 'RESPONSE_ACTOR_MISMATCH')
        ensure(answer['request_digest'] == key, 'RESPONSE_SNAPSHOT_MISMATCH')
        return answer

    def choose(self, observation, proposal):
        self._check_configuration()
        catalogue = [t for t in self.catalogue(observation)
                     if t['actor_state_id'] == self.state_id]
        self._check_configuration()
        answer = self._request('choice', observation,
                               {'catalogue': catalogue, 'proposal': proposal.read()})
        ensure(not answer['consents'], 'PREMATURE_CONSENT_FORBIDDEN')
        selected = []
        for decision in answer['decisions']:
            selection = {'choice_id': decision['choice_id'],
                         'requested_amount': decision['requested_amount'],
                         'provenance': {'source': self.source,
                                        'public_reason': decision['public_reason']}}
            choice = materialize_choice(selection, catalogue)
            ensure(choice['actor_state_id'] == self.state_id, 'ACTOR_AUTHORITY_REQUIRED')
            selected.append(selection)
        ensure(len({s['choice_id'] for s in selected}) == len(selected), 'DUPLICATE_DECISION')
        return selected

    def consent(self, observation, choices):
        self._check_configuration()
        # No proposal is manufactured when there are no choices to consider.
        records = choices.read()
        if not records:
            return {}
        answer = self._request('consent', observation, {'choices': records})
        ensure(not answer['decisions'], 'LATE_DECISION_FORBIDDEN')
        ensure(set(answer['consents']) <= {c['choice_id'] for c in records}, 'INVALID_CONSENT_REFERENCE')
        return answer['consents']

    def callbacks(self):
        self._check_configuration()
        return CountryInput(self.choose, self.consent)
