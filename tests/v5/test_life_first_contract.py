"""Offline contract checks; fixtures are not generated people or observations."""
from copy import deepcopy
import json
import unittest

from homeostasis_v5 import life_first_contract as contract


def life_fixture():
    return {
        'life_periods': [
            {'narrative': 'LIFE_ONLY_MARKER。架空の検証用前半。', 'elapsed_years': 6.25},
            {'narrative': '架空の検証用後半。この人物は現在Leader。', 'elapsed_years': 7.75},
        ],
        'name': 'OFFLINE_FIXTURE_PERSON',
        'gender_description': 'この検証用人物は性別を分類しない。',
    }


def person_fixture():
    return {
        'present_person': 'PERSON_ONLY_MARKER。前の記録を生きた検証用人物。',
        'age_years': 14,
        'values_and_beliefs': '検証用の記述であり人物生成例ではない。',
        'view_of_state_and_others': '具体的な担当国家の情報はない。',
        'tensions_and_vulnerabilities': '検証用の人物記述。',
        'conditional_principles': [{
            'perceived_condition': '本人にとって判然としない場面。',
            'what_matters': '本人の受け取った事実。',
            'judgment_tendency': '結論を保留することもある。',
            'deliberation_style': '知っている範囲を振り返る。',
            'exceptions_and_tensions': '急ぐこともある。',
            'life_refs': ['life#/life_periods/0'],
        }],
    }


def assessment_fixture():
    return {'assessments': {
        axis: {
            'value': None, 'status': 'insufficient_evidence',
            'supporting_refs': [], 'rationale': 'ASSESSMENT_ONLY_SECRET。記述では根拠不足。',
            'counterevidence_refs': [],
        }
        for axis in contract.AXES
    }}


def prior_fixture(phase):
    values = {'life': life_fixture(), 'person': person_fixture(),
              'assessment': assessment_fixture()}
    return {key: values[key] for key in contract.PHASES[:contract.PHASES.index(phase)]}


class LifeFirstContractTests(unittest.TestCase):
    def test_life_request_does_not_contain_age_field_axes_or_other_persons(self):
        request = contract.build_request('life', {})
        schema = request['generationConfig']['responseJsonSchema']
        self.assertEqual(list(schema['properties']), ['life_periods', 'name', 'gender_description'])
        wire = contract.request_bytes(request).decode()
        for forbidden in (*contract.AXES, 'age_years', 'current_age', 'ASSESSMENT_ONLY_SECRET',
                          '195', '52', 'v0', 'nation-001'):
            self.assertNotIn(forbidden, wire)
        self.assertLess(wire.index('"life_periods"'), wire.index('"name"'))
        self.assertLess(wire.index('"name"'), wire.index('"gender_description"'))
        self.assertNotIn('default', wire)
        self.assertNotIn('examples', wire)

    def test_person_request_only_uses_life_no_assessment(self):
        request = contract.build_request('person', prior_fixture('person'))
        wire = contract.request_bytes(request).decode()
        self.assertIn('LIFE_ONLY_MARKER', wire)
        self.assertNotIn('PERSON_ONLY_MARKER', wire)
        self.assertNotIn('ASSESSMENT_ONLY_SECRET', wire)
        for axis in contract.AXES:
            self.assertNotIn(axis, wire)

    def test_unknown_record_types_other_people_and_wrong_phase_order_are_rejected(self):
        for extra in ('other_people', 'nation', 'leaders', 'v0'):
            with self.subTest(extra=extra):
                prior = prior_fixture('person')
                prior[extra] = {'unrelated': 'NEVER_SEND'}
                with self.assertRaisesRegex(contract.LifeFirstValidationError, 'PRIOR_PHASE_SEQUENCE_MISMATCH'):
                    contract.build_request('person', prior)
        for phase, prior in (
            ('life', {'life': life_fixture()}),
            ('assessment', {'life': life_fixture()}),
            ('presentation', prior_fixture('assessment')),
        ):
            with self.subTest(phase=phase):
                with self.assertRaisesRegex(contract.LifeFirstValidationError, 'PRIOR_PHASE_SEQUENCE_MISMATCH'):
                    contract.build_request(phase, prior)
        polluted = life_fixture()
        polluted['other_person'] = {'name': 'UNRELATED_PERSON'}
        with self.assertRaisesRegex(contract.LifeFirstValidationError, 'PHASE_SCHEMA_ERROR'):
            contract.build_request('person', {'life': polluted})

    def test_prior_validation_cannot_be_skipped_by_later_phase(self):
        prior = prior_fixture('presentation')
        prior['person']['age_years'] = 15
        with self.assertRaisesRegex(contract.LifeFirstValidationError, 'LIFE_AGE_MISMATCH'):
            contract.build_request('presentation', prior)

    def test_assessment_has_exact_17_axes_without_changing_source_schema(self):
        before = contract.ASSESSMENT_SCHEMA_PATH.read_bytes()
        schema = contract.schema_for('assessment')
        axes = schema['properties']['assessments']
        self.assertEqual(len(axes['properties']), 17)
        self.assertEqual(tuple(axes['properties']), contract.AXES)
        self.assertEqual(tuple(axes['required']), contract.AXES)
        self.assertIn('decision_speed', axes['properties'])
        schema['properties']['assessments']['properties'].pop('decision_speed')
        self.assertIn('decision_speed', contract.schema_for('assessment')['properties']['assessments']['properties'])
        self.assertEqual(contract.ASSESSMENT_SCHEMA_PATH.read_bytes(), before)

    def test_assessment_input_contains_life_and_person(self):
        wire = contract.request_bytes(contract.build_request('assessment', prior_fixture('assessment'))).decode()
        self.assertIn('LIFE_ONLY_MARKER', wire)
        self.assertIn('PERSON_ONLY_MARKER', wire)
        self.assertNotIn('ASSESSMENT_ONLY_SECRET', wire)

    def test_presentation_never_receives_assessment_even_when_scores_change(self):
        first = prior_fixture('presentation')
        second = deepcopy(first)
        for rating in second['assessment']['assessments'].values():
            rating.update(value=87, status='rated', supporting_refs=['life#/life_periods/0'],
                          rationale='DIFFERENT_ASSESSMENT_ONLY_SECRET')
        one = contract.request_bytes(contract.build_request('presentation', first))
        two = contract.request_bytes(contract.build_request('presentation', second))
        self.assertEqual(one, two)
        wire = one.decode()
        self.assertIn('LIFE_ONLY_MARKER', wire)
        self.assertIn('PERSON_ONLY_MARKER', wire)
        self.assertNotIn('ASSESSMENT_ONLY_SECRET', wire)
        for axis in contract.AXES:
            self.assertNotIn(axis, wire)

    def test_age_matches_floor_of_decimal_time_without_changing_person(self):
        for periods, expected in (([6.25, 7.75], 14), ([0.1] * 30, 3),
                                  ([6.25, 7.74], 13), ([0], 0),
                                  ([10**40 - 1, 0.9], 10**40 - 1)):
            with self.subTest(periods=periods):
                life = life_fixture()
                life['life_periods'] = [
                    {'narrative': '記録された期間。', 'elapsed_years': years}
                    for years in periods
                ]
                person = person_fixture()
                person['age_years'] = expected
                original = deepcopy(person)
                result = contract.validate_phase('person', person, {'life': life})
                self.assertEqual(result['derived_age_years'], expected)
                self.assertEqual(person, original)
        invalid = person_fixture()
        invalid['age_years'] = 15
        with self.assertRaisesRegex(contract.LifeFirstValidationError, 'LIFE_AGE_MISMATCH'):
            contract.validate_phase('person', invalid, prior_fixture('person'))
        self.assertEqual(invalid['age_years'], 15)

    def test_invalid_numeric_types_and_nonfinite_periods_are_rejected(self):
        for value in (True, -1, float('nan'), float('inf'), '3'):
            with self.subTest(value=value):
                life = life_fixture()
                life['life_periods'][0]['elapsed_years'] = value
                with self.assertRaises(contract.LifeFirstValidationError):
                    contract.validate_phase('life', life, {})
        for value in (True, 14.0, '14'):
            with self.subTest(age=value):
                person = person_fixture()
                person['age_years'] = value
                with self.assertRaises(contract.LifeFirstValidationError):
                    contract.validate_phase('person', person, prior_fixture('person'))

    def test_no_gender_enum_or_age_maximum_or_principle_count_quota(self):
        life = life_fixture()
        life['gender_description'] = '分類されない独自の記述。'
        self.assertTrue(contract.validate_phase('life', life, {})['valid'])
        person = person_fixture()
        person['conditional_principles'] = []
        self.assertTrue(contract.validate_phase('person', person, {'life': life})['valid'])
        self.assertNotIn('enum', contract.schema_for('life')['properties']['gender_description'])
        self.assertNotIn('maximum', contract.schema_for('person')['properties']['age_years'])

    def test_principles_only_reference_existing_life_periods(self):
        for reference in ('life#/life_periods/2', 'person#/present_person',
                          'other-person#/life_periods/0'):
            with self.subTest(reference=reference):
                person = person_fixture()
                person['conditional_principles'][0]['life_refs'] = [reference]
                with self.assertRaisesRegex(contract.LifeFirstValidationError, 'UNKNOWN_EVIDENCE_REFERENCE'):
                    contract.validate_phase('person', person, prior_fixture('person'))

    def test_missing_assessment_stays_null_and_rated_needs_actual_support(self):
        value = assessment_fixture()
        result = contract.validate_phase('assessment', value, prior_fixture('assessment'))
        self.assertEqual(result['missing_assessment_axes'], list(contract.AXES))
        self.assertTrue(all(v['value'] is None for v in value['assessments'].values()))
        invalid_pairs = [
            {'status': 'rated', 'value': None, 'supporting_refs': ['life#/life_periods/0']},
            {'status': 'rated', 'value': 80, 'supporting_refs': []},
            {'status': 'rated', 'value': 80.0, 'supporting_refs': ['life#/life_periods/0']},
            {'status': 'rated', 'value': True, 'supporting_refs': ['life#/life_periods/0']},
            {'status': 'rated', 'value': 101, 'supporting_refs': ['life#/life_periods/0']},
            {'status': 'insufficient_evidence', 'value': 50, 'supporting_refs': []},
        ]
        for patch in invalid_pairs:
            with self.subTest(patch=patch):
                bad = assessment_fixture()
                bad['assessments']['empathy'].update(patch)
                with self.assertRaises(contract.LifeFirstValidationError):
                    contract.validate_phase('assessment', bad, prior_fixture('assessment'))

    def test_ratings_allow_high_apparently_conflicting_scores_and_existing_refs(self):
        value = assessment_fixture()
        for axis in ('empathy', 'instrumental_harm_tolerance'):
            value['assessments'][axis].update(
                status='rated', value=95,
                supporting_refs=['person#/conditional_principles/0'],
                counterevidence_refs=['life#/life_periods/1'],
            )
        before = deepcopy(value)
        result = contract.validate_phase('assessment', value, prior_fixture('assessment'))
        self.assertTrue(result['valid'])
        self.assertEqual(value, before)
        self.assertEqual(len(result['missing_assessment_axes']), 15)
        for field in ('supporting_refs', 'counterevidence_refs'):
            invalid = deepcopy(value)
            invalid['assessments']['empathy'][field] = ['person#/conditional_principles/1']
            with self.assertRaisesRegex(contract.LifeFirstValidationError, 'UNKNOWN_EVIDENCE_REFERENCE'):
                contract.validate_phase('assessment', invalid, prior_fixture('assessment'))

    def test_presentation_length_is_annotation_not_repair_or_failure(self):
        for text, count, warning in (
            ('短い紹介。', 5, True),
            ('私' * 200, 200, False),
            ('私' * 100 + '\r\n' + '私' * 200, 300, False),
            ('私' * 301, 301, True),
        ):
            with self.subTest(count=count):
                value = {'self_introduction': text}
                before = deepcopy(value)
                result = contract.validate_phase('presentation', value, prior_fixture('presentation'))
                self.assertTrue(result['valid'])
                self.assertEqual(result['intro_character_count'], count)
                self.assertEqual(bool(result['warnings']), warning)
                self.assertEqual(value, before)

    def test_requests_preserve_source_data_and_generation_settings(self):
        for phase in contract.PHASES:
            with self.subTest(phase=phase):
                prior = prior_fixture(phase)
                before = deepcopy(prior)
                request = contract.build_request(phase, prior)
                self.assertEqual(prior, before)
                config = request['generationConfig']
                self.assertEqual(config['temperature'], 1.0)
                self.assertEqual(config['candidateCount'], 1)
                self.assertEqual(config['thinkingConfig']['thinkingLevel'], 'LOW')
                self.assertNotIn('seed', config)
                self.assertNotIn('topP', config)
                self.assertNotIn('topK', config)
                self.assertEqual(json.loads(contract.request_bytes(request)), request)
                self.assertEqual(len(request['contents']), 1)
        self.assertEqual(contract.LEADER_COUNT, 12)


if __name__ == '__main__':
    unittest.main()
