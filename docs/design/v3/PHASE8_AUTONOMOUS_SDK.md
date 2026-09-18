# V3 autonomous initiatives and real-SDK offline boundary

2026-09-18. The user approved the next two steps after PR #22: connect
independent country choices and verify Gemini serialization without paid API
calls. This increment does both. It does not start a formal experiment.

## Country-authored initiatives

`autonomous.py` builds opportunities from the frozen world's actual routes
and resource types. It includes unavailable routes; structural existence does
not promise feasibility. Each opportunity has a snapshot-bound ID and a
Python-owned actor, target, resource and route. No crisis source, partner,
mediator, cooperation or recovery is chosen by the host.

All eight countries receive the same frozen world and opportunity definitions,
without earlier countries' submitted plans. Each country can independently
submit no initiative, or select its own opportunities and author quantities,
minimum fulfillment, partial fulfillment and conditions. A condition can
reference another country's potential offer without forcing that offer.
Only after all plans are collected do countries see the actual choices and
issue their own consent or refusal. An owner can withdraw its own offer by
refusing it. No coordinator is needed for independent exchange.

The existing `TurnRunner` still materializes choices, collects authenticated
consent, checks feasibility, settles jointly and commits atomically. This
adapter cannot write balances, choose another state's action or consent for it.
Planning failure invalidates the round; no automatic retry is attempted.

### Known opportunity versus nonexistent condition reference

Previously, a condition referencing a known opportunity that its owner did
not select was rejected as an unknown reference. This incorrectly turned
ordinary abstention into a technical failure. `SettlementEngine.settle` now
accepts an optional **trusted-core** `condition_catalogue`, validated against
the current snapshot, TURN, identities and unique IDs. The TURN runner passes
its saved catalogue. A known but unselected opportunity contributes zero to
participation/settled quantity, producing `CONDITION_NOT_MET`. It is never
inserted into selections, consents, shipments or history as an actual choice.
Invented references remain technical errors; historical arrival conditions
still require submitted/seen choices. Saved-input replay carries the same
catalogue and reproduces the result without calling an Agent.

The default empty argument preserves direct settlement callers. Existing
allocation, consent, ownership, conservation, delays and recovery rules are
unchanged. The new distinction is covered separately from the original
unknown-condition rejection test.

### Scope of executable actions

Current initiatives use the existing transfer handler. Transfers can represent
independent aid, trade legs or onward transfers, with conditions joining them.
Route choice is explicit; the host never silently reroutes. Multi-hop delivery
requires independent later choices by intermediate owners. There is no atomic
end-to-end multi-hop order, automatic third-country forwarding or invented
geography. A different one-hop route may have a different destination.

The host protocol specifies maximum amount and initiatives per state. The
current representation permits one offer per route/resource/state/TURN.
These are documented bounds, not permanent research design constraints.
The existing exact settlement search still has a 200,000-combination ceiling.
Too many partial offers can exceed it and must stop as a technical failure;
the host does not discard offers to manufacture a result. A live protocol must
fit the solver budget or first validate a replacement solver.
`extension_requests` preserves suggestions outside current laws, such as a
new storage or rebuilding action, with `unimplemented_not_executed` status.
Arbitrary prose never becomes executable code. Pool governance and coordinator
proposal negotiation are not enabled by this protocol. Same-TURN counteroffers
after consent begins require a separately specified negotiation round; states
can instead refuse and propose a different offer next TURN.

## Real SDK, zero remote calls

`gemini_preflight.py` constructs the pinned Google GenAI SDK with an explicit
dummy key and an `httpx.MockTransport`. The only permitted host is
`v3-offline.invalid`; responses come from local synthetic handlers. This module
has **no live client factory** and does not load a user's API key. The CLI also
denies socket connections. It exercises the SDK's actual JSON serialization,
Unicode handling, schema/config conversion and response parsing.

The configuration specifies JSON output, an explicit output-token cap, a
single attempt, and disabled automatic function calling. HTTP 503, timeout,
truncated output, malformed JSON and country/request binding mismatch all stop
without retry. Unknown usage is retained as `null`, not zero. Model availability,
remote schema acceptance and real billing are **not** verified offline.

The public prompt assigns only the requesting country's authority. It does
not equate cooperation, autonomy, self-reliance or refusal with a predetermined
good outcome. Only concise public explanations are requested; hidden reasoning
is not persisted.

References used for the boundary design: the installed `google-genai==2.20.0`
source (`HttpOptions.httpx_client`, `HttpRetryOptions.attempts`, and actual
GenerateContent serialization), Google's [structured output documentation](https://ai.google.dev/gemini-api/docs/generate-content/structured-output?hl=en),
and the [SDK source](https://github.com/googleapis/python-genai/blob/main/google/genai/_api_client.py).
Documentation is not proof that a particular live model accepts this schema.

## Attempt journal

SQLite records a reservation before SDK dispatch, using an immediate
transaction and FULL synchronous mode. It stores request digest, actor, phase,
status and optional token counts, never headers, raw errors, credentials,
prompts, responses or SDK objects. Run configuration, schema and prompt hashes
bind the journal; changing limits cannot silently reuse it.

A pending reservation after a crash or a failed dispatch blocks subsequent
dispatch. Reopening the journal cannot repeat an existing request. A validated
JSON response is labeled `response_validated`, not a completed world TURN or
research success. Core feasibility and settlement happen later and may reject
the proposal. A core failure must stop the host; it must not be bypassed by
opening another TURN. The journal is a local SQLite boundary, not a distributed
or monetary budget guarantee. No recovery/resume action is automated.

## Free reproducible scenarios

```sh
.venv/bin/python -B tools/check_v3_agent_sdk.py \
  --output .artifacts/v3-agent-sdk-new-run
```

The output directory must not exist. Three explicit synthetic scenarios each
run three TURNs: reciprocal conditional exchange, all refusal, and an absent
reciprocal offer. Together they exercise 144 **mock SDK dispatches**, 0 Google
API calls. Successful transfers arrive after their defined delays; refusals
and missing offers remain valid world outcomes. Each TURN is checkpointed,
observed, evidence-validated and exactly replayed without extra dispatch.
Reports, source hashes, transport configuration, attempt journals, round
records and observations remain `validation_run`, withheld from publication,
and ineligible for formal research. They are test fixtures, not discoveries.

## Next gate

The requested country-action connection and free SDK boundary are implemented.
Still required before a live experiment: a reviewed live transport/credential
entry point, an explicit model and current availability check, a preregistered
protocol with prompts/information policy, number of TURNs and repetitions,
call/token/currency limits and stopping rules, and formal provenance/eligibility
integration. The approximately ¥1,188 historical credit note is not a verified
balance. No paid execution, formal registry entry, UI outcome or automatic
recovery is authorized or performed by this increment.
