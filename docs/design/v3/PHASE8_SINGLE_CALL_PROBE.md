# V3: one-call connection probe

Prepared 2026-09-18. This is a connection validation, not a formal experiment.
No remote call is needed to prepare the protocol or run its tests.

## Frozen scope

- Gemini Developer API, `gemini-2.5-flash-lite`, standard synchronous generation.
- One request for MIL's initiative at the frozen first-TURN synthetic observation.
  MIL is selected for a connection check, not assigned a cooperation or crisis role.
- All eight states and defined opportunities are visible. Only MIL-owned proposals
  can pass local validation. No consent, settlement, resource movement, adopted TURN,
  coordinator, research registration, or public result follows this probe.
- Four proposals maximum, quantity bound 100, matching the offline protocol.
  Unsupported-law requests are retained as unimplemented text.
- Output 4,096 tokens, thinking budget zero, one candidate, no tools, no grounding,
  no cached-content resource, no automatic function calls, no fallback model.
- 500,000 input bytes maximum; input includes synthetic world data and the prompt,
  not user files, conversation history, credentials, or real-country statistics.
- Thirty-second HTTP timeout, one SDK attempt, zero HTTP retries, redirects refused.
  The timeout applies to HTTP operations, not a guaranteed whole-process deadline.

## Cost basis for approval

Official sources checked 2026-09-18:

- https://ai.google.dev/gemini-api/docs/pricing
- https://ai.google.dev/gemini-api/docs/models/gemini-2.5-flash-lite
- https://ai.google.dev/gemini-api/docs/generate-content/thinking

Published standard text rates: USD 0.10 / million input tokens and USD 0.40 /
million output tokens. To avoid an additional token-count network call or an
unverified byte-to-token estimate, the approval calculation deliberately uses the
model's entire 1,048,576-token input limit plus 4,096 output tokens:

`1,048,576 * 0.10 / 1,000,000 + 4,096 * 0.40 / 1,000,000 = USD 0.106496`.

Proposed approval ceiling: **USD 0.11 before tax and currency conversion**.
Actual usage should be much smaller but has not been measured remotely. This is
a conservative calculation at documented rates, not an account-wide billing cap.
No credit balance or project tier has been verified. Remote availability, schema
acceptance and actual charges remain unverified until execution. Missing usage
metadata remains unknown; it is never converted to zero cost.

## Review and execution

`tools/run_v3_live_probe.py --prepare <new-path>` writes the exact JSON request,
system instruction, schema, model, limits, SDK version and core source hashes.
Preparation never loads credentials or constructs a live client. The digest binds
all those values; execute regenerates and compares the entire protocol first.

After explicit user approval of that specific protocol and ceiling, the execution
entry accepts `--execute <prepared-path> --approval-digest <digest>` and reads only
`GEMINI_API_KEY` from the environment. Do not paste a key into chat or command text.
The CLI flag records operator acknowledgement; it is not an authentication system.

The fixed local journal `.artifacts/v3-live-single-probe/attempts.sqlite` reserves
the one allowed attempt before client creation. Changing output folders does not
renew the allowance. Failure, timeout, interruption, configuration changes, and a
second execution all stop. Never delete the journal to retry automatically.
Durability is local SQLite/POSIX, not a distributed billing or exactly-once remote
execution guarantee. A lost response can still have incurred a charge.

Valid results are written locally to `.artifacts/v3-live-single-probe/result.json`.
If result persistence fails after the response, the consumed journal still blocks
resubmission. Do not infer success or research results from a missing result file.
Errors printed to the console omit provider messages, credentials and headers.

## Free verification

Tests exercise the live entry through the installed real SDK with in-memory HTTP:
approval mismatch, protocol mutation, success, repeat execution, server error,
timeout, redirect, malformed response and foreign-country authority. The free
test runner forbids sockets. SDK 2.20.0 currently serializes thinking budget using
the protobuf `thinking_budget` spelling; remote acceptance is still to be checked.

No changes to V1/V2, UI, settlement law, recovery rules or formal eligibility.
