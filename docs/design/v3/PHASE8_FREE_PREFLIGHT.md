# V3 simulation preparation — free boundary and multi-TURN preflight

2026-09-18. Following publication of the common-frame correction in PR #21,
the user requested continuation toward simulation. This increment prepares
the country JSON boundary and an explicitly synthetic multi-TURN validation.
It does not run Gemini, approve a paid protocol, register an experiment or
publish synthetic observations as research.

## Implemented

`homeostasis_v3/agent_adapter.py` connects host-owned JSON exchange functions
to the existing `CountryInput` interface. A request binds country identity,
phase, frozen observation, proposal/catalogue or complete choice set by digest.
Choice replies contain only catalogue IDs, integer amounts and public reasons.
Executable targets, routes, conditions and laws remain Python-owned. The
consent phase accepts only decisions about submitted choice IDs. The model
cannot return a world patch, authorize another state's identity, add new
decisions after seeing everyone else's choices, or fabricate a coordinator.

Every exchange reserves its budget before dispatch. Duplicate attempts and
budget exhaustion fail closed; there is no automatic retry. This is a
sequential, in-memory budget, not a durable paid-dispatch journal or a
concurrency guarantee. Provider construction, credentials and SDK calls are
absent. Unknown fields, duplicate JSON keys, oversized replies, stale
request hashes and invalid quantities are rejected.

The catalogue is injected by the trusted host. No permanent action menu is
introduced: new actions require their own validated world-law extension.
The transfer test demonstrates an independent choice without a coordinator,
as well as valid refusal and non-settlement. No outcome is required for
technical success.

`homeostasis_v3/validation_runner.py` executes the existing laws for eight
synthetic states. The CLI disables Python network connections and uses
explicit synthetic abstention replies, never an AI impersonation. The empty
catalogue is a test condition only, not the proposed research action space.

For every TURN it validates exact saved-input replay, computes and validates
observations, commits the checkpoint with the existing POSIX store, then
writes the observation and progress report. A technical failure stops the
run, excludes raw exception text and leaves the checkpoint HEAD available
for inspection. A report write can lag a committed HEAD after a crash; the
HEAD is authoritative and no automatic resume is provided. Existing output
directories are rejected, so previous evidence cannot be silently replaced.

The protocol records input hashes, source-module hashes, runner configuration,
planned TURN count and fixture identity. Every report and observation remains
`validation_run`, `research_eligible=false`, publication withheld. Recovery
remains undefined; this implementation introduces no automatic recovery law.

## Reproduce the free validation

```sh
.venv/bin/python -B tools/run_v3_validation.py \
  --output .artifacts/v3-preflight-new-run --turns 8
```

The output path must not exist. The directory contains `protocol.json`,
`report.json`, immutable checkpoint records with an atomic HEAD, and eight
observation records. Eight TURNs produce 64 **synthetic exchanges**, not 64
API calls. With no choices there is no consent exchange. Exact replay does
not call the original adapters.

## Formal research readiness — still false

The remaining work is explicit:

1. A research catalogue/proposal extension that supports independent choices,
   conditional contracts and route alternatives without prescribed roles or
   histories; record the actions not yet modeled.
2. A Gemini transport with real-SDK offline serialization verification,
   durable pre-dispatch budgeting, usage records and zero retries. The old
   V2/legacy Agent gateway is not silently reused: it has different contracts
   and retry behavior.
3. A specific approved protocol: model, prompts, observation policy, duration,
   repetitions, comparison conditions, token/call/currency limits and stop
   rules. The old approximately ¥1,188 credit note is not a verified balance.
4. Formal runner/provenance and observation eligibility gates. Changing an
   offline checkpoint's label cannot promote it to formal research.

The first live API boundary check, if approved, is separate from a research
experiment. A valid reply alone does not establish research eligibility.
V1/V2 outcomes and the existing V3 initial world remain unchanged.
