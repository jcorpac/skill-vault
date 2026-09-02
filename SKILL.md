---
name: skill-vault
description: Universal agent-agnostic and OS-agnostic skill router, tiered storage manager, and lifecycle auditor. Solves context bloat and skill bleed by managing active skills vs archived cold storage across environments (Google Antigravity, Claude Code, Cursor, CI/CD).
---

# Skill Vault: Universal Agent Skill Lifecycle & Storage Manager

## Overview
**Skill Vault** provides an **agent-agnostic**, **environment-agnostic**, and **OS-agnostic** framework for:
1. **Tiered Context Optimization**: Managing active skills (L1 context memory) and cold-storage archives (L2 disk storage) to eliminate "skill bleed" and prompt token waste.
2. **Dynamic Skill Routing**: Discovering, querying, and dynamically executing specialized domain skills across active and archived repositories.
3. **Decoupled Categorization**: Organizing skills via manifest metadata without modifying `SKILL.md` files.
4. **Bi-Directional Integrity Auditing**: Verifying and self-healing consistency across disk folders, `backup_manifest.json`, and `INDEX.md`.

---

## 1. Skill Discovery & Execution Protocol (Agent-Agnostic)

Whenever a user request requires specialized domain knowledge:

1. **Locate Target Skill**:
   - Check active skill locations (`skills/`, `.agents/skills/`, `.claude/skills/`, `plugins/*/skills/`).
   - If missing from active locations, search the central archive manifest via CLI:
     ```bash
     python scripts/skill_vault.py search "<keyword or topic>"
     ```
     or consult `skill_archive/INDEX.md` / `skill_archive/backup_manifest.json`.

2. **Execute Based on Environment Capabilities**:
   - **Multi-Agent / Delegation Supported** (e.g., Antigravity `invoke_subagent`, Claude Code subagent):
     Spawn a subagent instructed to view the target `SKILL.md` and execute the task.
   - **Single-Agent CLI / Standalone Mode**:
     Use native file-reading tools to load the target `SKILL.md` directly into main context.

---

## 2. Skill Lifecycle Management Operations (Automated via CLI)

All lifecycle operations are executed via the portable Python CLI `scripts/skill_vault.py`.

> [!NOTE]
> `SKILL.md` files are **never modified** when categorizing or archiving. Categories are strictly routing metadata stored inside `backup_manifest.json` and presented in `INDEX.md`.

### A. Archiving Skills (LLM-Driven Categorization)
When asked to archive an active skill into cold storage:
1. Read the skill's `SKILL.md` to understand its domain.
2. Select a concise, human-readable category fitting the user's workspace (e.g. `"Cloud Infrastructure"`, `"Data Engineering"`, `"Mobile Development"`, `"Bioinformatics"`).
3. Run the archive command with `--category`:
```bash
# Archive a single skill with category
python scripts/skill_vault.py archive <skill_name> --category "<Category Name>"

# Archive multiple skills matching a pattern
python scripts/skill_vault.py archive --pattern "gcp-*" --category "GCP & Data Engineering"

# Archive while keeping the active folder intact
python scripts/skill_vault.py archive <skill_name> --category "<Category Name>" --keep-active
```

### B. Recategorizing Skills
To reorganize existing archived skills without touching `SKILL.md`:
```bash
python scripts/skill_vault.py recategorize <skill_name> "<New Category Name>"
```

### C. Unarchiving / Restoring Skills
To restore archived skills back to active availability:
```bash
# Restore a specific skill
python scripts/skill_vault.py restore <skill_name>

# Restore all skills in a category
python scripts/skill_vault.py restore --category "GCP & Data Engineering"

# Restore all archived skills
python scripts/skill_vault.py restore --all
```

### D. Reindexing & Manifest Refresh
To rebuild `INDEX.md` and ensure all paths and category sections are synchronized:
```bash
python scripts/skill_vault.py reindex
```

### E. Presenting Skills & Tier Status
To get a rapid overview of what skills are currently in active context memory (L1) vs. cold storage (L2):
```bash
# Full overview of active and archived skills
python scripts/skill_vault.py list

# Quick breakdown of counts and categories
python scripts/skill_vault.py status

# List only active skills in context
python scripts/skill_vault.py list --active

# List archived skills in a specific category
python scripts/skill_vault.py list --archived --category "Cloud SQL"

# Output structured JSON (for scripts/dashboards)
python scripts/skill_vault.py list --json
```

### F. Skill Discovery & Keyword Search
```bash
python scripts/skill_vault.py search "<keyword>"
```

### G. Archive Integrity Audit & Self-Healing
To confirm bi-directional consistency across disk folders, `backup_manifest.json`, and `INDEX.md`:
```bash
# Run integrity verification audit
python scripts/skill_vault.py verify

# Run audit and automatically fix any detected discrepancies
python scripts/skill_vault.py verify --fix
```

### H. Automated Context Optimization (Zero-Effort Pruning & Mounting)
To automatically keep only the minimum necessary skills active in context memory (L1) based on workspace fingerprints, while parking unneeded skills in cold storage (L2):
```bash
# Automatically optimize active skills for the current workspace
python scripts/skill_vault.py optimize

# Preview what would be archived and mounted without moving files
python scripts/skill_vault.py optimize --dry-run

# Optimize for a specific workspace folder and protect custom skills
python scripts/skill_vault.py optimize --workspace "C:\Projects\my-repo" --protect my-custom-skill
```

---

## 3. Environment & OS Compatibility Guidelines

- **Base Directory**: Auto-discovers the workspace root relative to the script location, current working directory, or via `--base-dir <path>` / `$SKILL_VAULT_BASE`.
- **Portable Relative Links**: `INDEX.md` and `backup_manifest.json` use relative paths, allowing the skill repository to be committed to Git or shared across environments seamlessly.
- **Pure Python**: Requires only Python 3 standard library (`os`, `sys`, `json`, `re`, `shutil`, `hashlib`, `argparse`, `pathlib`).

---

## 4. Automated Testing Harness

A sandboxed test suite is located in `tests/test_skill_vault.py` to prevent regressions whenever changes are made:

```bash
# Run test suite
python -m unittest discover -s tests -v
```
