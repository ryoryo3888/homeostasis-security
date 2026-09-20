"""Offline publication: exact messages, honest limits, no private payload leakage."""
from copy import deepcopy
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import unittest

from tools.build_v2_observation import EARTH_METRICS, build_html, turn_markup
from tools.export_v2_observation import digest, export_trials

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / 'results/v2-five-runs/data.json'


class Messages(HTMLParser):
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.bodies = []
        self.current = None
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        if tag == 'blockquote':
            self.current = ''

    def handle_data(self, text):
        if self.current is not None:
            self.current += text

    def handle_endtag(self, tag):
        if tag == 'blockquote':
            self.bodies.append(self.current)
            self.current = None


class ObservationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(DATA.read_text())
        cls.source = (ROOT / 'dashboard_v2.html').read_text()

    def test_published_inventory_and_no_private_fields(self):
        # Exact projection checked against the five private, replay-verified
        # states by export_v2_observation; regeneration cannot rewrite history.
        self.assertEqual(hashlib.sha256(DATA.read_bytes()).hexdigest(),
                         '8a93831c7f00fba06c844a1653d0a5f3bc1c09ce61a844a6b877b49a8f0a9b17')
        self.assertEqual([len(t['messages']) for t in self.data['trials']], [33,31,23,28,48])
        self.assertEqual(sum(len(m['body']) for t in self.data['trials'] for m in t['messages']), 73341)
        quiet = [d for t in self.data['trials'] for d in t['decisions'] if not d['message_ids']]
        self.assertEqual(len(quiet), 14)
        for trial in self.data['trials']:
            self.assertEqual(len(trial['decisions']), 32)
        def inspect(value):
            if isinstance(value, dict):
                self.assertFalse({'private_note','notes','sdk_response','usage_metadata','candidates','api_key'} & value.keys())
                for v in value.values(): inspect(v)
            elif isinstance(value, list):
                for v in value: inspect(v)
        inspect(self.data)

    def test_all_163_bodies_survive_html_exactly(self):
        for trial in self.data['trials']:
            actual = []
            for turn in range(1,9):
                actual.extend(Messages(turn_markup(trial, turn)).bodies)
            self.assertEqual(actual, [m['body'] for m in trial['messages']])

    def test_markup_is_literal_in_agent_output(self):
        trial = deepcopy(self.data['trials'][0])
        trial['messages'][0]['body'] = '<script>throw Error("execution")</script> & <img src=x onerror=alert(1)>'
        html = turn_markup(trial, 1)
        self.assertNotIn('<script>', html)
        self.assertNotIn('<img', html)
        self.assertEqual(Messages(html).bodies[0], trial['messages'][0]['body'])

    def test_generated_page_and_earth_are_current(self):
        generated = build_html(self.source, self.data)
        self.assertEqual((DATA.parent / 'index.html').read_text(), generated)
        start = self.source.index('    <section class="earth-panel panel">')
        end = self.source.index('    </section>', start) + len('    </section>')
        # The one authorized metrics insertion is the only Earth-subtree delta.
        self.assertEqual(generated.count(EARTH_METRICS), 1)
        self.assertIn(self.source[start:end], generated.replace(EARTH_METRICS, '', 1))
        self.assertNotIn('1ターンにつき2,000t回復', generated)
        self.assertNotIn('復旧まで4ターン', generated)
        self.assertIn('AIによる観測解説（実験後に作成）', generated)
        self.assertIn('物理的な復旧量は未測定', generated)

    def test_export_rejects_changed_evidence_and_activity_claims(self):
        base = {'round':8,'initial':self.data['initial'],'messages':[],
                'history':{a:[{'round':t,'output':{'outgoing':[],'activities':[],
                    'private_note':'DO_NOT_PUBLISH'}} for t in range(1,9)]
                    for a in ('A','B','C','COORDINATOR')}}
        states = [deepcopy(base) for _ in range(5)]
        audit = {'status':'verified_without_model_calls','trials':[
            {'trial':n,'state_sha256':digest(s),'messages':0,'body_characters':0}
            for n,s in enumerate(states,1)]}
        exported = export_trials(states,audit)
        self.assertNotIn('DO_NOT_PUBLISH', json.dumps(exported))
        states[0]['history']['A'][0]['output']['activities'] = [{'body':'recovered'}]
        with self.assertRaisesRegex(ValueError,'state mismatch'):
            export_trials(states,audit)
        audit['trials'][0]['state_sha256'] = digest(states[0])
        with self.assertRaisesRegex(ValueError,'physical activity'):
            export_trials(states,audit)

    def test_next_turn_availability_and_initial_conditions(self):
        self.assertFalse(self.data['physical_execution'])
        self.assertEqual(self.data['initial']['indicator_status'], 'historical_initial_conditions_not_live_measurements')
        for trial in self.data['trials']:
            for m in trial['messages']:
                self.assertEqual(m['available_round'], m['sent_round'] + 1)
                self.assertNotIn(m['sender'], m['to'])


if __name__ == '__main__':
    unittest.main()
