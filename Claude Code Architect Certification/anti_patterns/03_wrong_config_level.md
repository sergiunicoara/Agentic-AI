# CCA-F D3.1 Anti-Pattern: Wrong Configuration Level
# "Team standards put in user-level config" — #3 production failure on the exam

## The Three Levels (memorize this hierarchy)

```
~/.claude/settings.json          ← USER level
  • Personal preferences only
  • NOT committed to repo
  • Applies to ALL your projects
  • Example: theme, personal API keys, personal tool preferences

<project>/.claude/settings.json  ← PROJECT level  ← TEAM STANDARDS GO HERE
  • Shared with entire team
  • Committed to repo (unless has secrets)
  • Applies to this project only
  • Example: allowed tools, hooks, team coding standards

<project>/.claude/settings.local.json  ← LOCAL override
  • Personal overrides for this project only
  • Add to .gitignore — never commit
  • Example: local dev DB URL, personal debug flags
```

## The Exam Trap

### ❌ BAD: Team standard in user-level config
```json
// ~/.claude/settings.json  ← WRONG PLACE
{
  "permissions": {
    "allow": ["Bash(uv:*)"],   // team uses uv, not pip
    "deny": ["Bash(pip install:*)"]
  },
  "hooks": {
    "PreToolUse": [...]         // team-wide hook
  }
}
```

**Why this fails:**
- Only applies to YOUR machine — other team members don't get it
- When new dev joins, they have wrong permissions
- No audit trail in git
- Each developer must manually configure their `~/.claude/settings.json`
- The exam calls this: "team standards put in user-level config"

### ✅ GOOD: Team standard in project-level config
```json
// .claude/settings.json  ← CORRECT — committed to repo
{
  "_comment": "Team standards — all team members inherit these",
  "permissions": {
    "allow": ["Bash(uv:*)"],
    "deny": ["Bash(pip install:*)"]
  },
  "hooks": {
    "PreToolUse": [{
      "matcher": "Bash",
      "hooks": [{"type": "command", "command": "python .claude/hooks/pre_tool_use.py"}]
    }]
  }
}
```

```json
// ~/.claude/settings.json  ← personal prefs only
{
  "theme": "dark",
  "editor": "vscode"
}
```

## CLAUDE.md Hierarchy (D3.1 — also tested)

```
~/.claude/CLAUDE.md              ← applies to ALL projects (personal rules)
<project>/CLAUDE.md              ← applies to this project (team rules)
<project>/subdir/CLAUDE.md       ← applies only within that subdirectory
```

**@import syntax** — modular CLAUDE.md:
```markdown
# project/CLAUDE.md
@.claude/rules/agents.md     ← path-specific rule for agents/**
@.claude/rules/mcp.md        ← path-specific rule for mcp/**
```

**Path-specific rules with YAML frontmatter** (D3.3):
```markdown
---
paths:
  - "agents/**"
  - "agents/subagents/**"
---
Rules that ONLY apply to files matching the glob patterns above.
```

## Exam Question Pattern

Q: "A new team member joins and their Claude Code doesn't enforce the team's
   coding standards. The team lead set them up in their ~/.claude/settings.json.
   What should be done instead?"

A: Move team standards to `.claude/settings.json` (project level, committed to repo).
   The user-level config is personal — it doesn't propagate to other developers.
