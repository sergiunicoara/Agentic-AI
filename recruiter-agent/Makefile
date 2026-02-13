.PHONY: run-local test seed bootstrap

run-local:
	python -m app.server

test:
	pytest -q

seed:
	python scripts/seed_data.py

bootstrap:
	python scripts/bootstrap_sqlite.py
