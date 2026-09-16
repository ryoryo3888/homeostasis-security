"""Offline regression for the saved empty-CONDITIONAL failure (no SDK calls)."""
import copy
import json
from pathlib import Path
import unittest

from homeostasis_core.gemini_agents import country_choice_schema, parse_country_choice_json, _condition_met


def conforms(value, schema):
    """Independent evaluator of the JSON-schema subset used by this contract."""
    kind = schema.get('type')
    checks = {'object': lambda v: isinstance(v, dict), 'array': lambda v: isinstance(v, list),
              'string': lambda v: isinstance(v, str), 'number': lambda v: type(v) in (int, float),
              'integer': lambda v: type(v) is int, 'boolean': lambda v: type(v) is bool}
    if kind and not checks[kind](value): return False
    if 'enum' in schema and value not in schema['enum']: return False
    if 'anyOf' in schema and not any(conforms(value, branch) for branch in schema['anyOf']): return False
    if isinstance(value, dict):
        if not set(schema.get('required', ())) <= set(value): return False
        props = schema.get('properties', {})
        if schema.get('additionalProperties') is False and set(value)-set(props): return False
        if any(not conforms(v, props[k]) for k, v in value.items() if k in props): return False
    if isinstance(value, list) and 'items' in schema:
        if not all(conforms(v, schema['items']) for v in value): return False
    if type(value) in (float, int):
        if 'minimum' in schema and value < schema['minimum']: return False
        if 'maximum' in schema and value > schema['maximum']: return False
    return True


class CountryChoiceContractTests(unittest.TestCase):
    def setUp(self):
        self.fixture=json.loads(Path('tests/fixtures/conditional_empty_failure.json').read_text())
        f=self.fixture
        self.answer=copy.deepcopy(f['model_response'])
        self.schema=country_choice_schema(f['country_id'], f['proposal_id'], f['country_ids'], f['action_choices'])

    def parse(self, answer):
        f=self.fixture
        return parse_country_choice_json(json.dumps(answer), f['country_id'], f['proposal_id'],
                                         f['country_ids'], f['action_choices'], f['action_choices'])

    def test_saved_answer_exposes_old_schema_parser_mismatch(self):
        self.assertTrue(conforms(self.answer, self.fixture['original_schema']))
        with self.assertRaisesRegex(ValueError, 'conditions must exist'):
            self.parse(self.answer)
        self.assertFalse(conforms(self.answer, self.schema))
        # Neither prior result nor fixture is rewritten to make it valid.
        self.assertEqual(self.answer['conditions'], {})

    def test_all_supported_condition_types_match_schema_and_parser(self):
        for conditions in ({'required_countries':['MIL']}, {'minimum_aid_amount':5},
                           {'maximum_sovereignty_burden':30}, {'mutual_performance':True},
                           {'deadline_turn':2}):
            with self.subTest(conditions=conditions):
                answer=copy.deepcopy(self.answer);answer['conditions']=conditions
                self.assertTrue(conforms(answer, self.schema))
                action=self.parse(answer)['action']
                self.assertEqual(action['action_id'],'PROVIDE_FUNDS')
                self.assertEqual(action['parameters']['target_country'],'FRAGILE')
                self.assertEqual(action['parameters']['amount'],10)

    def test_invalid_conditions_are_rejected_by_schema_and_parser(self):
        for conditions in ({}, {'neutral_oversight':True}, {'required_countries':['WORLD']},
                           {'minimum_aid_amount':True}, {'maximum_sovereignty_burden':101},
                           {'mutual_performance':'yes'}, {'deadline_turn':0}, {'deadline_turn':True}):
            with self.subTest(conditions=conditions):
                answer=copy.deepcopy(self.answer);answer['conditions']=conditions
                self.assertFalse(conforms(answer, self.schema))
                with self.assertRaises(ValueError): self.parse(answer)

    def test_accept_reject_require_empty_conditions_and_matching_label(self):
        for response,label in (('ACCEPT','受け入れる'),('REJECT','拒否する')):
            answer={**self.answer,'response_id':response,'response_label':label}
            self.assertTrue(conforms(answer,self.schema));self.parse(answer)
            answer['conditions']={'deadline_turn':1}
            self.assertFalse(conforms(answer,self.schema))
            with self.assertRaises(ValueError):self.parse(answer)
        answer={**self.answer,'response_label':'受け入れる','conditions':{'deadline_turn':1}}
        self.assertFalse(conforms(answer,self.schema))
        with self.assertRaises(ValueError):self.parse(answer)

    def test_identity_and_free_action_tuple_still_rejected(self):
        valid={**self.answer,'conditions':{'deadline_turn':1}}
        for update in ({'country_id':'MIL'}, {'proposal_id':'wrong'}, {'action':{}}, {'choice_id':'UNKNOWN'}):
            answer={**valid,**update}
            self.assertFalse(conforms(answer,self.schema))
            with self.assertRaises(ValueError):self.parse(answer)

    def test_choice_amount_and_reason_remain_strict(self):
        valid={**self.answer,'conditions':{'deadline_turn':1}}
        for update in ({'amount':12}, {'amount':0}, {'amount':-1}, {'amount':True}, {'reason':''}):
            with self.subTest(update=update):
                with self.assertRaises(ValueError):self.parse({**valid,**update})

    def test_reason_text_never_substitutes_for_executable_conditions(self):
        with self.assertRaises(ValueError):self.parse(self.answer)
        answer={**self.answer,'conditions':{'minimum_aid_amount':11}}
        parsed=self.parse(answer)
        self.assertFalse(_condition_met(parsed,{'ECON'},1))
        parsed['conditions']={'minimum_aid_amount':9}
        self.assertTrue(_condition_met(parsed,{'ECON'},1))
