# HOMEOSTASIS Visual Constitution

## Authority and approved baseline

FRAME = FIXED. CONTENT = EXTENSIBLE.

This constitution protects the completed worlds; it is not a redesign specification.
The current approved copy revision source is commit **231fde90d6e6f0734e28ed820c28251dce236e8e**,
served by GitHub Pages from `main /`:

- https://ryoryo3888.github.io/homeostasis-security/dashboard_v1.html
- https://ryoryo3888.github.io/homeostasis-security/dashboard_v2.html

`tests/layout/public-baseline.json` records the actual published DOM relationships,
computed styles, bounds and content at desktop 1440×1000 and iPad-equivalent
1024×1366, device scale 1, for TURN 1, TURN 3 and each version's final TURN.
Animations are disabled **only in the test browser** to make the observation
reproducible. This is not a change to public motion behavior.

## LOCKED / STRUCTURAL

The following are completed architecture, not available space for new features:

- HEADER / IDENTITY and VERSION NAVIGATION.
- SIMULATION CONTROL, its place in the world, and its established typography.
- WORLD OBSERVATORY: V1 `.main-grid`; V2 `.hero`.
- EARTH and its existing parent container, representation and scale.
- V2 EARTH SYSTEM FIELD, its decorative layer, and primary world KPIs.
- PRIMARY WORLD STRUCTURE, country/coordinator panels and completed major grids.
- Major section order and the basic typography hierarchy.
- V2 recovery composition: the full-width condition band, equal left/right
  columns, causal flow with green note, and three equal-height observation cards.
- The established TURN controls and TURN-card interaction.

Adding content does not authorize move, delete, wrap changes, reorder, resize,
or runtime DOM relocation of these structures. In particular, Earth must never
be moved to make space for research or another version. Changing a source
layout and then moving it back with JavaScript is not an acceptable workaround.
No design cleanup, visual refactor, or opportunistic improvements are implied.

V1 order remains `topbar → simulation-control → main-grid → research narrative`.
V2 remains `mast → controls → hero/Earth → research narrative → existing lower sections`.
Each version retains its own visual expression. Do not force V1 and V2 into a
shared component architecture merely to satisfy this contract.

## Content slots

New research belongs to a named slot inside `#homeostasisResearchLayer`.
The slot registry is an adapter over existing DOM: it creates no empty visible
containers and does not move an existing element.

| Slot | V1 anchor | V2 anchor | Intended use |
| --- | --- | --- | --- |
| STORY_OBSERVATION | `.rn-intro` | `.rn-intro` | Context and observed phenomena |
| TURN_OBSERVATION | `.rn-turns` | `.rn-turns` | Additional TURN observations |
| RESEARCH_FINDINGS | `.rn-findings` | `.rn-say` | Findings, limits, hypotheses |
| EXPERIMENT_COMPARISON | `.rn-findings` | `.rn-compare` | Explicit comparisons |
| DEEP_RESEARCH | `#rnD > details` | `#rnD > details` | Evidence and methods |
| NEXT_WORLD | `.rn-next` | `.rn-next` | Future questions and links |

Slots can grow the research area and total page length. They cannot change the
locked world frame above it. Shared anchors in V1 are intentional; they avoid
wrapping or restructuring the completed page. Existing source material remains
in place. The baseline release's `ui/content.json` is empty: **no new research is displayed**.

Use the declarative manifest or `HomeostasisContent.addContent(slotName, record)`.
Do not accept a parent selector, raw HTML, JavaScript, CSS or an existing DOM node
as content. Unknown slots fail closed. Refer to the [insertion contract](CONTENT_SLOT_CONTRACT.md).

## Research/version policy

- **V1:** bilateral homeostasis.
- **V2:** planetary homeostasis.
- **V3:** multilateral/resource-network homeostasis.

The former “V2 complete” research direction is now treated as V3. Existing
filenames, historical results, and visible labels are not retrospectively
rewritten. `dashboard_final.html` and the final simulation lineage are historical
artifacts, not authorization to publish a new V3 UI.

V3 requires its own explicit frame and slot contract before UI implementation.
It may have a different Earth representation, worldview and research structure.
What is shared is the rule that an additional feature must not break a completed
world. This foundation does not start V3 development or authorize any API call.

## Change/review rules

1. Content-only work uses known slots and cited saved evidence. It does not edit
   frozen legacy HTML/JS/CSS or move a locked node.
2. Explicitly authorized structural work needs a separately reviewed contract
   revision with the old and proposed baselines, viewport evidence and rationale.
   Tests must not regenerate/accept a baseline just because an assertion fails.
3. `make check` must pass. A build alone is not evidence of layout integrity.
4. For a no-visual-change task, compare the same browser/viewport/state against
   the public snapshot and inspect screenshots as supporting evidence.
5. Publish through a reviewed PR to the existing Pages source. Never push an
   experimental working branch wholesale into the public site. Confirm public
   HTML and the Pages deployment afterward.

The CI check must be treated as a merge gate by maintainers. This change adds
checks but does not silently change repository branch-protection settings.

See [Layout Contract](LAYOUT_CONTRACT.md) for enforcement and limitations.

## Authorized copy sanitation revision

The user explicitly authorized FINAL META-COPY SANITATION after the initial
constitution release. `tests/layout/history/pre-copy-*` preserves the previous
baseline; `tests/layout/copy_revision.json` enumerates the exact replacements.
`docs/architecture/meta_copy_delta.json` records the 12-state difference proof.
Only viewer-directive copy was removed/relabelled. No CSS, research data,
Earth geometry, control geometry, section order or recovery composition changed.
Research blocks naturally shrink and subsequent content follows normal flow.
The empty former subtitle span remains; no spacing compensation was introduced.

The builder now refreshes the marked narrative script from its canonical source
in both dashboards. V1 previously carried an older, inactive V2 function; canonical
synchronization removes that source drift without executing V2 code in V1.
The source-delta test verifies the rest of each HTML document byte-for-byte.

`test_copy_contract.py` and the browser probe reject time/viewer directives in
current public generation paths and rendered text, including hidden evidence.
Historical reports/fixtures are not rewritten. Content/evidence labels remain.
The public baseline is reacquired after Pages deployment; the release record is
`docs/architecture/meta_copy_release.json`. V3 implementation remains unstarted.

The sanitized public baseline was reacquired from Pages at commit
**c9b436f9271b71804e27f30b72c6d057b271bdd6** (source revision `231fde9`). Both desktop/iPad
and all 12 TURN states match the verified candidate. The earlier copy-bearing
baseline is historical evidence only, not the current visual target.
