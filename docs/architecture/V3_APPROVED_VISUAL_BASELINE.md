# V3 — Approved Visual Baseline

The user approved the published aurora revision (「バッチリ！」), then explicitly
instructed us to proceed with formal visual-baseline protection (「進めて！」).
This approves the existing visual frame, not a research result or paid run.

- Published source SHA: `731e184ea6481f6311d33249d909c5396a403711` (PR #29).
- Public page: https://ryoryo3888.github.io/homeostasis-security/dashboard_v3.html
- Machine authority: `ui/v3/frame.json`, status `approved`.
- Public capture: `tests/layout/v3-public-baseline.json`.
- Desktop 1440×1000; iPad 1024×1366 and 768×1024; narrow 390×844; scale 1.
- Initial synthetic state, A selected, no formal TURN. Motion reduced for geometry. Test browser scrollbars are hidden so Linux
  classic scrollbar width and macOS overlay scrollbars use the same content area;
  public scrollbar behavior is untouched.

## Locked frame

Identity/navigation → Simulation Control → Earth/world → state/network details
→ research question → evidence. Protect Earth parent, size and position, its
system field, eight country positions, control typography, and aurora layering.
The approved aurora has cyan/green, magenta and purple, with 10/14-second drift.
It is decoration, not a measurement or resource flow. Reduced motion stops it.

New content belongs in named `STATE_DETAIL`, `NETWORK_DETAIL` or
`METRICS_EVIDENCE` slots. It may expand the lower evidence area; it must not
move or resize the world/control frame. A future content-only source change
requires reviewed source-hash refresh plus unchanged locked geometry evidence.
Changing the protected frame itself requires explicit user visual authorization.
Do not auto-record a new baseline to make a failing test pass.

## Enforcement

`make check` retains V1/V2 checks and adds approved V3 comparisons. The existing
`tools/check_v3_candidate.py` filename is retained for workflow compatibility.
It compares public-captured bounds/parents/state positions/Earth layers with a
2 CSS pixel renderer-rounding tolerance, not permission to shift the design.
Exact source hashes protect the stylesheet, page template and Earth image.
Generated page consistency remains covered by the existing unit test.

The browser watches removed locked nodes from document initialization, rejecting
runtime relocation even if restored later. A disposable relocation exercise proves
the detector works. Keyboard selection, route selection and Earth stability are
checked. Normal-motion ribbon transforms and timing are verified separately from
reduced-motion geometry. Regression tests reject parent, position, size, state,
layer and source changes. Evidence below the world is intentionally not locked
to its current total height.

This is DOM/computed-layout/source protection, not a cross-browser pixel identity
claim. Existing WebKit checks remain available; this capture uses Chromium. Image
screenshots are supplementary and are not the sole pass condition.

## No visual or research changes

This promotion changes metadata, documentation and tests only. Published HTML,
CSS, JS, Earth asset, source template and synthetic data remain byte-identical.
The page's historical candidate label and embedded `visual_baseline: candidate`
are preserved as artifact provenance to avoid an unrequested copy change. Current
approval status is the frame manifest above, not a promotion of that data into
formal research. A later explicit copy revision may align that historical label.

No Agent, API, Simulation, data connection or next-phase implementation is
started by this approval. Research eligibility remains unchanged.
