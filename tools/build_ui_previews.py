from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSS = (ROOT / "homeostasis-ui-system.css").read_text(encoding="utf-8")
MARK = "<!-- HOMEOSTASIS_UI_SYSTEM_PREVIEW -->"

for version in ("v1", "v2"):
    source = ROOT / f"dashboard_{version}.html"
    target = ROOT / f"preview_{version}_unified.html"
    html = source.read_text(encoding="utf-8")
    if MARK in html:
        raise SystemExit(f"Refusing to modify already-previewed source: {source}")
    injection = f"\n{MARK}\n<style>\n{CSS}\n</style>\n"
    if "</head>" not in html:
        raise SystemExit(f"Missing </head>: {source}")
    preview = html.replace("</head>", injection + "</head>", 1)
    target.write_text(preview, encoding="utf-8")
    print(f"built {target.name} from {source.name}")
