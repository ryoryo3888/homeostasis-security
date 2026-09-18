# Paired Gemini / deterministic pilot

The user requested paid Gemini country TURNs for comparison after discussing
the “ハッカソン更新監視” task. Payment is not a research quality metric. The
question here is what differs when the same world receives actual LLM decisions.

## Fixed scope

Three paired runs, three TURNs each, eight countries. Seeds 17/23/41 are model
sampling parameters, not a claim of exact provider reproducibility. All pairs
use the same synthetic initial world and network, frozen observation, transfer
law, solver, prompt, available opportunities and decision limits. Each pair has
the same core context ID. Control repetitions are deterministic checks, not
three independent statistical samples.

Control: each country preserves two TURNs of essential demand, then may offer
up to two surplus units to its reachable neighbor with greatest unmet two-TURN
need, resolving ties by route/resource ID. It accepts offered transfers. This
is one disclosed cooperative heuristic, not an optimal or neutral agent.

Gemini: gemini-2.5-flash-lite, temperature 0.3, output cap 4096, thinking budget
zero, no tools. One initiative maximum per state per TURN, quantity at most two.
These pilot limits keep the exact solver bounded; they limit interpretation and
are not permanent world laws. No country roles, outcomes, shocks, cooperation
or recovery are scripted for Gemini. No coordinator or law-toggle experiments
are implied: those interventions need separately defined implementations.

## Budget and dispatch

Maximum 144 generation attempts and 144 countTokens calls; one count then one
generation per slot. The exact generateContentRequest (including system prompt
and schema) goes to countTokens first. Count >48000 stops before generation.
No HTTP retries, SDK retries, redirect following, model fallback or automatic
resume. The fixed .artifacts/v3-paid-pilot-20260919 directory and durable SQLite
attempt journal retain pending/failed reservations across restarts.

Published text rates checked 2026-09-19: $0.10/M input, $0.40/M output.
Reserve a 2048-token input margin and the entire output cap in the calculation:
144 × ((48000+2048)×0.10 + 4096×0.40)/1e6 = **$0.9566208**.
Working estimated budget: **$1 before tax/FX**. This is not a provider-enforced
account cap; actual usage is recorded and any missing/excess usage stops further
requests. Prior credit balance and billing tier are unverified. A paid account
request does not establish that a particular amount has been billed.

Sources: https://ai.google.dev/gemini-api/docs/pricing and
https://ai.google.dev/api/tokens (generateContentRequest token counting).

## Evidence and interpretation

Save protocol/source hashes, exact country input and public JSON answer, full
generation response body and usage (never credential headers), choice/consent,
checkpoint, recomputed observation and exact replay checks for every adopted
TURN. Errors stop the whole pilot; partial runs stay partial, not successful
samples. No silent replacement or trimming of rejected decisions.

The existing source adapter still identifies checkpoints as offline/core
validation artifacts. Accordingly these exploratory pilot observations remain
`validation_run`, `research_eligible=false`, publication withheld. They can be
compared descriptively with explicit real-Gemini provenance but are not silently
promoted into formal experiment registry records. Raw logs remain local and
ignored by Git. The approved V3 visual baseline and saved fixture viewer stay
unchanged. Three short runs cannot support significance or broad causal claims.

Prepare controls: tools/run_v3_comparison.py (no API/credential needed).
Execute once after the already authorized paid scope is ready:
tools/run_v3_comparison.py --execute-paid --protocol-digest <saved digest>.
Credential is supplied through GEMINI_API_KEY only, never command text.
