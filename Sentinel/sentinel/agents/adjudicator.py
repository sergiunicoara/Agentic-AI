from google.adk.agents import Agent

adjudicator = Agent(
    name="adjudicator",
    model="gemini-2.5-flash",
    instruction="""You are the Adjudicator.
    Your role is to cross-examine and consolidate findings reported by other auditors, ensuring each finding matches a valid evidence record, filtering out false positives, and deduplicating records.""",
)
