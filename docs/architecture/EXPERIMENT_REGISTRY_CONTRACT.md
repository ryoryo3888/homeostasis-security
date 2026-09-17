# Experiment Registry / integration contract

FRAME = FIXED. EXPERIMENTS = EXTENSIBLE. WORLD = ALIVE.

The registry indexes evidence. It does not run experiments, generate findings,
rewrite originals, or publish UI. Freezing V1/V2's frame does not freeze their
research. Future replications, changed seeds/conditions, counterfactuals,
ablations, stress tests and comparisons can be independently cataloged.

## Authority and artifacts

- `research/experiments/registry.json`: versioned catalog, schema version 1.
- `registry.schema.json`: Draft 2020-12 schema, no remote schema references.
- `artifact_allowlist.json`: individually reviewed, tracked artifacts, SHA-256,
  version, classification, source eligibility, and review commit.
- `inventory.json`: registration scope, exclusions, absent locations and reasons.
- `tools/experiment_registry.py`: read-only schema, path, digest and relation gate.

Original artifacts remain the source of truth. A registry title/ID is an assigned
catalog label, not a claim that the original producer emitted an experiment ID.
`created_at` means the original experiment timestamp, never registration time or
Git commit time. Unrecorded timestamps/seeds are null. Type `unknown` is an
explicit epistemic value; arbitrary unrecognized types fail. V2's original
artifact does not specify the requested taxonomy, so its type stays unknown.
V1's exploratory/comparative descriptions are supported by the tracked README.

`completed` means the preserved run sequence reaches its recorded TURN count.
It is not retroactive certification by later transport/decision/contract audits.
This catalog does not confer a new research eligibility status. Existing failed,
rejected, aborted and development records are never promoted by registration.

## Provenance and counts

Experiment → `runs[].artifact` → original JSON → `turns_pointer` → TURN index →
original per-TURN decisions, world state, evaluation and evidence.
Pointers use JSON Pointer escaping (`~0`, `~1`). For example, the V1 representative
worldline's first TURN is `/results/0`, V2's is `/turns/0`; each original `turn`
number is checked. No synthetic run/worldline IDs or missing hierarchy is added.
`field_evidence` and `conditions` resolve to originals, not cloned research values.
Non-JSON documentary evidence uses an empty pointer and the full-file digest.

`run_count` and `worldline_count` count distinct referenced saved sequences
within one entry. `turn_count` is TURNs per worldline, not their sum; mixed lengths
use null. Unknown counts remain null. The representative V1 file is also part
of the 36-run study: **never add counts across overlapping catalog entries**.
The study's 36 original result arrays are distinct and membership follows
`summary.conditions[].files`, including the explicitly included `previous` file.
A filename alone neither establishes nor invalidates research status.

The summary's `api_used=false` describes aggregation, not the original Gemini
runs. The registry does not assert their API call counts. V2's textual V1 event
origin lacks a unique source run ID; its parent relation stays null.

Parent/control links are nullable, existing, non-self, same-version and acyclic.
A control must be completed. Comparison groups are explicit reciprocal member
sets with at least two same-version experiments. Condition rows inside the
existing V1 study are not fabricated into separate experiments to create a group.

## Explicit registration workflow

1. Run a separately authorized experiment outside this catalog subsystem.
2. Preserve raw output, including failure state, without rewriting old runs.
3. Use the applicable research/audit/secret validation; produce a validated
   observation. Do not interpret process exit alone as research eligibility.
4. Review source eligibility and publication safety. Only already tracked,
   approved repository artifacts may enter `artifact_allowlist.json`. Add exact
   hashes/classification intentionally; never discover-and-register via a glob.
5. Add an explicit record to `registry.json` with evidence, unknowns and limits.
   New metadata requires review; the validator cannot infer scientific truth
   from arbitrary prose or determine whether a hypothesis is justified.
6. Run `make registry-check` and `make check`; review the diff through a PR.
7. Obtain separate user/research approval for any new public observation.
8. Only then prepare content for the existing Content Slot Contract, validate it,
   and use the normal reviewed publication flow.

There is no automatic runner hook, registration write command, resume operation,
paid transport import, rendering fallback, or experiment execution in this tool.
Manual JSON + reviewed allowlist + validator is the explicit registration entry
point for this foundation. A future `register_experiment` must preserve these
boundaries and must not infer approval from completion.

## REGISTERED ≠ PUBLIC

`publication_status` is catalog metadata, not an executable authorization token.
`already_public_reference` acknowledges that existing dashboards already refer
to these originals; registration publishes no new content. Repository visibility
of a catalog is distinct from display in the Public Observatory.

The dashboards and content-slot loader do not fetch the registry. The registry
has no DOM API and cannot call `HomeostasisContent.addContent`. `ui/content.json`
remains byte-identical and empty. No unknown-slot or missing-evidence fallback is
allowed. Even `approved_for_slot` does not cause rendering automatically.

Future approved publication must use existing `HomeostasisContent.addContent`
or `ui/content.json`, with the current permitted `docs/` or `results/` evidence
paths. Root-level historical JSON is valid registry evidence, but is not a reason
to broaden the Content Slot path contract. An approved evidence document can
link to originals without modifying originals or inventing findings. This phase
adds no slot content, no V3 key and no V3 experiment.

## Path safety and validation

Only exact allowlisted, Git-tracked, existing, regular files are accepted. Digest
mismatches, any symlink component, hidden/secret/private paths, traversal,
absolute paths, external URLs, encoded/noncanonical paths and broken JSON
pointers fail. Both catalog prose and artifact text pass the existing secret
pattern scanner. Pattern scanning is not proof against every secret encoding;
manual provenance/publication review remains necessary. Do not admit private
local artifacts merely because their files exist.

Schema rejects extra fields and duplicate JSON keys, unknown versions/statuses/
types, negative or non-integer counts and inconsistent schema versions. Semantic
checks reject unapproved classifications, failed→completed promotion, unproven
seeds/counts, broken TURN sequences, invalid references/groups and cycles.
Errors exit nonzero; no partial catalog or UI fallback is emitted.

Current versions: V1 bilateral; V2 planetary; V3 multilateral/resource-network.
The old complete/final lineage is V3 scope and remains unregistered here. V3
architecture, simulation and UI work require a separate instruction.
