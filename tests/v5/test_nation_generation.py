"""Transport and evidence checks with synthetic fixtures, never live model calls."""
import base64
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import httpx
from homeostasis_v4.evidence import read_record,verify
from homeostasis_v5 import nation_generation as run
from test_nation_generation_contract import catalog,geography,nation
from test_nation_topology import from_map_fixture


class NationGenerationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/'batch'
        self.patch=patch.object(run,'source_hashes',return_value={'synthetic.py':'a'*64})
        self.patch.start();self.addCleanup(self.patch.stop)
        self.leaders=[{'leader_id':f'leader-{i:03d}','freeze_sha256':'a'*64} for i in range(1,13)]
        run.prepare(self.root,catalog=catalog(),leader_references=self.leaders,reference_archive={'synthetic':True})
        self.requests=[]

    def transport(self,*,count=100,mode='success'):
        def handle(request):
            self.requests.append(request)
            body=json.loads(request.content)
            if request.url.path.endswith(':countTokens'):
                return httpx.Response(200,json={'totalTokens':count})
            if mode=='timeout':raise httpx.ReadTimeout('DO_NOT_SERIALIZE_SECRET',request=request)
            if mode=='http':return httpx.Response(400,json={'error':{'code':400,'message':'synthetic schema error'}})
            context=json.loads(body['contents'][0]['parts'][1]['text'])
            m=geography();m['world_id']=context['world_id']
            text=json.dumps(from_map_fixture(m)) if mode!='invalid_json' else '{bad'
            if mode=='incomplete':reason='MAX_TOKENS'
            else:reason='STOP'
            return httpx.Response(200,json={'candidates':[{'finishReason':reason,'content':{'parts':[{'text':text}]}}],
                'usageMetadata':{'promptTokenCount':100,'candidatesTokenCount':200,'thoughtsTokenCount':50,'totalTokenCount':350},
                'modelVersion':run.MODEL,'responseId':'synthetic-response'})
        return httpx.MockTransport(handle)

    def invoke(self,**kwargs):
        return run.generate_next(self.root,credential='SYNTHETIC_SECRET',transport=self.transport(**kwargs))

    def test_provider_constant_is_equivalent_singleton_enum(self):
        schema={"type":"object","properties":{"coordinate_system":{"const":"planar_cartesian_km"}}}
        converted=run.provider_schema(schema)
        self.assertEqual(converted["properties"]["coordinate_system"],{"type":"string","enum":["planar_cartesian_km"]})
        self.assertEqual(schema["properties"]["coordinate_system"],{"const":"planar_cartesian_km"})

    def test_count_matches_wire_generation_and_review_blocks_successor(self):
        result=self.invoke();self.assertEqual(result['status'],'success')
        self.assertTrue(result['content_review_required'])
        counted=json.loads(self.requests[0].content)['generateContentRequest']
        model=counted.pop('model');self.assertEqual(model,'models/'+run.MODEL)
        self.assertEqual(run.wire_bytes(counted),self.requests[1].content)
        saved=read_record(self.root/'attempt-01/RAW/generation.wire.json')
        self.assertEqual(base64.b64decode(saved['body_base64']),self.requests[1].content)
        alltext=''.join(p.read_text() for p in self.root.rglob('*.json'))
        self.assertNotIn('SYNTHETIC_SECRET',alltext)
        with self.assertRaisesRegex(run.GenerationError,'CONTENT_REVIEW_REQUIRED'):self.invoke()
        self.assertEqual(len(self.requests),2)
        self.assertEqual(verify(self.root/'attempt-01')['status'],'success')

    def test_map_raw_is_distinct_from_canonical_and_required_for_country_input(self):
        result=self.invoke();self.assertEqual(result['status'],'success')
        root=self.root/'attempt-01'
        original=run._output(root)
        self.assertIn('vertices',original)
        derived=read_record(root/'DERIVED/canonical-map.json')['report']
        self.assertNotIn('vertices',derived['map'])
        plan=read_record(self.root/'plan.json')
        self.assertEqual(run._map_output(root,plan),derived['map'])
        package=run._package(self.root,plan,2)
        self.assertIn(derived['map_sha256'],json.dumps(package))
        raw_before=(root/'RAW/generation.response.json').read_bytes()
        altered={**derived,'map_sha256':'0'*64}
        with patch.object(run,'read_record',side_effect=lambda p: {'report':altered} if str(p).endswith('canonical-map.json') else read_record(p)):
            with self.assertRaisesRegex(run.GenerationError,'CANONICAL_MAP_CHANGED'):
                run._map_output(root,plan)
        self.assertEqual(raw_before,(root/'RAW/generation.response.json').read_bytes())

    def test_nation_wire_supplies_and_pins_the_expected_reference_hash(self):
        self.invoke()
        plan=read_record(self.root/'plan.json')
        package=run._package(self.root,plan,2)
        original=run.record_hash(package)
        body=run.http_body(package)
        context=json.loads(body['contents'][0]['parts'][1]['text'])
        self.assertEqual(context['input_references'],package['input_references'])
        actual=context['input_references']['map_sha256']
        self.assertEqual(body['generationConfig']['responseJsonSchema']['properties']['geography_ref']['properties']['map_sha256']['enum'],[actual])
        self.assertEqual(run.record_hash(package),original)
        self.assertEqual(actual,run.record_hash(context['common_geography']))
        self.assertNotIn('leader_references',context)
        self.assertNotIn('predecessor',context)

    def test_predecessor_reservation_and_assignment_are_retained(self):
        prior={'reserved_usd':'0.05508','assignment':{'method':'fixed synthetic','seed_hex':'ab'*32}}
        self.root=Path(self.tmp.name)/'batch-with-predecessor'
        with patch.object(run,'_predecessor',return_value=prior),patch.object(run.secrets,'token_hex',side_effect=AssertionError('must not redraw')):
            run.prepare(self.root,catalog=catalog(),leader_references=self.leaders,reference_archive={},predecessor='synthetic')
        plan=read_record(self.root/'plan.json')
        self.assertEqual(plan['assignment'],prior['assignment'])
        self.assertEqual(plan['predecessor']['reserved_usd'],'0.05508')
        too_large={**prior,'reserved_usd':'0.20'}
        with patch.object(run,'_predecessor',return_value=too_large):
            with self.assertRaisesRegex(run.GenerationError,'BUDGET_NOT_SUFFICIENT'):
                run.prepare(Path(self.tmp.name)/'over',catalog=catalog(),leader_references=self.leaders,reference_archive={},predecessor='synthetic')


    def continuation(self):
        self.invoke()
        run.review_last(self.root,accepted=True,review_notes=['Synthetic fixture only'])
        old=self.root
        plan=read_record(old/'plan.json')
        v=verify(old/'attempt-01')
        source={'directory':str(old),'world_id':plan['world_id'],'map_evidence_hash':v['evidence_hash'],
                'assignment':plan['assignment'],'leader_references':plan['leader_references'],
                'catalog_sha256':plan['catalog_sha256'],'charged_usd':'0.057411',
                'ledger':[{'basis':'synthetic-only'}]}
        imported=patch.object(run,'_frozen_source',return_value=source)
        imported.start();self.addCleanup(imported.stop)
        self.root=Path(self.tmp.name)/'continuation'
        run.prepare_continuation(self.root,frozen_source=old)
        return old,source

    def nation_transport(self,*,wrong_reference=False):
        def handle(request):
            self.requests.append(request)
            body=json.loads(request.content)
            if request.url.path.endswith(':countTokens'):
                return httpx.Response(200,json={'totalTokens':100})
            context=json.loads(body['contents'][0]['parts'][1]['text'])
            record=nation()
            record['world_id']=context['common_geography']['world_id']
            record['nation_id']=context['own_nation_id']
            slot=next(s for s in context['common_geography']['nation_slots'] if s['nation_id']==record['nation_id'])
            record['geography_ref']={'map_sha256':'0'*64 if wrong_reference else context['input_references']['map_sha256'],
                                     'territory_region_ids':slot['territory_region_ids']}
            return httpx.Response(200,json={'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':json.dumps(record)}]}}],
                'usageMetadata':{'promptTokenCount':100,'candidatesTokenCount':200,'totalTokenCount':300}})
        return httpx.MockTransport(handle)

    def test_continuation_uses_only_frozen_map_and_twelve_nation_calls(self):
        old,source=self.continuation()
        raw_before={str(p):p.read_bytes() for p in old.rglob('*') if p.is_file()}
        self.requests=[]
        plan=read_record(self.root/'plan.json')
        self.assertEqual(plan['assignment'],read_record(old/'plan.json')['assignment'])
        self.assertEqual(plan['maximum_reserved_usd'],'1.31328')
        for i in range(2,14):
            result=run.generate_next(self.root,credential='SYNTHETIC_SECRET',transport=self.nation_transport())
            self.assertEqual((result['status'],result['stage'],result['index']),('success','nation',i))
            manifest=read_record(self.root/f'attempt-{i:02d}/manifest.json')
            self.assertEqual(manifest['provenance']['parent_evidence_hash'],source['map_evidence_hash'])
            self.assertEqual(json.loads(self.requests[-2].content)['generateContentRequest']['contents'],
                             json.loads(self.requests[-1].content)['contents'])
            context=json.loads(json.loads(self.requests[-1].content)['contents'][0]['parts'][1]['text'])
            self.assertNotIn('leader_references',context)
            self.assertNotIn('previous_nations',context)
            run.review_last(self.root,accepted=True,review_notes=['Synthetic fixture only'])
        self.assertEqual(len(self.requests),24)
        self.assertFalse((self.root/'attempt-01').exists())
        assignment=read_record(self.root/'assignment.json')
        self.assertEqual(len(assignment['pairs']),12)
        self.assertEqual({p['nation_id'] for p in assignment['pairs']},set(run.IDS))
        with self.assertRaisesRegex(run.GenerationError,'BATCH_COMPLETE'):
            run.generate_next(self.root,credential='SYNTHETIC_SECRET',transport=self.nation_transport())
        self.assertEqual(len(self.requests),24)
        self.assertEqual(raw_before,{str(p):p.read_bytes() for p in old.rglob('*') if p.is_file()})

    def test_continuation_failure_never_retries_or_changes_frozen_map(self):
        old,_=self.continuation();self.requests=[]
        old_hash=verify(old/'attempt-01')['evidence_hash']
        result=run.generate_next(self.root,credential='SYNTHETIC_SECRET',transport=self.nation_transport(wrong_reference=True))
        self.assertEqual(result['error']['code'],'MAP_REFERENCE_MISMATCH')
        self.assertEqual(result['index'],2)
        with self.assertRaisesRegex(run.GenerationError,'BATCH_BLOCKED'):
            run.generate_next(self.root,credential='SYNTHETIC_SECRET',transport=self.nation_transport())
        self.assertEqual(len(self.requests),2)
        self.assertEqual(verify(old/'attempt-01')['evidence_hash'],old_hash)

    def test_continuation_cost_ceiling_includes_settled_prior_usage(self):
        old,source=self.continuation()
        with patch.object(run,'_frozen_source',return_value={**source,'charged_usd':'0.20'}):
            with self.assertRaisesRegex(run.GenerationError,'BUDGET_NOT_SUFFICIENT'):
                run.prepare_continuation(Path(self.tmp.name)/'too-expensive',frozen_source=old)

    def test_continuation_pin_change_blocks_before_transport(self):
        _,source=self.continuation();self.requests=[]
        with patch.object(run,'_frozen_source',return_value={**source,'map_evidence_hash':'0'*64}):
            with self.assertRaisesRegex(run.GenerationError,'FROZEN_SOURCE_CHANGED'):
                run.generate_next(self.root,credential='SYNTHETIC_SECRET',transport=self.nation_transport())
        self.assertEqual(self.requests,[])

    def test_input_over_limit_never_generates_or_retries(self):
        result=self.invoke(count=12001);self.assertEqual(result['status'],'failure')
        self.assertFalse(result['error']['generation_attempted']);self.assertEqual(len(self.requests),1)
        self.assertFalse(list(self.root.glob('reservation-*.json')))
        with self.assertRaisesRegex(run.GenerationError,'BATCH_BLOCKED'):self.invoke()
        self.assertEqual(len(self.requests),1)

    def test_http_failure_preserves_response_and_reservation(self):
        result=self.invoke(mode='http');self.assertEqual(result['error']['code'],'GENERATION_HTTP_ERROR')
        raw=read_record(self.root/'attempt-01/RAW/generation.response.json')
        self.assertEqual(raw['status'],400)
        self.assertIn(b'synthetic schema error',base64.b64decode(raw['body_base64']))
        self.assertTrue((self.root/'reservation-01.json').exists())
        with self.assertRaisesRegex(run.GenerationError,'BATCH_BLOCKED'):self.invoke()
        self.assertEqual(len(self.requests),2)

    def test_timeout_records_type_not_exception_secret_and_keeps_reservation(self):
        result=self.invoke(mode='timeout');self.assertEqual(result['error']['code'],'TRANSPORT_TIMEOUT')
        self.assertEqual(result['error']['exception_type'],'ReadTimeout')
        self.assertTrue((self.root/'reservation-01.json').exists())
        self.assertNotIn('DO_NOT_SERIALIZE_SECRET',''.join(p.read_text() for p in self.root.rglob('*.json')))
        self.assertEqual(verify(self.root/'attempt-01')['status'],'failure')

    def test_invalid_or_incomplete_output_preserves_received_bytes(self):
        for mode in ('invalid_json','incomplete'):
            if mode=='incomplete':
                self.root=Path(self.tmp.name)/'batch2'
                run.prepare(self.root,catalog=catalog(),leader_references=self.leaders,reference_archive={})
            result=self.invoke(mode=mode)
            self.assertEqual(result['status'],'failure')
            self.assertTrue((self.root/'attempt-01/RAW/generation.response.json').exists())
            self.assertTrue((self.root/'attempt-01/RAW/receipt.json').exists())

    def test_save_failure_sends_nothing(self):
        with patch.object(run.EvidenceRun,'write',side_effect=OSError('synthetic full disk')):
            with self.assertRaises(OSError):self.invoke()
        self.assertEqual(self.requests,[])
        self.assertEqual(verify(self.root/'attempt-01')['status'],'unfinalized')
        with self.assertRaisesRegex(run.GenerationError,'PRIOR_ATTEMPT_NOT_SUCCESSFUL'):self.invoke()

    def test_fourteenth_call_is_refused(self):
        with patch.object(run,'_history',return_value=[{}]*13):
            with self.assertRaisesRegex(run.GenerationError,'BATCH_COMPLETE'):self.invoke()
        self.assertEqual(self.requests,[])

    def test_reservation_ceiling_has_no_cli_override(self):
        plan=read_record(self.root/'plan.json')
        self.assertEqual(plan['maximum_reserved_usd'],'1.36836')
        self.assertEqual(plan['usd_stop_limit'],'1.50')
        self.assertEqual(plan['max_generation_calls'],13)
        self.assertEqual(plan['max_count_calls'],13)

    def test_assignment_reproducible_and_all_twelve_used_once(self):
        ids=[r['leader_id'] for r in self.leaders]
        first=run.permutation('ab'*32,ids)
        self.assertEqual(first,run.permutation('ab'*32,ids))
        self.assertEqual(set(first),set(ids));self.assertEqual(ids,[r['leader_id'] for r in self.leaders])


if __name__=='__main__':unittest.main()
