"""Pure baseline-to-display transform. Never executes TURNs, Agents or metrics."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from homeostasis_v3.physical import validate_baseline
from homeostasis_v3.network import validate_network
from homeostasis_v3.contracts import digest
from tools.build_v3_validation import build as build_validation


def transform(baseline, network):
    validate_network(network,baseline)
    world=baseline['world']; countries=world['countries']
    if len(countries)!=8: raise ValueError('Candidate frame requires eight states')
    labels={c['state_id']:chr(65+i) for i,c in enumerate(countries)}
    profiles={p['capacity_id']:p for p in baseline['capacity_profiles']}
    resources=[{'id':r['resource_id'],'unit':r['unit_id']} for r in world['resources']]
    states=[]
    for c in countries:
        sid=c['state_id']; values={}
        for r in resources:
            a=next(a for a in world['accounts'] if a['owner']==sid and a['resource_id']==r['id'])
            d=next(d for d in c['demands'] if d['resource_id']==r['id'])
            cap=next(cap for cap in world['capacities'] if cap['owner']==sid and cap['category']=='production' and profiles[cap['capacity_id']]['resource_id']==r['id'])
            values[r['id']]={'stock':a['balance'],'demand':d['quantity'],'production_capacity':cap['available'],
                             'unit':r['unit'],'account_id':a['account_id'],'capacity_id':cap['capacity_id']}
        states.append({'id':sid,'label':labels[sid],'resources':values})
    routes=[{'id':r['route_id'],'source':r['source'],'target':r['destination'],'resources':r['resource_types'],
             'capacity':r['capacity'],'delay':r['delay'],'available':r['availability'],'shared_group':r['shared_capacity_group']}
            for r in network['routes']]
    return {'schema_version':1,'version':'v3','visual_baseline':'candidate','artifact_class':'synthetic_baseline',
            'formal_worldline':None,'turn':None,'research_eligible':False,'states':states,'resources':resources,
            'routes':routes,'shared_capacities':deepcopy(network['shared_capacities']),
            'production_dependencies':deepcopy(network['production_dependencies']),
            'scales':{r['id']:max(s['resources'][r['id']]['stock'] for s in states) for r in resources},
            'measurements':{'essential_fulfillment':None,'shortage':None,'in_transit':None},
            'provenance':{'baseline':{'path':'scenarios/v3/synthetic_baseline.json','canonical_sha256':digest(baseline)},
                          'network':{'path':'scenarios/v3/synthetic_network.json','canonical_sha256':digest(network)}}}


def render_page(data):
    """One atomic document: stale CSS/JS/JSON caches cannot mix revisions."""
    html=(ROOT/'ui/v3/page.html').read_text()
    parts={
        '<!-- V3_BUNDLED_STYLE -->':'<style>\n'+(ROOT/'ui/v3/observatory.css').read_text()+'\n</style>',
        '<!-- V3_BUNDLED_DATA -->':'<script id="v3-baseline-data" type="application/json">'+json.dumps(data,ensure_ascii=False).replace('<','\\u003c')+'</script>',
        '<!-- V3_BUNDLED_SCRIPT -->':'<script>\n'+(ROOT/'ui/v3/observatory.js').read_text()+'\n</script>',
    }
    validation=build_validation()
    parts['<!-- V3_BUNDLED_SCRIPT -->'] += ('<style>'+ (ROOT/'ui/v3/validation/viewer.css').read_text()+'</style>'
        + '<script id="v3-validation-data" type="application/json">'+json.dumps(validation,ensure_ascii=False).replace('<','\\u003c')+'</script>'
        + '<script>'+(ROOT/'ui/v3/validation/viewer.js').read_text()+'</script>')
    for marker,content in parts.items():
        if html.count(marker)!=1:raise ValueError('Missing/duplicate V3 bundle marker')
        html=html.replace(marker,content)
    return html


def main():
    b=json.loads((ROOT/'scenarios/v3/synthetic_baseline.json').read_text())
    n=json.loads((ROOT/'scenarios/v3/synthetic_network.json').read_text())
    data=transform(b,n)
    for item in data['provenance'].values():item['file_sha256']=hashlib.sha256((ROOT/item['path']).read_bytes()).hexdigest()
    (ROOT/'ui/v3/baseline.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (ROOT/'dashboard_v3.html').write_text(render_page(data),encoding='utf-8')
    print('V3 candidate: synthetic baseline only; no TURN execution')

if __name__=='__main__':main()
