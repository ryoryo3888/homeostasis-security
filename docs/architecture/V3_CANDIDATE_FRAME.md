# V3 Phase 7A — Candidate Visual Frame

Status: **CANDIDATE**. User visual approval is pending. This is not the approved
V3 visual baseline and does not update any V1/V2 baseline.

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
- Earth is a static Natural Earth land-dot projection with illustrative lighting;
  it is not a metric or the location of any synthetic country. No false network
  is baked into the globe image. No pulse pretends to be Homeostasis.
- Read-only controls are disabled because no formal worldline exists. The page
  has no API dispatch, simulation or automatic advance code.

## Candidate checks

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
