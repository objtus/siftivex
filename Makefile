.PHONY: help install install-embed install-ocr pipeline list-tasks init-db select-sample import-manifest review build-vocabulary task-0.1 task-0.2 task-0.2b task-0.7 migrate-db ingest process-jobs embed-pending batch-archive

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
	@echo "  make migrate-db     Phase 1: apply DB migration"
	@echo "  make ingest         Ingest (INGEST_FILE= or INGEST_ARCHIVE=under_iphone|pixiv_bookmarks)"
	@echo "  make process-jobs   Drain index_jobs (JOB_TYPE=ocr|vlm_tag|all, JOB_LIMIT=10)"
	@echo "  make import-manifest Task 0.2b: import manifest to DB"
	@echo "  make review         Task 0.7: generate tag review HTML"
	@echo "  make build-vocabulary  Build tag_vocabulary.yaml from archive filenames"

$(VENV)/bin/activate:
	$(PYTHON) -m venv $(VENV)
	$(PIP) install -e .

install: $(VENV)/bin/activate

install-embed: install
	$(PIP) install -e ".[embed]"

install-ocr: install
	$(PIP) install -e ".[ocr]"

list-tasks:
	$(PY) -m siftivex.pipeline --list

pipeline:
	$(PY) -m siftivex.pipeline

select-sample:
	$(PY) scripts/select_phase0_sample.py

init-db:
	$(PY) scripts/init_db.py

migrate-db:
	$(PY) scripts/migrate_db.py --fresh

INGEST_FILE ?=
INGEST_EMBED ?=
INGEST_ARCHIVE ?=
ingest:
	@if [ -n "$(INGEST_FILE)" ]; then \
		$(PY) scripts/ingest.py --file "$(INGEST_FILE)" $(if $(INGEST_EMBED),--embed,); \
	elif [ -n "$(INGEST_ARCHIVE)" ]; then \
		$(PY) scripts/ingest.py --archive "$(INGEST_ARCHIVE)" $(if $(INGEST_EMBED),--embed,) $(if $(INGEST_LIMIT),--limit $(INGEST_LIMIT),); \
	else \
		echo "Set INGEST_FILE=... or INGEST_ARCHIVE=under_iphone|pixiv_bookmarks"; exit 1; \
	fi

JOB_TYPE ?= all
JOB_LIMIT ?= 10
process-jobs:
	$(PY) scripts/process_jobs.py --type "$(JOB_TYPE)" --limit $(JOB_LIMIT)

EMBED_ROUTE ?=
EMBED_LIMIT ?= 0
embed-pending:
	$(PY) scripts/embed_pending.py $(if $(EMBED_ROUTE),--route $(EMBED_ROUTE),) $(if $(filter-out 0,$(EMBED_LIMIT)),--limit $(EMBED_LIMIT),)

BATCH_ARCHIVE ?= pixiv_bookmarks
batch-archive:
	$(PY) scripts/run_archive_batch.py --archive "$(BATCH_ARCHIVE)"

import-manifest:
	$(PY) scripts/import_manifest.py

task-0.1: select-sample
task-0.2: init-db
task-0.2b: import-manifest

review:
	$(PY) scripts/generate_review.py

task-0.7: review

build-vocabulary:
	$(PY) scripts/build_tag_vocabulary.py
