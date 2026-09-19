"""Private choice records must not become another country's observations."""
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import socket
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import simulation
import experiment_runner
from test_simulation import FakeModels, sdk_reply


class PrivateModels(FakeModels):
    def __init__(self, a_plan='ALPHA_PRIVATE_PLAN'):
        super().__init__()
        self.a_plan = a_plan
        self.country_prompts = {'A': [], 'B': []}

    def generate_content(self, **kwargs):
        response = super().generate_content(**kwargs)
        if kwargs.get('config') and kwargs['config'].get('response_mime_type') == 'application/json':
            return response
        country = 'A' if '国家名: A国' in kwargs['contents'] else 'B'
        self.country_prompts[country].append(kwargs['contents'])
        private = self.a_plan if country == 'A' else 'BETA_PRIVATE_PLAN'
        return sdk_reply(f'現在認識: {country}_PRIVATE_BELIEF\n'
                         f'懸念: {country}_PRIVATE_CONCERN\n'
                         f'行動: 相手に知らせず{private}を準備する。\n'
                         f'理由: {country}_PRIVATE_REASON')


class PrivateObservationTests(unittest.TestCase):
    def setUp(self):
        network = patch.object(socket.socket, 'connect', side_effect=AssertionError('NO_NETWORK'))
        network.start(); self.addCleanup(network.stop)

    def run_direct(self, condition, plan='ALPHA_PRIVATE_PLAN'):
        models = PrivateModels(plan)
        with tempfile.TemporaryDirectory() as directory:
            previous = Path.cwd(); os.chdir(directory)
            try:
                with patch.object(simulation, 'USE_GEMINI', True), \
                     patch.object(simulation, 'TURN_COUNT', 3), \
                     patch.object(simulation, 'EXPERIMENT_CONDITION', condition), \
                     patch.object(simulation, 'getpass', return_value='offline-dummy'), \
                     patch.object(simulation.genai, 'Client', return_value=SimpleNamespace(models=models)), \
                     redirect_stdout(io.StringIO()):
                    simulation.main()
                result = json.loads(next(Path(directory).glob('simulation_result_*.json')).read_text())
            finally:
                os.chdir(previous)
        return models, result

    def assert_private(self, models):
        for country, other, own_plan, other_plan in (
            ('A', 'B', models.a_plan, 'BETA_PRIVATE_PLAN'),
            ('B', 'A', 'BETA_PRIVATE_PLAN', models.a_plan),
        ):
            for turn, prompt in enumerate(models.country_prompts[country]):
                self.assertNotIn(other_plan, prompt)
                for field in ('BELIEF', 'CONCERN', 'REASON'):
                    self.assertNotIn(f'{other}_PRIVATE_{field}', prompt)
                if turn:
                    self.assertIn(own_plan, prompt)
                    self.assertIn(f'{country}_PRIVATE_REASON', prompt)
                else:
                    self.assertNotIn(own_plan, prompt)

    def test_private_memory_and_observer_evidence_survive_without_broadcast(self):
        for condition in ('hotline', 'no_hotline'):
            with self.subTest(condition=condition):
                models, result = self.run_direct(condition)
                self.assert_private(models)
                for row in result['results']:
                    self.assertIn(models.a_plan, row['country_a']['action'])
                    self.assertIn('BETA_PRIVATE_PLAN', row['country_b']['action'])
                    self.assertIn(models.a_plan, row['world_state'])
                    self.assertIn('BETA_PRIVATE_PLAN', row['world_state'])
                    self.assertNotIn(models.a_plan, row['world_state_before'])
                    self.assertNotIn('BETA_PRIVATE_PLAN', row['world_state_before'])
                    self.assertEqual(row['country_a']['realization_status'], 'unverified')
                for prompt in models.prompts[2::3]:
                    self.assertIn(models.a_plan, prompt)
                    self.assertIn('BETA_PRIVATE_PLAN', prompt)

    def test_changing_a_private_plan_cannot_change_b_inputs(self):
        for condition in ('hotline', 'no_hotline'):
            with self.subTest(condition=condition):
                first, first_result = self.run_direct(condition, 'FIRST_PRIVATE_PLAN')
                second, second_result = self.run_direct(condition, 'SECOND_PRIVATE_PLAN')
                self.assertEqual(first.country_prompts['B'], second.country_prompts['B'])
                self.assertNotEqual(first.country_prompts['A'][1:], second.country_prompts['A'][1:])
                self.assertNotEqual(first_result['results'], second_result['results'])

    def test_comparison_runner_keeps_the_same_privacy_boundary(self):
        for condition in ('A', 'D'):
            with self.subTest(condition=condition), tempfile.TemporaryDirectory() as directory:
                models = PrivateModels()
                args = SimpleNamespace(output_dir=Path(directory), condition=condition,
                                       allow_over_limit=False, yes=True, seed=17)
                with patch.dict(os.environ, {'GEMINI_API_KEY': 'offline-dummy'}), \
                     patch.object(simulation.genai, 'Client', return_value=SimpleNamespace(models=models)), \
                     redirect_stdout(io.StringIO()):
                    experiment_runner.run_experiment(args)
                self.assertEqual(len(models.country_prompts['B']), 8)
                self.assert_private(models)
                saved = json.loads(experiment_runner.output_path(Path(directory), condition, 1).read_text())
                self.assertIn(models.a_plan, saved['results'][-1]['country_a']['action'])


if __name__ == '__main__':
    unittest.main()
