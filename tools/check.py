"""Dependency-free discovery of unittest classes AND plain test functions."""
import importlib
import inspect
import json
import os
from pathlib import Path
import sys
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

def main():
    if os.environ.get('HOMEOSTASIS_OFFLINE') != '1':
        raise RuntimeError('Use make check (offline guard required)')
    files = [*ROOT.glob('*.py'), *ROOT.glob('homeostasis_core/*.py'),
             *ROOT.glob('tools/**/*.py'), *ROOT.glob('tests/**/*.py')]
    for path in files:
        compile(path.read_bytes(), str(path), 'exec')
    # Legacy V1 imports its SDK at module load. Supply an explicit offline
    # stand-in; tests inject fake clients, accidental real construction fails.
    from types import ModuleType, SimpleNamespace
    google = ModuleType('google'); genai = ModuleType('google.genai')
    types = ModuleType('google.genai.types')
    def forbidden_client(*args, **kwargs):
        raise RuntimeError('Real Gemini SDK forbidden during check')
    genai.Client = forbidden_client
    types.HttpOptions = SimpleNamespace
    types.HttpRetryOptions = SimpleNamespace
    genai.types = types; google.genai = genai
    sys.modules.update({'google': google, 'google.genai': genai, 'google.genai.types': types})
    suite = unittest.TestSuite()
    for path in sorted([*ROOT.glob('test_*.py'), *ROOT.glob('tests/**/test_*.py')]):
        module = importlib.import_module('.'.join(path.relative_to(ROOT).with_suffix('').parts))
        suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(module))
        for name, function in inspect.getmembers(module, inspect.isfunction):
            if name.startswith('test_') and function.__module__ == module.__name__:
                suite.addTest(unittest.FunctionTestCase(function))
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    from preflight_emergent import run_preflight, print_verdict
    preflight = run_preflight()
    print_verdict(preflight)
    sdk = subprocess.run([sys.executable, '-B', str(ROOT/'tools/sdk_transport_check.py')], cwd=ROOT)
    passed = result.wasSuccessful() and preflight['status'] == 'PASS' and sdk.returncode == 0
    from homeostasis_core.observability import source_digest
    report = {'source_digest': source_digest(ROOT), 'status': 'PASS' if passed else 'FAIL', 'tests': result.testsRun,
              'sdk_transport': 'PASS' if sdk.returncode == 0 else 'FAIL', 'sdk_transport_tests': 4,
              'api_calls': 0, 'network': 'blocked by Python audit hook', 'preflight': preflight}
    Path('results/debug/check.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print('HOMEOSTASIS PREFLIGHT ' + ('PASSED' if passed else 'FAILED'))
    return 0 if passed else 1

if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception:
        Path('results/debug').mkdir(parents=True, exist_ok=True)
        Path('results/debug/check.json').write_text(json.dumps({'status': 'FAIL', 'api_calls': 0}))
        print('HOMEOSTASIS PREFLIGHT FAILED')
        raise
