# Content insertion contract

`ui/content.json` is the only declarative extension manifest for the frozen V1/V2
pages. It currently contains no entries. Its schema is:

```json
{
  "schema_version": 1,
  "v1": [],
  "v2": [
    {
      "slot": "NEXT_WORLD",
      "content": {
        "id": "unique-observation-id",
        "title": "Evidence-based title",
        "paragraphs": ["Public observation, interpretation, or hypothesis, clearly distinguished."],
        "evidence": "docs/research/existing-evidence.md"
      }
    }
  ]
}
```

This is a documentation example, not published research. Adding actual content
requires user authorization and an existing local evidence artifact.

The browser API is `HomeostasisContent.addContent(slotName, content)`. It accepts
only a plain record with `id`, `title`, `paragraphs`, `evidence`. It creates fresh
nodes using `textContent`; markup remains literal text. IDs are unique within a
page. External URLs, traversal, unknown fields/slots and non-record inputs are
rejected. Titles are limited to 200 characters, paragraphs to 20 × 4000
characters, and evidence links to local `docs/` or `results/` paths.

The manifest is validated before insertion. A missing or ambiguous anchor fails;
it never falls back to `body`, Earth, a sibling world, or an arbitrary selector.
Every insertion checks the structural guard before and after. Existing nodes are
not supplied as payload and are never reparented. Evidence must not be inferred
from decorative System Field lines. Secrets, internal model reasoning and SDK
objects do not belong in content.

V3 is intentionally not accepted by this manifest schema. Its architecture must
be explicitly defined first. Do not add a V3 key to bypass that review.

Legacy rendering and integration code is grandfathered at the approved hashes,
not generally exempted. New arbitrary insertion code inside those files fails
the source freeze. The contract loader is the only normalized nonvisual addition.

Run `make check` before proposing a content change. Future content can naturally
extend research-page length, but cannot move, replace or resize the locked frame.
