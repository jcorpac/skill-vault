---
name: skill-vault
version: 2.1.0
description: >-
  Universal agent-agnostic skill router and tiered storage manager.
  Background hooks automatically inject relevant vaulted skills on demand;
  use MCP tools list_skills/search_skills/load_skill for mid-turn lookups.
---

# Skill Vault: Automatic Skill Router & Cold-Storage Manager

**Skill Vault** keeps active L1 context minimal (core skills only) while preserving instant, zero-approval access to all vaulted L2 domain skills:

1. **Background Lifecycle Hooks (Primary Path)**:
   - `SessionStart` incrementally syncs newly installed/updated plugin skills, refreshes `search_index.json`, and caches workspace fingerprints.
   - `PreInvocation` / `UserPromptSubmit` / `BeforeAgent` scores prompts via BM25 (<100ms), injects top skills/pointers from L2, and adds **0 tokens** on unrelated turns.
2. **Read-Only MCP Fallback (Mid-Turn Discovery)**:
   - If a task pivots mid-turn to a specialized domain not present in context, call the `skill-vault` MCP tools:
     - `list_skills(category?, include_descriptions?)` — List all vaulted L2 skill names grouped by category in one call.
     - `search_skills(query, category?, limit?, offset?)` — Search vaulted L2 skills by keyword, intent, or list categories.
     - `load_skill(name, file?, section?, start_line?)` — Read a skill's `SKILL.md` (full, section, or lines) or companion file.
   - Never mutate L1 active directories or run shell commands solely to browse archived skills when MCP tools are available.

---

## CLI Operations (`skill-vault` / `npx @jcorpac/skill-vault`)

```bash
# Install background hooks, read-only MCP server, and plugin bundle
skill-vault setup --agent auto --scope global

# Dry-run JIT router scoring, tiers, and estimated token usage for a prompt
skill-vault route "<prompt>" [--workspace <path>] [--mode hybrid|inline|pointer]

# Search archived skills using the BM25 index
skill-vault search "<query>" [--category "<Category>"] [--limit 10]

# Inspect background routing telemetry (0-token turn rate, latency, top skills)
skill-vault stats [--limit 100]

# Scan plugins/active dirs, ingest updates, and prune non-core skills
skill-vault sync [--dry-run] [--keep-active]

# Re-classify 'General & Utility Skills' using built-in + custom rules
skill-vault recategorize --auto [--dry-run]

# Consolidate duplicate skills in L2 (keeps newest version)
skill-vault dedupe [--dry-run]

# Inspect or tune routing thresholds & core skills
skill-vault config --show
skill-vault config --set-routing mode hybrid
skill-vault config --set-routing show_ui_notice true

# Archive, restore, import, verify, or cleanly uninstall
skill-vault archive <name> --category "<Category>"
skill-vault restore <name>
skill-vault import <name> --dest "./.agents/skills"
skill-vault verify [--compat] [--fix]
skill-vault uninstall [--dry-run]
```
