"""Run the existing and layout unit suites with all Python network connections denied."""
import os
from pathlib import Path
import socket
import sys
import unittest
sys.dont_write_bytecode=True
os.environ["PYTHONDONTWRITEBYTECODE"]="1"
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
os.chdir(ROOT)
for name in list(os.environ):
    if any(part in name.upper() for part in ('API_KEY','TOKEN','SECRET','PASSWORD')):os.environ.pop(name,None)
def denied(*args,**kwargs):raise AssertionError('Network/API execution is forbidden in free tests')
socket.socket.connect=denied
socket.create_connection=denied
loader=unittest.TestLoader()
suite=unittest.TestSuite()
for directory,pattern in [('.', 'test_simulation*.py'),('tests/final','test_*.py'),('tests/layout','test_*.py')]:
    suite.addTests(loader.discover(directory,pattern=pattern))
result=unittest.TextTestRunner(verbosity=1).run(suite)
raise SystemExit(not result.wasSuccessful())
