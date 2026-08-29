.PHONY: selftest clean

# Phase 0: prove the verdict harness discriminates real reproductions from
# near-miss decoys before any agent code is trusted. See
# BUGPROOF_AGENT_BRIEF.md section 7.
selftest:
	python eval/harness_selftest.py

clean:
	find . -name "__pycache__" -type d -prune -exec rm -rf {} +
	rm -f cases/*/_bugproof_junit.xml
	# sandbox.py renames finished scratch dirs instead of deleting them in
	# the hot path (see run_pytest's cleanup comment) -- explicit, separate
	# maintenance sweeps them. Never run as part of `make selftest`.
	PYTHONPATH=src python -m bugproof.cleanup
