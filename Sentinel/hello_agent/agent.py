from google.adk.agents import Agent

root_agent = Agent(
    name="hello_agent",
    model="gemini-2.5-flash",
    instruction="You are a helpful assistant. Answer the user's question concisely.",
)