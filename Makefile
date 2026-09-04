.PHONY: help install install-embed pipeline list-tasks init-db select-sample import-manifest task-0.1 task-0.2 task-0.2b

PYTHON ?= python3
VENV ?= .venv
PIP := $(VENV)/bin/pip
PY := $(VENV)/bin/python
export SIFTIVEX_DEVICE ?= cuda:1

help:
	@echo "Siftivex Phase 0 pipeline"
	@echo ""
	@echo "  make install        Create venv and install base deps"
	@echo "  make install-embed  Install embedding extras (torch, lancedb, open_clip)"
	@echo "  make list-tasks     Show pipeline tasks"
	@echo "  make pipeline       Run full Phase 0 pipeline"
	@echo "  make select-sample  Task 0.1: generate manifest"
	@echo "  make init-db        Task 0.2: initialize SQLite"
	@echo "  make import-manifest Task 0.2b: import manifest to DB"

$(VENV)/bin/activate:
	$(PYTHON) -m venv $(VENV)
	$(PIP) install -e .

install: $(VENV)/bin/activate

install-embed: install
	$(PIP) install -e ".[embed]"

list-tasks:
	$(PY) -m siftivex.pipeline --list

pipeline:
	$(PY) -m siftivex.pipeline

select-sample:
	$(PY) scripts/select_phase0_sample.py

init-db:
	$(PY) scripts/init_db.py

import-manifest:
	$(PY) scripts/import_manifest.py

task-0.1: select-sample
task-0.2: init-db
task-0.2b: import-manifest
