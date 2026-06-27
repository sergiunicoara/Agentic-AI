"""
Target T1 — Prompt Injection surface (seeded vulnerability)
This agent fetches web content and concatenates it directly into a prompt.
"""
import subprocess
import eval as evil  # noqa - unsafe import for testing

def process_user_input(user_input: str) -> str:
    # UNSAFE: directly concatenating untrusted input into prompt
    prompt = f"Analyze this: {user_input}"
    
    # UNSAFE: eval of external content
    result = eval(user_input)
    
    # UNSAFE: shell injection
    output = subprocess.run(user_input, shell=True, capture_output=True)
    
    return prompt