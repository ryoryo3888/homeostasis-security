"""Explicit copy-only revision proof and current-public-path regression rules."""
from pathlib import Path
from html.parser import HTMLParser
import json,re,subprocess
from tools.navigation_revision import add_return_link
from tools.v2_metrics_position_revision import revise_anchor
ROOT=Path(__file__).resolve().parents[1]
REVISION=json.loads((ROOT/'tests/layout/copy_revision.json').read_text())
MARK='<!-- HOMEOSTASIS_RESEARCH_NARRATIVE_PREVIEW -->\n<script>\n'
PUBLIC_FILES=['homeostasis-research-layer.js','homeostasis-research-integration.js','homeostasis-research-layer.css','homeostasis-ui-system.css','ui/content-slots.js','ui/layout-guard.js','ui/content.json','dashboard_v1.html','dashboard_v2.html','preview_v1_unified.html','preview_v2_unified.html']
FORBIDDEN=re.compile(r'(?:[0-9０-９〇○一二三四五六七八九十]+\s*秒で(?:理解|分かる|わかる)|読み方|初見|初心者|研究者向け|まず.{0,30}(?:見て|見よう|読む)|詳しく知りたい人)')
def check_copy(text):
    if FORBIDDEN.search(text):raise ValueError('Viewer-directive copy detected')
    return True

def replace_script(html,source):
    if html.count(MARK)!=1:raise ValueError('Narrative marker count')
    before,tail=html.split(MARK,1)
    _,after=tail.split('\n</script>',1)
    return before+MARK+source+'\n</script>'+after

def revise(text,pairs):
    for old,new in pairs:text=text.replace(old,new)
    return text

def old_source(path):
    return subprocess.check_output(['git','show',REVISION['previous_public_sha']+':'+path],cwd=ROOT).decode()

def prove_source_delta():
    source=(ROOT/'homeostasis-research-layer.js').read_text()
    assert source==revise_anchor(revise(old_source('homeostasis-research-layer.js'),REVISION['narrative_replacements']))
    for version in ['v1','v2']:
        old=old_source('dashboard_'+version+'.html')
        if version=='v1':old=revise(old,REVISION['v1_static_replacements'])
        expected=add_return_link(replace_script(old,source),version)
        for name in [f'dashboard_{version}.html',f'preview_{version}_unified.html']:
            assert (ROOT/name).read_text()==expected,name
    for path in ['homeostasis-research-integration.js','homeostasis-research-layer.css','homeostasis-ui-system.css','ui/layout-guard.js','ui/content-slots.js']:
        assert (ROOT/path).read_text()==old_source(path),path
    return True

class Plain(HTMLParser):
    def __init__(self,text):super().__init__();self.parts=[];self.feed(text)
    def handle_data(self,data):self.parts.append(data)
def plain(text):return ''.join(Plain(text).parts)
def expected_text(text):
    return revise(text,[(plain(a),plain(b)) for a,b in REVISION['narrative_replacements']+REVISION['v1_static_replacements']])

def prove_layout_delta(old,new):
    """Only approved text, natural block shrinkage and its downstream translation."""
    assert len(old)==len(new)==12
    report=[]
    for before,after in zip(old,new):
        for k in ['version','viewport','state','turn','mainOrder']:assert before[k]==after[k],k
        assert before['nodes'].keys()==after['nodes'].keys()
        root='#homeostasisResearchLayer';intro='.rn-intro'
        a,b=before['nodes'],after['nodes']
        shrink=b[root]['bounds']['height']-a[root]['bounds']['height']
        intro_shrink=b[intro]['bounds']['height']-a[intro]['bounds']['height']
        assert shrink<=.05 and intro_shrink<=.05
        for selector,node in a.items():
            current=b[selector]
            for key in ['parent','tag','classes','before','after']:assert node[key]==current[key],(selector,key)
            assert expected_text(node['text'])==current['text'],(selector,'unapproved copy/research loss')
            for key,value in node['styles'].items():
                if selector==intro and key=='gridTemplateRows':continue # intrinsic row shrink only
                assert value==current['styles'][key],(selector,key)
            for key in ['x','width']:assert abs(node['bounds'][key]-current['bounds'][key])<.05,(selector,key)
            delta_y=current['bounds']['y']-node['bounds']['y']
            delta_h=current['bounds']['height']-node['bounds']['height']
            if selector==root:assert abs(delta_y)<.05 and abs(delta_h-shrink)<.05
            elif selector==intro:assert abs(delta_y)<.05 and abs(delta_h-intro_shrink)<.05
            elif node['bounds']['y']>=a[intro]['bounds']['y']+a[intro]['bounds']['height']:
                assert abs(delta_y-shrink)<.05 and abs(delta_h)<.05,(selector,'not natural downstream flow')
            else:assert abs(delta_y)<.05 and abs(delta_h)<.05,(selector,'locked world changed')
        report.append({'version':before['version'],'viewport':before['viewport']['name'],'turn':before['state'],'research_height_delta':shrink,'intro_height_delta':intro_shrink,'world_change':0,'result':'PASS'})
    return report
