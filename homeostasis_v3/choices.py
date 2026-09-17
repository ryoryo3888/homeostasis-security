"""Python-owned choice templates and trusted, in-memory actor capabilities.

No model/client is constructed. The authority is owned by a future trusted host;
actor capabilities, never the authority object, may be handed to adapters.
"""
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import hmac
import json
import secrets

from jsonschema import Draft202012Validator, ValidationError
from .contracts import ID, HASH, TEXT, POS, UINT, IDS, obj, arr, enum, canonical, digest


class TechnicalFailure(ValueError):
    """Invalid input/invariant, not a legitimate world-level rejection."""
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def ensure(value, code):
    if not value:
        raise TechnicalFailure(code)


CONDITION = obj({'kind': enum('participation', 'settled_amount', 'arrived_amount'),
                 'choice_id': ID, 'minimum_amount': UINT})
PROVENANCE = obj({'source': TEXT, 'public_reason': TEXT})
TEMPLATE = obj({'choice_id': ID, 'actor_state_id': ID, 'turn': UINT,
    'snapshot_hash': HASH, 'action_type': ID, 'resource': ID, 'maximum_amount': POS,
    'target': ID, 'route_preference': {'anyOf': [ID, {'type': 'null'}]},
    'conditions': arr(CONDITION), 'allow_partial': {'type': 'boolean'}, 'minimum_amount': POS})
SELECTION = obj({'choice_id': ID, 'requested_amount': POS, 'provenance': PROVENANCE})
CHOICE = obj({**TEMPLATE['properties'], 'requested_amount': POS, 'provenance': PROVENANCE})


def check(schema, value):
    try:
        canonical(value)
        Draft202012Validator(schema).validate(value)
    except (ValueError, TypeError, ValidationError):
        raise TechnicalFailure('SCHEMA_ERROR') from None


def materialize_choice(selection, catalogue):
    """Only trusted catalogues supply executable fields; no free action tuple."""
    check(SELECTION, selection)
    ids = set()
    for template in catalogue:
        check(TEMPLATE, template)
        ensure(template['choice_id'] not in ids, 'CHOICE_ID_COLLISION')
        ids.add(template['choice_id'])
    match = next((c for c in catalogue if c['choice_id'] == selection['choice_id']), None)
    ensure(match is not None, 'UNKNOWN_CHOICE')
    result = {**deepcopy(match), **deepcopy(selection)}
    validate_choice(result)
    return result


def validate_choice(choice):
    check(CHOICE, choice)
    for name in ('turn', 'maximum_amount', 'requested_amount', 'minimum_amount'):
        ensure(type(choice[name]) is int, 'INTEGER_QUANTITY_REQUIRED')
    ensure(choice['minimum_amount'] <= choice['requested_amount'] <= choice['maximum_amount'], 'INVALID_AMOUNT')
    for c in choice['conditions']:
        ensure(type(c['minimum_amount']) is int, 'INTEGER_QUANTITY_REQUIRED')
        ensure(c['choice_id'] != choice['choice_id'], 'SELF_CONDITION')
        ensure((c['kind'] == 'participation' and c['minimum_amount'] == 0) or
               (c['kind'] != 'participation' and c['minimum_amount'] > 0), 'INVALID_CONDITION')
    return choice


@dataclass(frozen=True)
class Envelope:
    payload: str
    signature: str


class Principal:
    """An issued capability; its issuer validates identity, not an input role field."""
    def __init__(self, role, state_id):
        self.role = role
        self.state_id = state_id


class Authority:
    def __init__(self, states):
        self._states = frozenset(states)
        self._key = secrets.token_bytes(32)
        self._principals = {}

    def issue(self, role, state_id=None):
        ensure(role in ('country', 'pool', 'coordinator', 'evaluator', 'core'), 'INVALID_ROLE')
        ensure((role == 'country' and state_id in self._states) or
               (role != 'country' and state_id is None), 'INVALID_PRINCIPAL')
        principal = Principal(role, state_id)
        self._principals[principal] = (role, state_id)
        return principal

    def _identity(self, principal):
        ensure(principal in self._principals, 'UNAUTHENTICATED_PRINCIPAL')
        role, sid = self._principals[principal]
        ensure((principal.role, principal.state_id) == (role, sid), 'PRINCIPAL_TAMPERED')
        return role, sid

    def _sign(self, data):
        payload = canonical(data)
        signature = hmac.new(self._key, payload.encode('utf-8'), hashlib.sha256).hexdigest()
        return Envelope(payload, signature)

    def verify(self, envelope, kind):
        ensure(type(envelope) is Envelope, 'UNAUTHENTICATED_ENVELOPE')
        expected = hmac.new(self._key, envelope.payload.encode('utf-8'), hashlib.sha256).hexdigest()
        ensure(hmac.compare_digest(expected, envelope.signature), 'ENVELOPE_TAMPERED')
        data = json.loads(envelope.payload)
        ensure(data['kind'] == kind, 'WRONG_ENVELOPE_KIND')
        return data

    def submit(self, principal, choice):
        role, sid = self._identity(principal)
        validate_choice(choice)
        ensure(role == 'country' and sid == choice['actor_state_id'], 'ACTOR_AUTHORITY_REQUIRED')
        return self._sign({'kind': 'choice', 'choice': deepcopy(choice)})

    def consent(self, principal, choice, *, accepted):
        role, sid = self._identity(principal)
        validate_choice(choice)
        ensure(role in ('country', 'pool'), 'CONSENT_AUTHORITY_REQUIRED')
        ensure(type(accepted) is bool, 'INVALID_CONSENT')
        return self._sign({'kind': 'consent', 'choice_hash': digest(choice),
                          'principal': sid if role == 'country' else 'world_pool', 'accepted': accepted})
