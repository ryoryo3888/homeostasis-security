# Approved public version names

Rio selected 「V3 自由対話にしたら？？？」 and confirmed that the unfinished
former V3 should simply be called V4. This supersedes the unpublished
「V2：自由対話」 label proposal. The previous published base is
`52ba16eb62997c6f00785a1d2a2e029213be5417`.

| Public name | Page | Saved implementation lineage |
| --- | --- | --- |
| V1：二国間の恒常性 | `dashboard_v1.html` | unchanged |
| V2：地球規模の恒常性 | `dashboard_v2.html` | unchanged |
| V3：自由対話 | `results/v2-five-runs/index.html` | five saved V2 dialogue trials, eight turns each |
| V4：相互依存（制作中） | `dashboard_v4.html` | former V3 finite-resource model |

The old `dashboard_v3.html` bookmark continues to open the same unfinished
model, now labelled V4. Both model pages are generated as identical documents.
Historical paths, schema versions, saved data, hashes and internal identifiers
remain intact. Renumbering is a presentation change, not a new experiment or
a claim that the unfinished model is complete.

The dialogue page title, brand, navigation buttons and its V2 content-slot
entry use V3. The unfinished model's title, brand, navigation and explanatory
labels use V4. Its existing three navigation buttons retain their layout.
The model template exception reverses only six exact, approved replacements
before checking the historical source hash. Frozen CSS, Earth assets, geometry
baselines, simulation rules and result records are not replaced.

Changed rendering functions: `build_html()` (dialogue identity) and `main()`
in `build_v3_candidate.py` (identical current/compatibility URLs).
`original_template()` documents the exact display exception; validation still
rejects unrelated edits. No simulation function changes.

Verification uses targeted layout/observation tests and the complete `make check`,
including original V1/V2 navigation, all 40 dialogue states at three viewports,
the unfinished model's four viewport/frame/interaction checks and saved
validation examples. After CI and deployment, verify public documents against
the tested source and repeat browser navigation checks. No paid API calls.

README keeps its historical prefix and appends the current version map. Only
its non-source documentation checksum is renewed in the artifact allowlist;
all experiment/evidence hashes and eligibility flags stay unchanged.
