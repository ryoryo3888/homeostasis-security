# V5 Paired Diplomacy Experiment — Implementation Preflight

APIは実行していません。20runも開始していません。

## Status

`pass`

## Added minimal implementation

- `homeostasis_v5/paired_diplomacy_experiment.py`
- `homeostasis_v5/world_law_settlement.py`
- `tests/v5/test_paired_diplomacy_experiment.py`

## What is fixed

- TURN 1〜29 event schedule
- NORMAL / NO-DIPLOMACY condition schemas
- NO-DIPLOMACY forbids direct diplomatic messages and cross-border proposals
- public_world_bulletin gives both A/B the same crisis information
- world-law requires quantity, acceptance, route eligibility, capacity, and requested world effect before dispatch
- dispatch and next-turn arrival can be recorded as world state mutations

## Preflight results

- A/B invariant failures: 0
- NO-DIPLOMACY rejects external contact: True
- Unit tests return code: 0
- World-law without acceptance: not_dispatched / explicit_acceptance
- World-law with acceptance: dispatch_scheduled
- Dispatch applied: True
- Next-turn arrivals: 1

## Still not executed

- Gemini/API 20run
- Final preregistration freeze
- Dry prepare-only manifests for all 20 runs

## SHA-256

`88167b627ccfc1a6acd78f23842f03bf79ae7e65d0a50c8154089da3e4b7182d`
