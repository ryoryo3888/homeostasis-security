"""Read-only Chromium layout contract runner. No simulation or paid transport imports."""
from __future__ import annotations
import argparse
import base64
import functools
import http.server
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import time
import urllib.request
from urllib.parse import urlsplit
from websockets.sync.client import connect

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = json.loads((ROOT / 'tests/layout/layout_contract.json').read_text())
PROBE = (ROOT / 'tests/layout/probe.js').read_text()

class Browser:
    def __enter__(self):
        self.profile = tempfile.TemporaryDirectory(prefix='homeostasis-layout-')
        chrome = os.environ.get('CHROME_BIN') or shutil.which('google-chrome') or shutil.which('chromium') or '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
        env = {k:v for k,v in os.environ.items() if not any(x in k.upper() for x in ('KEY','TOKEN','SECRET','PASSWORD'))}
        self.browser_log = tempfile.TemporaryFile(mode='w+b')
        self.process = subprocess.Popen([chrome,'--headless','--disable-gpu','--no-first-run','--disable-background-networking','--disable-component-update','--remote-debugging-port=0','--user-data-dir='+self.profile.name,'about:blank'],env=env,stdout=subprocess.DEVNULL,stderr=self.browser_log)
        portfile = Path(self.profile.name)/'DevToolsActivePort'
        until = time.monotonic()+20
        while not portfile.exists():
            if self.process.poll() is not None or time.monotonic()>until:
                self.process.terminate()
                self.process.wait(timeout=4)
                self.browser_log.seek(0)
                diagnostic=self.browser_log.read().decode('utf-8',errors='replace')[-4000:]
                self.browser_log.close();self.profile.cleanup()
                raise RuntimeError('Chromium did not start: '+diagnostic)
            time.sleep(.1)
        port, endpoint = portfile.read_text().splitlines()[:2]
        self.ws = connect('ws://127.0.0.1:'+port+endpoint,max_size=30_000_000)
        self.counter = 0
        self.blocked = []
        return self

    def call(self, method, params=None, session=None):
        self.counter += 1
        request_id = self.counter
        message = {'id':request_id,'method':method,'params':params or {}}
        if session: message['sessionId']=session
        self.ws.send(json.dumps(message))
        while True:
            result=json.loads(self.ws.recv(timeout=30))
            if result.get('method')=='Fetch.requestPaused':
                req=result['params']; url=req['request']['url']
                allowed=req['request']['method']=='GET' and (url.startswith(self.allowed_origin+'/') or url.startswith('data:'))
                self.counter+=1
                action={'id':self.counter,'sessionId':result['sessionId'],'method':'Fetch.continueRequest' if allowed else 'Fetch.failRequest','params':{'requestId':req['requestId']}}
                if not allowed:
                    action['params']['errorReason']='BlockedByClient';self.blocked.append(url.split('?')[0])
                self.ws.send(json.dumps(action))
            if result.get('id')==request_id:
                if 'error' in result: raise RuntimeError(result['error'])
                return result.get('result',{})

    def evaluate(self, expression, session):
        r=self.call('Runtime.evaluate',{'expression':expression,'returnByValue':True,'awaitPromise':True},session)
        if 'exceptionDetails' in r: raise AssertionError(r['exceptionDetails'])
        return r.get('result',{}).get('value')

    def wait(self, expression, session):
        until=time.monotonic()+20
        while not self.evaluate(expression,session):
            if time.monotonic()>until: raise AssertionError('Dashboard readiness timeout')
            time.sleep(.1)

    def __exit__(self,*_):
        self.ws.close(); self.process.terminate()
        try:self.process.wait(timeout=4)
        except subprocess.TimeoutExpired:self.process.kill();self.process.wait()
        self.browser_log.close();self.profile.cleanup()

def collect(base, output_dir=None, exercise=False):
    records=[]
    with Browser() as browser:
        parts=urlsplit(base);browser.allowed_origin=parts.scheme+'://'+parts.netloc
        for version, config in CONTRACT['versions'].items():
            for viewport in CONTRACT['viewports']:
                target=browser.call('Target.createTarget',{'url':'about:blank'})['targetId']
                session=browser.call('Target.attachToTarget',{'targetId':target,'flatten':True})['sessionId']
                browser.call('Page.enable',session=session)
                browser.call('Fetch.enable',{'patterns':[{'urlPattern':'*'}]},session)
                browser.call('Emulation.setDeviceMetricsOverride',{'width':viewport['width'],'height':viewport['height'],'deviceScaleFactor':1,'mobile':False},session)
                browser.call('Emulation.setEmulatedMedia',{'features':[{'name':'prefers-reduced-motion','value':'reduce'}]},session)
                browser.call('Page.navigate',{'url':base+'/dashboard_'+version+'.html'},session)
                browser.wait("!!document.querySelector('.rn-spine') && !!document.querySelector('[data-rn=\"3\"]') && !document.querySelector('#rnD').textContent.includes('読み込み中…')",session)
                # Test-only deterministic animation frame. Not shipped CSS.
                browser.evaluate("(()=>{const s=document.createElement('style');s.textContent='*{animation:none!important;transition:none!important;scroll-behavior:auto!important}';document.head.append(s)})()",session)
                browser.evaluate('document.fonts.ready.then(()=>true)',session)
                for turn in [1,3,config['last_turn']]:
                    browser.evaluate(f"document.querySelector('[data-turn=\"{turn}\"]').click();window.scrollTo(0,0)",session)
                    browser.wait(f"document.querySelector('{config['turn_selector']}').textContent.trim()==='{turn}'",session)
                    time.sleep(.1)
                    snapshot=browser.evaluate(f'({PROBE})({json.dumps(config)})',session)
                    records.append({'version':version,'viewport':viewport,'state':turn,**snapshot})
                    if output_dir and turn==1:
                        output_dir.mkdir(parents=True,exist_ok=True)
                        shot=browser.call('Page.captureScreenshot',{'format':'png'},session)['data']
                        (output_dir/f'{version}-{viewport["name"]}.png').write_bytes(base64.b64decode(shot))
                browser.evaluate("document.querySelector('[data-rn=\"3\"]').click()",session)
                browser.wait(f"document.querySelector('{config['turn_selector']}').textContent.trim()==='3'",session)
                if exercise:
                    script=(ROOT/'tests/layout/adversarial.js').read_text()
                    result=browser.evaluate(script,session)
                    print(version,viewport['name'],'guard tests:',result,flush=True)
                print(version,viewport['name'],'structure/layout/interaction PASS',flush=True)
                browser.call('Target.closeTarget',{'targetId':target})
        if browser.blocked: raise AssertionError('Unexpected external/non-GET requests: '+repr(browser.blocked))
    return records

def compare(expected, actual):
    if len(expected)!=len(actual):raise AssertionError('Snapshot count differs')
    def walk(a,b,path):
        if isinstance(a,(int,float)) and not isinstance(a,bool):
            if not isinstance(b,(int,float)) or abs(a-b)>.05:raise AssertionError(f'{path}: {a} != {b}')
        elif isinstance(a,dict):
            if a.keys()!=b.keys():raise AssertionError(f'{path}: keys differ')
            for key in a:walk(a[key],b[key],f'{path}/{key}')
        elif isinstance(a,list):
            if len(a)!=len(b):raise AssertionError(f'{path}: length differs')
            for i,(x,y) in enumerate(zip(a,b)):walk(x,y,f'{path}/{i}')
        elif a!=b:raise AssertionError(f'{path}: values differ')
    walk(expected,actual,'baseline')

class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self,*_):pass

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--url');p.add_argument('--output',type=Path,required=True)
    p.add_argument('--compare',type=Path);p.add_argument('--exercise',action='store_true')
    args=p.parse_args()
    server=None
    if args.url:base=args.url.rstrip('/')
    else:
        server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(QuietHandler,directory=str(ROOT)))
        threading.Thread(target=server.serve_forever,daemon=True).start()
        base=f'http://127.0.0.1:{server.server_port}'
    try:
        records=collect(base,args.output.parent/'screenshots',args.exercise)
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps({'baseline_sha':CONTRACT['baseline_sha'],'records':records},ensure_ascii=False,indent=2)+'\n')
        if args.compare:compare(json.loads(args.compare.read_text())['records'],records);print('PUBLIC VISUAL CHANGE = 0 (DOM, computed layout, content, bounds)',flush=True)
    finally:
        if server:server.shutdown();server.server_close()
if __name__=='__main__':main()
