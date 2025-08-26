# Multi-Agent System Project Using LLMs with Human Oversight 

This project implements a **multi-agent system** powered by large language models (LLMs) including OpenAI GPT, Anthropic Claude, and Google's Gemini. The system facilitates collaborative conversations across multiple specialized AI agents with optional human oversight, enabling flexible and scalable interaction workflows.

---

## 🧩 Overview

The system features:

- **Multi-agent collaboration:** Agents specialize in different roles, communicating via a shared group chat.
- **Configurable LLM backends:** Use OpenAI GPT, Anthropic Claude, or Google Gemini as underlying AI engines.
- **Human oversight:** Human agents can join conversations at any time, contributing or moderating.
- **Role-based agents:** Each agent focuses on distinct tasks to streamline workflows.

---

## 👥 Agents

| Agent Name               | Role Description                                          |
|-------------------------|------------------------------------------------------------|
| **Group Chat Manager**  | Coordinates communication among agents and humans.         |
| **Social Media Strategist** | Develops social media plans, campaigns, and engagement ideas. |
| **Chief Marketing Officer (CMO)** | Oversees marketing vision and strategy alignment.              |
| **Marketing Manager**   | Implements marketing campaigns, monitors metrics, and reports. |
| **Human Agent**         | Human participant for oversight, input, and decision-making.  |

---

## ⚙️ System Architecture

1. **Initialization:**  
   - Configure each agent with an LLM backend (OpenAI GPT, Anthropic Claude, or Google Gemini).  
   - Initialize the group chat manager to handle message routing and logging.

2. **Conversation Management:**  
   - Agents exchange messages within a shared conversation channel.  
   - The chat manager ensures messages are delivered to the appropriate participants.

3. **Human Oversight:**  
   - A human agent can join at any time to contribute or moderate.  
   - Human input can override or augment AI responses.

4. **Task Execution:**  
   - Agents perform their specialized roles autonomously or collaboratively as required.  
   - Social media strategist crafts content ideas, the marketing manager schedules campaigns, and the CMO approves strategy.

---

## 🔧 Configuration Example (Pseudocode)

```python
# Agent configuration
groupchat = GroupChat(
    agents = [user_proxy_agent, cmo_agent_gemini, brand_marketer_agent_openai],  # List of agents participating in the group chat
    messages = [ ],  # Initialize with empty message history
    max_round = 20,  # Optional: Limits how many conversation rounds can occur before terminating
)
# Initialize conversation
group_manager = GroupChatManager(groupchat = groupchat, llm_config = llm_config_openai)  # Uses OpenAI's LLM to manage the conversation
```
## 🛠️ Features

Modular agent design: Easily add or replace agents with different LLM backends.

Dynamic human involvement: Humans can join, leave, or supervise at any point.

Centralized message management: Group chat manager logs and routes conversations.

Role specialization: Each agent contributes unique expertise to the conversation.

## 🚀 Use Cases
Collaborative marketing campaign design.

Social media content brainstorming and scheduling.

Strategic decision-making with AI and human collaboration.

Automated multi-agent customer engagement and support.

## 📚 Requirements
Access to LLM APIs: OpenAI GPT, Anthropic Claude, Google Gemini

Python 3.8+
Optional frontend for human agent interaction
