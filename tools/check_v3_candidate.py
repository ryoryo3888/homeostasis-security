"""Approved V3 frame, motion and interaction checks; no baseline auto-update."""
import argparse,base64,functools,http.server,json,threading
from pathlib import Path
from urllib.parse import urlsplit
from check_layout import Browser,QuietHandler,ROOT
from v3_visual_contract import compare_layout,verify_sources

# Read the real V2 styles at the same viewport; do not bless a new pixel baseline.
FRAME_STYLES = '''(selectors => Object.fromEntries(Object.entries(selectors).map(([name,selector]) => {
    const s=getComputedStyle(document.querySelector(selector));
    const keys=name==='shell'?['width']:name==='body'?['backgroundImage','fontFamily','color']:
        name==='brandText'||name==='controlText'?['fontSize','fontWeight','letterSpacing','color']:
        ['borderTopColor','borderTopWidth','borderRadius','backgroundImage','boxShadow'];
    return [name,Object.fromEntries(keys.map(k=>[k,s[k]]))];
})))'''


def check(base):
    contract=json.loads((ROOT/'ui/v3/frame.json').read_text())
    baseline=json.loads((ROOT/contract['baseline']).read_text())
    verify_sources(baseline['protected_sources'])
    out=ROOT/'.artifacts/layout';out.mkdir(parents=True,exist_ok=True);records=[]
    with Browser() as browser:
        parts=urlsplit(base);browser.allowed_origin=parts.scheme+'://'+parts.netloc
        for vp in contract['viewports']:
            target=browser.call('Target.createTarget',{'url':'about:blank'})['targetId']
            session=browser.call('Target.attachToTarget',{'targetId':target,'flatten':True})['sessionId']
            browser.call('Page.enable',session=session)
            # Normalize Linux classic vs macOS overlay scrollbars in the test only.
            browser.call('Emulation.setScrollbarsHidden',{'hidden':True},session)
            browser.call('Fetch.enable',{'patterns':[{'urlPattern':'*'}]},session)
            browser.call('Emulation.setDeviceMetricsOverride',{'width':vp['width'],'height':vp['height'],'deviceScaleFactor':1,'mobile':False},session)
            browser.call('Emulation.setEmulatedMedia',{'features':[{'name':'prefers-reduced-motion','value':'reduce'}]},session)
            browser.call('Page.navigate',{'url':base+'/dashboard_v2.html'},session)
            browser.wait("!!document.querySelector('.control-heading')",session)
            reference=browser.evaluate(FRAME_STYLES+'('+json.dumps({'shell':'.shell','body':'body','panel':'.brand','control':'.controls','brandText':'.brand-en','controlText':'.control-heading'})+')',session)
            reference_earth=browser.evaluate("document.querySelector('.earth-panel .earth').getBoundingClientRect().width",session)
            browser.call('Page.addScriptToEvaluateOnNewDocument',{'source':"""
                window.__v3Relocations=[];
                const locked=['v3-identity','v3-control','v3-world','v3-canvas','v3-earth','v3-network','state-nodes'];
                new MutationObserver(records=>records.forEach(r=>r.removedNodes.forEach(n=>{
                    if(n.nodeType===1) for(const id of locked)
                        if(n.id===id || n.querySelector('#'+id)) window.__v3Relocations.push(id);
                }))).observe(document,{childList:true,subtree:true});
            """},session)
            browser.call('Page.navigate',{'url':base+'/dashboard_v3.html'},session)
            browser.wait('!!window.V3Candidate?.ready',session)
            browser.evaluate('document.fonts.ready.then(()=>true)',session)
            inherited=browser.evaluate(FRAME_STYLES+'('+json.dumps({'shell':'.shell','body':'body','panel':'.brand','control':'#v3-control','brandText':'.identity','controlText':'#v3-control h2'})+')',session)
            assert inherited==reference, (vp['name'], 'V1/V2 shared frame drift', reference, inherited)
            result=browser.evaluate('''(() => {
                const rect=id=>{const b=document.getElementById(id).getBoundingClientRect();return {x:b.x,y:b.y,width:b.width,height:b.height,bottom:b.bottom}};
                const ids=['v3-identity','v3-control','v3-world','v3-state-detail','v3-evidence'];
                const caption=document.querySelector('.earth-caption').getBoundingClientRect();
                const measurements=document.querySelector('.world-measurements').getBoundingClientRect();
                return {bounds:Object.fromEntries(ids.concat(['v3-earth','v3-canvas']).map(id=>[id,rect(id)])),
                 captionBottom:caption.bottom,measurementsTop:measurements.top,measurementsBottom:measurements.bottom,
                 parents:Object.fromEntries(['v3-earth','v3-canvas','v3-network','state-nodes'].map(id=>[id,document.getElementById(id).parentElement.id])),
                 nodes:[...document.querySelectorAll('.state-node')].map(n=>{const b=n.getBoundingClientRect();return {id:n.dataset.state,x:b.x,y:b.y,width:b.width,height:b.height}}),
                 routeCount:document.querySelectorAll('.route').length,
                 aurora:{count:document.querySelectorAll('.v3-aurora').length,
                   decorative:document.querySelector('.v3-aurora')?.getAttribute('aria-hidden'),
                   animations:[...document.querySelectorAll('.aurora-ribbon')].map(n=>getComputedStyle(n).animationName)},
                 earthLayers:['#v3-earth img','.v3-aurora'].map(s=>{const r=document.querySelector(s).getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height}}),
                 turnDisabled:[...document.querySelectorAll('.turn-control button')].every(b=>b.disabled),
                 horizontalOverflow:document.documentElement.scrollWidth>innerWidth,
                 text:document.body.innerText,
                 nav:[...document.querySelectorAll('nav a')].map(a=>a.getAttribute('href')),
                 reducedMotion:matchMedia('(prefers-reduced-motion: reduce)').matches};
            })()''',session)
            compare_layout(next(r for r in baseline['records'] if r['viewport']==vp),result)
            bounds=result['bounds'];earth=bounds['v3-earth'];canvas=bounds['v3-canvas']
            assert result['parents']==contract['parents']
            assert all(bounds[a]['bottom']<=bounds[b]['y']+.5 for a,b in zip(contract['order'],contract['order'][1:]))
            assert abs(earth['x']+earth['width']/2-(canvas['x']+canvas['width']/2))<1
            assert canvas['width']*.24<=earth['width']<=reference_earth+1 and earth['y']>=bounds['v3-control']['bottom'], (vp['name'],earth['width'],reference_earth)
            assert result['aurora']=={'count':1,'decorative':'true','animations':['none','none']}
            assert abs(earth['width']-earth['height'])<1
            for layer in result['earthLayers']:
                assert all(abs(layer[k]-earth[k])<1 for k in layer), (vp['name'],'Detached Earth/aurora',layer,earth)
            assert earth['bottom']<=result['measurementsTop'] and result['captionBottom']<=result['measurementsTop'], (vp['name'],'Earth/measurement overlap')
            assert result['measurementsBottom']<=canvas['bottom'], (vp['name'],'measurements outside world')
            assert earth['y']<vp['height']*.65 and earth['bottom']<vp['height']
            assert len(result['nodes'])==8 and result['routeCount']==18
            for node in result['nodes']:
                # Visible labels; globe/node boxes do not intersect.
                assert node['x']>=0 and node['x']+node['width']<=vp['width']
                assert node['y']>=canvas['y'] and node['y']+node['height']<=canvas['bottom']
                cx=earth['x']+earth['width']/2;cy=earth['y']+earth['height']/2
                near_x=max(node['x'],min(cx,node['x']+node['width']));near_y=max(node['y'],min(cy,node['y']+node['height']))
                assert (near_x-cx)**2+(near_y-cy)**2 >= (earth['width']*232/520)**2, (vp['name'],node,earth)
            assert not result['horizontalOverflow'] and result['turnDisabled'] and result['reducedMotion']
            assert result['nav']==['dashboard_v1.html','dashboard_v2.html','dashboard_v3.html']
            assert 'STRUCTURE / BASELINE STATE' in result['text'] and '正式世界線なし' in result['text']
            for banned in ('10秒','30秒','秒で理解','読み方','初心者向け','研究者向け','支援国','被災国'):assert banned not in result['text']
            browser.call('Page.bringToFront',session=session)
            browser.evaluate("window._errors=[];addEventListener('error',e=>_errors.push(e.message));document.querySelectorAll('.state-node')[0].focus()",session)
            shot=browser.call('Page.captureScreenshot',{'format':'png'},session)['data']
            (out/f'v3-{vp["name"]}.png').write_bytes(base64.b64decode(shot))
            browser.call('Input.dispatchKeyEvent',{'type':'keyDown','key':'ArrowRight','code':'ArrowRight'},session)
            browser.call('Input.dispatchKeyEvent',{'type':'keyUp','key':'ArrowRight','code':'ArrowRight'},session)
            assert browser.evaluate("document.activeElement===document.querySelectorAll('.state-node')[1]",session)
            browser.call('Input.dispatchKeyEvent',{'type':'keyDown','key':'Enter','code':'Enter','windowsVirtualKeyCode':13,'text':'\r','unmodifiedText':'\r'},session)
            browser.call('Input.dispatchKeyEvent',{'type':'keyUp','key':'Enter','code':'Enter','windowsVirtualKeyCode':13,'text':'\r','unmodifiedText':'\r'},session)
            assert browser.evaluate("document.getElementById('selected-label').textContent==='B'",session), browser.evaluate("({label:document.getElementById('selected-label').textContent,focus:document.activeElement.outerHTML,errors:window._errors})",session)
            browser.evaluate("document.querySelector('.route-row').click()",session)
            assert browser.evaluate("document.querySelectorAll('.route.focused').length===1",session)
            after=browser.evaluate("(()=>{const b=document.getElementById('v3-earth').getBoundingClientRect();return {x:b.x,y:b.y,width:b.width,height:b.height,bottom:b.bottom}})()",session)
            assert after==earth
            browser.call('Emulation.setEmulatedMedia',{'features':[{'name':'prefers-reduced-motion','value':'no-preference'}]},session)
            assert browser.evaluate("[...document.querySelectorAll('.aurora-ribbon')].every(n=>getComputedStyle(n).animationName==='aurora-drift')",session)
            motion=browser.evaluate("""(async()=>{
                await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));
                const nodes=[...document.querySelectorAll('.aurora-ribbon')];
                const animations=nodes.flatMap(n=>n.getAnimations());
                const styles=nodes.map(n=>{const s=getComputedStyle(n);return {duration:s.animationDuration,delay:s.animationDelay,easing:s.animationTimingFunction}});
                const sample=t=>{animations.forEach(a=>{a.pause();a.currentTime=t});return nodes.map(n=>getComputedStyle(n).transform)};
                return {count:animations.length,styles,start:sample(0),later:sample(5000)};
            })()""",session)
            assert motion['count']==2 and motion['start']!=motion['later'],motion
            assert motion['styles']==[{'duration':'14s','delay':'-6s','easing':'ease-in-out'},{'duration':'10s','delay':'0s','easing':'ease-in-out'}],motion
            browser.call('Emulation.setEmulatedMedia',{'features':[{'name':'prefers-reduced-motion','value':'reduce'}]},session)
            browser.evaluate("document.getElementById('clear-selection').click()",session)
            assert browser.evaluate("document.querySelectorAll('.state-node[aria-pressed=true]').length===0 && document.querySelectorAll('.route-row').length===18",session)
            browser.evaluate("document.querySelectorAll('.state-node')[0].click();document.activeElement.blur();window.scrollTo(0,0)",session)
            shot=browser.call('Page.captureScreenshot',{'format':'png'},session)['data']
            (out/f'v3-{vp["name"]}.png').write_bytes(base64.b64decode(shot))
            browser.wait('!!window.V3Validation?.ready',session)
            assert browser.evaluate("document.getElementById('v3-validation').closest('[data-v3-slot]').dataset.v3Slot==='METRICS_EVIDENCE'",session)
            browser.evaluate("document.getElementById('v3-validation').open=true",session)
            for case_id,total in [('abstention',8),('conditional_exchange',3),('all_refuse',3),('missing_offer',3)]:
                view=browser.evaluate("""(([id,last])=>{
                    const c=document.getElementById('validation-case');c.value=id;c.dispatchEvent(new Event('change'));
                    const t=document.getElementById('validation-turn');t.value=last;t.dispatchEvent(new Event('change'));
                    return {turns:t.options.length,rows:document.querySelectorAll('.validation-table')[0].querySelectorAll('tbody tr').length,
                        text:document.querySelector('.validation-output').innerText,transactions:document.querySelectorAll('.validation-transaction').length};
                })("""+json.dumps([case_id,total])+')',session)
                assert view['turns']==total and view['rows']==16,view
                assert '未成立量とは別' in view['text'] and '原本との対応' in view['text']
                if case_id=='abstention':assert view['transactions']==0
                else:
                    assert view['transactions']>0
                    assert browser.evaluate("document.querySelector('.validation-transaction').open=true;document.querySelector('.validation-transaction').innerText.includes('Choice ID:') && document.querySelector('.validation-transaction').innerText.includes('JSON pointer:')",session)
            browser.evaluate("document.querySelectorAll('.validation-controls button')[0].click()",session)
            assert browser.evaluate("document.getElementById('validation-turn').value==='2'",session)
            browser.evaluate("document.querySelectorAll('.validation-controls button')[1].click()",session)
            assert browser.evaluate("document.getElementById('validation-turn').value==='3'",session)
            browser.evaluate("document.getElementById('validation-state').value='MIL';document.getElementById('validation-state').dispatchEvent(new Event('change'));window.scrollTo(0,0)",session)
            assert browser.evaluate("document.querySelectorAll('.validation-table')[0].querySelectorAll('tbody tr').length===2",session)
            locked=browser.evaluate("(()=>{const b=document.getElementById('v3-earth').getBoundingClientRect();return {x:b.x,y:b.y,width:b.width,height:b.height,bottom:b.bottom}})()",session)
            assert locked==earth,'Validation viewer moved Earth'
            assert browser.evaluate('document.documentElement.scrollWidth<=innerWidth',session),'Validation view overflow'
            browser.evaluate("document.getElementById('v3-validation').scrollIntoView()",session)
            shot=browser.call('Page.captureScreenshot',{'format':'png'},session)['data']
            (out/f'v3-validation-{vp["name"]}.png').write_bytes(base64.b64decode(shot))
            browser.evaluate("document.getElementById('v3-validation').open=false;window.scrollTo(0,0)",session)
            assert browser.evaluate('window.__v3Relocations.length===0',session), 'Locked runtime relocation'
            # Exercise the observer in this disposable test document, never public code.
            assert browser.evaluate("""(async()=>{const e=document.getElementById('v3-earth'),p=e.parentNode,next=e.nextSibling;
                document.body.append(e);p.insertBefore(e,next);await Promise.resolve();return window.__v3Relocations.includes('v3-earth')})()""",session)
            result.pop('text');records.append({'viewport':vp,'v2_earth_width':reference_earth,**result})
            print('V3',vp['name'],'approved frame/data/keyboard/interaction PASS',flush=True)
            browser.call('Target.closeTarget',{'targetId':target})
        assert not browser.blocked,browser.blocked
    (out/'v3-candidate-check.json').write_text(json.dumps({'status':contract['status'],'approved_baseline':True,'source_commit':baseline['source_commit'],'records':records},indent=2))


def main():
    p=argparse.ArgumentParser();p.add_argument('--url');args=p.parse_args();server=None
    if args.url:base=args.url.rstrip('/')
    else:
        server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(QuietHandler,directory=str(ROOT)))
        threading.Thread(target=server.serve_forever,daemon=True).start();base=f'http://127.0.0.1:{server.server_port}'
    try:check(base)
    finally:
        if server:server.shutdown();server.server_close()
if __name__=='__main__':main()
