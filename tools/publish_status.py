"""Prepare/verify observations; --sync is explicit and refuses main."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from homeostasis_core.observability import PublicationError, prepare, validate_publication, read_json, source_digest, validate_bundle, digest


def gate(root):
    state=validate_publication(root)
    for path in (root/'results/status').rglob('*.json'):
        data=read_json(path)  # Validate even unreferenced prior export versions.
        if 'observation_version' in data:
            validate_bundle(data)
            if path.stem!=digest(path.read_bytes()):raise PublicationError('PUBLIC_BUNDLE_NAME_MISMATCH')
    tracked=subprocess.check_output(['git','ls-files','-z'],cwd=root).decode().split('\0')
    protected=json.loads((root/'tests/fixtures/protected_artifacts.json').read_text())
    for name in tracked:
        if name.endswith('.checkpoint'):
            if name not in protected or hashlib.sha256((root/name).read_bytes()).hexdigest()!=protected[name]:
                raise PublicationError('UNAPPROVED_CHECKPOINT_IS_TRACKED')
        if any(name.startswith('results/'+c+'/') and name!='results/'+c+'/README.md' for c in ('probe','rejected','research')):
            raise PublicationError('RAW_RUNTIME_FILE_IS_TRACKED')
    return state


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--verify',action='store_true');parser.add_argument('--sync',action='store_true')
    args=parser.parse_args()
    if args.sync:
        branch=subprocess.check_output(['git','branch','--show-current'],cwd=ROOT,text=True).strip()
        if not branch or branch in ('main','master'):raise PublicationError('PUSH_TO_MAIN_FORBIDDEN')
        if subprocess.run(['git','diff','--cached','--quiet'],cwd=ROOT).returncode:raise PublicationError('UNRELATED_STAGED_CHANGES')
        state=gate(ROOT)
        if state['validation']['preflight']!='PASS' or state['source_digest']!=source_digest(ROOT):
            raise PublicationError('FRESH_PREFLIGHT_REQUIRED')
        subprocess.run(['git','add','--','results/status','RESEARCH_STATE.md'],cwd=ROOT,check=True)
        if subprocess.run(['git','diff','--cached','--quiet'],cwd=ROOT).returncode:
            subprocess.run(['git','commit','-m','Publish validated HOMEOSTASIS observation snapshot'],cwd=ROOT,check=True)
        subprocess.run(['git','push','origin','HEAD:refs/heads/'+branch],cwd=ROOT,check=True)
    elif args.verify:
        gate(ROOT);print('PUBLIC OBSERVABILITY VERIFIED; Gemini API calls: 0')
    else:
        state=prepare(ROOT)
        print('Public status prepared; Gemini API calls: 0; blocked runs:',state['blocked_run_count'])
        if state['latest_blocked_run']:raise PublicationError('LATEST_RUN_PUBLICATION_BLOCKED')

if __name__=='__main__':
    try:main()
    except (PublicationError,KeyError,TypeError,ValueError,OSError):
        print('PUBLICATION BLOCKED: validation or secret scan failed; no push performed.',file=sys.stderr)
        sys.exit(1)
