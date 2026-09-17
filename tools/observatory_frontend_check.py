"""Real Chromium checks of saved public evidence. Only a loopback HTTP server."""
import functools
import http.server
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import threading

ROOT = Path(__file__).resolve().parents[1]

def main():
    candidates = [shutil.which(name) for name in ('google-chrome', 'chromium', 'chromium-browser')]
    candidates.append('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')
    chrome = next((p for p in candidates if p and Path(p).is_file()), None)
    if not chrome:
        raise RuntimeError('Chromium is required for frontend verification')
    finished = threading.Event()
    result = []
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def do_POST(self):
            if self.path != '/__observatory_test_result':
                self.send_error(404)
                return
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size < 1024:
                self.send_error(400)
                return
            result.append(self.rfile.read(size).decode('utf-8'))
            self.send_response(204)
            self.end_headers()
            finished.set()
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Quiet, directory=str(ROOT)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    env = {k:v for k,v in os.environ.items() if not any(word in k.upper() for word in ('KEY','TOKEN','SECRET','PASSWORD'))}
    try:
        with tempfile.TemporaryDirectory(prefix='observatory-browser-') as profile:
            command = [chrome, '--headless', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
                '--disable-background-networking', '--disable-component-update', '--disable-sync',
                '--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1', '--force-prefers-reduced-motion',
                '--user-data-dir='+profile, '--remote-debugging-port=0',
                f'http://127.0.0.1:{server.server_port}/tests/frontend/index.html']
            with tempfile.TemporaryFile() as errors:
                process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=errors, env=env)
                try:
                    done = finished.wait(40)
                finally:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                if not done:
                    raise RuntimeError('Browser did not report completed frontend checks')
                if not re.fullmatch(r'OBSERVATORY PASS \d+', result[0]):
                    raise RuntimeError(result[0])
                print(result[0] + '; Gemini API calls: 0')
    finally:
        server.shutdown()
        server.server_close()

if __name__ == '__main__':
    main()
