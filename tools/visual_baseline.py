"""Compare retained UI baselines after reversing explicitly approved additions."""
from pathlib import Path
from tools.navigation_revision import original_navigation
from tools.v2_metrics_position_revision import original_anchor
from tools.v2_turn_width_revision import original_turn_width
LOADER='<script src="ui/layout-guard.js"></script>\n<script src="ui/content-slots.js"></script>\n'
def protected_bytes(path: Path) -> bytes:
    data=path.read_bytes()
    versions = {'dashboard_v1.html':'v1','dashboard_v2.html':'v2',
                'preview_v1_unified.html':'v1','preview_v2_unified.html':'v2'}
    if path.name in versions:
        if data.count(LOADER.encode())>1:raise ValueError('Duplicate protection loader')
        data=data.replace(LOADER.encode(),b'',1)
        data=original_navigation(data, versions[path.name])
        if versions[path.name] == 'v2':
            data=original_turn_width(data)
    if path.name in versions or path.name == 'homeostasis-research-layer.js':
        data=original_anchor(data)
    return data
