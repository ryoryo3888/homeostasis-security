"""Persist only public decision JSON; never SDK objects, thoughts or credentials."""
import json
import os
import re
from .action_choices import materialize_choice


class AuditPersistenceError(RuntimeError):
    pass


def safe_data(value):
    """Defense in depth for configured credentials and conventional secret keys."""
    secret_names = {'apikey', 'authorization', 'password', 'secret', 'token',
                    'accesstoken', 'refreshtoken', 'credentials', 'thought',
                    'thoughts', 'thoughtsignature', 'chainofthought', 'internalreasoning'}
    secrets = [v for k, v in os.environ.items() if v and
               any(term in k.upper() for term in ('API_KEY', 'TOKEN', 'PASSWORD', 'SECRET'))]
    def protected_key(key):
        name = re.sub('[^a-z]', '', key.lower())
        return (name in secret_names or any(term in name for term in ('apikey', 'password', 'credentials', 'secret'))
                or name.endswith('accesstoken') or name.endswith('refreshtoken'))
    def clean(item):
        if isinstance(item, dict):
            return {k: ('[REDACTED]' if protected_key(k) else clean(v))
                    for k, v in item.items()}
        if isinstance(item, (list, tuple)):
            return [clean(v) for v in item]
        if isinstance(item, str):
            for secret in secrets:
                item = item.replace(secret, '[REDACTED]')
            return re.sub(r'AIza[0-9A-Za-z_-]{30,}', '[REDACTED]', item)
        return item
    return clean(value)


def decision_json(text, schema):
    """Keep only declared final-answer fields; invalid/extra raw text is not logged."""
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError('response must be an object')
    if schema is None:
        return safe_data(value)
    allowed = set(schema['properties'])
    return safe_data({k: v for k, v in value.items() if k in allowed})


def validate_choice_trace(record):
    """Recompute the action using the ORIGINAL selected ID, not reverse inference."""
    for key in ('run_id', 'turn', 'agent_id', 'attempt', 'call_id'):
        if not record.get(key):
            raise ValueError('missing audit identity: ' + key)
    if record.get('audit_version') != 1 or record.get('validation_status') != 'PASS':
        raise ValueError('choice audit is not validated')
    answer = record['model_response']
    selected = {k: answer[k] for k in ('choice_id', 'amount', 'reason')}
    if selected != record['choice_response']:
        raise ValueError('original choice response mismatch')
    catalog = record['public_observation_payload']['action_choices']
    action = materialize_choice(record['agent_id'], selected['choice_id'], selected['amount'],
                                selected['reason'], catalog, catalog)
    if action != record['materialized_action']:
        raise ValueError('choice/action trace mismatch')
    parsed = record['structured_response']
    if 'action' in parsed:
        expected = dict(answer)
        expected.pop('choice_id')
        expected.pop('amount')
        expected['action'] = action
        if expected != parsed:
            raise ValueError('original structured response mismatch')
    elif set(answer) != {'choice_id', 'amount', 'reason'}:
        raise ValueError('unexpected probe response fields')
    if action != parsed.get('action', parsed):
        raise ValueError('parsed action mismatch')
    return True
