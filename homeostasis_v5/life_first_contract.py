"""Life-first persona contracts; no network, simulation, or evidence mutation.

Every request contains one phase and only that person's permitted earlier
records. Formal validation does not establish psychological validity or factual
consistency of prose; those limits remain explicit in the validation report.
"""
from prompt_interface import private_text
from copy import deepcopy
from fractions import Fraction
import json
import math
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
ASSESSMENT_SCHEMA_PATH = (
    ROOT / 'docs/design/v5/PERSONA_GENERATOR_V1_MEASUREMENT_SCHEMA.proposed.json'
)
GENERATION_METHOD_VERSION = 'life-first-v1'
CONTRACT_VERSION = 'life-first-contract-1'
SCHEMA_VERSION = 'life-first-persona-schema-1'
MODEL = 'gemini-3.6-flash'
LEADER_COUNT = 12
PHASES = ('life', 'person', 'assessment', 'presentation')
PHASE_LIMITS = {
    'life': {'max_input_tokens': 8000, 'max_output_tokens': 4096},
    'person': {'max_input_tokens': 16000, 'max_output_tokens': 4096},
    'assessment': {'max_input_tokens': 24000, 'max_output_tokens': 6144},
    'presentation': {'max_input_tokens': 16000, 'max_output_tokens': 1536},
}
AXES = (
    'empathy', 'initial_trust', 'vigilance', 'risk_tolerance',
    'ambiguity_tolerance', 'instrumental_harm_tolerance',
    'compromise_readiness', 'retaliation_tendency', 'norm_commitment',
    'outcome_orientation', 'future_orientation', 'information_openness',
    'power_seeking', 'responsibility_ownership', 'national_interest_weight',
    'external_welfare_weight', 'decision_speed',
)


class LifeFirstValidationError(ValueError):
    """A machine-readable validation failure without echoing model content."""


def _ensure(condition, code):
    if not condition:
        raise LifeFirstValidationError(code)


def _object(properties, description):
    return {
        'type': 'object', 'description': description,
        'properties': properties, 'required': list(properties),
        'additionalProperties': False,
    }


def _text(description):
    return {'type': 'string', 'minLength': 1, 'description': description}


def _life_schema():
    # The wire order deliberately starts with lived periods, not age or identity.
    period = _object({
        'narrative': _text('この区間で生きた経験。出来事の種類や件数は自由。'),
        'elapsed_years': {
            'type': 'number', 'minimum': 0,
            'description': 'この区間だけの経過年数。0以上、小数可。重なる活動の期間を二重に加算しない。',
        },
    }, '出生から現在までの連続した時間軸の一区間。')
    return _object({
        'life_periods': {
            'type': 'array', 'minItems': 1, 'items': period,
            'description': '出生から現在までを順番に覆う可変数の区間。空白期間や重複を設けない。',
        },
        'name': _text('この人物の氏名。'),
        'gender_description': _text('性別についての自由な記述。分類の選択肢や割合は指定されない。'),
    }, '一人の架空の人間の人生史。現在、この人物は国家Leaderである。')


def _person_schema():
    principle = _object({
        'perceived_condition': _text('本人がどのような状況だと受け取った場合の原則か。'),
        'what_matters': _text('その状況で本人が判断材料として重く見ること。'),
        'judgment_tendency': _text('本人がどのように判断しやすいか。将来の確定行動ではない。'),
        'deliberation_style': _text('本人が情報を扱い判断を進める過程。'),
        'exceptions_and_tensions': _text('例外や葛藤についての記述。存在しないものを無理に作らない。'),
        'life_refs': {
            'type': 'array', 'minItems': 1, 'items': {'type': 'string'},
            'description': 'この原則の根拠となる固定済み人生区間の参照ID。入力の参照一覧から選ぶ。',
        },
    }, '人生経験から形成された条件付き判断原則。状況一覧は固定されていない。')
    return _object({
        'present_person': _text('固定済みの人生を経て現在国家Leaderである人物像。'),
        'age_years': {
            'type': 'integer', 'minimum': 0,
            'description': '人生区間の経過年数の合計から成立する満年齢。合計の小数部分を切り捨てる。',
        },
        'values_and_beliefs': _text('現在の価値観や信念。'),
        'view_of_state_and_others': _text('国家と他者をどのように捉えるか。担当国家の具体的な設定は与えられていない。'),
        'tensions_and_vulnerabilities': _text('本人の矛盾や弱点について。矛盾を解消せず、無理に作ることも求めない。'),
        'conditional_principles': {
            'type': 'array', 'items': principle,
            'description': 'この人物の経験に基づく原則。件数や対象状況は人物に応じて決める。',
        },
    }, '固定済みの人生から成立する現在の人物。氏名や性別は人生史の記録を保持する。')


def _assessment_schema():
    # Read the proposal as a source; never rewrite the frozen or proposed file.
    schema = json.loads(ASSESSMENT_SCHEMA_PATH.read_text(encoding='utf-8'))
    axis_schema = schema.get('properties', {}).get('assessments', {})
    _ensure(tuple(axis_schema.get('properties', {})) == AXES
            and tuple(axis_schema.get('required', ())) == AXES,
            'ASSESSMENT_AXES_MISMATCH')
    schema['title'] = 'Life-first persona retrospective assessment schema 1'
    schema['description'] = (
        '固定済みの人生と人物記述に基づく17軸の事後LLM評定。'
        '実際の行動や心理検査の測定値ではない。根拠不足はnullで保持する。'
    )
    return schema


def _presentation_schema():
    return _object({
        'self_introduction': _text(
            '初めて他国のLeaderと会う場面で本人が自由に語る、一人称の自己紹介。200〜300文字程度。'
        ),
    }, '本人が他者に表明する自己像。真の自己認識の測定ではない。')


def schema_for(phase):
    """Return a fresh schema; callers cannot change later requests by mutation."""
    _ensure(phase in PHASES, 'UNKNOWN_PHASE')
    schema = {
        'life': _life_schema,
        'person': _person_schema,
        'assessment': _assessment_schema,
        'presentation': _presentation_schema,
    }[phase]()
    Draft202012Validator.check_schema(schema)
    return schema


def _check_json_text(value):
    """Reject non-JSON numbers, booleans masquerading as numbers, and blank text."""
    if type(value) is str:
        _ensure(bool(value.strip()), 'EMPTY_TEXT')
    elif type(value) is float:
        _ensure(math.isfinite(value), 'NONFINITE_NUMBER')
    elif type(value) in (int, bool) or value is None:
        return
    elif type(value) is dict:
        for key, child in value.items():
            _ensure(type(key) is str, 'NONSTRING_OBJECT_KEY')
            _check_json_text(child)
    elif type(value) is list:
        for child in value:
            _check_json_text(child)
    else:
        raise LifeFirstValidationError('NON_JSON_VALUE')


def age_from_life(life):
    """Compute the age check without modifying the source or choosing an age."""
    _ensure(type(life) is dict and type(life.get('life_periods')) is list
            and bool(life['life_periods']), 'LIFE_PERIODS_REQUIRED')
    years = Fraction(0)
    for period in life['life_periods']:
        _ensure(type(period) is dict, 'LIFE_PERIOD_REQUIRED')
        elapsed = period.get('elapsed_years')
        _ensure(type(elapsed) in (int, float), 'ELAPSED_YEARS_NUMBER_REQUIRED')
        if type(elapsed) is float:
            _ensure(math.isfinite(elapsed), 'NONFINITE_NUMBER')
        number = Fraction(str(elapsed))
        _ensure(number >= 0, 'INVALID_ELAPSED_YEARS')
        years += number
    return years.numerator // years.denominator


def reference_catalog(prior):
    """Stable, host-defined references; scores and introductions are never sources.

    Catalog values are copies of the original records. Prompts include only the
    IDs beside the source records, avoiding a second copy of all source prose.
    """
    _ensure(type(prior) is dict and set(prior) <= set(PHASES), 'INVALID_PRIOR_RECORDS')
    result = {}
    if 'life' in prior:
        life = prior['life']
        _ensure(type(life) is dict and type(life.get('life_periods')) is list,
                'LIFE_PERIODS_REQUIRED')
        for index, period in enumerate(life['life_periods']):
            result[f'life#/life_periods/{index}'] = deepcopy(period)
    if 'person' in prior:
        person = prior['person']
        _ensure(type(person) is dict, 'PERSON_REQUIRED')
        for field in ('present_person', 'values_and_beliefs',
                      'view_of_state_and_others', 'tensions_and_vulnerabilities'):
            if field in person:
                result[f'person#/{field}'] = deepcopy(person[field])
        principles = person.get('conditional_principles', [])
        _ensure(type(principles) is list, 'PRINCIPLES_ARRAY_REQUIRED')
        for index, principle in enumerate(principles):
            result[f'person#/conditional_principles/{index}'] = deepcopy(principle)
    return result


def _validate_refs(refs, permitted):
    _ensure(all(reference in permitted for reference in refs), 'UNKNOWN_EVIDENCE_REFERENCE')


def _validate_value(phase, value, prior):
    _check_json_text(value)
    schema = schema_for(phase)
    _ensure(not any(Draft202012Validator(schema).iter_errors(value)), 'PHASE_SCHEMA_ERROR')
    report = {
        'phase': phase, 'valid': True, 'warnings': [],
        'content_review_required': True,
        'semantic_consistency_verified': False,
        'personality_alignment_scored': False,
    }
    if phase == 'life':
        report['derived_age_years'] = age_from_life(value)
        report['life_period_count'] = len(value['life_periods'])
    elif phase == 'person':
        _ensure(type(value['age_years']) is int, 'AGE_INTEGER_REQUIRED')
        derived_age = age_from_life(prior['life'])
        _ensure(value['age_years'] == derived_age, 'LIFE_AGE_MISMATCH')
        permitted = reference_catalog({'life': prior['life']})
        for principle in value['conditional_principles']:
            _validate_refs(principle['life_refs'], permitted)
        report['derived_age_years'] = derived_age
    elif phase == 'assessment':
        permitted = reference_catalog({'life': prior['life'], 'person': prior['person']})
        missing = []
        for axis in AXES:
            rating = value['assessments'][axis]
            _validate_refs(rating['supporting_refs'], permitted)
            _validate_refs(rating['counterevidence_refs'], permitted)
            if rating['status'] == 'rated':
                _ensure(type(rating['value']) is int, 'RATED_VALUE_INTEGER_REQUIRED')
                _ensure(bool(rating['supporting_refs']), 'RATED_SUPPORT_REQUIRED')
            else:
                _ensure(rating['value'] is None, 'MISSING_ASSESSMENT_MUST_BE_NULL')
                missing.append(axis)
        report['missing_assessment_axes'] = missing
        report['measurement_kind'] = 'retrospective_llm_rating_not_behavioral_measurement'
    else:
        text = value['self_introduction']
        count = len(text.replace('\r', '').replace('\n', ''))
        report['intro_character_count'] = count
        report['character_count_basis'] = 'Unicode code points excluding CR and LF'
        if not 200 <= count <= 300:
            report['warnings'].append('INTRO_OUTSIDE_APPROXIMATE_LENGTH')
    return report


def _validate_prior(phase, prior):
    _ensure(phase in PHASES, 'UNKNOWN_PHASE')
    _ensure(type(prior) is dict, 'INVALID_PRIOR_RECORDS')
    earlier = PHASES[:PHASES.index(phase)]
    _ensure(set(prior) == set(earlier), 'PRIOR_PHASE_SEQUENCE_MISMATCH')
    validated = {}
    for previous_phase in earlier:
        _validate_value(previous_phase, prior[previous_phase], validated)
        validated[previous_phase] = prior[previous_phase]


def validate_phase(phase, parsed, prior):
    """Validate without repairing, selecting, or mutating generated records."""
    _validate_prior(phase, prior)
    return _validate_value(phase, parsed, prior)


SYSTEM_INSTRUCTION = (
    private_text('homeostasis_v5/life_first_contract.py:278:4')
)

LIFE_PROMPT = private_text('homeostasis_v5/life_first_contract.py:283:14')

PERSON_PROMPT = private_text('homeostasis_v5/life_first_contract.py:295:16')

ASSESSMENT_PROMPT = private_text('homeostasis_v5/life_first_contract.py:305:20')

PRESENTATION_PROMPT = private_text('homeostasis_v5/life_first_contract.py:315:22')


def build_request(phase, prior):
    """Build one provider request, preserving schema and source insertion order.

    All earlier phases are validated to enforce chronology, but assessment data
    is never included in the presentation model's context. The host must enforce
    each input-token cap before sending and preserve the actual request bytes.
    """
    _validate_prior(phase, prior)
    prompts = {
        'life': LIFE_PROMPT, 'person': PERSON_PROMPT,
        'assessment': ASSESSMENT_PROMPT, 'presentation': PRESENTATION_PROMPT,
    }
    permitted = () if phase == 'life' else (
        ('life',) if phase == 'person' else ('life', 'person')
    )
    source = {key: deepcopy(prior[key]) for key in permitted}
    prompt = prompts[phase]
    if source:
        material = {'source_records': source}
        if phase in ('person', 'assessment'):
            material['valid_evidence_refs'] = list(reference_catalog(source))
        prompt += private_text('homeostasis_v5/life_first_contract.py:344:18')
        prompt += json.dumps(material, ensure_ascii=False, allow_nan=False, separators=(',', ':'))
    return {
        'systemInstruction': {'parts': [{'text': SYSTEM_INSTRUCTION}]},
        'contents': [{'role': private_text('homeostasis_v5/life_first_contract.py:348:30'), 'parts': [{'text': prompt}]}],
        'generationConfig': {
            'responseMimeType': 'application/json', 'responseJsonSchema': schema_for(phase),
            'temperature': 1.0, 'candidateCount': 1,
            'maxOutputTokens': PHASE_LIMITS[phase]['max_output_tokens'],
            'thinkingConfig': {'thinkingLevel': 'LOW', 'includeThoughts': False},
        },
    }


def request_bytes(request):
    """The actual wire form is distinct from sorted-key hashing representations."""
    return json.dumps(request, ensure_ascii=False, allow_nan=False,
                      separators=(',', ':'), sort_keys=False).encode('utf-8')
