# Marge — developer commands. CI runs the same targets (5 min budget).

PYTHON ?= python3
PYTEST ?= $(PYTHON) -m pytest
RUFF   ?= $(PYTHON) -m ruff
SRC    := src tests data infra scripts

.PHONY: help install lint format test smoke demo assets limits all clean deploy destroy

help:
	@echo "make install  - dev dependencies"
	@echo "make lint     - ruff check + format --check"
	@echo "make format   - ruff format (writes)"
	@echo "make limits   - < 500 lines per file, < 50 per function"
	@echo "make test     - offline unit + integration tests"
	@echo "make smoke    - generate data, run the pipeline, print the margin table"
	@echo "make demo     - full local demo (portal + review + MCP self-test)"
	@echo "make assets   - write the QuickSight asset bundle"
	@echo "make all      - lint + limits + test (what CI runs)"
	@echo "make deploy   - deploy the AWS environment and load the demo data"
	@echo "make destroy  - delete the AWS environment and its data"

install:
	$(PYTHON) -m pip install --user -e ".[dev,api]"

lint:
	$(RUFF) check $(SRC)
	$(RUFF) format --check $(SRC)

format:
	$(RUFF) format $(SRC)
	$(RUFF) check --fix $(SRC)

limits:
	$(PYTHON) scripts/check_limits.py

test:
	PYTHONPATH=src $(PYTEST) -m "not slow"

smoke:
	PYTHONPATH=src $(PYTHON) -m marge.cli smoke

demo:
	PYTHONPATH=src $(PYTHON) -m marge.cli demo

assets:
	PYTHONPATH=src $(PYTHON) -m marge.cli assets --out infra/quicksight-assets

all: lint limits test

deploy:
	bash scripts/deploy.sh

destroy:
	bash scripts/teardown.sh

clean:
	rm -rf .pytest_cache .ruff_cache build dist *.egg-info data/generated
