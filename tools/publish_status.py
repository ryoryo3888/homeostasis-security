"""Prepare/verify observations; --sync is explicit and refuses main."""
import argparse
import hashlib
import json
import os
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


def git(root, *args):
    # Git does not need model credentials. Never print captured git diagnostics.
    env={k:v for k,v in os.environ.items() if k not in ('GEMINI_API_KEY','GOOGLE_API_KEY','OPENAI_API_KEY')}
    result=subprocess.run(['git',*args],cwd=root,env=env,text=True,capture_output=True,timeout=120)
    if result.returncode:
        raise PublicationError('GIT_'+args[0].upper().replace('-','_')+'_FAILED')
    return result.stdout.strip()


def publication_preconditions(root):
    root=Path(root);branch=git(root,'branch','--show-current')
    if not branch or branch in ('main','master'):raise PublicationError('PUSH_TO_MAIN_FORBIDDEN')
    git(root,'remote','get-url','origin')
    # A snapshot must refer to committed implementation, not unpublished code.
    changed=set(filter(None,git(root,'diff','HEAD','--name-only').splitlines()))
    changed.update(filter(None,git(root,'ls-files','--others','--exclude-standard').splitlines()))
    if any(name!='RESEARCH_STATE.md' and not name.startswith('results/status/') for name in changed):
        raise PublicationError('COMMIT_IMPLEMENTATION_BEFORE_EXPERIMENT_OR_SYNC')
    if git(root,'diff','--cached','--name-only'):raise PublicationError('UNRELATED_STAGED_CHANGES')
    return branch


def sync_status(root, expected_run=None):
    root=Path(root);branch=publication_preconditions(root);state=gate(root)
    if state['latest_blocked_run']:raise PublicationError('LATEST_RUN_PUBLICATION_BLOCKED')
    if expected_run and state['latest_observed_run']!=expected_run:raise PublicationError('EXPECTED_RUN_NOT_PUBLISHED')
    if state['validation']['preflight']!='PASS' or state['source_digest']!=source_digest(root):
        raise PublicationError('FRESH_PREFLIGHT_REQUIRED')
    git(root,'add','--','results/status','RESEARCH_STATE.md')
    if git(root,'diff','--cached','--name-only'):
        git(root,'commit','-m','Publish validated HOMEOSTASIS observation snapshot')
    head=git(root,'rev-parse','HEAD')
    # Verify the exact outgoing tree even if local git hooks are not installed.
    from tools import publication_gate
    previous_root=publication_gate.ROOT
    try:
        publication_gate.ROOT=root
        publication_gate.verify_commit(head,'refs/heads/'+branch)
    finally:publication_gate.ROOT=previous_root
    if git(root,'branch','--show-current')!=branch:raise PublicationError('BRANCH_CHANGED')
    git(root,'push','origin','HEAD:refs/heads/'+branch)
    git(root,'fetch','origin')
    local=git(root,'rev-parse','HEAD');remote=git(root,'rev-parse','refs/remotes/origin/'+branch)
    advertised=git(root,'ls-remote','--heads','origin','refs/heads/'+branch).split()
    if local!=head or remote!=head or not advertised or advertised[0]!=head:
        raise PublicationError('REMOTE_HEAD_MISMATCH')
    receipt={'publication_version':1,'status':'PASS','branch':branch,'local_head':local,
             'remote_head':remote,'run_id':state['latest_observed_run'],'api_calls':0}
    from homeostasis_core.observability import atomic_write,encoded
    atomic_write(root/'results/debug/publication-receipt.json',encoded(receipt))
    print('REMOTE OBSERVABILITY READY: '+head)
    return receipt


def complete_publication(root, expected_run=None, expected_branch=None):
    """Publish saved evidence only; this function cannot launch any experiment."""
    root=Path(root)
    # A failed retry must not leave an old successful local receipt visible.
    from homeostasis_core.observability import atomic_write,encoded
    atomic_write(root/'results/debug/publication-receipt.json',encoded({'status':'PENDING','api_calls':0}))
    try:
        branch=publication_preconditions(root)
        if expected_branch and branch!=expected_branch:raise PublicationError('BRANCH_CHANGED')
        report=read_json(root/'results/debug/check.json',optional=True)
        if not report or report.get('status')!='PASS' or report.get('source_digest')!=source_digest(root):
            env={k:v for k,v in os.environ.items() if not any(x in k.upper() for x in ('API_KEY','TOKEN','PASSWORD','SECRET'))}
            env.update(HOMEOSTASIS_OFFLINE='1',PYTHONDONTWRITEBYTECODE='1',PYTHONPATH=os.pathsep.join((str(root/'tools/offline'),str(root))))
            subprocess.run([sys.executable,'-B','tools/check.py'],cwd=root,env=env,check=True)
        state=prepare(root)
        if state['latest_blocked_run']:raise PublicationError('LATEST_RUN_PUBLICATION_BLOCKED')
        return sync_status(root,expected_run)
    except Exception as exc:
        # Fixed error codes only; no git stderr, exception payload or secrets.
        code=str(exc) if isinstance(exc,PublicationError) else 'PUBLICATION_PROCESS_FAILED'
        atomic_write(root/'results/debug/publication-receipt.json',encoded({'status':'FAIL','code':code,'api_calls':0}))
        raise PublicationError(code) from None


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--verify',action='store_true');parser.add_argument('--sync',action='store_true')
    parser.add_argument('--complete',action='store_true');parser.add_argument('--expected-run')
    args=parser.parse_args()
    if args.complete:complete_publication(ROOT,args.expected_run)
    elif args.sync:sync_status(ROOT,args.expected_run)
    elif args.verify:
        gate(ROOT);print('PUBLIC OBSERVABILITY VERIFIED; Gemini API calls: 0')
    else:
        state=prepare(ROOT)
        print('Public status prepared; Gemini API calls: 0; blocked runs:',state['blocked_run_count'])
        if state['latest_blocked_run']:raise PublicationError('LATEST_RUN_PUBLICATION_BLOCKED')

if __name__=='__main__':
    try:main()
    except (PublicationError,KeyError,TypeError,ValueError,OSError):
        print('PUBLICATION NOT CONFIRMED: inspect results/debug/publication-receipt.json; retry make sync-status only, never rerun the experiment.',file=sys.stderr)
        sys.exit(1)
