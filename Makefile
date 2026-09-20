PYTHON ?= python3
LAYOUT_OUTPUT ?= .artifacts/layout/local.json

.PHONY: check test build secret-scan layout-check registry-check
check: build test registry-check secret-scan layout-check v3-layout-check v2-observation-check
build:
	$(PYTHON) -B tools/build_ui_previews.py
	$(PYTHON) -B tools/build_v3_candidate.py
	$(PYTHON) -B tools/build_v3_earth.py
	$(PYTHON) -B tools/build_v2_observation.py
test:
	$(PYTHON) -B tools/run_free_tests.py
secret-scan:
	$(PYTHON) -B tools/secret_scan.py
layout-check:
	$(PYTHON) -B tools/check_layout.py --output $(LAYOUT_OUTPUT) --exercise
registry-check:
	$(PYTHON) -B tools/experiment_registry.py

.PHONY: v3-layout-check
v3-layout-check:
	$(PYTHON) -B tools/check_v3_candidate.py

.PHONY: v2-observation-check
v2-observation-check:
	$(PYTHON) -B tools/check_v2_observation.py
