"""Conservative staged/publication secret check; reports paths, never matching values."""
import argparse
from pathlib import Path
import re
import subprocess
PATTERNS=[
    re.compile(r'AIza[0-9A-Za-z_-]{35}'),
    re.compile(r'(?:ghp_|github_pat_)[0-9A-Za-z_]{30,}'),
    re.compile(r'sk-(?:proj-)?[0-9A-Za-z_-]{32,}'),
    re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    re.compile(r'''(?i)["']?(?:api_key|access_token|client_secret|password)["']?\s*[:=]\s*["'][^"'\s]{16,}["']'''),
]
def has_secret(text):return any(pattern.search(text) for pattern in PATTERNS)
def scan(paths):
    bad=[]
    for path in paths:
        if path.is_file() and has_secret(path.read_bytes().decode('utf-8',errors='ignore')):bad.append(str(path))
    if bad:raise ValueError('Secret scan rejected files: '+', '.join(bad))
    return len(paths)
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--base',default='36d0b8c225214a13e54a88b8b8e6751255b922ce');a=p.parse_args()
    names=subprocess.check_output(['git','diff','--name-only','--diff-filter=ACMR',a.base],text=True).splitlines()
    names+=subprocess.check_output(['git','ls-files','--others','--exclude-standard'],text=True).splitlines()
    count=scan([Path(name) for name in sorted(set(names))]);print(f'Secret scan PASS ({count} files; values withheld)')
if __name__=='__main__':main()
