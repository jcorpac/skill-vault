# Skill Vault 🛡️

[![CI Test Suite](https://github.com/jcorpac/skill-vault/actions/workflows/test.yml/badge.svg)](https://github.com/jcorp/skill-vault/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![npm version](https://img.shields.io/npm/v/@jcorpac/skill-vault.svg)](https://www.npmjs.com/package/@jcorpac/skill-vault)
[![Agent Skills](https://img.shields.io/badge/Agent%20Skills-Standard-green.svg)](SKILL.md)

> **Automatic Background Skill Router, Read-Only JIT MCP Server & Tiered Cold-Storage Engine for AI Coding Agents.**
> Works across **Google Antigravity, Claude Code, Gemini CLI, Cursor, and CI/CD**.

---

## ⚡ The Problem: Context Bloat & Skill Bleed

Loading 50–250+ specialized skills into active AI prompts causes:
1. **Context Window Saturation**: Thousands of prompt tokens consumed before a conversation starts.
2. **Skill Bleed**: Conflicting instructions from unrelated frameworks degrade tool selection and reasoning.
3. **Manual Friction**: Constantly enabling/disabling plugins or approving CLI searches slows down every session.

## 💡 The Solution: Zero-Approval Background JIT Orchestration

**Skill Vault v2.0** keeps **L1 Active Context** permanently minimal (core skills only) while giving the agent **automatic, zero-approval access** to every skill stored in **L2 Cold Storage (`skill_archive/`)**:

```text
┌─────────────────────────────────────────────────────────────────────────┐
│                             AI CODING AGENT                             │
│          (Google Antigravity / Claude Code / Gemini CLI / Cursor)       │
└──────────────┬────────────────────────────────────────┬─────────────────┘
               │                                        │
   [1. Background Lifecycle Hooks]         [2. Mid-Turn Read-Only MCP]
     • SessionStart (silent sync & index)    • search_skills(query)
     • PreInvocation / UserPromptSubmit      • load_skill(name, file?)
       └─► Pre-built BM25 + Multi-Signal Router (~50–90ms, no approvals)
           ├─ Unrelated prompt  ──► Injects 0 tokens
           ├─ High confidence   ──► Inlines top 1–2 SKILL.md (<=12 KB cap)
           └─ Broad / medium    ──► Emits 1-line compact pointers
               │                                        │
               └───────────────────┬────────────────────┘
                                   ▼
                      [L2 Cold Storage Archive]
                    skill_archive/search_index.json
                    skill_archive/backup_manifest.json
                    skill_archive/skills/<skill_name>/
```

---

## 🚀 Quickstart

### 1. One-Command Setup (Recommended)
Install the background lifecycle hooks, read-only MCP server, and pre-built search index for your agent:

```bash
# Auto-detect installed agents (Antigravity, Claude Code, Gemini CLI, Cursor)
npx @jcorpac/skill-vault setup

# Or target Antigravity explicitly (and migrate legacy nested archive if present)
npx @jcorpac/skill-vault setup --agent antigravity --migrate-archive
```

### 2. Run Directly via Python CLI (Pure Standard Library)
```bash
# Test what the background router injects for any prompt
python scripts/skill_vault.py route "optimize slow postgres query"

# Check routing telemetry (0-token turn %, latency, top skills)
python scripts/skill_vault.py stats

# Verify archive integrity
python scripts/skill_vault.py verify --fix
```

---

## 🛠️ CLI Command Reference

| Command | Description |
| :--- | :--- |
| `skill-vault setup` | Install background hooks, read-only MCP server, and plugin bundle (`--agent`, `--scope`, `--migrate-archive`, `--dry-run`). |
| `skill-vault route "<prompt>"` | Dry-run the JIT router and inspect BM25 scores, tiers (`INLINE`/`POINTER`), and estimated token budget. |
| `skill-vault stats` | Summarize local routing telemetry (`0`-token turn %, avg/p95 latency, top matched skills). |
| `skill-vault search "<query>"` | Multi-term BM25 search across skill names, tags, descriptions, headings, and body identifiers. |
| `skill-vault sync` | Scan plugins & active dirs, ingest updates, prune non-core skills (automatically protecting hook/MCP dependencies). |
| `skill-vault recategorize --auto` | Re-classify `"General & Utility Skills"` using expanded domain rules. |
| `skill-vault dedupe` | Consolidate hyphen/underscore duplicate skills in L2 while keeping the newest version. |
| `skill-vault list` / `status` | Present active (L1) and archived (L2) skills and category counts. |
| `skill-vault archive` / `restore` | Move specific skills or categories between L1 and L2 (recency-aware). |
| `skill-vault import <name>` | Copy vaulted skills into a project's `.agents/skills` or `skills/` directory. |
| `skill-vault optimize` | Prune/mount active skills using workspace file fingerprints. |
| `skill-vault config` | Inspect or customize core skills, fingerprints, category rules, and `--set-routing` thresholds. |
| `skill-vault reindex` / `verify` | Rebuild `INDEX.md` + `search_index.json` and audit archive integrity. |
| `skill-vault uninstall` | Safely restore all archived skills to L1 and remove Skill Vault wiring & files (`eject` alias). |

---

## 🎯 Key Design Principles

1. **Zero Context Bloat by Default**: Generic prompts (`"Refactor this function"`, `"Write a git commit message"`) inject **0 tokens**. Same-turn tool-call loops short-circuit automatically, and already-injected skills never re-inject in the same conversation.
2. **Zero-Approval Background Execution**: Hooks run natively in the agent lifecycle before the model is called; mid-turn fallback uses a 2-tool read-only MCP server (`search_skills`, `load_skill`) with strict directory-containment guards.
3. **`SKILL.md` Purity**: `SKILL.md` files are never modified during indexing or categorization.
4. **Hook-Dependency Safety**: `sync`, `optimize`, and `archive` inspect sibling `hooks.json` and `mcp_config.json` files so plugin-referenced skill scripts are never accidentally pruned.
5. **Zero Runtime Dependencies**: Pure Python 3.10+ standard library across Windows, macOS, and Linux.

---

## 🧪 Running the Test Suite

```bash
python -m unittest discover -s tests -v
# Or via npm:
npm test
```

---

## 📄 License

MIT License. See [LICENSE](LICENSE) for details.
