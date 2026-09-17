PYTHON ?= $(if $(wildcard .venv/bin/python),$(CURDIR)/.venv/bin/python,python3)
.DEFAULT_GOAL := check
.PHONY: check probe turn experiment setup-gemini check-sdk
check:
	HOMEOSTASIS_OFFLINE=1 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$(CURDIR)/tools/offline:$(CURDIR)" $(PYTHON) -B tools/check.py
probe turn experiment:
	$(PYTHON) -B research_workflow.py $@ $(if $(filter YES,$(CONFIRM)),--execute --confirm YES,)

# Dependency setup only; never creates a Gemini client or runs a probe.
setup-gemini:
	test -x .venv/bin/python || uv venv --python 3.13 .venv
	uv pip install --python .venv/bin/python -r requirements-gemini.txt

# Real SDK import under the same network guard as free checks.
check-sdk:
	HOMEOSTASIS_OFFLINE=1 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$(CURDIR)/tools/offline:$(CURDIR)" $(PYTHON) -B -c 'from google import genai; print("Gemini SDK import: PASS; Gemini API calls: 0")'

.PHONY: publish-status verify-status sync-status
publish-status:
	HOMEOSTASIS_OFFLINE=1 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$(CURDIR)/tools/offline:$(CURDIR)" $(PYTHON) -B tools/publish_status.py
verify-status:
	HOMEOSTASIS_OFFLINE=1 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$(CURDIR)/tools/offline:$(CURDIR)" $(PYTHON) -B tools/publish_status.py --verify
sync-status:
	$(PYTHON) -B tools/publish_status.py --complete
