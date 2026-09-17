"""Generated UI must reflect canonical copy without touching the original shell."""
from pathlib import Path
import re
import unittest
ROOT=Path(__file__).resolve().parents[1]
class UICopyTests(unittest.TestCase):
    def test_generated_layers_match_canonical_sources(self):
        for version in ('v1','v2'):
            html=(ROOT/f'dashboard_{version}.html').read_text()
            self.assertEqual(html,(ROOT/f'preview_{version}_unified.html').read_text())
            for filename in ('homeostasis-research-layer.js','homeostasis-research-layer.css','homeostasis-research-integration.js'):
                self.assertIn((ROOT/filename).read_text(),html)
            self.assertFalse(re.search(r'\d+秒で理解|研究者向け|初心者向け|初見は簡単',html))
            self.assertIn('まだ分からないこと',html)
            self.assertIn('この1回だけでは分かりません',html)
    def test_world_precedes_narrative(self):
        source=(ROOT/'homeostasis-research-layer.js').read_text()
        self.assertIn('world.after(layer)',source)
        self.assertNotIn('a.before(r)',source)
        self.assertIn("summary.textContent='初期条件・event'",source)
