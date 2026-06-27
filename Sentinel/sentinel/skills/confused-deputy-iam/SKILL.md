---
name: confused-deputy-iam
description: Evaluates whether tools and agents run with excessive privileges or are susceptible to unauthorized privilege escalation.
triggers:
  - iam
  - credentials
  - confused deputy
  - privilege
---

# Confused Deputy IAM

## What to look for
- Agents calling tools with the user's authority without explicit authorization check.
- Over-privileged credentials or IAM service account configurations shared globally.
- Inability to restrict tool parameter parameters based on the current context.

## Evidence required
- Configuration or code templates revealing overly broad IAM scopes.
- Lack of resource-level isolation checks when calling file system or network APIs.

## Remediation patterns
- Principle of Least Privilege: bind agent tool permissions to specific roles.
- Implement explicit user-in-the-loop validation for dangerous actions.
- Use sandboxing/namespaces for execution environments.
