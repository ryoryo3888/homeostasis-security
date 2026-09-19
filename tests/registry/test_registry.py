import copy,json,subprocess,sys,tempfile,unittest
from pathlib import Path
from tools.experiment_registry import ROOT,REGISTRY,ALLOWLIST,RegistryError,load_json,pointer,safe_path,validate_registry

class RegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.original=load_json(REGISTRY);cls.allowlist=load_json(ALLOWLIST)
    def setUp(self):self.registry=copy.deepcopy(self.original)
    def reject(self):
        with self.assertRaises(RegistryError):validate_registry(self.registry)
    def test_valid_registry(self):self.assertEqual(validate_registry(self.registry)['experiments'],3)
    def test_duplicate_id(self):self.registry['experiments'].append(copy.deepcopy(self.registry['experiments'][0]));self.reject()
    def test_missing_artifact(self):self.registry['experiments'][0]['source_artifacts'][0]['path']='results/missing.json';self.reject()
    def test_invalid_version(self):
        for value in ['v3','v0','V1',None]:
            self.registry['experiments'][0]['version']=value;self.reject()
    def test_invalid_type(self):self.registry['experiments'][0]['experiment_type']='made_up';self.reject()
    def test_supported_future_types(self):
        for value in ['baseline','replication','parameter_sweep','counterfactual','ablation','seed_replication','stress_test','comparative','exploratory','unknown']:
            self.registry['experiments'][0]['experiment_type']=value
            self.assertTrue(validate_registry(self.registry))
    def test_invalid_status(self):self.registry['experiments'][0]['status']='aborted';self.reject()
    def test_supported_statuses(self):
        for value in ['planned','running','completed','failed','invalidated','superseded']:
            self.registry['experiments'][0]['status']=value;self.registry['experiments'][0]['publication_status']='withheld';self.assertTrue(validate_registry(self.registry))
    def test_negative_counts(self):
        for field in ['run_count','worldline_count','turn_count']:
            for bad in [-1,True,1.5]:
                self.registry=copy.deepcopy(self.original);self.registry['experiments'][0][field]=bad;self.reject()
    def test_unsafe_paths(self):
        for path in ['../summary.json','/tmp/summary.json','https://example.org/result.json','results/../summary.json','results//x.json','.env','credentials.json','private/result.json','results/%2e%2e/key','results\\key.json']:
            self.registry=copy.deepcopy(self.original);self.registry['experiments'][0]['source_artifacts'][0]['path']=path;self.reject()
    def test_broken_parent(self):self.registry['experiments'][0]['parent_experiment']='missing';self.reject()
    def test_broken_control(self):self.registry['experiments'][0]['control_experiment']='missing';self.reject()
    def test_cross_version_reference(self):self.registry['experiments'][0]['parent_experiment']='v2-first-representative';self.reject()
    def test_provenance_cycle(self):
        a,b=self.registry['experiments'][:2];a['parent_experiment']=b['experiment_id'];b['parent_experiment']=a['experiment_id'];self.reject()
    def test_completed_without_source(self):self.registry['experiments'][0]['source_artifacts']=[];self.reject()
    def test_schema_mismatch(self):
        self.registry['schema_version']=2;self.reject();self.registry=copy.deepcopy(self.original);self.registry['experiments'][0]['schema_version']=2;self.reject()
    def test_broken_group(self):self.registry['experiments'][0]['comparison_group']='missing';self.reject()
    def test_valid_group_and_nonreciprocal_rejection(self):
        ids=[x['experiment_id'] for x in self.registry['experiments'][:2]]
        self.registry['comparison_groups']=[{'group_id':'example','members':ids,'question':'Fixture only'}]
        for e in self.registry['experiments'][:2]:e['comparison_group']='example'
        self.assertTrue(validate_registry(self.registry))
        self.registry['experiments'][0]['comparison_group']=None;self.reject()
    def test_group_missing_member(self):self.registry['comparison_groups']=[{'group_id':'example','members':['missing','also-missing'],'question':'Fixture only'}];self.reject()
    def test_bad_pointer(self):self.registry['experiments'][0]['conditions'][0]['pointer']='/not-here';self.reject()
    def test_unproven_counts(self):self.registry['experiments'][0]['run_count']=2;self.reject()
    def test_seed_invention(self):self.registry['experiments'][0]['runs'][0]['seed']=42;self.reject()
    def test_duplicate_worldline(self):self.registry['experiments'][0]['runs']*=2;self.reject()
    def test_secret_registry(self):self.registry['experiments'][0]['title']='AI'+'za'+'x'*35;self.reject()
    def test_hash_mismatch(self):
        catalog=copy.deepcopy(self.allowlist);catalog['artifacts'][0]['sha256']='0'*64
        with self.assertRaises(RegistryError):validate_registry(self.registry,allowlist=catalog)
    def test_probe_cannot_be_approved_as_research(self):
        catalog=copy.deepcopy(self.allowlist);catalog['artifacts'][0]['classification']='probe'
        with self.assertRaises(RegistryError):validate_registry(self.registry,allowlist=catalog)
    def test_failed_artifact_not_completed(self):
        catalog=copy.deepcopy(self.allowlist);catalog['artifacts'][0]['classification']='failed'
        with self.assertRaises(RegistryError):validate_registry(self.registry,allowlist=catalog)
    def test_untracked_and_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'result.json').write_text('{}')
            with self.assertRaises(RegistryError):safe_path(root,'result.json',set())
            (root/'link.json').symlink_to(root/'result.json')
            with self.assertRaises(RegistryError):safe_path(root,'link.json',{'link.json'})
    def test_duplicate_json_keys_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'x.json';p.write_text('{"schema_version":1,"schema_version":2}')
            with self.assertRaises(RegistryError):load_json(p)
    def test_no_automatic_publication(self):
        manifest=load_json(ROOT/'ui/content.json');self.assertEqual(manifest,{'schema_version':1,'v1':[],'v2':[]})
        for name in ['dashboard_v1.html','dashboard_v2.html','homeostasis-research-layer.js','homeostasis-research-integration.js','ui/content-slots.js','ui/layout-guard.js']:
            self.assertNotIn('research/experiments/',(ROOT/name).read_text())
        before=(ROOT/'ui/content.json').read_bytes();validate_registry(self.registry);self.assertEqual((ROOT/'ui/content.json').read_bytes(),before)
    def test_original_research_preserved_with_exact_backend_repair(self):
        base=load_json(ROOT/'research/experiments/inventory.json')['scope_commit']
        # The registry's source provenance and historical artifacts stay at base.
        # Only these exact repair bytes supersede the old ENGINE freeze. This is
        # not a general exception, and does not reattribute any historical run.
        repair='57127a5bb8c6a8c60f42a35b2f09f4fdb2a259ed'
        repaired={'final_experiment_runner.py','homeostasis_core/gemini_agents.py',
                  'homeostasis_core/resume_guard.py','homeostasis_core/execution_identity.py','homeostasis_core/execution_lock.py',
                  'response_receipts.py','provider_retry.py','provider_response.py'}
        v2_repair='614d77a37bcdc2a243edd80f23734df87c2f2e07'
        names=subprocess.check_output(['git','ls-tree','-r','--name-only',base],cwd=ROOT,text=True).splitlines()
        for name in sorted(set(names)|repaired):
            if name in repaired or name.endswith('.json') and not name.startswith(('tests/','docs/architecture/')) or name.startswith(('simulation','experiment_runner','final_experiment_runner','homeostasis_core/')):
                source=repair if name in repaired else base
                if name=='simulation_v2.py':source=v2_repair
                if name in ('simulation.py','experiment_runner.py'):source='614d77a37bcdc2a243edd80f23734df87c2f2e07'
                if name in ('simulation_final.py','homeostasis_core/gemini_agents.py'):source='d8bc495d61e95917d602e5a8b27ebd76fa121f72'
                if name=='homeostasis_core/gemini_agents.py':source='79f52bcd67ec1d038506258732b58ec761606b34'
                if name=='homeostasis_core/resume_guard.py':source='79f52bcd67ec1d038506258732b58ec761606b34'
                if name in ('final_experiment_runner.py','homeostasis_core/gemini_agents.py','response_receipts.py'):source='f2aa9fcce4cc90c6c5645480886a769b1ddedfcb'
                if name in ('homeostasis_core/gemini_agents.py','provider_retry.py','provider_response.py'):source='614d77a37bcdc2a243edd80f23734df87c2f2e07'
                if name=='response_receipts.py':source='35a6a17eae3897b3ab49a64face7c11ecb0dc437'
                if name in ('final_experiment_runner.py','homeostasis_core/experiments.py'):source='2c2df0f4cb7f967b258846ac44dc804a9b56db95'
                if name in ('final_experiment_runner.py','homeostasis_core/resume_guard.py','homeostasis_core/execution_identity.py'):source='16243bf2672139c770af01d2cafe65ee5c25d72a'
                if name in ('final_experiment_runner.py','homeostasis_core/execution_lock.py'):source='2d8aef00896c66ac650f228d9c1224c58a6154c5'
                self.assertEqual((ROOT/name).read_bytes(),subprocess.check_output(['git','show',source+':'+name],cwd=ROOT),name)
    def test_saved_comparison_membership(self):
        summary=load_json(ROOT/'summary.json');study=self.registry['experiments'][1]
        paths=[f for c in summary['conditions'] for f in c['files']]
        self.assertEqual(paths,[r['artifact']['path'] for r in study['runs']]);self.assertEqual(len(paths),sum(c['run_count'] for c in summary['conditions']))
        signatures=[json.dumps(load_json(ROOT/f)['results'],sort_keys=True) for f in paths]
        self.assertEqual(len(signatures),len(set(signatures)))
        for c in summary['conditions']:
            self.assertFalse(c['errors']);self.assertEqual(len(c['files']),c['run_count'])
    def test_cli_is_read_only_and_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'bad.json';p.write_text('{}')
            result=subprocess.run([sys.executable,'-B',str(ROOT/'tools/experiment_registry.py'),str(p)],capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0);self.assertNotIn('REGISTRY PASS',result.stdout)

    def test_counts_without_run_provenance_rejected(self):
        self.registry['experiments'][0]['runs']=[];self.reject()
    def test_unparseable_timestamp_rejected(self):
        self.registry['experiments'][2]['created_at']='not-a-date';self.reject()
