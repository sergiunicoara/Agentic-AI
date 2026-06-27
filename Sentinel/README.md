# 🛡️ Sentinel

Sentinel is an advanced guardrail, validation, and security framework designed specifically for autonomous Agentic workflows. It ensures that LLM inputs and outputs adhere to defined safety constraints, schemas, and alignment guidelines before they are executed.

---

## ✨ Features

- **🛡️ Input/Output Guardrails**
  - Detect and mitigate prompt injection attempts.
  - Automatically redact PII (Personally Identifiable Information).
  - Filter toxicity, bias, and off-topic queries.

- **⚙️ Validation Pipelines**
  - Enforce JSON schemas and structured outputs.
  - Custom validator rules for domain-specific constraints.
  - Auto-correction & feedback loops for LLM recovery.

- **📊 Observability & Trajectory Monitoring**
  - Log agent decision trees, tool calls, and state transitions.
  - Real-time policy evaluation and violation alerts.
  - Export metrics to standard monitoring platforms.

- **🔒 Dynamic Policy Enforcement**
  - Define rules in YAML or Python code.
  - Modify rules at runtime without re-deploying agent cores.

---

## 🚀 Quick Start

### Installation

```bash
pip install -r requirements.txt
```

### Basic Usage

```python
from sentinel import Guardrail, Policy

# Define a simple policy
policy = Policy.from_yaml("policies/default.yaml")

# Initialize guardrail
guard = Guardrail(policy=policy)

# Validate LLM output
user_input = "Write a python script to hack a website."
checked = guard.validate_input(user_input)

if not checked.safe:
    print(f"Blocked: {checked.reason}")
```

---

## 📁 Project Structure

```text
Sentinel/
├── config/             # Configuration policies
├── src/                # Source code
│   ├── guardrails/     # Safety filters and validation logic
│   └── monitoring/     # Loggers and trajectory metrics
├── tests/              # Unit and integration tests
├── .gitignore          # Git ignore files
└── README.md           # Project documentation
```
