Private publication boundary

Set HOMEOSTASIS_PRIVATE_CONFIG to the researcher-owned prompts.json file.
Set HOMEOSTASIS_PRIVATE_FILES to the private mirror containing exact original files.
Set HOMEOSTASIS_PRIVATE_RUNS to a private directory outside the checkout, or use
private_runs/ (ignored by Git, and must also be excluded from any web publisher).
Never put the real configuration in this directory. The example is intentionally empty.

No default prompt exists. Missing configuration fails before provider dispatch.
Text bytes and f-string dynamic expressions are preserved. decision_factors.py is
researcher-owned, byte-exact original code loaded only after hash validation; never
put model-generated code into this configuration. Physical feasibility and world
settlement remain public and unchanged.

Gateway.calls and checkpoint hooks are PRIVATE in-memory evidence. Public output
must use Gateway.public_calls() or audit.public_result(), never serialize calls
or checkpoint data directly. A public export cannot be used for resume.
Full requests and SDK responses persist locally before/after dispatch, without
HTTP headers. Failure to preserve a returned response does not cause another call.
New private checkpoints are located by private_checkpoint(output), not next to
public result files. Existing original checkpoints remain in the private backup.
Do not relabel an old run with the new source/configuration identity or bypass
existing resume identity checks. Continue legacy runs only under their frozen code.

Public fingerprints:
- request_sha256: canonical full JSON payload, not necessarily exact HTTP bytes.
- prompt_sha256: canonical dictionary of the explicitly listed instruction keys.
- observation_sha256: canonical dictionary of explicitly listed observation keys.
- private_configuration_sha256: entire private bundle, including private module hashes.
- artifact_sha256: exact original saved file bytes.
Unknown historical metadata is null. File preservation date is not run timestamp.
Prompt fragments use exact UTF-8 hashes; do not normalize whitespace or Unicode.
All canonical JSON hashes use sorted keys, compact separators, UTF-8, allow_nan=False.

This boundary does not revoke historical Git blobs or previously downloaded copies.
Public Agent statements/results are retained. Suspected quotation of private content
inside these statements must be reported, not automatically edited.
