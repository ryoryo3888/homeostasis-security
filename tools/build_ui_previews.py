import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI_CSS = (ROOT / "homeostasis-ui-system.css").read_text(encoding="utf-8")
RESEARCH_CSS = (ROOT / "homeostasis-research-layer.css").read_text(encoding="utf-8")
RESEARCH_JS = (ROOT / "homeostasis-research-layer.js").read_text(encoding="utf-8")
INTEGRATION_JS = (ROOT / "homeostasis-research-integration.js").read_text(encoding="utf-8")
MARK = "<!-- HOMEOSTASIS_UI_SYSTEM_PREVIEW -->"
RESEARCH_MARK = "<!-- HOMEOSTASIS_RESEARCH_NARRATIVE_PREVIEW -->"
INTEGRATION_MARK = "<!-- HOMEOSTASIS_RESEARCH_INTEGRATION -->"

for version in ("v1", "v2"):
    source = ROOT / f"dashboard_{version}.html"
    target = ROOT / f"preview_{version}_unified.html"
    html = source.read_text(encoding="utf-8")

    # Sources may already be the promoted unified dashboards. Keep the existing
    # visual shell and narrative; only add missing layers.
    if MARK in html or RESEARCH_MARK in html:
        integrated = html
    else:
        head_injection = f"\n{MARK}\n<style>\n{UI_CSS}\n</style>\n{RESEARCH_MARK}\n<style>\n{RESEARCH_CSS}\n</style>\n"
        body_injection = f"\n{RESEARCH_MARK}\n<script>\n{RESEARCH_JS}\n</script>\n"
        if "</head>" not in html or "</body>" not in html:
            raise SystemExit(f"Missing document boundary: {source}")
        integrated = html.replace("</head>", head_injection + "</head>", 1)
        integrated = integrated.replace("</body>", body_injection + "</body>", 1)

    if INTEGRATION_MARK not in integrated:
        if "</body>" not in integrated:
            raise SystemExit(f"Missing body boundary: {source}")
        integration = f"\n{INTEGRATION_MARK}\n<script>\n{INTEGRATION_JS}\n</script>\n"
        integrated = integrated.replace("</body>", integration + "</body>", 1)

    # Refresh owned embedded layers from their canonical sources on every build.
    # Preserve the original dashboard shell, data bindings and experiment outputs.
    for marker, tag, content in [(MARK, 'style', UI_CSS), (RESEARCH_MARK, 'style', RESEARCH_CSS),
                                 (RESEARCH_MARK, 'script', RESEARCH_JS), (INTEGRATION_MARK, 'script', INTEGRATION_JS)]:
        pattern = re.escape(marker) + r"\s*<" + tag + r">.*?</" + tag + r">"
        integrated, count = re.subn(pattern, lambda _: marker + "\n<" + tag + ">\n" + content + "\n</" + tag + ">", integrated, flags=re.S)
        if count != 1:
            raise SystemExit(f"Expected one {marker} {tag} layer, found {count}")

    # The same verified artifact is both the preview and the formal dashboard.
    # This prevents the preview/formal-version split that caused earlier drift.
    target.write_text(integrated, encoding="utf-8")
    source.write_text(integrated, encoding="utf-8")
    print(f"built and promoted {version}: {target.name} + {source.name}")