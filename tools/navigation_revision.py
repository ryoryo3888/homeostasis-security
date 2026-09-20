"""Rio-approved static return links; every other frozen source byte stays fixed.

Only these complete navigation fragments may differ from the retained baseline.
No runtime DOM relocation, arbitrary HTML stripping or replacement hash baseline.
"""
NAV = '<nav class="version-switch" aria-label="バージョン切替">'
WRAPPED_NAV = '<nav class="version-switch" aria-label="バージョン切替" style="flex-wrap:wrap">'
LINK = '<a href="results/v2-five-runs/index.html">V2：自由対話</a>'
OLD = {
    'v1': NAV + '\n      <span aria-current="page">v1：二国間の恒常性</span>\n      <a href="dashboard_v2.html">v2：地球規模の恒常性</a>\n    </nav>',
    'v2': NAV + '\n        <a href="dashboard_v1.html">v1：二国間の恒常性</a>\n        <a href="dashboard_v2.html" class="active" aria-current="page">v2：地球規模の恒常性</a>\n      </nav>',
}
NEW = {version: old.replace(NAV, WRAPPED_NAV).replace(
    '\n' + ('    ' if version == 'v1' else '      ') + '</nav>',
    '\n' + ('      ' if version == 'v1' else '        ') + LINK +
    '\n' + ('    ' if version == 'v1' else '      ') + '</nav>')
    for version, old in OLD.items()}


def add_return_link(html, version):
    if html.count(OLD[version]) != 1:
        raise ValueError('Expected exactly one original version navigation')
    return html.replace(OLD[version], NEW[version], 1)


def original_navigation(data, version):
    """Reverse only the exact approved fragment for historical hash checks."""
    approved = NEW[version].encode()
    if data.count(approved) != 1:
        raise ValueError('Approved return navigation missing or altered')
    return data.replace(approved, OLD[version].encode(), 1)
