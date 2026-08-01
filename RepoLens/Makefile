.PHONY: up down lint test eval eval-ingest eval-hybrid submission

up:
	docker compose up --build

down:
	docker compose down

lint:
	cd backend && ruff check . && mypy app/retrieval/citations.py app/retrieval/models.py app/ingest/models.py app/browse/models.py --ignore-missing-imports

test:
	cd backend && pytest -q

FASTAPI_URL ?= https://github.com/fastapi/fastapi.git

eval-ingest:
	cd backend && python -m app.ingest $(FASTAPI_URL) --subdir fastapi

eval:
	cd backend && python -m app.evals ../evals/golden.yaml --source-url $(FASTAPI_URL) --results-dir ../evals/results

eval-hybrid:
	cd backend && python -m app.evals ../evals/golden.yaml --source-url $(FASTAPI_URL) --hybrid --results-dir ../evals/results

submission:
	git archive --format=zip --output=submission.zip HEAD -- . ':(exclude)*.zip' ':(exclude)evals/results-ci/**' ':(exclude)evals/results-hybrid/**' ':(exclude)evals/results-live/**'
