"""Read-only Q1 replay using frozen Leader responses; never calls an LLM."""
import json, shutil
from pathlib import Path
from .runner import World, parse_response, fingerprint

class OfflineReplay:
    def __init__(self, frozen_root, derived_root):
        self.src=Path(frozen_root); self.out=Path(derived_root); self.out.mkdir(parents=True,exist_ok=True)
    def _response(self,w,t,c):
        candidates=[self.src/'raw'/w/str(t)/c/'response.json']
        # Archived responses are turn-specific.  Do not let a partial archive
        # for another turn shadow the requested response.
        if t == 9:
            candidates.append(self.src/'raw-partial-9-archive'/w/c/'response.json')
        if t == 6:
            candidates.append(self.src/'raw-partial-turn6-archive-resume'/w/c/'response.json')
        for p in candidates:
            if p.exists(): return json.loads(p.read_text())
        raise FileNotFoundError(f'missing frozen response {w}:{t}:{c}')
    def baseline(self):
        init=json.loads((self.src/'initial_worlds.json').read_text())
        worlds={}
        for w,s in init.items():
            obj=World.__new__(World); obj.s=s; worlds[w]=obj
        for t in range(1,14):
            for w,obj in worlds.items():
                decisions={}
                for c in obj.s['config']['active']:
                    raw=self._response(w,t,c)
                    decisions[c]=parse_response(raw['text'])
                obj.advance(decisions)
            for w,obj in worlds.items():
                (self.out/f'baseline/{w}').mkdir(parents=True,exist_ok=True)
                (self.out/f'baseline/{w}'/f'turn-{t:02d}.json').write_text(json.dumps(obj.s,ensure_ascii=False))
        frozen=json.loads((self.src/'checkpoint.json').read_text())
        result={w:fingerprint(obj.s)==fingerprint(frozen['worlds'][w]) for w,obj in worlds.items()}
        (self.out/'baseline-result.json').write_text(json.dumps({'pass':all(result.values()),'worlds':result},indent=2))
        return result
