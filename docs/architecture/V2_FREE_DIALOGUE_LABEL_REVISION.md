# Approved V2 navigation label

Rio selected 「自由対話にする」 after the proposed name 「V2：自由対話」.
Relative to published commit `52ba16eb62997c6f00785a1d2a2e029213be5417`,
replace only the button text `v2追加：5回分` with `V2：自由対話` on
V1, original V2 and the five-trial observation page, including generated previews.

The link destinations, selected states, page titles, experiment metadata,
saved results and all CSS/JavaScript behavior remain unchanged. The five trials
and eight turns per trial remain identified in the experiment information.

`tools/navigation_revision.py` retains its exact-fragment protection with the
approved label. Historical source hashes and visual baselines are not replaced.
`build_html()` in `tools/build_v2_observation.py` emits the same label for the
active button. The existing browser return journeys verify the label, clickable
links and non-overlapping navigation on desktop, iPad and phone.

Validation: targeted layout/observation tests, the complete `make check`, then
the same navigation journeys against the published site. No experiment or
paid API execution is part of this change.
