"""Candidate structural/interaction checks, not an approved pixel baseline."""
import argparse,base64,functools,http.server,json,threading
from pathlib import Path
from urllib.parse import urlsplit
from check_layout import Browser,QuietHandler,ROOT

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
    out=ROOT/'.artifacts/layout';out.mkdir(parents=True,exist_ok=True);records=[]
    with Browser() as browser:
        parts=urlsplit(base);browser.allowed_origin=parts.scheme+'://'+parts.netloc
        for vp in contract['viewports']:
            target=browser.call('Target.createTarget',{'url':'about:blank'})['targetId']
            session=browser.call('Target.attachToTarget',{'targetId':target,'flatten':True})['sessionId']
            browser.call('Page.enable',session=session)
            browser.call('Fetch.enable',{'patterns':[{'urlPattern':'*'}]},session)
            browser.call('Emulation.setDeviceMetricsOverride',{'width':vp['width'],'height':vp['height'],'deviceScaleFactor':1,'mobile':False},session)
            browser.call('Emulation.setEmulatedMedia',{'features':[{'name':'prefers-reduced-motion','value':'reduce'}]},session)
            browser.call('Page.navigate',{'url':base+'/dashboard_v2.html'},session)
            browser.wait("!!document.querySelector('.control-heading')",session)
            reference=browser.evaluate(FRAME_STYLES+'('+json.dumps({'shell':'.shell','body':'body','panel':'.brand','control':'.controls','brandText':'.brand-en','controlText':'.control-heading'})+')',session)
            reference_earth=browser.evaluate("document.querySelector('.earth-panel .earth').getBoundingClientRect().width",session)
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
                 turnDisabled:[...document.querySelectorAll('.turn-control button')].every(b=>b.disabled),
                 horizontalOverflow:document.documentElement.scrollWidth>innerWidth,
                 text:document.body.innerText,
                 nav:[...document.querySelectorAll('nav a')].map(a=>a.getAttribute('href')),
                 reducedMotion:matchMedia('(prefers-reduced-motion: reduce)').matches};
            })()''',session)
            bounds=result['bounds'];earth=bounds['v3-earth'];canvas=bounds['v3-canvas']
            assert result['parents']==contract['parents']
            assert all(bounds[a]['bottom']<=bounds[b]['y']+.5 for a,b in zip(contract['order'],contract['order'][1:]))
            assert abs(earth['x']+earth['width']/2-(canvas['x']+canvas['width']/2))<1
            assert canvas['width']*.24<=earth['width']<=reference_earth+1 and earth['y']>=bounds['v3-control']['bottom'], (vp['name'],earth['width'],reference_earth)
            assert result['aurora']=={'count':1,'decorative':'true','animations':['none','none']}
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
            browser.call('Emulation.setEmulatedMedia',{'features':[{'name':'prefers-reduced-motion','value':'reduce'}]},session)
            browser.evaluate("document.getElementById('clear-selection').click()",session)
            assert browser.evaluate("document.querySelectorAll('.state-node[aria-pressed=true]').length===0 && document.querySelectorAll('.route-row').length===18",session)
            browser.evaluate("document.querySelectorAll('.state-node')[0].click();document.activeElement.blur();window.scrollTo(0,0)",session)
            shot=browser.call('Page.captureScreenshot',{'format':'png'},session)['data']
            (out/f'v3-{vp["name"]}.png').write_bytes(base64.b64decode(shot))
            result.pop('text');records.append({'viewport':vp,'v2_earth_width':reference_earth,**result})
            print('V3',vp['name'],'candidate frame/data/keyboard/interaction PASS',flush=True)
            browser.call('Target.closeTarget',{'targetId':target})
        assert not browser.blocked,browser.blocked
    (out/'v3-candidate-check.json').write_text(json.dumps({'status':'candidate','approved_baseline':False,'records':records},indent=2))


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
