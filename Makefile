PYTHON ?= python3
.DEFAULT_GOAL := check
.PHONY: check probe turn experiment
check:
	HOMEOSTASIS_OFFLINE=1 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$(CURDIR)/tools/offline:$(CURDIR)" $(PYTHON) -B tools/check.py
probe turn experiment:
	$(PYTHON) -B research_workflow.py $@ $(if $(filter YES,$(CONFIRM)),--execute --confirm YES,)
