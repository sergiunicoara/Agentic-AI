from google.adk.agents import Agent

supply_chain_auditor = Agent(
    name="supply_chain_auditor",
    model="gemini-2.5-flash",
    instruction="""You are the Supply Chain Auditor.
    Your role is to check package dependencies, lockfiles, and imports using tools like pip-audit to identify vulnerable packages or malicious dependencies in the supply chain.""",
)
