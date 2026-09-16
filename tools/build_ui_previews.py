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

    # Sources may already be the promoted unified dashboards. In that case,
    # keep the existing shell/narrative and only add the new integration layer.
    if MARK in html or RESEARCH_MARK in html:
        preview = html
    else:
        head_injection = f"\n{MARK}\n<style>\n{UI_CSS}\n</style>\n{RESEARCH_MARK}\n<style>\n{RESEARCH_CSS}\n</style>\n"
        body_injection = f"\n{RESEARCH_MARK}\n<script>\n{RESEARCH_JS}\n</script>\n"
        if "</head>" not in html or "</body>" not in html:
            raise SystemExit(f"Missing document boundary: {source}")
        preview = html.replace("</head>", head_injection + "</head>", 1)
        preview = preview.replace("</body>", body_injection + "</body>", 1)

    if INTEGRATION_MARK not in preview:
        if "</body>" not in preview:
            raise SystemExit(f"Missing body boundary: {source}")
        integration = f"\n{INTEGRATION_MARK}\n<script>\n{INTEGRATION_JS}\n</script>\n"
        preview = preview.replace("</body>", integration + "</body>", 1)

    target.write_text(preview, encoding="utf-8")
    print(f"built {target.name} from {source.name}")