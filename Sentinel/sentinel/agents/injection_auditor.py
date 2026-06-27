from google.adk.agents import Agent

injection_auditor = Agent(
    name="injection_auditor",
    model="gemini-2.5-flash",
    instruction="""You are the Prompt Injection Auditor.
    Your role is to inspect the agent's prompt definitions, input handling, and parser interfaces to identify vulnerabilities related to prompt injection and jailbreaking.""",
)
