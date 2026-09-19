"""Decode model JSON without choosing duplicate fields or non-finite numbers."""
import json
import math


def _unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError('duplicate JSON response field')
        value[key] = item
    return value


def _invalid_constant(_value):
    raise ValueError('non-finite JSON response number')


def _finite_float(text):
    value = float(text)
    if not math.isfinite(value):
        raise ValueError('non-finite JSON response number')
    return value


def load_response_object(text):
    value = json.loads(text, object_pairs_hook=_unique_object,
                       parse_constant=_invalid_constant, parse_float=_finite_float)
    if not isinstance(value, dict):
        raise ValueError('response JSON must be an object')
    return value
