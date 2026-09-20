import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from tools.check_content import validate_manifest,SLOTS
from tools.secret_scan import has_secret,scan
from tools.visual_baseline import protected_bytes,LOADER
ROOT=Path(__file__).resolve().parents[2]

class LayoutSourceTests(unittest.TestCase):
    def test_approved_public_source_is_frozen(self):
        manifest=json.loads((ROOT/'tests/layout/source_baseline.json').read_text())
        for name,digest in manifest['assets'].items():
            data=(ROOT/name).read_bytes()
            if name.endswith('.html'):
                self.assertEqual(data.count(LOADER.encode()),1,name)
            data=protected_bytes(ROOT/name)
            self.assertEqual(hashlib.sha256(data).hexdigest(),digest,name)
    def test_generated_previews_equal_dashboards(self):
        for version in ['v1','v2']:
            self.assertEqual((ROOT/f'dashboard_{version}.html').read_bytes(),(ROOT/f'preview_{version}_unified.html').read_bytes())
    def test_baseline_provenance_and_viewports(self):
        spec=json.loads((ROOT/'tests/layout/layout_contract.json').read_text());snapshot=json.loads((ROOT/'tests/layout/public-baseline.json').read_text())
        self.assertEqual(spec['baseline_sha'],snapshot['baseline_sha'])
        self.assertEqual(len(snapshot['records']),12)
        self.assertEqual({v['name'] for v in spec['viewports']},{'desktop','ipad'})
        self.assertEqual({x['state'] for x in snapshot['records']},{1,3,5,8})
    def test_new_runtime_relocation_cannot_hide_in_legacy_source(self):
        source=(ROOT/'dashboard_v2.html').read_bytes()
        original=source.replace(LOADER.encode(),b'',1)
        changed=original.replace(b'</body>',b'<script>document.body.append(document.querySelector(".earth-panel"))</script></body>')
        self.assertNotEqual(hashlib.sha256(original).digest(),hashlib.sha256(changed).digest())
    def test_protection_loader_precedes_legacy_scripts(self):
        for version in ['v1','v2']:
            source=(ROOT/f'dashboard_{version}.html').read_text()
            self.assertLess(source.index(LOADER),source.index('<script>'))
    def test_declarative_manifest_is_valid(self):
        manifest=json.loads((ROOT/'ui/content.json').read_text());validate_manifest(manifest)

class ContentContractTests(unittest.TestCase):
    def sample(self):return {'schema_version':1,'v1':[],'v2':[{'slot':'NEXT_WORLD','content':{'id':'example','title':'Observation','paragraphs':['Saved evidence only'],'evidence':'docs/example.md'}}]}
    def test_all_named_slots(self):
        for slot in SLOTS:
            m=self.sample();m['v2'][0]['slot']=slot;self.assertTrue(validate_manifest(m))
    def test_unknown_or_missing_slot_rejected(self):
        for slot in ['EARTH','body','',None]:
            m=self.sample();m['v2'][0]['slot']=slot
            with self.assertRaises(ValueError):validate_manifest(m)
    def test_duplicate_id_rejected(self):
        m=self.sample();m['v2']*=2
        with self.assertRaises(ValueError):validate_manifest(m)
    def test_executable_or_selector_fields_rejected(self):
        for field in ['html','script','css','selector','parent']:
            m=self.sample();m['v2'][0]['content'][field]='arbitrary'
            with self.assertRaises(ValueError):validate_manifest(m)
    def test_external_and_traversal_evidence_rejected(self):
        for path in ['https://example.com','javascript:alert(1)','docs/../secret','/private/key','results//../x']:
            m=self.sample();m['v2'][0]['content']['evidence']=path
            with self.assertRaises(ValueError):validate_manifest(m)
    def test_unknown_version_rejected(self):
        m=self.sample();m['v3']=[]
        with self.assertRaises(ValueError):validate_manifest(m)
    def test_secret_content_rejected(self):
        m=self.sample();m['v2'][0]['content']['paragraphs']=['AI'+'za'+'A'*35]
        with self.assertRaises(ValueError):validate_manifest(m)
    def test_literal_markup_is_plain_text(self):
        m=self.sample();m['v2'][0]['content']['title']='<script>text only</script>';self.assertTrue(validate_manifest(m))
    def test_empty_title_and_oversize_content_rejected(self):
        for title in ['', ' '*5, 'x'*201]:
            m=self.sample();m['v2'][0]['content']['title']=title
            with self.assertRaises(ValueError):validate_manifest(m)

class SecretScanTests(unittest.TestCase):
    def test_sensitive_patterns(self):
        for value in ['AI'+'za'+'a'*35,'gh'+'p_'+'x'*40,'sk-'+'x'*40,'password="'+'x'*20+'"']:
            self.assertTrue(has_secret(value))
    def test_scan_never_echoes_secret(self):
        secret='AI'+'za'+'x'*35
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'fixture';path.write_text(secret)
            with self.assertRaises(ValueError) as error:scan([path])
            self.assertNotIn(secret,str(error.exception))
    def test_plain_research_text_allowed(self):self.assertFalse(has_secret('choice A003; observation; 17px; API calls = 0'))
