# Target Agent with privilege escalation / confused deputy vulnerability planted for evaluation.
import os

def run_agent(cmd: str) -> None:
    # Vulnerable because it runs arbitrary shell commands requested by untrusted user
    os.system(cmd)
