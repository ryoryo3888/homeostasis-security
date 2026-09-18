# V3 saved validation observation view

User-authorized reuse of existing V3 validation records. No new simulation,
Agent, replay or API request is executed. This is **not formal research**.

## Sources and classification

The original files remain in the separate Codex project workspace under
`.artifacts/v3-preflight-20260918-verified` and
`.artifacts/v3-agent-sdk-20260918-final`. The former has eight abstention TURNs,
source commit `b4adb20`; the latter has three TURNs each of conditional exchange,
all-refuse and missing-offer, source commit `7f69d43`. Full source revisions and
file hashes are recorded in the export. All report `api_calls=0`,
`artifact_class=validation_run`, `research_eligible=false`. Mock SDK dispatches
are not remote API calls. A case name is a fixture definition, not an inferred
national role or research finding.

The importer checks every saved observation with `verify_observation`, supplying
exactly its declared source checkpoints, and checks the original execution source
hashes against Git history. It does not execute the saved TURN inputs. All 17
observations pass recomputation. Original files are never written.

## Published evidence boundary

`ui/v3/validation/evidence.json` contains only selected world/account, input
selection, settlement, shipment, consumption, production and conservation
records. Each excerpt retains its original checkpoint digest, JSON pointer and
value digest. Source observation/checkpoint file hashes and code provenance are
retained. No complete checkpoint tree, SDK objects, credentials, transport
journal or private reasoning is copied. Public reasons are synthetic fixture
text. Secret scanning rejects an export rather than silently editing evidence.

`manifest.json` pins the exact exported file-byte hash. This is a dedicated
**validation display export**, not Registry registration, research eligibility or
approval to publish the originals. The existing research Registry is untouched.
The originals remain withheld. CI verifies excerpt hashes, cross-record Choice
consistency, semantic quantities and deterministic view conversion; full original
observation recomputation occurred at import and is not claimed to run from the
reduced public export. Checksums detect changes; they are not authenticity signatures.

`tools/build_v3_validation.py` is pure except for explicitly writing generated
view files. `--import-saved` is a one-time read of the original directory and
refuses overwriting an existing export. Normal builds need only the pinned export,
not private paths or network access.

## UI and frame

The isolated viewer mounts in `METRICS_EVIDENCE`, below the protected world.
The default page retains the synthetic initial world and disabled formal TURN
controls. The lower viewer has independent case/TURN/state selectors, always
labelled validation data / synthetic judgments. `#v3-validation` opens it directly.
Its TURN selection never changes the upper initial-world display and never calls
an engine. No formal-result mode is provided.

Demand shortage differs from unsettled requested quantity. Settled, dispatched
and arrived quantities remain separate. Shipments from previous TURNs remain
visible; pending receipt is not domestic stock. No Choice submission does not
imply explicit refusal. Conditions, consents, reason codes and exact materialized
intent are available through disclosure. World resource conservation and
production inputs/output are shown separately from national balances.

Source template, main stylesheet, Earth asset and V1/V2 are byte-identical to the
approved baseline. Only lower content grows. Existing layout guards stay enabled.
All text uses textContent. Data/scripts/styles are bundled atomically into V3 to
preserve the Safari cache repair. No fetch, automatic playback or persisted user
selection is introduced.

## Limits

This view validates observation plumbing, not the behavior of real Gemini
countries. It cannot support research conclusions about cooperation or recovery.
No causal claims or invented missing observations are added. Formal V3 publication
still requires its own runner provenance, audit and Registry/publication gates.
