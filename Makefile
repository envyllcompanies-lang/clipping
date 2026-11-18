PY ?= .venv/bin/python
STAGE ?= 05

.PHONY: test lint fmt db backtest backtest-all datasets
test:
	$(PY) -m pytest
lint:
	$(PY) -m ruff check clipping tests && $(PY) -m ruff format --check clipping tests
fmt:
	$(PY) -m ruff format clipping tests && $(PY) -m ruff check --fix clipping tests
db:
	$(PY) -m clipping.cli db migrate
datasets:
	$(PY) -m clipping.cli eval build-synthetic
backtest:
	$(PY) -m clipping.cli eval run --stage $(STAGE)
backtest-all:
	$(PY) -m clipping.cli eval run --all
