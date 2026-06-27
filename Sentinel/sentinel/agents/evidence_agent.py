from google.adk.agents import Agent

evidence_agent = Agent(
    name="evidence_agent",
    model="gemini-2.5-flash",
    instruction="""You are the Evidence Agent.
    Your role is to collect deterministic evidence by calling static analysis tools (like bandit, ruff, pip-audit, semgrep) and compiling the raw results into normalized Evidence models.""",
)
