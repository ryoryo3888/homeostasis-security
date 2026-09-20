"""Exercise every published V2 trial/turn with all external requests blocked."""
import argparse
import base64
import functools
import http.server
import json
import threading
from urllib.parse import urlsplit

from check_layout import Browser, QuietHandler, ROOT


def follow_version_link(browser, session, href):
    """Click the visible button, including hit testing; never substitute a URL load."""
    point = browser.evaluate('''(() => {
        const a=document.querySelector('.version-switch a[href='+JSON.stringify(%s)+']');
        if (!a) throw Error('Missing version link');
        a.scrollIntoView({block:'center',behavior:'instant'});
        const r=a.getBoundingClientRect(), x=r.x+r.width/2, y=r.y+r.height/2;
        if (document.elementFromPoint(x,y)?.closest('a')!==a) throw Error('Version link obscured');
        return {x,y};
    })()''' % json.dumps(href), session)
    browser.call('Input.dispatchMouseEvent', {'type':'mousePressed','button':'left','clickCount':1,**point}, session)
    browser.call('Input.dispatchMouseEvent', {'type':'mouseReleased','button':'left','clickCount':1,**point}, session)


def check(base):
    data = json.loads((ROOT / 'results/v2-five-runs/data.json').read_text())
    original_v2 = json.loads((ROOT / 'v2_first_run.json').read_text())
    out = ROOT / '.artifacts/layout'
    out.mkdir(parents=True, exist_ok=True)
    records = []
    with Browser() as browser:
        parts = urlsplit(base)
        browser.allowed_origin = parts.scheme + '://' + parts.netloc
        for name, width, height in [('desktop',1440,1000),('ipad',1024,1366),('phone',390,844)]:
            target = browser.call('Target.createTarget', {'url':'about:blank'})['targetId']
            session = browser.call('Target.attachToTarget', {'targetId':target,'flatten':True})['sessionId']
            browser.call('Page.enable', session=session)
            browser.call('Fetch.enable', {'patterns':[{'urlPattern':'*'}]}, session)
            browser.call('Emulation.setDeviceMetricsOverride', {'width':width,'height':height,'deviceScaleFactor':1,'mobile':False}, session)
            browser.call('Emulation.setEmulatedMedia', {'features':[{'name':'prefers-reduced-motion','value':'reduce'}]}, session)
            url = base + '/results/v2-five-runs/index.html'
            browser.call('Page.navigate', {'url':url}, session)
            browser.wait("document.body?.dataset.observationReady === 'true' && document.querySelector('.earth').naturalWidth > 0", session)
            assert browser.evaluate("[...document.querySelectorAll('.version-switch a')].map(a=>[a.textContent,a.getAttribute('href'),a.getAttribute('aria-current')])", session) == [
                ['v1：二国間の恒常性','dashboard_v1.html',None],
                ['v2：地球規模の恒常性','dashboard_v2.html',None],
                ['v2追加：5回分','results/v2-five-runs/index.html','page']]
            browser.evaluate("window._errors=[];addEventListener('error',e=>_errors.push(e.message))", session)
            for trial in data['trials']:
                number = trial['trial']
                browser.evaluate(f"document.querySelector('#trialSelect').value='{number}';document.querySelector('#trialSelect').dispatchEvent(new Event('change'))", session)
                for turn in range(1,9):
                    browser.evaluate(f"document.querySelector('[data-turn=\"{turn}\"]').click()", session)
                    actual = browser.evaluate('''(() => ({
                        visible:[...document.querySelectorAll('.record-turn')].filter(s=>!s.hidden).map(s=>[+s.dataset.trial,+s.dataset.round]),
                        bodies:[...document.querySelectorAll('.record-turn:not([hidden]) blockquote')].map(s=>s.textContent),
                        metrics:[...document.querySelectorAll('.primary-kpi strong,.metric strong')].map(s=>s.textContent),
                        overflow:document.documentElement.scrollWidth>innerWidth,
                        controls:[document.querySelector('#prevTurn').disabled,document.querySelector('#nextTurn').disabled],
                        hash:location.hash,errors:window._errors
                    }))()''', session)
                    expected = [m['body'] for m in trial['messages'] if m['sent_round'] == turn]
                    assert actual['visible'] == [[number,turn]], (name,number,turn,'selection')
                    assert actual['bodies'] == expected, (name,number,turn,'text changed')
                    messages = [m for m in trial['messages'] if m['sent_round'] == turn]
                    senders = {m['sender'] for m in messages}
                    assert actual['metrics'] == [
                        f"{sum(m['sent_round'] <= turn for m in trial['messages']):,}通",
                        f"{sum(d['round'] <= turn for d in trial['decisions']):,}件",
                        f'{len(messages):,}通', f'{len(senders)} / 4',
                        f'{4-len(senders)}件', f"{sum(len(m['to']) for m in messages):,}件",
                        f"{sum(bool(m.get('reply_to')) for m in messages):,}通",
                        f"{sum(len(m['body']) for m in messages):,}字",
                    ], (name,number,turn,actual['metrics'])
                    assert browser.evaluate("document.querySelectorAll('#sovereignty,#homeostasis').length",session) == 0
                    assert not actual['overflow'] and not actual['errors'], (name,actual)
                    assert actual['controls'] == [turn==1,turn==8]
                    assert actual['hash'] == f'#run={number}&turn={turn}'
                    geometry = browser.evaluate('''(() => {
                        const earth=document.querySelector('.earth-panel'), group=document.querySelector('.earth-metrics'), metrics=group.getBoundingClientRect(), e=earth.getBoundingClientRect();
                        return {insideEarth:group.parentElement===earth,
                            adjacent:group.previousElementSibling===earth.querySelector('.primary-kpis'),
                            below:metrics.top>=earth.querySelector('.primary-kpis').getBoundingClientRect().bottom,
                            contained:metrics.left>=e.left && metrics.right<=e.right && metrics.bottom<=e.bottom,
                            cards:[...group.querySelectorAll('.metric')].map(n=>{const r=n.getBoundingClientRect();return r.left>=metrics.left-1 && r.right<=metrics.right+1}),
                            worldBeforeAgents:document.querySelector('.world-column').getBoundingClientRect().bottom<=document.querySelector('#agents').getBoundingClientRect().top};
                    })()''', session)
                    assert all(geometry[k] for k in ('insideEarth','adjacent','below','contained')), (name,geometry)
                    assert len(geometry['cards'])==6 and all(geometry['cards']), (name,geometry)
                    if width<=760:
                        assert geometry['worldBeforeAgents'], (name,geometry)
            # Reloadable deep link; an empty turn must not masquerade as loading.
            browser.call('Page.navigate', {'url':url+'#run=3&turn=8'}, session)
            browser.wait("document.body?.dataset.observationReady === 'true'", session)
            assert browser.evaluate("document.querySelectorAll('.record-turn:not([hidden]) .silent').length", session) == 4
            # Invalid selection never exposes another trial or silently invents a result.
            browser.call('Page.navigate', {'url':url+'#run=99&turn=-4'}, session)
            browser.wait("document.body?.dataset.observationReady === 'true'", session)
            assert browser.evaluate("document.querySelector('.record-turn:not([hidden])').dataset.trial", session) == '1'
            browser.evaluate("document.fonts.ready.then(()=>true)", session)
            shot = browser.call('Page.captureScreenshot', {'format':'png'}, session)['data']
            (out / f'v2-observation-{name}.png').write_bytes(base64.b64decode(shot))
            browser.evaluate("document.querySelector('.record-link').click()", session)
            assert browser.evaluate("location.hash", session) == '#run=1&turn=1&actor=A'
            browser.wait("Math.abs(document.querySelector('.record-turn:not([hidden]) [data-actor=A]').getBoundingClientRect().top - 110) < 2", session)
            shot = browser.call('Page.captureScreenshot', {'format':'png'}, session)['data']
            (out / f'v2-observation-records-{name}.png').write_bytes(base64.b64decode(shot))
            # Exercise the complete return journey on each viewport, not just
            # the outgoing links on the additional-runs page.
            for version in ('v1','v2'):
                follow_version_link(browser, session, f'dashboard_{version}.html')
                browser.wait(f"location.pathname.endsWith('/dashboard_{version}.html') && !!window.HomeostasisLayout && !!document.querySelector('.rn-spine')", session)
                browser.evaluate('window.HomeostasisLayout.assertIntegrity()',session)
                nav = browser.evaluate('''(() => {
                    const n=document.querySelector('.version-switch');
                    const boxes=[...n.children].map(a=>a.getBoundingClientRect());
                    return {count:boxes.length,inside:boxes.every(r=>r.left>=0 && r.right<=innerWidth),
                        overlap:boxes.some((a,i)=>boxes.slice(i+1).some(b=>a.left<b.right && a.right>b.left && a.top<b.bottom && a.bottom>b.top))};
                })()''', session)
                assert nav == {'count':3,'inside':True,'overlap':False}, (name,version,nav)
                if version == 'v2':
                    # Original V2: retain its own six scores and bars, directly
                    # below Earth and above the V1 → 16 conditions → V2 narrative.
                    for saved_turn in original_v2['turns']:
                        t = saved_turn['turn']
                        browser.evaluate(f"document.querySelector('[data-turn=\"{t}\"]').click()",session)
                        browser.wait(f"document.querySelector('#turnNumber').textContent.trim()==='{t}'",session)
                        actual = browser.evaluate('''(() => {
                            const m=document.querySelector('#metrics'), h=m.previousElementSibling,
                                world=document.querySelector('.hero'), r=document.querySelector('#homeostasisResearchLayer');
                            return {order:h.previousElementSibling===world && m.nextElementSibling===r,
                                title:h.textContent,
                                below:h.getBoundingClientRect().top>=world.getBoundingClientRect().bottom,
                                before:m.getBoundingClientRect().bottom<=r.getBoundingClientRect().top,
                                labels:[...m.querySelectorAll('.metric>span')].map(n=>n.textContent),
                                values:[...m.querySelectorAll('strong')].map(n=>n.textContent),
                                bars:[...m.querySelectorAll('.mini i')].map(n=>n.style.width)};
                        })()''',session)
                        values = [saved_turn['world_state'][k] for k in
                                  ('food','energy','economy','environment','international_trust','conflict_load')]
                        assert actual == {'order':True,'title':'GLOBAL STATE｜地球全体の6指標',
                            'below':True,'before':True,
                            'labels':['食料','エネルギー','経済','環境','国際信頼','紛争負荷'],
                            'values':[f'{v:.1f}' for v in values],
                            'bars':[f'{v}%' for v in values]}, (name,t,actual)
                        if t == 2:
                            browser.evaluate("document.querySelector('#metrics').previousElementSibling.scrollIntoView({block:'center',behavior:'instant'})",session)
                            shot=browser.call('Page.captureScreenshot',{'format':'png'},session)['data']
                            (out / f'v2-global-metrics-{name}.png').write_bytes(base64.b64decode(shot))
                follow_version_link(browser, session, 'results/v2-five-runs/index.html')
                browser.wait("location.pathname.endsWith('/results/v2-five-runs/index.html') && document.body?.dataset.observationReady === 'true'", session)
                assert browser.evaluate("document.querySelector('#trialSelect').options.length",session) == 5
            records.append({'viewport':name,'selections_verified':40,'original_messages_verified':163,'return_journeys':['v1','v2'],'original_v2_metric_turns':5})
            browser.call('Target.closeTarget', {'targetId':target})
        # Entry point remains the existing V2 page and its approved content slot.
        target = browser.call('Target.createTarget', {'url':'about:blank'})['targetId']
        session = browser.call('Target.attachToTarget', {'targetId':target,'flatten':True})['sessionId']
        browser.call('Page.enable', session=session)
        browser.call('Fetch.enable', {'patterns':[{'urlPattern':'*'}]}, session)
        browser.call('Page.navigate', {'url':base+'/dashboard_v2.html'}, session)
        browser.wait("!!document.querySelector('[data-content-id=\"v2-five-dialogue-runs\"] a')", session)
        assert browser.evaluate("document.querySelector('[data-content-id=\"v2-five-dialogue-runs\"] a').getAttribute('href')", session) == 'results/v2-five-runs/index.html'
        browser.evaluate('window.HomeostasisLayout.assertIntegrity()',session)
        assert not browser.blocked, browser.blocked
    (out/'v2-observation.json').write_text(json.dumps(records,indent=2)+'\n')
    print('V2 observation: 120 selections, saved-record counts, V1/V2 return journeys and original V2 metrics across 15 viewport/turn states PASS')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url')
    args = parser.parse_args()
    if args.url:
        check(args.url.rstrip('/'))
        return
    server = http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(QuietHandler,directory=str(ROOT)))
    threading.Thread(target=server.serve_forever,daemon=True).start()
    try:
        check(f'http://127.0.0.1:{server.server_port}')
    finally:
        server.shutdown()
        server.server_close()


if __name__ == '__main__':
    main()
