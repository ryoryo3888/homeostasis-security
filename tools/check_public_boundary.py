"""Fail closed on working-tree/deployment files with private records; no model calls.

Use --directory for an actual publication staging directory. This is not a proof
that free-text outputs never quote an instruction: those findings need review.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess

FORBIDDEN_KEYS={'public_observation_payload','attempt_payload','sdk_response','raw_response',
                'private_observation','private_note','systemInstruction','system_instruction',
                'decision_instruction','action_instruction','proposal_instruction','contents','candidates','prompt'}

def scan_json(value, path='$'):
    hits=[]
    if isinstance(value,dict):
        for k,v in value.items():
            if k in FORBIDDEN_KEYS:hits.append(path+'.'+k)
            hits.extend(scan_json(v,path+'.'+k))
    elif isinstance(value,list):
        for i,v in enumerate(value):hits.extend(scan_json(v,path+'[]'))
    return sorted(set(hits))

def check(root, names):
    bad=[]
    for name in names:
        p=root/name
        if not p.is_file():continue
        if any(x.lower() in ('raw','private_runs','private_config','private_prompts') for x in Path(name).parts):
            bad.append({'path':name,'reason':'private directory'});continue
        if name.endswith('_PROMPT.txt') or name.endswith(('.sdk.json','.request.json','.wire.json')):
            bad.append({'path':name,'reason':'private artifact name'});continue
        if p.suffix in ('.json','.checkpoint'):
            try:data=json.loads(p.read_text())
            except (ValueError,UnicodeError):continue
            hits=scan_json(data)
            if hits:bad.append({'path':name,'reason':'private JSON keys','fields':hits})
        if p.suffix=='.html' and re.search(r'href=["\'][^"\']*(?:/raw/|/RAW/|["\']raw/)',p.read_text()):
            bad.append({'path':name,'reason':'RAW link'})
    return bad

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--directory',type=Path);args=parser.parse_args()
    root=args.directory.resolve() if args.directory else Path(__file__).resolve().parents[1]
    if args.directory:names=[str(p.relative_to(root)) for p in root.rglob('*') if p.is_file()]
    else:
        names=subprocess.check_output(['git','-C',str(root),'ls-files','--cached','--others','--exclude-standard','-z']).decode().split('\0')
    bad=check(root,filter(None,names));print(json.dumps({'files_with_findings':bad},ensure_ascii=False,indent=2))
    raise SystemExit(bool(bad))
if __name__=='__main__':main()
