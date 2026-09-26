.PHONY: setup data test lint fmt run replay clean

setup:            ## Create the venv and install dependencies
	uv sync

data:             ## Build SQLite + retriever index from data/
	uv run python scripts/build_knowledge_base.py

test:             ## Run the offline test suite
	uv run pytest -q

lint:             ## Lint + type-check
	uv run ruff check src tests scripts
	uv run mypy src

fmt:              ## Auto-fix lint issues
	uv run ruff check --fix src tests scripts
	uv run ruff format src tests scripts

GOAL ?= Which critical findings on production assets have breached or are about to breach their remediation SLA?
run:              ## Run the agent: make run GOAL="..."
	uv run secops-agent run "$(GOAL)"

ID ?=
replay:           ## make replay ID=<run_id>
	uv run secops-agent replay "$(ID)"

transcript:       ## make transcript ID=<run_id>
	uv run secops-agent report "$(ID)"

clean:
	rm -rf data/secops.db data/chroma runs .pytest_cache
