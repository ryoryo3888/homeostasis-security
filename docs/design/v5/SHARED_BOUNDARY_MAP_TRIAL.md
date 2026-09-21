# Shared-boundary map generation trial

## Scope

A separately authorized map trial follows the rejected coordinate-map proposal. The rejected proposal and its RAW remain unchanged. This is one new map-generation request, followed by the previously authorized independent nation initialization requests only if the map passes both mechanical and content review. No simulation or publication is included.

The world still contains twelve nation slots and twelve frozen life-first personas, with one leader per nation. World size, geographic diversity and country shape are not assigned by the experimenter. The initial acquisition catalogue and unused-point policy remain unchanged. The leader-assignment seed and procedure are inherited from the first trial, without another draw.

## Representation

The model supplies a shared table of vertices and directed boundary edges. Regions identify closed exterior and hole loops by edge references and traversal direction, rather than independently rewriting border coordinates. Multiple disconnected polygons remain available for islands and exclaves. Nation territory references and political boundary claims remain separate.

The compiler reconstructs polygon coordinates from those references, without moving, rounding, snapping, deleting or allocating land. Unknown references, broken loops, crossing or duplicated boundary edges, and invalid geometry stop acceptance. Whole-map geometry validation still runs: shared references alone are not a guarantee that a model will produce a valid map. An island label is a geographic claim requiring content review, not evidence that the shape is surrounded by water.

No equal-area layout, fixed grid, mandatory connectivity, port, road, common nation shape or scripted event is added. Unallocated space is not silently declared sea or assigned to a country. Territorial disputes are preserved as claims; undefined joint actual control is not silently adjudicated by a geometry routine.

## Evidence and stopping

Model output remains RAW topology. Compiled polygon geometry is DERIVED, with both its source-topology hash and its own map hash. Nation requests use this canonical derived map and reference its hash. Each continuation recomputes it from RAW and checks agreement with the saved derived map. The compiler, prompt, schema, runtime and source revision are pinned before the first request.

Each request stores outgoing bytes, incoming bytes, status, usage and validation results. A topology or geometry error preserves its diagnostic and stops the batch. Requests are serial; no automatic model repair or retry is performed. A failed map is an initialization failure, not a simulated worldline or a conclusion about leader behaviour.

The previous trial's reservation remains included in the execution cap. Detailed operational cost records are private. Any further redesign or trial is recorded separately rather than rewriting the source or acceptance rules of an already started batch.

## Complete initial nation slots

The first shared-boundary response passed edge and overlap checks but left nine nation territories unspecified. Its complete RAW and rejection remain frozen at their original revision. A new revision aligns the input contract with the existing completion gate: every one of the twelve initial nation slots must reference at least one valid territory region in the response. No area, shape, distribution, connectivity or initial resource allocation is prescribed. This is an initial-world completeness condition; it does not prohibit loss of territory or other subsequent political phenomena.

The follow-up uses a separate batch and version, preserving both prior map attempts, their cost reservations, the original catalogue, personas and assignment seed. Only one further map request is included in this corrective trial; no failed response is repaired or overwritten. Shared-boundary generation is not claimed universally reliable from these trials.

## Reference binding adapter correction

The completed twelve-territory map passed validation. The first nation response then failed its map-reference check: the provider adapter had sent the common map but omitted the expected reference hashes, which existed only in the local request package. The model's reported hash was therefore not a supplied identifier. This is an adapter defect, not evidence of a different world state or a leader judgement.

A separate source revision now transmits the reference hashes in the nation context and pins the expected map hash with a singleton output-schema enum. The generation content, geography and acquisition rules are unchanged. Offline regression tests check the outgoing payload, metadata binding and unchanged local package. The failed RAW and its batch stay frozen; this correction does not retroactively accept the failed nation or initiate a paid retry.


## Authorized nation-only continuation

After explicit execution authorization, a new batch imports the accepted map
by reference and starts with the first nation. No new map call is made. The
original world ID, canonical map, catalogue, twelve persona references and
assignment draw remain fixed; the failed nation's output is not an input.
Every request verifies the frozen source and uses the corrected reference
binding. Earlier RAW, failed status and acceptance records remain immutable.

Prior completed requests with a verified usage receipt are settled in the new
ledger at their reported usage estimate, retaining original reservations and
invoice uncertainty. Unsettled requests keep their maximum reservation. The
execution ceiling is unchanged. New calls continue to reserve their full
maximum and stop after the first technical or unresolved content failure.
This continuation initializes nations only; it does not run the simulation,
add sea or transport routes, or publish the working evidence.


## Collect proposals before bundled acceptance review

A subsequent operator decision separates proposal collection from nation
acceptance. The first structurally valid nation proposal is retained by
reference, including its original content rejection and unresolved warehouse.
A new protocol collects only the eleven remaining nation proposals. The map,
world ID, catalogue, nation-generation prompt, response schema, generation
settings, twelve persona references and assignment seed remain fixed.
The earlier proposal and its problems are not supplied to the other nations.

Unresolved asset specifications and accounting discrepancies are preserved for
one bundled review after collection. They do not grant a free asset, a zero
price, a settled balance, or executable capacity. The existing catalogue stop
rule still prevents acceptance and physical use of unresolved assets; the
amendment changes when proposal collection pauses. Transport, malformed output,
reference, evidence-integrity and execution-limit failures still stop the batch.
No automatic retry, supplemental generation or replacement choice is added.

Collection completion means twelve saved proposals, not twelve accepted initial
nations. This mode cannot finalize nation acceptance or the leader assignment,
start simulation, or publish the evidence. The separate protocol records the
post-generation change to the stopping rule without rewriting earlier RAW.
