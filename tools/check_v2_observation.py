"""Exercise every published V2 trial/turn with all external requests blocked."""
import argparse
import base64
import functools
import http.server
import json
import threading
from urllib.parse import urlsplit

from check_layout import Browser, QuietHandler, ROOT


def check(base):
    data = json.loads((ROOT / 'results/v2-five-runs/data.json').read_text())
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
            assert browser.evaluate("[...document.querySelectorAll('.version-switch a')].map(a=>a.textContent)", session) == ['v1：二国間の恒常性','v2：地球規模の恒常性']
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
                    assert actual['metrics'] == ['未測定'] * 8
                    assert not actual['overflow'] and not actual['errors'], (name,actual)
                    assert actual['controls'] == [turn==1,turn==8]
                    assert actual['hash'] == f'#run={number}&turn={turn}'
                    geometry = browser.evaluate('''(() => {
                        const earth=document.querySelector('.earth-panel'), group=document.querySelector('.earth-metrics'), metrics=group.getBoundingClientRect(), e=earth.getBoundingClientRect();
                        return {sameColumn:earth.parentElement===group.parentElement,
                            adjacent:earth.nextElementSibling===group, below:metrics.top>=e.bottom,
                            aligned:Math.abs(metrics.left-e.left)<1 && Math.abs(metrics.width-e.width)<1,
                            cards:[...group.querySelectorAll('.metric')].map(n=>{const r=n.getBoundingClientRect();return r.left>=metrics.left-1 && r.right<=metrics.right+1}),
                            worldBeforeAgents:document.querySelector('.world-column').getBoundingClientRect().bottom<=document.querySelector('#agents').getBoundingClientRect().top};
                    })()''', session)
                    assert all(geometry[k] for k in ('sameColumn','adjacent','below','aligned')), (name,geometry)
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
            records.append({'viewport':name,'selections_verified':40,'original_messages_verified':163})
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
    print('V2 observation: 120 selections, original text, unmeasured metrics, deep links and entry point PASS')


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
