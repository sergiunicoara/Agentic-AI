.PHONY: install db-bootstrap db-seed eval eval-ci

install:
	python -m pip install --upgrade pip
	pip install -r requirements.txt

db-bootstrap:
	python scripts/bootstrap_db.py

db-seed:
	python scripts/seed_eval_data.py

eval:
	python -m app.eval.run --json_out eval_report.json

# CI target: ensures DB is ready and seeded before running gates
eval-ci: db-bootstrap db-seed
	python -m app.eval.run --json_out eval_report.json --fail_threshold 0.80 --min_recall_mean 1.0 --min_mrr_mean 0.50
