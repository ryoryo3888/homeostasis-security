# V3 Phase 7A — Candidate Visual Frame

Status: **CANDIDATE**. User visual approval is pending. This is not the approved
V3 visual baseline and does not update any V1/V2 baseline.

## 2026-09-18 common-frame correction

The first published candidate (PR #20, `b0ca4da`) was rejected as visually
inconsistent with the completed V1/V2 pages. The user's current direction
supersedes the earlier allowance for an independently designed V3 frame:
research evolves, while the established HOMEOSTASIS SECURITY frame is inherited.

The revised candidate inherits the approved V2 shell's 1500px maximum width,
14px desktop outer margin, dark radial background, 14px panel corners, cyan
borders, panel gradients/shadows, 20px identity and 17px SIMULATION CONTROL.
The upper frame is `brand + context panels → control panel → Earth world`.
V3 context replaces the historical V2 event; it never reuses V2 outcomes.
Eight state cards flank the central Earth/system-field panel. Their stocks are
initial definitions, not TURN observations. Exact resources and dependencies
remain in the existing lower slots. Earth's DOM parent is unchanged.

The central Earth inherits `earth_japan_network_v2.png`, statically rendered.
All embedded lights, satellites and lines are decorative. Only the separate
dashed SVG routes represent the 18 defined V3 transport paths. This boundary
is stated in the image alternative text and evidence section.

The 760px desktop world reserves space below the 490px maximum Earth for its
caption and four unobserved metrics; no card may overlap either. The world is
640px at tablet widths and 530px on narrow screens. These are candidate
geometry choices, not an approved replacement of V1/V2 geometry. The context
panel is omitted on narrow screens to keep Earth in the first viewport.

The browser check compares live computed shell, background, panel, identity
and control styles directly against V2 at the same four viewports. It also
rejects Earth/caption/metric overlap. No existing pixel baseline is regenerated.
Local screenshots under `.artifacts/layout/` accompany review. V1/V2 sources,
simulations, scenario definitions and formal research records remain unchanged.

The [Visual Constitution](HOMEOSTASIS_VISUAL_CONSTITUTION.md) applies: a new
feature must not move an existing world. This candidate adds a separate page,
`dashboard_v3.html`, isolated CSS/JS, and named detail slots. It does not load or
modify the V1/V2 shared rendering layers. V3 navigation links to the unchanged
V1/V2 pages; the existing V1/V2 navigation is not rewritten to add a V3 link.

Candidate frame order:
`#v3-identity → #v3-control → #v3-world → #v3-state-detail → research question → #v3-evidence`.
`#v3-earth` remains inside `#v3-canvas` inside `#v3-world`. State nodes and route
paths are created inside their existing containers; no frame node is relocated.
Future content must enter a named detail slot: STATE_DETAIL, NETWORK_DETAIL or
METRICS_EVIDENCE. Content is not inserted before the control or Earth.

## Data and visual semantics

- Only the existing Phase 2/3 synthetic initial baseline/network is read.
  `tools/build_v3_candidate.py` is a pure view-model conversion, never a TURN run.
- A–H map to the source countries in their stable baseline order. All countries
  share the same glyph and typography. Initial selection of A is a UI focus,
  not a world role or preferred choice. Mapping is available under evidence.
- Stock bars use a common scale per resource: the largest initial stock among
  the eight states. Food and energy have different units and separate scales.
  The exact amounts, demand and production capacity are in state detail.
- All transport routes are dashed existence paths. Stroke width is
  `0.6 + 1.8 * route.capacity / maximum_route_capacity` CSS pixels. Selection
  changes emphasis only. There is no moving flow, invented utilization, policy
  ranking or highlighted future crisis. Direction is present in the path tip
  and the A→B text list. Shared capacity and exact route IDs are in source data.
- Production-input dependencies remain distinct in an expandable detail.
- Formal TURN, fulfillment, shortage, transit and Agent judgment are unobserved.
  No fixture outcome or Phase 6 test observation is published as research.
- Earth uses the static V2 visual asset as described above. Its decorative
  network is not V3 transport evidence or the location of a synthetic country.
  No pulse pretends to be Homeostasis. The former Natural Earth SVG and its
  generator remain historical candidate assets; the revised page does not use it.
- Read-only controls are disabled because no formal worldline exists. The page
  has no API dispatch, simulation or automatic advance code.

## Candidate checks

Safari loading/layout repair (2026-09-18): `ui/v3/page.html` is the editable
markup source. `build_v3_candidate.py` now emits a single `dashboard_v3.html`
containing the exact CSS, script and validated synthetic baseline together.
No separate JSON fetch or CSS/JS cache entry is needed to initialize the view.
The baseline JSON remains a generated evidence artifact. The Earth square uses
percentage padding with absolutely positioned image/aurora layers, avoiding
percentage-height/aspect-ratio differences. Both layer rectangles are checked.
`tools/check_v3_webkit.cjs` optionally verifies all four viewport sizes through
Playwright WebKit with every separate `/ui/v3/` request configured to fail.
This supplements Chrome checks; it does not claim access to the user's Safari
cache or an exact reproduction of their browser's failure.

User visual revision (2026-09-18): reduce the V3 globe to V2 scale (368px
maximum, responsive within the existing eight-state frame). Keep its center
and surrounding cards in place. V1 retains state communications, V2 retains
satellites, and V3 adds gently moving green/cyan/violet aurora curtains. The
aurora is decorative, independent of all research measurements, hidden from
assistive technology, and static with reduced motion enabled. It is rendered
as SVG/CSS over the existing Earth asset; no image or V1/V2 edits are needed.

`tools/check_v3_candidate.py` checks desktop 1440×1000, iPad landscape
1024×1366, iPad portrait 768×1024 and narrow 390×844: frame order/parents,
Earth-centered composition, eight visible nodes, no horizontal document
 overflow, no Earth-node overlap, baseline status, route count, keyboard state
selection, route emphasis, disabled TURN controls and reduced motion. Screenshots
are supporting evidence in `.artifacts/layout/v3-*`; no approved pixel baseline
is created. V1/V2 retain their independent existing exact layout tests.

The candidate is published through PR/CI/Pages for user visual review. Approval
of this commit is not approval of a final V3 visual baseline. No next phase or
formal Simulation is started.
