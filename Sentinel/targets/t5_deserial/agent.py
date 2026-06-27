"""
Target T5 — Unsafe deserialization (seeded vulnerability).
pickle.loads on untrusted data allows arbitrary code execution.
"""
import pickle
import subprocess


def load_agent_state(serialized_data: bytes) -> dict:
    """
    UNSAFE: pickle.loads on untrusted input.
    Attacker can craft malicious pickle data to execute arbitrary code.
    """
    # UNSAFE: deserializing untrusted data with pickle
    state = pickle.loads(serialized_data)
    return state


def save_and_restore(data: dict, filepath: str) -> dict:
    """
    UNSAFE: pickle round-trip with user-controlled filepath.
    """
    with open(filepath, "wb") as f:
        pickle.dump(data, f)

    with open(filepath, "rb") as f:
        # UNSAFE: loading from potentially attacker-controlled file
        return pickle.loads(f.read())


def run_cleanup(temp_dir: str) -> None:
    """UNSAFE: shell injection in cleanup routine."""
    subprocess.run(f"rm -rf {temp_dir}", shell=True)