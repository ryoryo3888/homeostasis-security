"""Offline boundary tests. Private originals never become public fixtures."""
import ast
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

from prompt_interface import private_text, private_function, private_file
from prompt_interface.audit import public_audit, public_result, require_private_path

ROOT = Path(__file__).resolve().parents[2]
BASE = Path(os.environ['HOMEOSTASIS_PRIVATE_FILES'])
BUNDLE = json.loads(Path(os.environ['HOMEOSTASIS_PRIVATE_CONFIG']).read_text())

class Restore(ast.NodeTransformer):
    def visit_ImportFrom(self, n):
        if n.module and n.module.startswith('prompt_interface'): return None
        return n
    def visit_Call(self,n):
        if isinstance(n.func,ast.Name) and n.func.id=='private_text':
            return ast.copy_location(ast.Constant(BUNDLE['texts'][n.args[0].value]['text']),n)
        if isinstance(n.func,ast.Name) and n.func.id=='private_value':
            return ast.copy_location(ast.Constant(BUNDLE['values'][n.args[0].value]['value']),n)
        return self.generic_visit(n)
    def visit_JoinedStr(self,n):
        n=self.generic_visit(n);values=[]
        for v in n.values:
            if isinstance(v,ast.FormattedValue) and isinstance(v.value,ast.Constant) and v.conversion==-1 and v.format_spec is None:v=v.value
            if values and isinstance(v,ast.Constant) and isinstance(values[-1],ast.Constant):values[-1].value+=v.value
            else:values.append(v)
        n.values=values;return n

class BoundaryTests(unittest.TestCase):
    def setUp(self):
        self.net=patch.object(socket.socket,'connect',side_effect=AssertionError('NETWORK_FORBIDDEN'));self.net.start()
    def tearDown(self):self.net.stop()
    def test_all_extracted_literals_exact(self):
        for key,item in BUNDLE['texts'].items():
            self.assertEqual(private_text(key),item['text'])
            self.assertEqual(hashlib.sha256(private_text(key).encode()).hexdigest(),item['sha256'])
    def test_agent_payload_builders_ast_identical(self):
        targets={'simulation.py':['call_agent','call_evaluator'],
                 'simulation_v2.py':['call_coordinator','call_country','call_evaluator'],
                 'homeostasis_core/gemini_agents.py':['run_gemini_turn','build_private_views','apply_structured_actions','ordered_feasible_actions','ordered_response_options'],
                 'homeostasis_v5/life_first_contract.py':[],
                 'homeostasis_v5/nation_generation_contract.py':[],
                 'homeostasis_v5/nation_topology.py':[]}
        compared=0
        for file,names in targets.items():
            old=ast.parse((BASE/file).read_text());new=Restore().visit(ast.parse((ROOT/file).read_text()))
            for a in old.body:
                if isinstance(a,ast.FunctionDef) and (not names or a.name in names):
                    b=next(n for n in new.body if isinstance(n,ast.FunctionDef) and n.name==a.name)
                    self.assertEqual(ast.dump(a),ast.dump(b),file+':'+a.name);compared+=1
        self.assertGreater(compared,10)
    def test_exact_private_decision_function(self):
        tree=ast.parse((BASE/'homeostasis_core/gemini_agents.py').read_text())
        node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='decision_factors')
        source=ast.get_source_segment((BASE/'homeostasis_core/gemini_agents.py').read_text(),node)+'\n'
        self.assertEqual(source,(Path(os.environ['HOMEOSTASIS_PRIVATE_CONFIG']).parent/'decision_factors.py').read_text())
        ns={};exec(compile(ast.Module(body=[node],type_ignores=[]),'original-decision-helper','exec'),ns)
        for resources in ({},{'food':12,'water':31}):
            args=({'own_state':{'resources':resources},'observed_world':{'conflict_load':37}}, {'predicted_global_effect':20,'predicted_sovereignty_burden':3},[{'event':'確認'}])
            self.assertEqual(ns['decision_factors'](*args),private_function('decision_factors',*args))
    def test_mock_provider_contents_and_config_exact(self):
        from homeostasis_core import gemini_agents as new
        spec=importlib.util.spec_from_file_location('homeostasis_core._private_original',BASE/'homeostasis_core/gemini_agents.py')
        old=importlib.util.module_from_spec(spec)
        import sys
        sys.modules[spec.name]=old;spec.loader.exec_module(old)
        from google.genai import types
        def Response():
            return types.GenerateContentResponse(candidates=[types.Candidate(content=types.Content(parts=[types.Part(text='{"result":"固定応答"}')]),finish_reason='STOP')])
        class Models:
            def __init__(self):self.sent=[]
            def generate_content(self,**kwargs):self.sent.append(kwargs);return Response()
        class Client:
            def __init__(self):self.models=Models()
        payload={'role':'TEST_PRIVATE_SENTINEL','turn_start_observation':{'text':'改行\n空白  Ω','number':1.0},'memory':[]}
        with tempfile.TemporaryDirectory() as temp,patch.dict(os.environ,{'HOMEOSTASIS_PRIVATE_RUNS':temp}):
            a,b=Client(),Client();x,y=old.GeminiGateway(a),new.GeminiGateway(b)
            self.assertEqual(x.call('A',1,2,payload,json.loads,json_schema={'type':'object'}),y.call('A',1,2,payload,json.loads,json_schema={'type':'object'}))
            self.assertEqual(a.models.sent,b.models.sent)
            self.assertNotIn('TEST_PRIVATE_SENTINEL',json.dumps(y.public_calls()))
            self.assertIn('TEST_PRIVATE_SENTINEL',''.join(p.read_text() for p in Path(temp).rglob('*.json')))
    def test_mock_country_payloads_exact_no_world_execution(self):
        from homeostasis_core import gemini_agents as new
        import sys
        if 'homeostasis_core._private_original' not in sys.modules:
            spec=importlib.util.spec_from_file_location('homeostasis_core._private_original',BASE/'homeostasis_core/gemini_agents.py');mod=importlib.util.module_from_spec(spec);sys.modules[spec.name]=mod;spec.loader.exec_module(mod)
        old=sys.modules['homeostasis_core._private_original']
        class Capture:
            def __init__(self):self.calls=[]
            def call(self,*args,**kwargs):
                # Only capture assembly. No provider, world settlement, or new decision.
                self.calls.append((args[0:4],kwargs.get('json_schema')))
                return {'proposal_id':'fixture','predicted_global_effect':1,'predicted_sovereignty_burden':2} if kwargs['agent_type']=='coordinator' else {'response_id':'REJECT'}
        a,b=Capture(),Capture();args=(1,1,{'world':{'food':70},'decision_seed':17},{'A':{'own_country':'A','observed_world':{'food':70}}},{'A':()},('A',))
        self.assertEqual(old.run_gemini_turn(a,*args),new.run_gemini_turn(b,*args))
        self.assertEqual(json.dumps(a.calls,ensure_ascii=False),json.dumps(b.calls,ensure_ascii=False))
    def test_public_audit_allowlist(self):
        record={'public_observation_payload':{'role':'SECRET','observation':{'private_note':'SECRET'}},'sdk_response':'SECRET','private_note':'SECRET','attempt':2,'response_status':'validated'}
        value=public_audit(record);self.assertNotIn('SECRET',json.dumps(value));self.assertEqual(value['retry_count'],1);self.assertTrue(value['validation_success'])
    def test_no_public_raw_destinations(self):
        with self.assertRaises(ValueError):require_private_path(ROOT/'results/new-run')
        self.assertEqual(require_private_path(ROOT/'private_runs/test'),ROOT/'private_runs/test')
    def test_missing_config_fails_closed(self):
        with patch.dict(os.environ,{},clear=True),self.assertRaises(RuntimeError):private_text('unknown')
    def test_historical_projection_only_changes_audit(self):
        manifest=json.loads((BASE.parent/'separation-manifest.json').read_text())
        for name in manifest['projected_results']:
            old=json.loads((BASE/name).read_text());new=json.loads((ROOT/name).read_text())
            self.assertEqual(new,public_result(old))
    def test_moved_records_retained_byte_exact(self):
        manifest=json.loads((BASE.parent/'separation-manifest.json').read_text());hashes=json.loads((BASE.parent/'baseline-sha256.json').read_text())
        for name in manifest['moved']:
            self.assertFalse((ROOT/name).exists())
            self.assertEqual(hashlib.sha256((BASE/name).read_bytes()).hexdigest(),hashes[name])
    def test_ui_structure_and_assets_unchanged(self):
        import re
        hashes=json.loads((BASE.parent/'baseline-sha256.json').read_text())
        for name,h in hashes.items():
            if Path(name).suffix in ('.html','.css','.js','.png','.jpg','.svg','.pdf','.pptx'):
                if name=='results/evidence/index.html':
                    a=(BASE/name).read_text();b=(ROOT/name).read_text()
                    # Only the 17 user-approved evidence explanations may change.
                    approved_wording = [
                        (87, '保存済み実験の生ログと検証資料', '保存済み実験の監査情報と検証資料'),
                        (117, '入口では人間向けに全体像を示し、奥では保存されたファイルへ直接到達できるようにしています。RAWの内容、DERIVEDの計算結果、出典情報を同じものとして扱いません。', '入口では全体像を示し、公開可能な監査情報と検証資料へ接続します。完全RAWは非公開で保全し、公開資料とは区別します。'),
                        (119, 'RAW / OBSERVED', 'AUDIT / METADATA'),
                        (119, '生の実験記録', '原本の監査情報'),
                        (119, 'AI Agentへの入力、応答、世界状態、ターン、checkpoint、journalなど、加工前の保存済み実験記録です。', '非公開で保全した実験原本のSHA-256と、確認可能な研究メタデータです。入力全文・完全RAWは含みません。'),
                        (119, '全RAWのinventoryを見る', '公開監査用inventoryを見る'),
                        (123, 'このHTMLはEvidenceへ入るための表示だけを担当します。RAW / JSON / JSONL / inventory / hashは、保存されたまま直接確認できます。', 'このHTMLは公開Evidenceへの入口です。監査メタデータ・inventory・hashを確認できます。完全RAWは非公開で保全しています。'),
                        (137, '研究結果からRAWまで', '研究結果から原本の指紋まで'),
                        (140, '全ファイルの公開パス、由来、SHA-256、公開コピーとの一致状況は', '以前の公開パス、由来、SHA-256、当時のコピー照合記録は'),
                        (140, 'で追跡できます。', 'で確認できます。現在のRAW公開を意味しません。'),
                        (145, '各入口は、現在保存構造に存在する代表的なRAWファイルへつながっています。全ファイルはinventoryから確認できます。', '各入口は、非公開原本から生成した公開監査情報へつながっています。原本一覧はinventoryから確認できます。'),
                        (157, '以下は保存済みのinventoryとscan結果から確認できる事実です。入口UIの追加によって、Evidence本体は変更していません。', '以下は公開可能な監査inventoryと、過去のscan結果の記録です。現在の公開範囲を表すものではありません。原本は非公開で保全しています。'),
                        (161, 'byte完全一致ファイル', '当時のbyte一致ファイル'),
                        (162, '公開コピーのsecret検出', '当時のsecret検出'),
                        (163, '公開コピーのprivacy残存finding', '当時のprivacy検出'),
                        (165, '公開前確認済み：', '過去の公開前確認記録：'),
                        (182, '加工前の生の実験記録。観測された入力・応答・状態です。', '完全な入力・内部指示・RAWは非公開で保全し、公開側には検証用指紋と監査メタデータのみを表示します。'),
                    ]
                    lines = a.splitlines(keepends=True)
                    for line, before, after in approved_wording:
                        self.assertEqual(lines[line - 1].count(before), 1, before)
                        lines[line - 1] = lines[line - 1].replace(before, after, 1)
                    a = "".join(lines)
                    strip=lambda s:re.sub(r'<a\b[^>]*>.*?</a>','<a/>',s,flags=re.S)
                    self.assertEqual(strip(a),strip(b))
                    continue
                self.assertEqual(hashlib.sha256((ROOT/name).read_bytes()).hexdigest(),h,name)

    def test_v2_prompt_contents_exact(self):
        from types import SimpleNamespace
        import sys
        def load(name, path):
            spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m
        old=load('_private_simulation_v2',BASE/'simulation_v2.py');new=load('_public_simulation_v2',ROOT/'simulation_v2.py')
        outputs=[]
        for module in (old,new):
            seen=[]
            module.call_json=lambda client,prompt: seen.append(prompt) or '{}'
            module.parse_coordinator_response=lambda text: {}
            module.parse_country_response=lambda text,code: {}
            module.parse_evaluator_response=lambda text: {}
            actor=SimpleNamespace(code='A',private_context=lambda:'SENTINEL 私的情報\nΩ')
            module.call_coordinator(None,{'event':'観測'})
            module.call_country(None,actor,{'event':'観測'},'固定した提案')
            module.call_evaluator(None,{'event':'観測'},{'proposal':'固定'}, {'A':{'action':'固定','proposal_response':'固定'}}, 10)
            outputs.append([x.encode('utf-8') for x in seen])
        self.assertEqual(*outputs)
    def test_private_file_prompts_exact(self):
        for name in ('LEADER_GENERATION_PROMPT.txt','IDENTITY_ADDENDUM_PROMPT.txt'):
            rel='docs/design/v5/'+name
            self.assertEqual(private_file(rel).read_bytes(),(BASE/rel).read_bytes())
    def test_guard_detects_private_publication(self):
        from tools.check_public_boundary import check
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'leak.json').write_text(json.dumps({'contents':[{'text':'PRIVATE'}]}))
            self.assertTrue(check(root,['leak.json']))
    def test_config_changes_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'config.json';path.write_text(json.dumps({'format':'homeostasis-private-text-v1','version':'test','texts':{'x':{'text':'x','sha256':hashlib.sha256(b'x').hexdigest()}}}))
            with patch.dict(os.environ,{'HOMEOSTASIS_PRIVATE_CONFIG':str(path)}):
                self.assertEqual(private_text('x'),'x')
                path.write_text(path.read_text()+' ')
                with self.assertRaises(RuntimeError):private_text('x')

    def test_all_extracted_definitions_restore_exactly(self):
        private = BASE.parent
        files = set(json.loads((private/'extracted-files.json').read_text()) + json.loads((private/'context-extracted-files.json').read_text()))
        allowed = {
            ('homeostasis_core/gemini_agents.py','GeminiGateway'),
            ('homeostasis_core/gemini_agents.py','decision_factors'),
            ('homeostasis_v3/gemini_preflight.py','AttemptJournal'),
            ('homeostasis_v5/identity_addendum.py','source_hashes'),
            ('homeostasis_v5/identity_addendum.py','build_request'),
            ('homeostasis_v5/persona_generation.py','source_hashes'),
            ('homeostasis_v5/persona_generation.py','build_request'),
            ('v2_autonomous.py','Journal'),
        }
        for name in files:
            old=ast.parse((BASE/name).read_text())
            new=Restore().visit(ast.parse((ROOT/name).read_text()))
            for node in old.body:
                if not isinstance(node,(ast.FunctionDef,ast.ClassDef)) or (name,node.name) in allowed:continue
                match=next(x for x in new.body if type(x)==type(node) and x.name==node.name)
                self.assertEqual(ast.dump(node),ast.dump(match),name+':'+node.name)

    def test_private_config_files_equal_original(self):
        from prompt_interface import configuration_path
        for name in ('country_archetypes.json','country_types.json','information_policies.json'):
            self.assertEqual(configuration_path(ROOT/'config'/name).read_bytes(),(BASE/'config'/name).read_bytes())

    def test_v5_request_assembly_equal(self):
        import sys
        from homeostasis_v5 import persona_generation, identity_addendum
        for new,rel,args in ((persona_generation,'homeostasis_v5/persona_generation.py',()),
                             (identity_addendum,'homeostasis_v5/identity_addendum.py',({'fixture':'saved identity'},))):
            name='homeostasis_v5._baseline_'+Path(rel).stem
            spec=importlib.util.spec_from_file_location(name,BASE/rel)
            old=importlib.util.module_from_spec(spec);sys.modules[name]=old;spec.loader.exec_module(old)
            # Only assemble requests against preserved files, no API/provider.
            self.assertEqual(old.build_request(*args),new.build_request(*args))

if __name__=='__main__':unittest.main()
