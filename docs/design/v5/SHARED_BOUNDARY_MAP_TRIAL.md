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
