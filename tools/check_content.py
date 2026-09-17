"""Validate declarative content insertion; no DOM selectors or executable content."""
import json
from pathlib import Path
import re
from tools.secret_scan import has_secret
SLOTS={'STORY_OBSERVATION','TURN_OBSERVATION','RESEARCH_FINDINGS','EXPERIMENT_COMPARISON','DEEP_RESEARCH','NEXT_WORLD'}
def validate_manifest(manifest):
    if set(manifest)!={'schema_version','v1','v2'} or type(manifest['schema_version']) is not int or manifest['schema_version']!=1:raise ValueError('Invalid manifest schema')
    for version in ['v1','v2']:
        if not isinstance(manifest[version],list):raise ValueError('Content must be a list')
        seen=set()
        for item in manifest[version]:
            if set(item)!={'slot','content'} or item['slot'] not in SLOTS:raise ValueError('Explicit known slot required')
            c=item['content']
            if not isinstance(c,dict) or set(c)!={'id','title','paragraphs','evidence'}:raise ValueError('Content fields')
            if not isinstance(c['id'],str) or not re.fullmatch('[a-z][a-z0-9-]{0,63}',c['id']) or c['id'] in seen:raise ValueError('Content id')
            seen.add(c['id'])
            if not isinstance(c['title'],str) or not c['title'].strip() or len(c['title'])>200:raise ValueError('Title')
            if not isinstance(c['paragraphs'],list) or not 1<=len(c['paragraphs'])<=20 or any(not isinstance(p,str) or len(p)>4000 for p in c['paragraphs']):raise ValueError('Paragraphs')
            if not isinstance(c['evidence'],str) or not re.fullmatch(r'(docs|results)/[a-zA-Z0-9_./-]+',c['evidence']) or '..' in c['evidence'].split('/'):raise ValueError('Local evidence path required')
            if has_secret(json.dumps(c)):raise ValueError('Secret content rejected')
    return True
