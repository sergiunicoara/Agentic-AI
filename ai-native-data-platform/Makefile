.PHONY: install db-bootstrap db-seed eval eval-ci

# ADMIN_DATABASE_URL must be the bootstrap superuser (schema owner) — this
# is what scripts/init_db.sql uses to create the non-superuser `app` role
# and own the tables, so Row Level Security actually applies to `app`
# connections at query time. DATABASE_URL is the app's own runtime role,
# used for everything else (seeding, evaluation).
ADMIN_DATABASE_URL ?= postgresql://postgres:postgres@localhost:5432/app
DATABASE_URL ?= postgresql://app:app@localhost:5432/app

install:
	python -m pip install --upgrade pip
	pip install -r requirements.txt

db-bootstrap:
	psql "$(ADMIN_DATABASE_URL)" -f scripts/init_db.sql

db-seed:
	DATABASE_URL="$(DATABASE_URL)" python scripts/seed_eval_corpus.py --workspace demo

eval:
	python -m app.eval.run \
		--experiment app/eval/experiments/baseline.yaml \
		--cases app/eval/datasets/cases.jsonl \
		--json_out artifacts/eval_summary.json

# CI target: ensures DB is ready and seeded before running gates
eval-ci: db-bootstrap db-seed
	DATABASE_URL="$(DATABASE_URL)" python -m app.eval.run \
		--experiment app/eval/experiments/baseline.yaml \
		--cases app/eval/datasets/cases.jsonl \
		--json_out artifacts/eval_summary.json
