PYTHON ?= python3
LAYOUT_OUTPUT ?= .artifacts/layout/local.json

.PHONY: check test build secret-scan layout-check
check: build test secret-scan layout-check
build:
	$(PYTHON) -B tools/build_ui_previews.py
test:
	$(PYTHON) -B tools/run_free_tests.py
secret-scan:
	$(PYTHON) -B tools/secret_scan.py
layout-check:
	$(PYTHON) -B tools/check_layout.py --output $(LAYOUT_OUTPUT) --exercise
