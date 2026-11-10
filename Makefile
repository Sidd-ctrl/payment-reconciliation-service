.PHONY: setup test reconcile digest findings clean zip

PYTHON ?= python3

setup:
	$(PYTHON) -m pip install -e ".[dev]"

test:
	$(PYTHON) -m pytest

reconcile:
	$(PYTHON) -m payment_reconciliation reconcile --orders data/orders.csv --events data/events.jsonl --out outputs

digest:
	$(PYTHON) -m payment_reconciliation digest --summary outputs/summary.json

findings: ## Generate docs/findings.md from YOUR outputs/summary.json + order_states.csv
	$(PYTHON) scripts/generate_findings.py --summary outputs/summary.json --states outputs/order_states.csv --out docs/findings.md

clean:
	rm -f outputs/order_states.csv outputs/summary.json outputs/orphan_events.csv outputs/mismatches.csv outputs/.reconcile_work.sqlite
	rm -rf .pytest_cache src/*.egg-info build dist

zip: clean
	cd .. && zip -r payment-reconciliation-service.zip payment-reconciliation-service -x "*/node_modules/*" "*/__pycache__/*" "*/.pytest_cache/*"
