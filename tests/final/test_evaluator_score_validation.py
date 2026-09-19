"""Invalid evaluator output is a technical failure, not a repaired observation."""
import json
from types import SimpleNamespace
import unittest
from test_simulation import sdk_reply

import simulation
import simulation_v2


class EvaluatorScoreValidationTests(unittest.TestCase):
    def test_invalid_score_types_and_ranges_are_not_repaired(self):
        for module in (simulation,simulation_v2):
            fields=module.EVALUATION_FIELDS if module is simulation else module.EVALUATOR_FIELDS
            good={**{field:50 for field in fields},'assessment':'観測'}
            for field in fields:
                for bad in (-1,101,'50',True,False,None,[],{}):
                    with self.subTest(module=module.__name__,field=field,value=bad):
                        with self.assertRaises(ValueError):
                            module.parse_evaluator_response(json.dumps({**good,field:bad}))

    def test_v1_fractional_scores_are_not_rounded_into_requested_integers(self):
        good={field:50 for field in simulation.EVALUATION_FIELDS}
        for field in good:
            with self.subTest(field=field):
                with self.assertRaises(ValueError):
                    simulation.parse_evaluator_response(json.dumps({**good,field:50.5}))

    def test_valid_boundaries_and_existing_numeric_behavior_are_preserved(self):
        for value in (0,50,100,50.0):
            good={field:value for field in simulation.EVALUATION_FIELDS}
            self.assertEqual(simulation.parse_evaluator_response(json.dumps(good)),
                             {field:int(value) for field in good})
        for value in (0,50.25,100):
            good={**{field:value for field in simulation_v2.EVALUATOR_FIELDS},'assessment':'観測'}
            self.assertEqual(simulation_v2.parse_evaluator_response(json.dumps(good)),
                             {**{field:simulation_v2.clamp_score(value) for field in simulation_v2.EVALUATOR_FIELDS},
                              'assessment':'観測'})

    def test_invalid_v1_evaluation_stops_after_one_received_answer(self):
        answer={field:50 for field in simulation.EVALUATION_FIELDS}
        answer['actual_threat_level']=999
        calls=[]
        def generate(**kwargs):
            calls.append(kwargs)
            return sdk_reply(json.dumps(answer))
        client=SimpleNamespace(models=SimpleNamespace(generate_content=generate))
        with self.assertRaises(ValueError):
            simulation.call_evaluator(client,simulation.EXTERNAL_EVENTS[0],'世界',
                '行動A','理由A','認識A','行動B','理由B','認識B',simulation.INTERNATIONAL_LAW)
        self.assertEqual(len(calls),1)


if __name__ == '__main__': unittest.main()
