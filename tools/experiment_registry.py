"""Read-only, fail-closed catalog validation. Never imports simulation or UI code."""
from __future__ import annotations
import argparse
import hashlib
from datetime import datetime
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
from jsonschema import Draft202012Validator, FormatChecker

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.secret_scan import has_secret
from tools.v2_metrics_position_revision import original_anchor
SCHEMA=ROOT/'research/experiments/registry.schema.json'
ALLOWLIST=ROOT/'research/experiments/artifact_allowlist.json'
REGISTRY=ROOT/'research/experiments/registry.json'

class RegistryError(ValueError):pass

def require(condition,message):
    if not condition:raise RegistryError(message)

def load_json(path):
    def pairs(items):
        result={}
        for key,value in items:
            require(key not in result,'Duplicate JSON key')
            result[key]=value
        return result
    return json.loads(Path(path).read_text(),object_pairs_hook=pairs,parse_constant=lambda _:(_ for _ in ()).throw(RegistryError('Non-finite JSON')))

def safe_path(root,name,tracked):
    require(isinstance(name,str) and bool(re.fullmatch(r'[A-Za-z0-9_./-]+',name)),'Unsafe artifact path')
    parts=PurePosixPath(name).parts
    require(not name.startswith('/') and name==str(PurePosixPath(name)) and not any(p in ('.','..') or p.startswith('.') for p in parts),'Traversal/absolute/hidden path')
    require(not re.search(r'(?:secret|credential|api[_-]?key|private|password|\.env)',name,re.I),'Secret/private path forbidden')
    require(name in tracked,'Artifact is not tracked')
    current=root
    for part in parts:
        current=current/part
        require(not current.is_symlink(),'Symlink artifact forbidden')
    require(current.is_file() and current.resolve().is_relative_to(root.resolve()),'Missing/outside artifact')
    return current

def pointer(data,path):
    if path=='':return data
    require(isinstance(path,str) and path.startswith('/') and not re.search(r'~(?![01])',path),'Invalid JSON pointer')
    try:
        for part in path[1:].split('/'):
            part=part.replace('~1','/').replace('~0','~')
            if isinstance(data,list):
                require(bool(re.fullmatch(r'0|[1-9][0-9]*',part)),'Invalid array index')
                data=data[int(part)]
            else:data=data[part]
        return data
    except (KeyError,IndexError,TypeError):raise RegistryError('Broken artifact pointer') from None

def validate_registry(registry,root=ROOT,allowlist=None):
    root=Path(root)
    schema=load_json(SCHEMA)
    Draft202012Validator.check_schema(schema)
    errors=list(Draft202012Validator(schema,format_checker=FormatChecker()).iter_errors(registry))
    require(not errors,'Registry schema mismatch (values withheld)')
    require(not has_secret(json.dumps(registry,ensure_ascii=False)),'Registry contains sensitive data')
    catalog=load_json(ALLOWLIST) if allowlist is None else allowlist
    require(set(catalog)=={'schema_version','reviewed_at_commit','artifacts'} and catalog['schema_version']==1,'Artifact allowlist schema mismatch')
    require(isinstance(catalog['reviewed_at_commit'],str) and bool(re.fullmatch('[0-9a-f]{40}',catalog['reviewed_at_commit'])),'Review commit missing')
    tracked=set(subprocess.check_output(['git','ls-files','-z'],cwd=root).decode().split('\0'))
    artifacts={}
    for item in catalog['artifacts']:
        require(set(item)=={'path','sha256','version','classification','source_eligible'},'Artifact approval fields invalid')
        name=item['path'];require(name not in artifacts,'Duplicate approved artifact')
        require(item['version'] in ('v1','v2','shared'),'Unknown artifact version')
        require(item['classification'] in ('representative_run','comparison_study','formal_research','failed','invalidated','documentation','publication_source'),'Unapproved artifact classification')
        require(type(item['source_eligible']) is bool and bool(re.fullmatch('[0-9a-f]{64}',item['sha256'])),'Invalid artifact approval')
        p=safe_path(root,name,tracked);raw=p.read_bytes()
        checked=raw
        # The retained publication source permits only Rio's exact V2 anchor
        # revision. Research data, evidence text and the catalog stay immutable.
        if (name=='homeostasis-research-layer.js' and item['classification']=='publication_source'
                and not item['source_eligible'] and hashlib.sha256(raw).hexdigest()!=item['sha256']):
            try:checked=original_anchor(raw)
            except ValueError:raise RegistryError('Unapproved publication source revision') from None
        require(hashlib.sha256(checked).hexdigest()==item['sha256'],'Artifact hash mismatch')
        require(not has_secret(raw.decode()),'Artifact secret scan failed')
        artifacts[name]=(item,load_json(p) if p.suffix=='.json' else None)
    def resolve(ref,version,source=False,status=None):
        name=ref['path'];safe_path(root,name,tracked)
        require(name in artifacts,'Artifact not explicitly approved')
        item,data=artifacts[name]
        require(item['version'] in (version,'shared'),'Cross-version artifact')
        if source:
            require(item['source_eligible'],'Not a research source')
            require(item['classification'] in ('representative_run','comparison_study','formal_research','failed','invalidated'),'Source classification forbidden')
            if status=='completed':require(item['classification'] not in ('failed','invalidated'),'Failed artifact cannot be completed')
        require(data is not None or ref['pointer']=='','Pointer into non-JSON artifact')
        return pointer(data,ref['pointer']) if data is not None else None
    entries={}
    for entry in registry['experiments']:
        eid=entry['experiment_id'];require(eid not in entries,'Duplicate experiment_id');entries[eid]=entry
        version,status=entry['version'],entry['status']
        if entry['created_at'] is not None:
            try:stamp=datetime.fromisoformat(entry['created_at'].replace('Z','+00:00'))
            except ValueError:raise RegistryError('Invalid original timestamp') from None
            require(stamp.tzinfo is not None,'Original timestamp needs timezone')
        if not entry['runs']:
            require(all(entry[k] in (None,0) for k in ('run_count','worldline_count','turn_count')),'Counts require run provenance')
        if status=='completed':require(bool(entry['source_artifacts']),'Completed experiment needs source')
        refs=entry['source_artifacts']+entry['evidence_artifacts']
        require(len({(r['path'],r['pointer']) for r in refs})==len(refs),'Duplicate artifact reference')
        for ref in entry['source_artifacts']:resolve(ref,version,True,status)
        for ref in entry['evidence_artifacts']:resolve(ref,version)
        approved_paths={r['path'] for r in refs}
        for ref in entry['conditions']+[r for rs in entry['field_evidence'].values() for r in rs]:
            require(ref['path'] in approved_paths,'Unlinked field evidence');resolve(ref,version)
        require(set(entry['field_evidence']).issubset(entry),'Unknown field evidence')
        for key in ('experiment_type','research_question','status','result_summary','created_at'):
            if entry[key] is not None and entry[key]!='unknown':require(bool(entry['field_evidence'].get(key)),'Claim lacks field evidence')
        run_paths=set();lengths=[];seeds=[]
        for run in entry['runs']:
            ref=run['artifact'];require(ref in entry['source_artifacts'],'Run source not linked')
            require(ref['path'] not in run_paths,'Duplicate run artifact');run_paths.add(ref['path'])
            data=resolve(ref,version,True,status);require(isinstance(data,dict),'Run root must be an object')
            turns=pointer(data,run['turns_pointer']);require(isinstance(turns,list),'TURN sequence missing')
            require(run['turn_count']==len(turns),'Run turn_count mismatch')
            require([t.get('turn') for t in turns]==list(range(1,len(turns)+1)),'Broken TURN sequence')
            if status=='completed':
                configured=data.get('turn_count',data.get('metadata',{}).get('turn_count'))
                require(configured==len(turns) and len(turns)>0,'Incomplete run marked completed')
            actual_seed=pointer(data,run['seed_pointer']) if run['seed_pointer'] else None
            require(run['seed']==actual_seed,'Unproven seed');seeds.append(actual_seed);lengths.append(len(turns))
        if entry['runs']:
            require(entry['run_count']==len(run_paths) and entry['worldline_count']==len(run_paths),'Run/worldline count mismatch')
            require(entry['turn_count']==(lengths[0] if len(set(lengths))==1 else None),'Per-worldline turn count mismatch')
            expected='unknown' if all(s is None for s in seeds) else 'recorded' if all(s is not None for s in seeds) else 'partially_recorded'
            require(entry['seed_policy']==expected,'Seed policy mismatch')
            require(entry['seed']==(seeds[0] if len(set(seeds))==1 else None),'Aggregate seed mismatch')
        # A catalog record does not constitute UI publication approval.
        if status in ('failed','invalidated'):require(entry['publication_status'] in ('registered_only','withheld'),'Failed publication status')
    groups={}
    for group in registry['comparison_groups']:
        gid=group['group_id'];require(gid not in groups,'Duplicate comparison group');groups[gid]=group
        require(all(m in entries for m in group['members']),'Broken comparison member')
        require(len({entries[m]['version'] for m in group['members']})==1,'Cross-version comparison group')
        require(all(entries[m]['comparison_group']==gid for m in group['members']),'Nonreciprocal comparison group')
    for eid,entry in entries.items():
        for field in ('parent_experiment','control_experiment'):
            target=entry[field]
            if target is not None:
                require(target in entries and target!=eid,'Broken/self experiment reference')
                require(entries[target]['version']==entry['version'],'Cross-version experiment reference')
                if field=='control_experiment':require(entries[target]['status']=='completed','Control is not completed')
        gid=entry['comparison_group']
        if gid is not None:require(gid in groups and eid in groups[gid]['members'],'Invalid comparison_group relation')
    def visit(eid,trail):
        require(eid not in trail,'Cyclic experiment provenance')
        for field in ('parent_experiment','control_experiment'):
            target=entries[eid][field]
            if target:visit(target,trail|{eid})
    for eid in entries:visit(eid,set())
    return {'experiments':len(entries),'approved_artifacts':len(artifacts),'publication_performed':False}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('registry',nargs='?',type=Path,default=REGISTRY);args=p.parse_args()
    try:result=validate_registry(load_json(args.registry))
    except (RegistryError,OSError,ValueError) as error:
        print('REGISTRY FAIL: '+str(error),file=sys.stderr);return 1
    print('REGISTRY PASS: '+json.dumps(result));return 0
if __name__=='__main__':raise SystemExit(main())
