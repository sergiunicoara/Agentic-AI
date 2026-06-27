from google.adk.agents import Agent

privilege_auditor = Agent(
    name="privilege_auditor",
    model="gemini-2.5-flash",
    instruction="""You are the Privilege Auditor.
    Your role is to evaluate tool permissions, access controls, and authentication scopes to detect overprivileged agents or vulnerable confused-deputy pathways.""",
)
