"""
Standalone eval runner — run against live Cloud Run or local server.
Usage:
  python run_eval.py https://recruiter-agent-xxx-ew.a.run.app
  python run_eval.py http://localhost:8000
"""
import sys
from app.ops.eval_runner import load_eval_cases, run_eval_suite, results_to_json

base_url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
print(f"Running eval against: {base_url}\n")

cases = load_eval_cases()
print(f"Loaded {len(cases)} golden cases\n")

results = run_eval_suite(base_url, session_id="eval-run-001", cases=cases)
output = results_to_json(results)
print(output)

# Save to file
with open("eval_results.json", "w", encoding="utf-8") as f:
    f.write(output)
print("\nSaved to eval_results.json")
