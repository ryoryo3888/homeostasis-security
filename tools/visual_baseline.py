"""Normalize only the nonvisual protection loader when comparing approved UI bytes."""
from pathlib import Path
LOADER='<script src="ui/layout-guard.js"></script>\n<script src="ui/content-slots.js"></script>\n'
def protected_bytes(path: Path) -> bytes:
    data=path.read_bytes()
    if path.name in ('dashboard_v1.html','dashboard_v2.html'):
        if data.count(LOADER.encode())>1:raise ValueError('Duplicate protection loader')
        data=data.replace(LOADER.encode(),b'',1)
    return data
