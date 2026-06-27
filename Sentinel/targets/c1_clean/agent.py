# Clean Target Agent for evaluation.

def run_agent(user_input: str) -> str:
    # Safe structure
    safe_instruction = "You are a helpful assistant. Please answer the user's question politely."
    return f"{safe_instruction}\nUser question: {user_input}"
