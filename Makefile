.PHONY: help install install-embed install-ocr install-api pipeline list-tasks init-db select-sample import-manifest review build-vocabulary task-0.1 task-0.2 task-0.2b task-0.7 migrate-db ingest process-jobs embed-pending batch-archive vlm-overnight api-dev n8n-status n8n-ingest n8n-embed n8n-vlm

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
	@echo "  make n8n-status     JSON index status (scheduled tasks)"
	@echo "  make n8n-ingest     Incremental ingest (N8N_LIMIT=500)"
	@echo "  make n8n-embed      Embed pending (N8N_EMBED_LIMIT=200)"
	@echo "  make n8n-vlm        VLM queue (N8N_VLM_ROUTE=, N8N_VLM_LIMIT=5)"

$(VENV)/bin/activate:
	$(PYTHON) -m venv $(VENV)
	$(PIP) install -e .

install: $(VENV)/bin/activate

install-embed: install
	$(PIP) install -e ".[embed]"

install-ocr: install
	$(PIP) install -e ".[ocr]"

install-api: install
	$(PIP) install -e ".[api]"

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

VLM_ROUTE ?= route/under-iphone
VLM_BATCH ?= 10
vlm-overnight:
	nohup $(PY) scripts/run_vlm_overnight.py --route "$(VLM_ROUTE)" --batch-size $(VLM_BATCH) >> data/batch/vlm-overnight.log 2>&1 &

api-dev:
	$(PY) -m siftivex.api.main --host 127.0.0.1 --port 8787

N8N_LIMIT ?= 500
n8n-status:
	$(PY) scripts/n8n_task.py status

n8n-ingest:
	$(PY) scripts/n8n_task.py ingest --limit $(N8N_LIMIT)

N8N_EMBED_LIMIT ?= 200
n8n-embed:
	$(PY) scripts/n8n_task.py embed --limit $(N8N_EMBED_LIMIT)

N8N_VLM_LIMIT ?= 5
N8N_VLM_ROUTE ?= route/under-iphone
n8n-vlm:
	$(PY) scripts/n8n_task.py vlm --limit $(N8N_VLM_LIMIT) --route $(N8N_VLM_ROUTE)

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
