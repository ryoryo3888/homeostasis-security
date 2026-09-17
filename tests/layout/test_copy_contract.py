import copy,json,subprocess,sys,unittest
from tools.copy_contract import ROOT,PUBLIC_FILES,MARK,check_copy,prove_source_delta,prove_layout_delta
class CopyContractTests(unittest.TestCase):
    def test_current_public_generation_paths_are_clean(self):
        for path in PUBLIC_FILES:
            with self.subTest(path=path):self.assertTrue(check_copy((ROOT/path).read_text()))
    def test_time_and_viewer_directives_rejected(self):
        for text in ['10秒で理解','30秒で理解','この世界を２０秒で理解','○秒で分かる','読み方','初見は簡単に','初心者向け','研究者向け：証拠','まずここを見て','詳しく知りたい人は']:
            with self.subTest(text=text),self.assertRaises(ValueError):check_copy(text)
    def test_research_and_evidence_labels_remain_allowed(self):
        self.assertTrue(check_copy('研究質問 世界の構成 局所危機から地球規模の回復へ この8ターンで何が起きた？ 証拠・原データ まだ分からないこと'))
    def test_only_explicitly_authorized_source_changes(self):self.assertTrue(prove_source_delta())
    def test_generator_refreshes_stale_narrative(self):
        # Exercise the actual builder in a temporary source tree, no research execution.
        import tempfile,shutil
        with tempfile.TemporaryDirectory() as directory:
            target=__import__('pathlib').Path(directory);(target/'tools').mkdir()
            shutil.copyfile(ROOT/'tools/build_ui_previews.py',target/'tools/build_ui_previews.py')
            for name in ['homeostasis-ui-system.css','homeostasis-research-layer.css','homeostasis-research-layer.js','homeostasis-research-integration.js','dashboard_v1.html','dashboard_v2.html']:
                shutil.copyfile(ROOT/name,target/name)
            for version in ['v1','v2']:
                p=target/f'dashboard_{version}.html';before,tail=p.read_text().split(MARK);_,after=tail.split('\n</script>',1);p.write_text(before+MARK+'// stale narrative\n</script>'+after)
            subprocess.run([sys.executable,'-B',str(target/'tools/build_ui_previews.py')],check=True,capture_output=True)
            for version in ['v1','v2']:
                self.assertEqual((target/f'dashboard_{version}.html').read_bytes(),(ROOT/f'dashboard_{version}.html').read_bytes())
    def test_approved_layout_delta_and_negative_earth_case(self):
        old=json.loads((ROOT/'tests/layout/history/pre-copy-public-baseline.json').read_text())['records']
        new=json.loads((ROOT/'tests/layout/public-baseline.json').read_text())['records']
        self.assertEqual(len(prove_layout_delta(old,new)),12)
        broken=copy.deepcopy(new);broken[0]['nodes']['.earth-panel']['bounds']['y']+=1
        with self.assertRaises(AssertionError):prove_layout_delta(old,broken)
    def test_research_loss_rejected(self):
        old=json.loads((ROOT/'tests/layout/history/pre-copy-public-baseline.json').read_text())['records']
        new=json.loads((ROOT/'tests/layout/public-baseline.json').read_text())['records']
        new[0]['nodes']['.rn-turns']['text']=''
        with self.assertRaises(AssertionError):prove_layout_delta(old,new)
