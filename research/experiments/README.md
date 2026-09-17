# Existing experiment catalog

Read [the integration contract](../../docs/architecture/EXPERIMENT_REGISTRY_CONTRACT.md)
and [inventory](inventory.json) before adding a record. The registry is an index,
not a result generator or public UI manifest.

| Entry | Evidence | Classification |
| --- | --- | --- |
| `v1-condition-a-representative` | Published condition-A mapping and its original 8-TURN JSON | representative, exploratory |
| `v1-sixteen-condition-comparison` | `summary.json`, all 36 named original files and README | comparison study, comparative |
| `v2-first-representative` | `v2_first_run.json`, README and existing public mapping | representative; type unknown |

The representative V1 worldline overlaps the comparison study. There are 36
unique V1 study sequences, not 37. Twenty-six have recorded seeds, ten do not.
V2 has five saved TURNs; seed is not recorded. Counts are checked against saved
artifacts, not conversation history. No fresh simulation was run.

The source scope is main commit `b151cb25802c8352ce3c4eefc2d80814c91f12b0`.
`inventory.json` enumerates unregistered JSON artifacts and absent main locations.
The final/complete lineage, deterministic prototypes and rejected/aborted audit
records stay outside this V1/V2 catalog. Other legacy 5-TURN snapshots,
backups and contrast-score intermediates lack unambiguous registration evidence
and remain unregistered. Records on other branches/private local directories are
not silently imported into main.

```sh
make registry-check PYTHON=.venv/bin/python
make check PYTHON=.venv/bin/python
```

Install the pinned `requirements/free-check.txt` in the test environment first.
The validator only reads files. It never changes originals, content slots,
public dashboards or the simulation engines.

## Readiness boundary

This foundation supports cataloging separately authorized V2 counterfactual
experiments and defining a separately authorized V3 architecture. It does not
establish runtime/API-budget readiness for either, grant experiment permission,
or start either task. Research eligibility and publication approval remain
separate decisions. V3 records are rejected by this phase's schema.
