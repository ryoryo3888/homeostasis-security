# Expanded paid Gemini comparison — 2026-09-19

User authorized approximately USD 3 for additional simulation. This run is separate
from the earlier USD 0.399717 uncached-rate estimate; it does not overwrite it.

Plan: seeds 17/23/41, five TURNs per seed and per arm, eight states. Same synthetic
initial world, network, frozen observation, transfer law and limits. Gemini uses
3.5 Flash-Lite, temperature 0.3, minimal thinking, max output 1536, one initiative
per state per TURN, maximum amount two. Control preserves two TURNs of domestic
demand, offers surplus to greatest reachable shortage, and accepts transfers.
Control repeats are not independent statistical samples. No shocks or recovery
rules are added, and seeds control model sampling rather than world variation.

For consent, the response schema explicitly lists every proposed choice ID as a
required boolean property and forbids extra keys. Both true and false remain
available. This prevents the prior empty-map interface failure without prescribing
cooperation. Consent is the replying state's own answer, not another state's.
The core's consent authority and settlement rules are unchanged.

Maximum 240 generation requests, no automatic retries. Every request is counted
before dispatch (input limit 60000). Before generation, prior durable usage at
uncached rates plus this request's counted input +2048 margin and full 1536 output
cap must fit USD 3. Rates are $0.30/M input and $2.50/M output, verified against
https://deepmind.google/models/model-cards/gemini-3-5-flash-lite/ on 2026-09-19.
This is an estimated API-spend limit before tax/FX, not a provider billing cap.
Unknown usage or excess reported usage stops later requests; unfinished journal
entries block reuse. Count-only calls do not generate responses.

Protocol, exact prompts and unmodified public answers, provider response/usage,
checkpoint, observation, and replay evidence remain locally under
`.artifacts/v3-paid-expanded-20260919`. Its protocol binds current source hashes.
No responses or keys are published. Each adopted TURN must pass exact replay and
observation-evidence recomputation. Errors and budget stops retain partial results.
Results remain exploratory validation artifacts, not formal research registration.
No claims of significance, causality or universal agent ranking from three runs.
