# Layout Contract — enforcement

## Artifacts

- `tests/layout/layout_contract.json`: baseline SHA, viewports, selectors, parents,
  ordered frame and observed regions.
- `tests/layout/public-baseline.json`: actual pre-change public observations,
  including content, typography and bounding rectangles, 12 states.
- `tests/layout/source_baseline.json`: hashes of completed public HTML/JS/CSS.
- `tests/layout/protected-baseline.sha256`: the original 117 protected files from
  `06a4994`. Only V1/V2 HTML hashes advance to the explicitly approved visual
  authorized baseline in `source_baseline.json`; the historical README prefix remains separately checked.
- `ui/layout-guard.js`: synchronous guards for common node relocation/removal/
  replacement methods, plus persistent MutationObserver evidence for native
  bypasses. No style or visual node is added.
- `ui/content-slots.js`, `ui/content.json`: bounded, explicit content extension.
- `tools/check_layout.py`, `tests/layout/probe.js`: isolated Chrome, DOM/computed
  layout assertions, current TURN and research-card interaction.
- `tests/layout/adversarial.js`: attempted append/prepend/before/after,
  insert/replace/remove, wrapper movement, HTML/text replacement, slot rejection,
  safe literal text insertion and native Range bypass detection.

## Runtime versus build enforcement

The guard loads before legacy runtime code, after the static world DOM exists.
It preserves actual node identity, parent identity and same-parent order.
Reparenting a wrapper that contains Earth is also forbidden. A prohibited common
DOM call throws **before mutation**. Native browser mechanisms such as Range may
mutate before an observer runs; the observer retains the violation and the CI
check fails. This is regression protection, not a security boundary against
hostile arbitrary JavaScript. The guard cannot claim to undo every browser API.

Frozen source hashes reject unreviewed new scripts, styles, wrappers and insertion
logic in the legacy dashboards, including dormant relocation code that did not
run during one test. Only the exact two protection-script tags are normalized.
The content manifest is the extension path; structural changes require explicit
baseline review. No regex pretends to prove general JavaScript safety.

The browser guard deliberately does not freeze dynamic text nodes or country
Agent output. Existing TURN changes continue normally. Generated research content
is checked after it settles. Source hashes and layout relations protect the
recovery structure without preventing V1's legitimate condition rendering.

## Commands

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements/free-check.txt
make check PYTHON=.venv/bin/python
```

An installed Chrome/Chromium is required; set `CHROME_BIN` if it is not in a usual
location. Browser checks use a separate temporary profile, no credentials, only
same-origin GET requests, and never import simulation/transport code. Unit tests
use fakes and deny Python network connections; SDK installation is for existing
mocked tests, not permission to call an API.

To verify zero visual change on the same platform as the recorded public capture:

```sh
.venv/bin/python tools/check_layout.py \
  --output .artifacts/layout/zero-change.json \
  --compare tests/layout/public-baseline.json --exercise
```

The comparison permits only 0.05 CSS pixel numerical rounding, and checks text,
parents, main order and selected computed styles. Screenshots are supplementary
and kept outside Git. No auto-update/bless-baseline command is part of `make check`.

CI runs structural/bounding **relations**, parent-child checks, 3 equal recovery
rows, typography, interactions and negative guards on Linux at both viewports.
It does not compare Mac font rasterization or exact absolute pixels with Linux.
The same-machine pre/post capture establishes this release's visual zero.
Future content growth can change research-area length; the locked world frame
and relationships must stay valid.

## Existing test portability

The prior 199-test suite depended on an absent `/tmp` hash file and used an
obsolete schema-v1 loader test against a schema-v2 scenario. The hash list is now
versioned. The loader test uses the original schema-v1 fixture from `bbbb742`;
current research scenarios and simulation code are unchanged. Python bytecode
writes are disabled because a historical tracked `.pyc` is part of the original
protected file list. No test is skipped or removed.

## Publication

`.github/workflows/layout-contract.yml` adds read-only free preflight to PRs and
main. It does not execute experiments, write commits, or deploy alternate hosting.
The existing GitHub Pages source remains `main /`. Require a green preflight
before merging; confirm the automatic Pages build and the live public contract
afterward. Secret scan reports filenames only. It is a conservative pattern
scanner, not proof against every possible secret encoding.

Copy sanitation adds seven tests in `test_copy_contract.py`: forbidden-copy rejection,
research-label retention, exact authorized source delta, stale-generator repair,
12-state approved geometry delta, Earth-movement rejection and research-loss rejection.
The immutable pre-copy snapshots remain under `tests/layout/history/`.
