"""Read-only approved V3 frame comparison. Never writes/accepts a baseline."""
from pathlib import Path
import hashlib
import math
from copy import deepcopy
ROOT = Path(__file__).resolve().parents[1]
LOCKED_BOUNDS = ('v3-identity', 'v3-control', 'v3-world', 'v3-canvas', 'v3-earth')

def compare_layout(expected, actual):
    """Small renderer rounding tolerance; not permission to redesign."""
    def compare(a, b, path):
        if isinstance(a, (int, float)) and not isinstance(a, bool):
            if not isinstance(b, (int, float)) or not math.isfinite(b) or abs(a-b)>2:
                raise ValueError(f'V3 geometry drift: {path}: {a} -> {b}')
        elif isinstance(a, dict):
            if not isinstance(b, dict) or set(a)!=set(b): raise ValueError('V3 fields drift: '+path)
            for k in a: compare(a[k], b[k], path+'.'+k)
        elif isinstance(a, list):
            if not isinstance(b, list) or len(a)!=len(b): raise ValueError('V3 count drift: '+path)
            for i,(x,y) in enumerate(zip(a,b)): compare(x,y,path+'.'+str(i))
        elif a!=b: raise ValueError('V3 structure drift: '+path)
    if expected.get('viewport',{}).get('width',1000)<540:
        # Narrow copy wraps differently with platform fonts. Preserve relative
        # world geometry and section gaps, not one OS's header text line count.
        def relative(record):
            r=deepcopy(record);origin=r['bounds']['v3-canvas']['y']
            for n in r['nodes']+r['earthLayers']:
                n['y']-=origin
            for k in ('captionBottom','measurementsTop','measurementsBottom'):r[k]-=origin
            for key in ('v3-world','v3-canvas','v3-earth'):
                r['bounds'][key]['y']-=origin;r['bounds'][key]['bottom']-=origin
            for key in ('v3-identity','v3-control'):
                r['bounds'][key]={k:v for k,v in r['bounds'][key].items() if k in ('x','width')}
            r['parents']=dict(r['parents'])
            return r
        compare(expected['bounds']['v3-control']['y']-expected['bounds']['v3-identity']['bottom'],
                actual['bounds']['v3-control']['y']-actual['bounds']['v3-identity']['bottom'],'control gap')
        compare(expected['bounds']['v3-world']['y']-expected['bounds']['v3-control']['bottom'],
                actual['bounds']['v3-world']['y']-actual['bounds']['v3-control']['bottom'],'world gap')
        expected,actual=relative(expected),relative(actual)
    for field in ('parents','nodes','earthLayers','captionBottom','measurementsTop','measurementsBottom'):
        compare(expected[field], actual[field], field)
    for key in LOCKED_BOUNDS: compare(expected['bounds'][key],actual['bounds'][key],key)

def verify_sources(manifest, root=ROOT):
    for name, expected in manifest.items():
        if hashlib.sha256((root/name).read_bytes()).hexdigest()!=expected:
            raise ValueError('Explicit visual revision approval required: '+name)
