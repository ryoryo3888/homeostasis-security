"""Verify the exact outgoing commit, not merely the current working directory."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from homeostasis_core.observability import PublicationError, read_json, validate_publication, validate_bundle, digest


def verify_commit(commit, destination):
    if destination in ('refs/heads/main','refs/heads/master'):
        raise PublicationError('DIRECT_MAIN_PUSH_FORBIDDEN')
    def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT)
    listing=git('ls-tree','-r','--name-only',commit).decode().splitlines()
    protected=json.loads(git('show',commit+':tests/fixtures/protected_artifacts.json'))
    with tempfile.TemporaryDirectory() as folder:
        root=Path(folder)
        for name in listing:
            if any(name.startswith('results/'+c+'/') and name!='results/'+c+'/README.md' for c in ('probe','rejected','research')):
                raise PublicationError('RAW_RUNTIME_FILE_COMMITTED')
            if name.endswith('.checkpoint'):
                if name not in protected or hashlib.sha256(git('show',commit+':'+name)).hexdigest()!=protected[name]:
                    raise PublicationError('UNAPPROVED_CHECKPOINT_COMMITTED')
            if name.startswith('results/status/') or name=='RESEARCH_STATE.md':
                if '..' in Path(name).parts:raise PublicationError('UNSAFE_PUBLIC_PATH')
                mode=git('ls-tree',commit,'--',name).decode().split()[0]
                if mode!='100644':raise PublicationError('INVALID_PUBLIC_FILE_MODE')
                path=root/name;path.parent.mkdir(parents=True,exist_ok=True)
                path.write_bytes(git('show',commit+':'+name))
        validate_publication(root)
        for path in (root/'results/status').rglob('*.json'):
            data=read_json(path)
            if 'observation_version' in data:
                validate_bundle(data)
                if path.stem!=digest(path.read_bytes()):raise PublicationError('PUBLIC_BUNDLE_NAME_MISMATCH')


if __name__=='__main__':
    try:
        for line in sys.stdin:
            local_ref,local_sha,remote_ref,remote_sha=line.split()
            if set(local_sha)=={'0'}:continue
            verify_commit(local_sha,remote_ref)
        print('Outgoing observation snapshot verified; API calls: 0')
    except Exception:
        print('PUSH BLOCKED: public audit, secret scan, raw-file policy or branch validation failed.',file=sys.stderr)
        sys.exit(1)
