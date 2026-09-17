"""Build a static, allowlisted read-only exhibit. No raw runs or simulator bundled."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from homeostasis_core.observability import read_json, secret_scan


def build(destination):
    config = read_json(ROOT/'observatory/config.json')
    paths = ['worldline_observatory.html', 'observatory/app.js', 'observatory/view-model.js',
             'observatory/style.css', 'observatory/config.json', 'README.md',
             'DESIGN_RESEARCH_PRINCIPLES.md', 'docs/CREATIVE_RESEARCH_ROADMAP.md',
             'docs/WORLDLINE_OBSERVATORY.md', config['timeline'], config['researchBundle'], config['report']]
    expected = hashlib.sha256((ROOT/config['timeline']).read_bytes()).hexdigest()
    if expected != config['sha256']:
        raise ValueError('Timeline content hash mismatch')
    contents = {}
    for name in paths:
        path = ROOT/name
        if path.is_symlink() or ROOT not in path.resolve().parents:
            raise ValueError('Unsafe build path')
        raw = path.read_bytes()
        if path.suffix == '.json':
            read_json(path)
        else:
            secret_scan(raw.decode('utf-8').splitlines())
        contents[name] = raw
    # Validate all inputs before creating an output. Never delete source material.
    if destination.is_symlink():
        raise ValueError('Unsafe build destination')
    if destination.exists():
        allowed = set(contents) | {'build-manifest.json'}
        for existing in destination.rglob('*'):
            if existing.is_symlink() or (existing.is_file() and str(existing.relative_to(destination)) not in allowed):
                raise ValueError('Unexpected file in build destination; use a clean directory')
    destination.mkdir(parents=True, exist_ok=True)
    manifest = {'version': 1, 'run_id': config['runId'], 'api_calls': 0, 'files': {}}
    for name, raw in contents.items():
        target = destination/name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        manifest['files'][name] = hashlib.sha256(raw).hexdigest()
    (destination/'build-manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    print(f'OBSERVATORY BUILD PASS: {len(contents)} files; secret scan PASS; API calls 0')
    return manifest

if __name__ == '__main__':
    build(ROOT/'dist/observatory')
