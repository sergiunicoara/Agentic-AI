from google.adk.agents import Agent

attestation_agent = Agent(
    name="attestation_agent",
    model="gemini-2.5-flash",
    instruction="""You are the Attestation Agent.
    Your role is to compile the final security report, assign a safety verdict, sign the metadata, and generate the final Attestation structure.""",
)
