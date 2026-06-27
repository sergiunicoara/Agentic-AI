from google.adk.agents import Agent

scope_agent = Agent(
    name="scope_agent",
    model="gemini-2.5-flash",
    instruction="""You are the Scope Agent.
    Your role is to scan the target codebase, identify its entry points, mapping target agent capabilities, APIs, and defining the overall assessment boundary.""",
)
