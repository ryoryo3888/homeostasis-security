# V6 Q1-13TURN milestone

Status: Q1 A/B analysis complete; offline replication is not complete.

- Scope: paired A/B worlds, TURN 1–13, DAY 91.
- Q1 original: frozen read-only outside this repository.
- Freeze manifest SHA-256: `a0ae901e08b5c6d440aed529ff2ffe977eb84b560e301d53ac629b183bddf262`
- Baseline replay: A PASS, B PASS after a replay-runner-only turn-specific archive mapping fix.
- API/LLM after Q1: 0 calls.
- 10 paired seeds: not run.
- 100 paired seeds: not run.
- 1000 paired seeds: not run.

The original Q1 raw set is retained in the frozen artifact store rather than copied into this repository. The manifest, hashes, analysis, preregistration, and replay status above provide the public traceability anchor without committing credentials, local paths, or raw response payloads.

## Replay fix

The offline replay runner previously considered the TURN 9 partial archive while resolving TURN 6 responses. Archive selection is now constrained by the requested turn. The frozen Q1 and V6 world logic were not changed.

## What Q1 establishes

Q1 documents one observed A/B trajectory and its evidence-linked propagation. It does not establish a population-level causal effect or robustness across physical uncertainty. Those claims remain pending the preregistered offline paired-seed phases.
