# Common commands (Ubuntu / WSL / macOS). On Windows, run the `uv run ...` commands shown in the README.
.PHONY: help install run test lint format report eval-score docker-build docker-run clean

IMAGE ?= vcu-impact
PORT  ?= 8501

help:            ## Show the available targets
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-14s %s\n", $$1, $$2}'

install:         ## Create .venv and install dependencies (needs uv)
	uv sync
	@test -f .env || (cp .env.example .env && echo "Created .env from .env.example: add your API key(s).")

run:             ## Start the Streamlit app on http://localhost:$(PORT)
	uv run streamlit run app/streamlit_app.py --server.port $(PORT)

test:            ## Run the offline test suite (no API key needed)
	uv run pytest -q

lint:            ## Lint and check formatting
	uv run ruff check src app tests eval
	uv run ruff format --check src app tests eval

format:          ## Format the code
	uv run ruff format src app tests eval

report:          ## Regenerate the example report from the recorded analysis (no API key needed)
	uv run vcu-impact analyze --mode replay --report reports/example_impact_report.html
	uv run vcu-impact analyze --mode replay --report reports/example_impact_report.md

eval-score:      ## Recompute the LLM evaluation tables from the stored runs
	uv run python eval/evaluate.py score --version v1
	uv run python eval/evaluate.py score --version v3

docker-build:    ## Build the container image
	docker build -t $(IMAGE) .

docker-run:      ## Run the container (uses .env if present, otherwise replay mode only)
	docker run --rm -p $(PORT):8501 $(if $(wildcard .env),--env-file .env,) $(IMAGE)

clean:           ## Remove caches (keeps .venv and recorded analyses)
	rm -rf .pytest_cache .ruff_cache .cache
	find . -name __pycache__ -type d -prune -not -path './.venv/*' -exec rm -rf {} +
