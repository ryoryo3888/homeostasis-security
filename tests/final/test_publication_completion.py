"""Publication integration against a local bare git remote: no model/network."""
import json
import subprocess
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from homeostasis_core.observability import source_digest, PublicationError
from tools import publish_status as pub

FIXTURE=Path(__file__).parents[1]/'fixtures/transport_failure.json'

class PublicationCompletionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name);self.root=self.base/'work';self.root.mkdir()
        self.run_git('init','-b','work')
        self.run_git('config','user.name','Offline Test');self.run_git('config','user.email','offline@example.invalid')
        self.save('.gitignore', 'results/debug/\nresults/rejected/*/\nresults/probe/*/\n')
        self.save('Makefile','# offline fixture\n');self.save('tests/fixtures/protected_artifacts.json',{})
        self.run_git('add','.');self.run_git('commit','-m','Initial offline fixture')
        subprocess.run(['git','init','--bare',str(self.base/'origin.git')],check=True,capture_output=True)
        self.run_git('remote','add','origin',str(self.base/'origin.git'))
        f=json.loads(FIXTURE.read_text());self.run_id=f['failed_run']
        prefix='results/rejected/'+self.run_id+'/'
        self.save(prefix+'failure.json',f['failure']);self.save(prefix+'transport.audit.json',f['transport'])
        self.save(prefix+'result.json.checkpoint',{'active_run':{'completed_turn':0,'turns':[],'call_audit':[f['failed_decision']]}})
        self.save('results/debug/check.json',{'status':'PASS','source_digest':source_digest(self.root)})

    def run_git(self,*args):
        return subprocess.check_output(['git',*args],cwd=self.root,stderr=subprocess.DEVNULL,text=True).strip()

    def save(self,path,value):
        p=self.root/path;p.parent.mkdir(parents=True,exist_ok=True)
        p.write_text(value if isinstance(value,str) else json.dumps(value,ensure_ascii=False),encoding='utf-8')

    def test_failed_run_committed_pushed_fetched_and_raw_excluded(self):
        original=(self.root/'results/rejected'/self.run_id/'result.json.checkpoint').read_bytes()
        receipt=pub.complete_publication(self.root,self.run_id)
        self.assertEqual(receipt['local_head'],receipt['remote_head'])
        self.assertEqual(receipt['local_head'],self.run_git('rev-parse','origin/work'))
        self.assertEqual(receipt['local_head'],self.run_git('ls-remote','origin','refs/heads/work').split()[0])
        self.assertNotIn('result.json.checkpoint',self.run_git('ls-tree','-r','--name-only','HEAD'))
        self.assertEqual(original,(self.root/'results/rejected'/self.run_id/'result.json.checkpoint').read_bytes())
        state=pub.gate(self.root);self.assertFalse(state['validation']['research_eligible'])

    def test_successful_mock_probe_published_without_another_model_call(self):
        from research_workflow import probe
        from tests.final.test_decision_audit import SelectionModels
        from homeostasis_core.api_budget import BoundedClient
        from final_experiment_runner import _checkpoint
        from homeostasis_core.research_validation import research_manifest
        run='20260918T000000Z-aaaaaaaa';p=self.root/'results/probe'/run;p.mkdir(parents=True)
        fake=SimpleNamespace(models=SelectionModels())
        bounded=BoundedClient(fake,1,p/'transport.audit.json')
        result=probe(bounded,audit_hook=lambda calls:_checkpoint(p/'decision.audit.json',{'run_id':run,'calls':calls}))
        self.save(str((p/'result.json').relative_to(self.root)),result)
        self.save(str((p/'result.audit.json').relative_to(self.root)),research_manifest(p/'result.json',['probe']))
        with patch.object(fake.models,'generate_content',side_effect=AssertionError('no re-execution')):
            receipt=pub.complete_publication(self.root,run)
        self.assertEqual(receipt['run_id'],run);self.assertEqual(pub.gate(self.root)['latest_run']['status'],'success')

    def test_main_refused_before_commit_or_push(self):
        self.run_git('branch','-m','main')
        with self.assertRaisesRegex(PublicationError,'MAIN'):pub.complete_publication(self.root)
        self.assertEqual(self.run_git('rev-list','--count','HEAD'),'1')

    def test_secret_blocks_publication(self):
        self.save('results/status/leak.json',{'password':'synthetic-do-not-publish'})
        with self.assertRaisesRegex(PublicationError,'SECRET'):pub.complete_publication(self.root)
        self.assertEqual(self.run_git('rev-list','--count','HEAD'),'1')

    def test_uncommitted_code_blocks_before_publication(self):
        self.save('unsafe.py','pass\n')
        with self.assertRaisesRegex(PublicationError,'COMMIT_IMPLEMENTATION'):pub.complete_publication(self.root)

    def test_expected_run_mismatch_is_not_success(self):
        with self.assertRaisesRegex(PublicationError,'EXPECTED_RUN'):pub.complete_publication(self.root,'missing-run')
        self.assertEqual(self.run_git('rev-list','--count','HEAD'),'1')

    def test_push_failure_and_sync_only_retry(self):
        real=pub.git
        def failing(root,*args):
            if args[0]=='push':raise PublicationError('GIT_PUSH_FAILED')
            return real(root,*args)
        with patch.object(pub,'git',side_effect=failing):
            with self.assertRaisesRegex(PublicationError,'PUSH_FAILED'):pub.complete_publication(self.root)
        receipt=json.loads((self.root/'results/debug/publication-receipt.json').read_text())
        self.assertEqual(receipt['status'],'FAIL')
        with patch('research_workflow.probe',side_effect=AssertionError('experiment rerun')):
            receipt=pub.complete_publication(self.root)
        self.assertEqual(receipt['status'],'PASS')

    def test_remote_mismatch_cannot_report_ready(self):
        real=pub.git
        def mismatch(root,*args):
            if args[0]=='ls-remote':return '0'*40+' refs/heads/work'
            return real(root,*args)
        with patch.object(pub,'git',side_effect=mismatch):
            with self.assertRaisesRegex(PublicationError,'REMOTE_HEAD'):pub.complete_publication(self.root)
        self.assertEqual(json.loads((self.root/'results/debug/publication-receipt.json').read_text())['status'],'FAIL')

    def test_branch_switch_cannot_publish_to_a_different_branch(self):
        with self.assertRaisesRegex(PublicationError,'BRANCH_CHANGED'):
            pub.complete_publication(self.root,expected_branch='different-branch')
        self.assertEqual(self.run_git('rev-list','--count','HEAD'),'1')
