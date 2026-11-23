#!/usr/bin/env python3
"""Skill Vault: Universal Skill Archive, Lifecycle Manager & Router.

Works across Google Antigravity, Claude Code, Cursor, CI/CD, and standalone repositories.
Resolves paths relatively without hardcoded user directories. Categories are stored
strictly in backup_manifest.json and INDEX.md, keeping SKILL.md files pure and untouched.
"""

import argparse
from datetime import datetime
import fnmatch
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import skill_router  # noqa: E402

# Default Core Foundation Skills that are protected from auto-archiving
DEFAULT_CORE_SKILLS = {
    "skill-vault",
    "accidental-data-loss-prevention",
    "managing-python-dependencies",
    "find-skills",
    "skill-repair",
}

# Workspace fingerprint signatures mapping to skill categories
WORKSPACE_FINGERPRINTS = {
    "Frontend & Web Development": [
        "package.json",
        "tsconfig.json",
        "next.config.*",
        "vite.config.*",
        "angular.json",
        "svelte.config.*",
        "tailwind.config.*",
    ],
    "Backend & APIs": [
        "pyproject.toml",
        "requirements.txt",
        "go.mod",
        "Cargo.toml",
        "pom.xml",
        "Gemfile",
        "composer.json",
        "openapi.yaml",
        "swagger.json",
    ],
    "Cloud & DevOps": [
        "Dockerfile",
        "docker-compose.yml",
        "docker-compose.yaml",
        "*.tf",
        "Chart.yaml",
        "Pulumi.yaml",
        "serverless.yml",
    ],
    "Databases & Storage": [
        "schema.prisma",
        "drizzle.config.*",
        "alembic.ini",
        "flyway.conf",
        "*.sql",
    ],
    "Mobile & Cross-Platform": [
        "pubspec.yaml",
        "Podfile",
        "Package.swift",
        "app.json",
        "metro.config.js",
    ],
    "AI, LLM & Machine Learning": [
        "*.ipynb",
        "MLproject",
        "conda.yaml",
        "dvc.yaml",
    ],
    "Testing, QA & Security": [
        "playwright.config.*",
        "cypress.config.*",
        "vitest.config.*",
        "jest.config.*",
        "pytest.ini",
    ],
    "BigQuery & Data Warehouse": [
        "dbt_project.yml",
        "dataform.json",
        "bigquery.json",
        "*.sql",
    ],
    "GCP & Data Engineering": [
        "dags",
        "airflow.cfg",
        "cloudbuild.yaml",
        "cloudbuild.json",
        "*.tf",
        "Dockerfile",
    ],
    "AlloyDB": [
        "alembic.ini",
        "alloydb.json",
    ],
    "Cloud SQL": [
        "cloudsql.json",
    ],
    "Science & Biomedicine": [
        "*.pdb",
        "*.fasta",
        "*.fa",
        "*.cif",
        "*.vcf",
        "*.bam",
    ],
    "Gemini API & AI Agents": [
        "agent.py",
        "evals.py",
        "gemini.json",
    ],
    "Android Development": [
        "build.gradle",
        "build.gradle.kts",
        "AndroidManifest.xml",
    ],
    "Firebase": [
        "firebase.json",
        "firestore.rules",
        ".firebaserc",
    ],
    "Robotics & MuJoCo": [
        "*.urdf",
        "*.mjcf",
    ],
}

DEFAULT_WORKSPACE_FINGERPRINTS = WORKSPACE_FINGERPRINTS

# Default keyword rules for auto-categorizing skills across universal ecosystems
DEFAULT_CATEGORY_RULES = {
    "Knowledge & Wiki Architecture": [
        "wiki",
        "knowledge base",
        "documentation architecture",
    ],
    "Firebase": [
        "firebase",
        "firestore",
        "crashlytics",
        "remote config",
        "app hosting",
        "firebase auth",
    ],
    "Google Workspace": [
        "gmail",
        "gcalendar",
        "gdocs",
        "gdrive",
        "gsheets",
        "gslides",
        "google workspace",
        "google calendar",
        "google docs",
        "google sheets",
        "google slides",
        "google drive",
    ],
    "Robotics & MuJoCo": [
        "mujoco",
        "mjcf",
        "urdf",
        "robotics",
        "kinematics",
        "inverse kinematics",
        "gripper",
        "actuator",
    ],
    "Chrome DevTools & Web Performance": [
        "chrome-devtools",
        "chrome devtools",
        "chrome-extension",
        "chrome extension",
        "memory leak",
        "memory-leak",
        "lcp",
        "core web vitals",
        "lighthouse",
    ],
    "Google Maps & Geo": [
        "google-maps",
        "google_maps",
        "maps-platform",
        "maps platform",
    ],
    "Gemini API & AI Agents": [
        "gemini",
        "adk",
        "live-api",
        "live api",
        "llm agent",
        "vertex ai",
        "vertex",
    ],
    "Android Development": [
        "android",
        "gradle",
        "apk",
        "adb",
        "jetpack compose",
    ],
    "BigQuery & Data Warehouse": [
        "bigquery",
        "dbt",
        "dataform",
        "data warehouse",
        "lakehouse",
    ],
    "AlloyDB": [
        "alloydb",
        "omni",
    ],
    "Databases & Storage": [
        "prisma",
        "drizzle",
        "sqlalchemy",
        "redis",
        "mongodb",
        "dynamodb",
        "cassandra",
        "clickhouse",
        "supabase",
        "sqlite",
        "vector db",
        "pinecone",
        "qdrant",
    ],
    "Cloud SQL": [
        "cloud sql",
        "cloudsql",
        "postgres",
        "postgresql",
        "mysql",
    ],
    "Science & Biomedicine": [
        "protein",
        "alphafold",
        "pdb",
        "dna",
        "rna",
        "chembl",
        "bioinformatics",
        "variant",
        "genome",
        "pymol",
        "foldseek",
        "pubmed",
    ],
    "GCP & Data Engineering": [
        "gcp",
        "airflow",
        "composer",
        "spanner",
        "dataflow",
        "dataproc",
        "pubsub",
        "cloud storage",
        "cloud run",
        "bigtable",
        "gcloud",
        "gcs",
        "google-cloud",
        "google_cloud",
        "spark",
        "lakehouse",
    ],
    "Testing, QA & Security": [
        "playwright",
        "cypress",
        "jest",
        "vitest",
        "pytest",
        "selenium",
        "e2e",
        "unit test",
        "tdd",
        "owasp",
        "pentest",
        "vulnerability",
        "security audit",
    ],
    "Mobile & Cross-Platform": [
        "flutter",
        "dart",
        "swift",
        "swiftui",
        "ios",
        "xcode",
        "react native",
        "expo",
        "kotlin multiplatform",
    ],
    "Frontend & Web Development": [
        "react",
        "nextjs",
        "next.js",
        "vue",
        "svelte",
        "angular",
        "tailwind",
        "css",
        "frontend",
        "vite",
        "webpack",
        "dom",
        "a11y",
        "accessibility",
    ],
    "Cloud & DevOps": [
        "aws",
        "azure",
        "kubernetes",
        "k8s",
        "helm",
        "docker",
        "terraform",
        "pulumi",
        "ansible",
        "github actions",
        "ci/cd",
        "cloudflare",
        "vercel",
        "netlify",
        "devops",
        "prometheus",
        "grafana",
    ],
    "AI, LLM & Machine Learning": [
        "openai",
        "anthropic",
        "claude",
        "langchain",
        "llamaindex",
        "huggingface",
        "pytorch",
        "tensorflow",
        "rag",
        "embeddings",
        "fine-tuning",
        "machine learning",
        "deep learning",
    ],
    "Backend & APIs": [
        "fastapi",
        "flask",
        "django",
        "express",
        "nestjs",
        "graphql",
        "rest api",
        "grpc",
        "golang",
        "rust",
        "spring boot",
        "rails",
        "microservice",
        "backend",
        "oauth",
        "jwt",
        "stripe",
    ],
}


def parse_version_tuple(ver_str):
    """Parse version string into a comparable numeric tuple, e.g. 'v20' -> (20,), '1.1.5' -> (1, 1, 5)."""
    if not ver_str:
        return None
    cleaned = str(ver_str).strip().strip("'\"").lstrip("vV")
    nums = re.findall(r"\d+", cleaned)
    if nums:
        return tuple(int(n) for n in nums)
    return None


def compare_version_tuples(ver_a, ver_b):
    """Compare two version tuples with zero-padding. Returns 1, -1, or 0."""
    if ver_a is None or ver_b is None:
        return 0
    ta = tuple(ver_a)
    tb = tuple(ver_b)
    max_len = max(len(ta), len(tb))
    pa = ta + (0,) * (max_len - len(ta))
    pb = tb + (0,) * (max_len - len(tb))
    if pa > pb:
        return 1
    if pa < pb:
        return -1
    return 0


def get_skill_metadata(skill_dir):
    """Extract parsed version and latest modification timestamp for a skill directory."""
    skill_dir = Path(skill_dir)
    skill_md = skill_dir / "SKILL.md"

    ver_tuple = None
    if skill_md.exists():
        try:
            content = skill_md.read_text(encoding="utf-8", errors="ignore")
            fm_match = re.match(r"^---\s*\n(.*?)\n---(?:\s*\n|\s*\Z)", content, re.DOTALL)
            if fm_match:
                fm_text = fm_match.group(1)
                v_match = re.search(r"^version:\s*([^\n]+)", fm_text, re.MULTILINE | re.IGNORECASE)
                if not v_match:
                    v_match = re.search(r"^[ \t]+version:\s*([^\n]+)", fm_text, re.MULTILINE | re.IGNORECASE)
                if v_match:
                    ver_tuple = parse_version_tuple(v_match.group(1))
        except Exception:
            pass

    latest_mtime = 0.0
    try:
        files = []
        if skill_dir.exists():
            for root, dirs, filenames in os.walk(skill_dir):
                root_path = Path(root)
                # Do not bleed mtimes from nested sibling skill folders inside a single_skill_dir
                dirs[:] = [d for d in dirs if not (root_path / d / "SKILL.md").exists()]
                for fname in filenames:
                    files.append(root_path / fname)
        if files:
            latest_mtime = max(f.stat().st_mtime for f in files)
        elif skill_dir.exists():
            latest_mtime = skill_dir.stat().st_mtime
    except Exception:
        pass

    return ver_tuple, latest_mtime


def compare_skill_recency(dir_a, dir_b):
    """Compare two skill directories to determine which is newer.

    Returns:
       1 if dir_a is newer than dir_b
      -1 if dir_b is newer than dir_a
       0 if they are equivalent in version and recency
    """
    a_exists = (Path(dir_a) / "SKILL.md").exists()
    b_exists = (Path(dir_b) / "SKILL.md").exists()
    if a_exists != b_exists:
        return 1 if a_exists else -1

    ver_a, mtime_a = get_skill_metadata(dir_a)
    ver_b, mtime_b = get_skill_metadata(dir_b)

    # 1. Compare semantic/numeric versions if both exist and differ
    if ver_a is not None and ver_b is not None:
        vcmp = compare_version_tuples(ver_a, ver_b)
        if vcmp != 0:
            return vcmp

    # 2. Compare file modification timestamps (allowing a 1-second margin for filesystem granularity)
    if abs(mtime_a - mtime_b) > 1.0:
        return 1 if mtime_a > mtime_b else -1

    # 3. Tie-breaker when timestamps match: prefer an explicitly versioned skill
    if (ver_a is not None) != (ver_b is not None):
        return 1 if ver_a is not None else -1

    return 0


def resolve_base_dir(cli_base=None):
    """Dynamically resolve the base directory for skills and archives."""
    if cli_base:
        p = Path(cli_base).resolve()
        if p.exists():
            return p

    env_base = os.environ.get("SKILL_VAULT_BASE") or os.environ.get("SKILL_BASE_DIR") or os.environ.get("AGENTS_HOME")
    if env_base:
        p = Path(env_base).resolve()
        if p.exists():
            return p

    # 1. Prioritize ancestors of the script location that actually contain a skill_archive
    script_path = Path(__file__).resolve()
    for parent in script_path.parents:
        if parent.name != "skill_archive" and (parent / "skill_archive").exists():
            return parent

    cwd = Path.cwd().resolve()
    home = Path.home()
    candidates = [
        cwd,
        cwd / ".agents",
        cwd / ".claude",
        cwd / ".gemini",
        cwd / ".cursor",
        home / ".gemini" / "config",
        home / ".gemini" / "config" / "skills" / "skill-vault",
        home / ".agents",
        home / ".claude",
        home / ".gemini",
        home / ".cursor",
    ]
    # 2. Check standard workspace and global locations for an existing skill_archive
    for candidate in candidates:
        if candidate.exists() and (candidate / "skill_archive").exists():
            return candidate

    # 3. Fallback to ancestors with skills/ (skipping installed plugins/skill-vault wrapper)
    for parent in script_path.parents:
        if parent.name == "skill-vault" and parent.parent.name == "plugins":
            continue
        if parent.name != "skill_archive" and (parent / "skills").exists():
            return parent

    # 4. Fallback to workspace or global locations with skills/
    for candidate in candidates:
        if candidate.exists() and (candidate / "skills").exists():
            return candidate

    return cwd


class SkillVault:
    def __init__(self, base_dir=None):
        self._explicit_base_dir = bool(base_dir)
        self.base_dir = resolve_base_dir(base_dir)
        self.archive_dir = self.base_dir / "skill_archive"
        self.manifest_file = self.archive_dir / "backup_manifest.json"
        self.index_file = self.archive_dir / "INDEX.md"
        self.search_index_file = self.archive_dir / "search_index.json"
        self.config_file = self.archive_dir / "vault_config.json"
        self.skills_dir = self.base_dir / "skills"

    def _load_raw_config(self):
        """Read raw vault_config.json without creating files or merging defaults."""
        if self.config_file.exists():
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data if isinstance(data, dict) else {}
            except Exception as e:
                print(f"[Warning] Failed to parse {self.config_file}: {e}")
        return {}

    def load_config(self):
        """Load vault_config.json if present and merge with universal defaults."""
        user_cfg = self._load_raw_config()

        disabled_core = set(user_cfg.get("disabled_core_skills", []))
        core_skills = (set(DEFAULT_CORE_SKILLS) | set(user_cfg.get("core_skills", []))) - disabled_core

        merged_fp = {cat: list(pats) for cat, pats in WORKSPACE_FINGERPRINTS.items()}
        for cat, pats in user_cfg.get("workspace_fingerprints", {}).items():
            if cat in merged_fp:
                merged_fp[cat] = list(dict.fromkeys(list(pats) + merged_fp[cat]))
            else:
                merged_fp[cat] = list(pats)

        custom_rules = user_cfg.get("category_rules", {})
        merged_rules = {}
        # Evaluate non-default custom categories first so user overrides take precedence
        for cat, kws in custom_rules.items():
            if cat not in DEFAULT_CATEGORY_RULES:
                merged_rules[cat] = list(kws)
        for cat, kws in custom_rules.items():
            if cat in DEFAULT_CATEGORY_RULES:
                merged_rules[cat] = list(dict.fromkeys(list(kws) + list(DEFAULT_CATEGORY_RULES[cat])))
        for cat, kws in DEFAULT_CATEGORY_RULES.items():
            if cat not in merged_rules:
                merged_rules[cat] = list(kws)

        routing_cfg = dict(skill_router.DEFAULT_ROUTING_CONFIG)
        if isinstance(user_cfg.get("routing"), dict):
            routing_cfg.update(user_cfg["routing"])

        return {
            "core_skills": sorted(core_skills),
            "disabled_core_skills": sorted(disabled_core),
            "workspace_fingerprints": merged_fp,
            "category_rules": merged_rules,
            "routing": routing_cfg,
        }

    def save_config(self, config_data):
        """Persist configuration to vault_config.json."""
        self.archive_dir.mkdir(parents=True, exist_ok=True)
        with open(self.config_file, "w", encoding="utf-8") as f:
            json.dump(config_data, f, indent=2, ensure_ascii=False)

    def get_core_skills(self, extra_protected=None):
        """Return effective set of protected core skill names."""
        core_set = set(self.load_config()["core_skills"])
        if extra_protected:
            core_set.update(extra_protected)
        return core_set

    def parse_skill_frontmatter_field(self, skill_md_path, field_name):
        """Extract a single scalar field from SKILL.md YAML frontmatter."""
        skill_md_path = Path(skill_md_path)
        if not skill_md_path.exists():
            return None
        try:
            content = skill_md_path.read_text(encoding="utf-8", errors="ignore")
            fm_match = re.search(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
            if fm_match:
                pattern = rf"^{re.escape(field_name)}:\s*([^\n]+)"
                match = re.search(pattern, fm_match.group(1), re.MULTILINE | re.IGNORECASE)
                if match:
                    val = match.group(1).strip().strip("'\"")
                    return val if val else None
        except Exception:
            pass
        return None

    def is_core_skill_frontmatter(self, skill_md_path):
        """Return True if SKILL.md frontmatter marks the skill as core/pinned/always_active."""
        for field in ("core", "pinned", "always_active"):
            val = self.parse_skill_frontmatter_field(skill_md_path, field)
            if val and val.strip().lower() in {"true", "yes", "1"}:
                return True
        return False

    def _keyword_matches(self, keyword, text, normalized_text):
        """Match a category keyword against skill name/description text safely."""
        kw = str(keyword).lower().strip()
        if not kw:
            return False
        if kw.isalpha() and len(kw) <= 4:
            pattern = rf"(?<![a-z]){re.escape(kw)}(?![a-z])"
            return bool(re.search(pattern, text) or re.search(pattern, normalized_text))
        return kw in text or kw in normalized_text

    def init(self):
        """Bootstrap standard directory structure for a new workspace or repository."""
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        (self.archive_dir / "skills").mkdir(parents=True, exist_ok=True)
        if not self.manifest_file.exists():
            self.save_manifest([])
        if not self.index_file.exists():
            self.index_file.write_text("# Skill Archive Index\n\nTotal Archived Skills: 0\n", encoding="utf-8")
        print(f"[Initialized] Skill Vault initialized at: {self.base_dir}")
        print(f"  * Active skills:  {self.skills_dir}")
        print(f"  * Archive store:  {self.archive_dir}")

    def get_active_skill_dirs(self):
        """Discover active skill directories."""
        dirs = []
        if self.skills_dir.exists():
            dirs.append(self.skills_dir)

        for sub in [".agents/skills", ".claude/skills"]:
            p = self.base_dir / sub
            if p.exists() and p not in dirs:
                dirs.append(p)

        # Also search active working directory and its skill locations if distinct from base_dir
        cwd = Path.cwd().resolve()
        if cwd != self.base_dir:
            for sub in ["skills", ".agents/skills", ".claude/skills"]:
                p = cwd / sub
                if p.exists() and p not in dirs:
                    dirs.append(p)

        # If base_dir is nested inside a skills folder (e.g. skills/skill-vault)
        if self.base_dir.parent.name == "skills" and self.base_dir.parent.exists():
            if self.base_dir.parent not in dirs:
                dirs.append(self.base_dir.parent)
            parent_plugins = self.base_dir.parent.parent / "plugins"
            if parent_plugins.exists():
                for p in parent_plugins.iterdir():
                    if p.is_dir() and (p / "skills").exists() and (p / "skills") not in dirs:
                        dirs.append(p / "skills")

        plugins_dir = self.base_dir / "plugins"
        if plugins_dir.exists():
            for p in plugins_dir.iterdir():
                if p.is_dir() and (p / "skills").exists() and (p / "skills") not in dirs:
                    dirs.append(p / "skills")
        return dirs

    def parse_skill_name(self, skill_md_path):
        """Extract name from SKILL.md frontmatter."""
        skill_md_path = Path(skill_md_path)
        if not skill_md_path.exists():
            return None
        try:
            content = skill_md_path.read_text(encoding="utf-8", errors="ignore")
            fm_match = re.search(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
            if fm_match:
                n_match = re.search(r"^name:\s*([^\n]+)", fm_match.group(1), re.MULTILINE)
                if n_match:
                    return n_match.group(1).strip().strip("'\"")
        except Exception:
            pass
        return None

    def get_active_skills(self):
        """Discover all currently active skills on disk across standard and plugin layouts."""
        active = {}
        for search_dir in self.get_active_skill_dirs():
            if not search_dir.exists():
                continue

            # Case 1: search_dir contains subdirectories with SKILL.md (e.g. skills/<name>/SKILL.md)
            for folder in search_dir.iterdir():
                if folder.is_dir() and (folder / "SKILL.md").exists():
                    skill_name = self.parse_skill_name(folder / "SKILL.md") or folder.name
                    desc = self.parse_skill_description(folder / "SKILL.md")
                    active[skill_name] = {
                        "name": skill_name,
                        "path": str(folder),
                        "relative_path": self.make_portable_path(folder),
                        "description": desc,
                        "single_skill_dir": False,
                    }

            # Case 2: search_dir itself has SKILL.md directly (e.g. plugins/<plugin>/skills/SKILL.md)
            if (search_dir / "SKILL.md").exists():
                skill_name = self.parse_skill_name(search_dir / "SKILL.md") or search_dir.parent.name
                desc = self.parse_skill_description(search_dir / "SKILL.md")
                active[skill_name] = {
                    "name": skill_name,
                    "path": str(search_dir),
                    "relative_path": self.make_portable_path(search_dir),
                    "description": desc,
                    "single_skill_dir": True,
                }
        return active

    def get_archived_skill_folders(self):
        """Discover all skill folders physically present in the archive directory."""
        archive_subdirs = [self.archive_dir / "skills"]
        if self.archive_dir.exists():
            for p in self.archive_dir.iterdir():
                if p.is_dir() and p.name.startswith("plugins_") and p.name.endswith("_skills"):
                    archive_subdirs.append(p)

        folders = {}
        for base in archive_subdirs:
            if base.exists():
                for folder in base.iterdir():
                    if folder.is_dir():
                        skill_md = folder / "SKILL.md"
                        has_md = skill_md.exists()
                        candidate = {
                            "name": folder.name,
                            "folder": folder,
                            "skill_md": skill_md,
                            "has_skill_md": has_md,
                            "size": skill_md.stat().st_size if has_md else 0,
                        }
                        existing = folders.get(folder.name)
                        if existing is None:
                            folders[folder.name] = candidate
                        elif has_md and (
                            not existing["has_skill_md"]
                            or compare_skill_recency(folder, existing["folder"]) > 0
                        ):
                            folders[folder.name] = candidate
        return folders

    def load_manifest(self):
        """Load backup_manifest.json."""
        if self.manifest_file.exists():
            try:
                with open(self.manifest_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"[Warning] Failed to parse {self.manifest_file}: {e}")
        return []

    def save_manifest(self, manifest):
        """Save manifest sorted by category and name."""
        manifest.sort(key=lambda x: (x.get("category", "").lower(), x.get("name", "").lower()))
        self.archive_dir.mkdir(parents=True, exist_ok=True)
        with open(self.manifest_file, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)

    def parse_skill_description(self, skill_md_path):
        """Extract description from SKILL.md without modifying it."""
        skill_md_path = Path(skill_md_path)
        if not skill_md_path.exists():
            return "No description available."

        with open(skill_md_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()

        fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
        if fm_match:
            fm_text = fm_match.group(1)
            desc_match = re.search(
                r"^description:\s*(?:>[-+]?|\|[-+]?)?\s*\n?(.*?)(?=\n[a-zA-Z0-9_-]+:|\Z)",
                fm_text,
                re.DOTALL | re.MULTILINE,
            )
            if desc_match:
                raw_desc = desc_match.group(1).strip()
                return " ".join(line.strip() for line in raw_desc.splitlines() if line.strip())
            simple_desc = re.search(r"^description:\s*([^\n]+)", fm_text, re.MULTILINE)
            if simple_desc:
                return simple_desc.group(1).strip().strip("'\"")
        return "No description available."

    def find_active_skill(self, skill_name):
        """Find active skill across discovered search paths."""
        for search_dir in self.get_active_skill_dirs():
            target = search_dir / skill_name
            if target.exists() and (target / "SKILL.md").exists():
                return target
        return None

    def get_root_dir(self):
        """Return the top-level environment or workspace root directory.

        When base_dir is an installed skill directory nested inside 'skills/skill-vault',
        returns the parent of 'skills' (e.g. ~/.gemini/config or workspace root).
        """
        if self.base_dir.name == "skill-vault" and self.base_dir.parent.name == "skills":
            return self.base_dir.parent.parent
        return self.base_dir

    def get_skill_vault_dir(self):
        """Locate the installed skill-vault skill/plugin directory if present (excluding git repo roots)."""
        if self.base_dir.name == "skill-vault" and self.base_dir.parent.name in ("skills", "plugins"):
            if not (self.base_dir / ".git").exists():
                return self.base_dir
        root_dir = self.get_root_dir()
        for rel in [
            "plugins/skill-vault",
            "skills/skill-vault",
            ".agents/skills/skill-vault",
            ".claude/skills/skill-vault",
        ]:
            cand = (root_dir / rel).resolve()
            if cand.exists() and not (cand / ".git").exists():
                return cand
        return None

    def get_hook_protected_skills(self):
        """Inspect plugin hooks.json and mcp_config.json files to protect skills referenced by commands."""
        protected = {"skill-vault"}
        plugin_roots = []
        for cand in (self.base_dir / "plugins", self.get_root_dir() / "plugins"):
            if cand.exists() and cand.is_dir():
                res = cand.resolve()
                if res not in plugin_roots:
                    plugin_roots.append(res)

        skill_ref_re = re.compile(r"(?:^|[\s\"'=/\\])skills[/\\]([a-zA-Z0-9._-]+)")

        def _scan_obj(obj):
            if isinstance(obj, str):
                for m in skill_ref_re.finditer(obj):
                    protected.add(m.group(1))
            elif isinstance(obj, list):
                for item in obj:
                    _scan_obj(item)
            elif isinstance(obj, dict):
                for val in obj.values():
                    _scan_obj(val)

        for proot in plugin_roots:
            for pdir in proot.iterdir():
                if not pdir.is_dir():
                    continue
                for cfg_name in ("hooks.json", "mcp_config.json"):
                    cfg_path = pdir / cfg_name
                    if not cfg_path.exists():
                        continue
                    try:
                        data = json.loads(cfg_path.read_text(encoding="utf-8", errors="replace"))
                        _scan_obj(data)
                    except Exception:
                        pass
        return protected

    def _collect_bin_shim_targets(self):
        """Read small launcher shims in antigravity/bin or base_dir/bin to detect path-bound scripts."""
        app_data = os.environ.get("ANTIGRAVITY_APP_DATA_DIR")
        agy_bin = (Path(app_data) / "bin") if app_data else (Path.home() / ".gemini" / "antigravity" / "bin")
        bin_dirs = []
        for cand in (agy_bin, self.base_dir / "bin", self.get_root_dir() / "bin"):
            if cand.exists() and cand.is_dir():
                res = cand.resolve()
                if res not in bin_dirs:
                    bin_dirs.append(res)

        shims = []
        for bdir in bin_dirs:
            try:
                for fp in bdir.iterdir():
                    if not fp.is_file():
                        continue
                    if fp.suffix.lower() not in {".cmd", ".bat", ".sh", ""}:
                        continue
                    try:
                        if fp.stat().st_size > 4096:
                            continue
                        txt = fp.read_text(encoding="utf-8", errors="ignore").lower()
                        shims.append((fp.name, txt))
                    except OSError:
                        pass
            except OSError:
                pass
        return shims

    def assess_skill_compat(self, skill_dir, original_path=None, bin_shim_targets=None, max_single_chars=None):
        """Inspect a skill directory for path dependencies, cross-skill refs, truncation size, and guardrails."""
        skill_dir = Path(skill_dir)
        if max_single_chars is None:
            max_single_chars = int(self.load_config().get("routing", {}).get("max_single_skill_chars", 9000))
        else:
            max_single_chars = int(max_single_chars)

        companion_files = []
        if skill_dir.exists():
            for root, dirs, files in os.walk(skill_dir):
                rp = Path(root)
                dirs[:] = sorted(
                    d for d in dirs
                    if d not in {"__pycache__", ".git", "node_modules"}
                    and not (rp / d / "SKILL.md").exists()
                )
                for fname in sorted(files):
                    if rp == skill_dir and fname == "SKILL.md":
                        continue
                    companion_files.append((rp / fname).relative_to(skill_dir).as_posix())

        has_companions = len(companion_files) > 0
        skill_md = skill_dir / "SKILL.md"
        skill_md_bytes = 0
        md_text = ""
        if skill_md.exists():
            try:
                skill_md_bytes = skill_md.stat().st_size
                md_text = skill_md.read_text(encoding="utf-8", errors="replace")
            except OSError:
                pass
        oversized_skill_md = skill_md_bytes > max_single_chars

        traversal_re = re.compile(
            r"(?:%~dp0\s*\.\.[\\/]\.\.|(?:\.\.[\\/]){2,}|"
            r"path\.resolve\(\s*__dirname\s*,\s*['\"](?:\.\.[\\/]){2,}|\.parents\[\s*[234]\s*\])",
            re.IGNORECASE,
        )
        plugin_env_re = re.compile(
            r"\b(?:PLUGIN_DIR_NAME|CLAUDE_PLUGIN_ROOT|PLUGIN_DIR|PLUGIN_DATA|plugin_data)\b"
        )
        script_exts = {".py", ".js", ".ts", ".sh", ".cmd", ".bat", ".ps1", ".toml"}

        path_reasons = []
        for rel in companion_files:
            fp = skill_dir / rel
            if not rel.startswith("scripts/") and fp.suffix.lower() not in script_exts:
                continue
            try:
                if fp.stat().st_size > 262144:
                    continue
                ftxt = fp.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if traversal_re.search(ftxt):
                path_reasons.append(f"script_parent_traversal: {rel}")
            if plugin_env_re.search(ftxt):
                path_reasons.append(f"script_plugin_root_ref: {rel}")

        if original_path and bin_shim_targets:
            orig_fwd = str(Path(original_path)).lower().replace("\\", "/")
            orig_bck = str(Path(original_path)).lower().replace("/", "\\")
            for shim_name, shim_txt in bin_shim_targets:
                for pat in (orig_fwd, orig_bck):
                    pos = shim_txt.find(pat)
                    if pos != -1:
                        end_pos = pos + len(pat)
                        if end_pos == len(shim_txt) or shim_txt[end_pos] in ("/", "\\", "\"", "'", " ", "\t", "\r", "\n"):
                            path_reasons.append(f"path_shim_target: bin/{shim_name}")
                            break

        cross_re = re.compile(
            r"(?:\.\./[a-zA-Z0-9._-]+(?:/[a-zA-Z0-9._-]+)*|"
            r"\$\{?CLAUDE_PLUGIN_ROOT\}?|\$PLUGIN_DIR|<PLUGIN_DIR>|@skill:[a-zA-Z0-9._-]+)"
        )
        cross_skill_refs = []
        seen_refs = set()
        for m in cross_re.finditer(md_text):
            val = m.group(0)
            if val not in seen_refs:
                seen_refs.add(val)
                cross_skill_refs.append(val)
                if len(cross_skill_refs) >= 15:
                    break

        if has_companions and re.search(
            r"(?:\$\{?CLAUDE_PLUGIN_ROOT\}?|\$PLUGIN_DIR|<PLUGIN_DIR>|\.\./[a-zA-Z0-9._-]+/scripts/)",
            md_text,
        ):
            path_reasons.append("skill_plugin_path_ref: SKILL.md")

        # Deduplicate while preserving order
        path_reasons = list(dict.fromkeys(path_reasons))

        guard_re = re.compile(
            r"(?:trigger:\s*always_on|MANDATORY:\s*Execute FIRST|CRITICAL RULE|STOP AND VERIFY)"
        )
        guardrail_signals = list(dict.fromkeys(m.group(0) for m in guard_re.finditer(md_text[:2000])))

        path_dependent = bool(path_reasons)
        needs_runtime_in_place = bool(path_dependent and has_companions)
        return {
            "path_dependent": path_dependent,
            "needs_runtime_in_place": needs_runtime_in_place,
            "has_companions": has_companions,
            "path_reasons": path_reasons,
            "cross_skill_refs": cross_skill_refs,
            "oversized_skill_md": oversized_skill_md,
            "skill_md_bytes": skill_md_bytes,
            "guardrail_signals": guardrail_signals,
        }

    def _prune_skill_runtime_in_place(self, active_path):
        """Remove SKILL.md only so L1 context drops to 0 while path-dependent companions stay in place."""
        active_path = Path(active_path)
        if not active_path.exists():
            return False
        skill_md = active_path / "SKILL.md"
        if skill_md.exists():
            skill_md.unlink()
        try:
            has_remaining = any(active_path.iterdir())
        except OSError:
            has_remaining = False
        if not has_remaining:
            try:
                active_path.rmdir()
            except OSError:
                pass
            return False
        return True

    def _materialize_runtime_companions(self, archived_dir, target_dir):
        """Copy companion files from L2 to target_dir without creating SKILL.md."""
        archived_dir = Path(archived_dir).resolve()
        target_dir = Path(target_dir).resolve()
        if (target_dir / "SKILL.md").exists():
            return False
        target_dir.mkdir(parents=True, exist_ok=True)

        def _ignore_skill_md_and_nested(curr_dir, names):
            curr_path = Path(curr_dir).resolve()
            ignored = []
            if curr_path == archived_dir:
                for n in names:
                    if n == "SKILL.md":
                        ignored.append(n)
                    elif (curr_path / n).is_dir() and (curr_path / n / "SKILL.md").exists():
                        ignored.append(n)
            return ignored

        shutil.copytree(archived_dir, target_dir, dirs_exist_ok=True, ignore=_ignore_skill_md_and_nested)
        return True

    def make_portable_path(self, abs_path):
        """Convert path to relative from base_dir or root_dir if possible."""
        resolved = Path(abs_path).resolve()
        try:
            return str(resolved.relative_to(self.base_dir))
        except ValueError:
            root_dir = self.get_root_dir()
            if root_dir != self.base_dir:
                try:
                    return str(resolved.relative_to(root_dir))
                except ValueError:
                    pass
            return str(abs_path)

    def resolve_portable_path(self, path_str):
        """Resolve a stored relative path back to an absolute Path."""
        p = Path(path_str)
        if p.is_absolute():
            return p
        cand = (self.base_dir / p).resolve()
        if not cand.exists():
            root_dir = self.get_root_dir()
            if root_dir != self.base_dir:
                root_cand = (root_dir / p).resolve()
                if root_cand.exists():
                    return root_cand
        return cand

    def resolve_original_path(self, path_str, skill_name=None):
        """Resolve a stored original_path to an active L1 Path outside skills/skill-vault."""
        root_dir = self.get_root_dir()
        sv_dir = self.get_skill_vault_dir()
        if not path_str:
            skills_root = root_dir / "skills" if root_dir != self.base_dir else self.skills_dir
            return (skills_root / (skill_name or "unknown-skill")).resolve()

        p = Path(path_str)
        if p.is_absolute():
            resolved = p.resolve()
            if sv_dir and (sv_dir in resolved.parents or resolved == sv_dir):
                try:
                    rel = resolved.relative_to(sv_dir)
                    return (root_dir / rel).resolve()
                except ValueError:
                    pass
            return resolved

        return (root_dir / p).resolve()

    def _copy_skill_safely(self, src_dir, dst_dir):
        """Copy a skill folder from src_dir to dst_dir without deleting nested sibling skills."""
        src_dir = Path(src_dir).resolve()
        dst_dir = Path(dst_dir).resolve()
        dst_dir.parent.mkdir(parents=True, exist_ok=True)

        def _ignore_nested_skills(curr_dir, names):
            curr_path = Path(curr_dir).resolve()
            if curr_path == src_dir:
                return [
                    n for n in names
                    if (curr_path / n).is_dir() and (curr_path / n / "SKILL.md").exists()
                ]
            return []

        if dst_dir.exists():
            nested_skill_dirs = {
                sub.name for sub in dst_dir.iterdir()
                if sub.is_dir() and (sub / "SKILL.md").exists()
            }
            if nested_skill_dirs or dst_dir.name == "skills":
                for item in list(dst_dir.iterdir()):
                    if item.name in nested_skill_dirs:
                        continue
                    if item.is_dir():
                        shutil.rmtree(item)
                    else:
                        item.unlink()
                shutil.copytree(src_dir, dst_dir, dirs_exist_ok=True, ignore=_ignore_nested_skills)
                return
            shutil.rmtree(dst_dir)

        shutil.copytree(src_dir, dst_dir, dirs_exist_ok=True, ignore=_ignore_nested_skills)

    def parse_index_file(self):
        """Parse INDEX.md and return extracted skills with categories and link targets."""
        if not self.index_file.exists():
            return {}

        with open(self.index_file, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()

        indexed_skills = {}
        current_category = "General & Utility Skills"

        for line in content.splitlines():
            cat_match = re.match(r"^##\s+(.*?)\s+\(\d+\s+skills?\)", line)
            if cat_match:
                current_category = cat_match.group(1).strip()
                continue

            skill_match = re.match(r"^###\s+`([^`]+)`", line)
            if skill_match:
                skill_name = skill_match.group(1).strip()
                indexed_skills[skill_name] = {
                    "name": skill_name,
                    "category": current_category,
                    "link_path": None,
                }
                continue

            link_match = re.search(r"\- \*\*Archived Path\*\*:\s+\[`SKILL\.md`\]\((.*?)\)", line)
            if link_match and indexed_skills:
                last_skill = list(indexed_skills.keys())[-1]
                if indexed_skills[last_skill]["link_path"] is None:
                    indexed_skills[last_skill]["link_path"] = link_match.group(1).strip()

        return indexed_skills

    # --- Workspace & Optimization Engine ---

    def detect_workspace_categories(self, workspace_path=None):
        """Inspect workspace files in a single depth-bounded pass and return matched skill categories."""
        target_ws = Path(workspace_path).resolve() if workspace_path else Path.cwd().resolve()
        matched = {}
        config = self.load_config()
        fingerprints = config["workspace_fingerprints"]

        if not target_ws.exists():
            return matched

        ignored_dirs = {".git", "node_modules", "__pycache__", ".venv", "venv", ".tox", "dist", "build", ".next", "target"}
        seen_names = set()
        seen_rel_paths = set()
        ws_tokens = {}

        for root, dirs, files in os.walk(target_ws):
            dirs[:] = [d for d in dirs if d not in ignored_dirs]
            rel_path = Path(root).relative_to(target_ws)
            rel_depth = len(rel_path.parts)
            if rel_depth > 3:
                dirs[:] = []
                continue
            rel_prefix = "" if rel_path == Path(".") else rel_path.as_posix().lower() + "/"
            for entry_name in dirs + files:
                low_name = entry_name.lower()
                seen_names.add(low_name)
                seen_rel_paths.add(rel_prefix + low_name)
                tokens = {t for t in re.split(r"[-_.\s]+", low_name) if t}
                for tok in tokens:
                    ws_tokens.setdefault(tok, entry_name)

        for category, patterns in fingerprints.items():
            for pat in patterns:
                pat_l = str(pat).lower()
                if "*" in pat_l or "?" in pat_l:
                    hit = any(fnmatch.fnmatchcase(n, pat_l) for n in seen_names) or any(
                        fnmatch.fnmatchcase(rp, pat_l) for rp in seen_rel_paths
                    )
                else:
                    hit = (pat_l in seen_names) or (pat_l in seen_rel_paths)
                if hit:
                    matched.setdefault(category, []).append(pat)
                    break

        # Inspect categories present in manifest for workspace filename/directory keyword matches
        manifest = self.load_manifest()
        manifest_categories = {m.get("category") for m in manifest if m.get("category")}
        unmatched_cats = [c for c in sorted(manifest_categories) if c not in matched]
        if unmatched_cats:
            stop_words = {"and", "the", "skills", "general", "utility"}
            for cat in unmatched_cats:
                words = [
                    w.lower()
                    for w in re.findall(r"[a-zA-Z0-9]+", cat)
                    if len(w) > 2 and w.lower() not in stop_words
                ]
                for w in words:
                    if w in ws_tokens:
                        matched.setdefault(cat, []).append(ws_tokens[w])
                        break

        return matched

    def optimize(self, workspace_path=None, protected_skills=None, dry_run=False, force=False):
        """Automatically minimize active skills to essential Core + workspace-relevant skills.
        
        Archives unneeded active skills into cold storage and mounts matching domain skills,
        prioritizing newer versions when versions overlap.
        """
        target_ws = Path(workspace_path).resolve() if workspace_path else Path.cwd().resolve()
        core_set = self.get_core_skills(protected_skills)
        hook_protected = self.get_hook_protected_skills()

        print("==================================================")
        print("          SKILL VAULT AUTO-OPTIMIZATION")
        print(f"  Target Workspace: {target_ws}")
        print("==================================================\n")

        # 1. Detect workspace domain
        detected_categories = self.detect_workspace_categories(target_ws)
        if detected_categories:
            print("Detected Tech Stack & Fingerprints:")
            for cat, sigs in detected_categories.items():
                print(f"  * {cat} (matched: {', '.join(sigs)})")
        else:
            print("Detected Tech Stack: Generic / Multi-purpose (Only Core Foundation Skills required)")
        print("")

        # 2. Inspect active skills vs vault
        active_map = self.get_active_skills()
        manifest = self.load_manifest()
        manifest_by_name = {m["name"]: m for m in manifest}

        to_archive = []
        to_keep = []

        for name, data in active_map.items():
            skill_md_path = Path(data["path"]) / "SKILL.md"
            if name in core_set:
                to_keep.append((name, "Core Foundation Skill"))
            elif name in hook_protected:
                to_keep.append((name, "Protected Plugin Hook/MCP Dependency"))
            elif self.is_core_skill_frontmatter(skill_md_path):
                to_keep.append((name, "Core Foundation Skill (Pinned in Frontmatter)"))
            else:
                skill_cat = manifest_by_name.get(name, {}).get("category") or self.infer_category(
                    name, data["description"], skill_md_path
                )
                if skill_cat in detected_categories:
                    to_keep.append((name, f"Matched Stack ({skill_cat})"))
                else:
                    to_archive.append((name, skill_cat))

        # Check if any kept active skill has a newer version in the archive
        to_upgrade = []
        for name, reason in to_keep:
            if name in manifest_by_name:
                item = manifest_by_name[name]
                archived_path = self.resolve_portable_path(item.get("archived_path", ""))
                active_path = self.find_active_skill(name)
                if archived_path.exists() and active_path and active_path.exists():
                    if compare_skill_recency(archived_path, active_path) > 0:
                        to_upgrade.append((name, reason))

        # 3. Determine skills in vault that should be mounted
        to_mount = []
        for cat in detected_categories.keys():
            for item in manifest:
                if item.get("category") == cat and item["name"] not in active_map:
                    to_mount.append((item["name"], cat))

        # Output Plan
        print(f"Active Skills Action Plan:")
        print(f"  * Retained in Context ({len(to_keep)} skills):")
        for name, reason in to_keep:
            print(f"    [KEEP] {name} - {reason}")

        if to_upgrade:
            print(f"\n  * Upgrading Active Skills with Newer Vault Versions ({len(to_upgrade)} skills):")
            for name, reason in to_upgrade:
                print(f"    [UPGRADE] {name} (Newer version found in Vault)")

        if to_archive:
            print(f"\n  * Evicting to Cold Storage Archive ({len(to_archive)} skills):")
            for name, cat in to_archive:
                print(f"    [ARCHIVE] {name} ({cat})")
        else:
            print("\n  * Evictions: None needed (Context is already minimal).")

        if to_mount:
            print(f"\n  * Mounting from Vault ({len(to_mount)} skills):")
            for name, cat in to_mount:
                print(f"    [MOUNT] {name} ({cat})")

        if dry_run:
            print("\n[Dry Run] Optimization preview complete. No files were moved.")
            return

        # Execute Upgrades
        if to_upgrade:
            print("\nExecuting Auto-Upgrades from Newer Vault Copies...")
            for name, _ in to_upgrade:
                self.restore(name=name, force=True)

        # Execute Evictions (Archive)
        if to_archive:
            print("\nExecuting Auto-Archival...")
            for name, cat in to_archive:
                self.archive(name=name, category=cat, keep_active=False, force=force)

        # Execute Mounts (Restore)
        if to_mount:
            print("\nExecuting Auto-Mounts...")
            for name, cat in to_mount:
                self.restore(name=name, force=force)

        print("\n[OK] Optimization complete! Active context surface is at absolute minimum.")

    # --- Sync & Ingestion Engine ---

    def infer_category(self, skill_name, skill_desc="", skill_md_path=None):
        """Infer an appropriate category for a skill via frontmatter, custom rules, or universal defaults."""
        resolved_md = Path(skill_md_path) if skill_md_path else None
        if resolved_md is None:
            active_dir = self.find_active_skill(skill_name)
            if active_dir:
                resolved_md = active_dir / "SKILL.md"

        if resolved_md is not None:
            explicit_cat = self.parse_skill_frontmatter_field(resolved_md, "category")
            if explicit_cat:
                return explicit_cat

        if skill_name in self.get_core_skills():
            return "General & Utility Skills"

        rules = self.load_config()["category_rules"]
        text = f"{skill_name} {skill_desc}".lower()
        normalized_text = re.sub(r"[-_]+", " ", text)

        for cat, keywords in rules.items():
            for kw in keywords:
                if self._keyword_matches(kw, text, normalized_text):
                    return cat

        return "General & Utility Skills"

    def sync(self, dry_run=False, keep_active=False, force=False, protect_skills=None):
        """Automatically scan plugins and active directories for new or updated skills,
        ingest them into the vault, preserve Core Foundation Skills, and prune non-core active skills."""
        print("==================================================")
        print("           SKILL VAULT AUTO-SYNC & INGEST")
        print(f"  Base Directory: {self.base_dir}")
        print(f"  Vault Store:    {self.archive_dir}")
        print("==================================================\n")

        core_set = self.get_core_skills(protect_skills)
        hook_protected = self.get_hook_protected_skills()
        bin_shims = self._collect_bin_shim_targets()

        active_skills = self.get_active_skills()
        manifest = self.load_manifest()
        manifest_map = {m["name"]: m for m in manifest}

        to_ingest_new = []
        to_ingest_update = []
        to_prune = []
        in_sync = []
        retained_core = []
        protected_hooks = []

        for name, data in sorted(active_skills.items()):
            if name == "skill-vault":
                retained_core.append(name)
                continue

            active_path = Path(data["path"])
            skill_md_path = active_path / "SKILL.md"
            is_core = (name in core_set) or self.is_core_skill_frontmatter(skill_md_path)
            is_hook_dep = name in hook_protected

            if name in manifest_map:
                item = manifest_map[name]
                archived_path = self.resolve_portable_path(item.get("archived_path", ""))
                if not archived_path.exists():
                    archived_path = self.archive_dir / "skills" / name

                recency = compare_skill_recency(active_path, archived_path)
                if recency > 0 or force:
                    to_ingest_update.append(
                        (
                            name,
                            data,
                            item.get("category") or self.infer_category(name, data["description"], skill_md_path),
                        )
                    )
                else:
                    in_sync.append(name)
            else:
                assigned_cat = self.infer_category(name, data["description"], skill_md_path)
                to_ingest_new.append((name, data, assigned_cat))

            if is_core:
                retained_core.append(name)
            elif is_hook_dep:
                protected_hooks.append(name)
            elif not keep_active:
                compat = (
                    self.assess_skill_compat(active_path, original_path=active_path, bin_shim_targets=bin_shims)
                    if not data.get("single_skill_dir")
                    else {"needs_runtime_in_place": False, "path_reasons": []}
                )
                to_prune.append((name, data, compat))

        print("Scan Results:")
        print(f"  * New skills to ingest into vault:     {len(to_ingest_new)}")
        for name, _, cat in to_ingest_new:
            print(f"    [NEW] {name} -> Category: {cat}")

        print(f"  * Updated skills to refresh in vault:  {len(to_ingest_update)}")
        for name, _, cat in to_ingest_update:
            print(f"    [UPDATE] {name} (Newer active version detected)")

        print(f"  * In-sync skills in vault:             {len(in_sync)}")
        print(f"  * Retained Core Foundation Skills:     {len(retained_core)} ({', '.join(sorted(retained_core))})")
        if protected_hooks:
            print(f"  * Hook/MCP-Protected Plugin Skills:    {len(protected_hooks)}")
            for name in sorted(protected_hooks):
                print(f"    [Protected (Hook Dependency)] {name}")
        print(f"  * Non-core active skills to prune:     {len(to_prune)}")
        for name, data, compat in to_prune:
            if compat.get("needs_runtime_in_place"):
                print(f"    [PRUNE (Runtime-in-Place)] {name} (Remove SKILL.md only; keep scripts at {data['path']})")
            else:
                print(f"    [PRUNE] {name} (Will be removed from active context to prevent context bloat)")
        print("")

        if dry_run:
            print("[Dry Run] Preview complete. No files were modified.")
            return 0

        total_ingested = 0
        items_to_write = to_ingest_new + to_ingest_update
        for name, data, cat in items_to_write:
            active_path = Path(data["path"]).resolve()
            if self.archive_dir in active_path.parents or active_path == self.base_dir:
                continue

            if name in manifest_map and manifest_map[name].get("archived_path"):
                dest = self.resolve_portable_path(manifest_map[name]["archived_path"])
            else:
                dest = self.archive_dir / "skills" / name

            dest.parent.mkdir(parents=True, exist_ok=True)
            if dest.exists():
                shutil.rmtree(dest)

            shutil.copytree(active_path, dest)
            print(f"[Vaulted] {name} -> {dest}")

            manifest_map[name] = {
                "name": name,
                "category": cat,
                "original_path": data["relative_path"],
                "archived_path": self.make_portable_path(dest),
            }
            total_ingested += 1

        for name, data, compat in to_prune:
            active_path = Path(data["path"])
            if data.get("single_skill_dir"):
                for sub in active_path.iterdir():
                    if sub.is_dir():
                        if (sub / "SKILL.md").exists():
                            continue
                        shutil.rmtree(sub)
                    else:
                        sub.unlink()
                print(f"[Pruned] Emptied single-skill directory: {active_path}")
            elif compat.get("needs_runtime_in_place"):
                kept_rt = self._prune_skill_runtime_in_place(active_path)
                if kept_rt and name in manifest_map:
                    manifest_map[name]["runtime_dir"] = self.make_portable_path(active_path)
                    manifest_map[name]["relocation_mode"] = "runtime_in_place"
                    reasons_str = ", ".join(compat.get("path_reasons", [])[:3])
                    print(
                        f"[Pruned (Runtime-in-Place)] Removed SKILL.md only; kept companion files at: "
                        f"{active_path} ({reasons_str})"
                    )
                else:
                    print(f"[Pruned] Removed active folder: {active_path}")
            else:
                if active_path.exists():
                    shutil.rmtree(active_path)
                    print(f"[Pruned] Removed active folder: {active_path}")

        if total_ingested > 0 or to_prune:
            self.save_manifest(list(manifest_map.values()))
            self.reindex()
            self.verify()

        print(f"\n[OK] Sync complete: {total_ingested} skill(s) vaulted/refreshed, {len(to_prune)} active skill(s) pruned.")
        print(f"Active context memory is clean with {len(retained_core)} Core Foundation Skill(s).\n")
        return 0

    # --- Actions ---

    def list_skills(self, show_active=True, show_archived=True, category_filter=None, as_json=False, summary_only=False):
        """Present active and archived skills in structured, human-readable or JSON formats."""
        active_map = self.get_active_skills() if show_active else {}
        manifest = self.load_manifest() if show_archived else []

        if category_filter and show_archived:
            manifest = [m for m in manifest if m.get("category", "").lower() == category_filter.lower()]

        archived_by_cat = {}
        for item in manifest:
            cat = item.get("category", "General & Utility Skills")
            archived_path = self.resolve_portable_path(item["archived_path"])
            skill_md = archived_path / "SKILL.md"
            desc = self.parse_skill_description(skill_md)
            archived_by_cat.setdefault(cat, []).append({
                "name": item["name"],
                "path": str(archived_path),
                "relative_path": item["archived_path"],
                "description": desc,
            })

        if as_json:
            result = {}
            if show_active:
                result["active"] = list(active_map.values())
            if show_archived:
                result["archived"] = archived_by_cat
                result["archived_total"] = len(manifest)
            print(json.dumps(result, indent=2))
            return

        print("==================================================")
        print("                 SKILL VAULT OVERVIEW")
        print(f"  Base Directory: {self.base_dir}")
        print("==================================================\n")

        total_active = len(active_map)
        total_archived = len(manifest)
        total_categories = len(archived_by_cat)

        print("Storage Tier Summary:")
        if show_active:
            print(f"  * L1 Active Context Memory:  {total_active} skill(s)")
        if show_archived:
            print(f"  * L2 Cold Storage Archive:   {total_archived} skill(s) across {total_categories} categories")
        print("")

        if summary_only:
            if show_archived and archived_by_cat:
                print("Archived Categories Breakdown:")
                for cat, skills in sorted(archived_by_cat.items()):
                    print(f"  - {cat}: {len(skills)} skill(s)")
                print("")
            return

        if show_active:
            print("--------------------------------------------------")
            print(f"  [L1 ACTIVE SKILLS] ({total_active} in context)")
            print("--------------------------------------------------")
            if not active_map:
                print("  (No active skills found. Use 'restore' to mount skills from archive.)\n")
            else:
                for name, data in sorted(active_map.items()):
                    desc = data["description"]
                    desc_snippet = desc[:110] + "..." if len(desc) > 110 else desc
                    print(f"  * {name}")
                    print(f"    Desc: {desc_snippet}")
                    print(f"    Path: {data['relative_path']}")
                print("")

        if show_archived:
            print("--------------------------------------------------")
            print(f"  [L2 ARCHIVED SKILLS] ({total_archived} in vault)")
            print("--------------------------------------------------")
            if not archived_by_cat:
                print("  (No archived skills found.)\n")
            else:
                for cat, skills in sorted(archived_by_cat.items()):
                    print(f"\n  [{cat}] ({len(skills)} skills):")
                    for s in sorted(skills, key=lambda x: x["name"].lower()):
                        desc = s["description"]
                        desc_snippet = desc[:110] + "..." if len(desc) > 110 else desc
                        print(f"    * {s['name']}: {desc_snippet}")
                print("")

    def archive(self, name=None, pattern=None, category=None, keep_active=False, force=False):
        """Archive active skills with an assigned category, prioritizing newer versions."""
        manifest = self.load_manifest()
        manifest_map = {item["name"]: item for item in manifest}
        hook_protected = self.get_hook_protected_skills()
        bin_shims = self._collect_bin_shim_targets()

        skills_to_archive = []
        if name:
            skills_to_archive.append(name)
        elif pattern:
            regex = re.compile(pattern.replace("*", ".*"))
            for s_dir in self.get_active_skill_dirs():
                for item in s_dir.iterdir():
                    if item.is_dir() and regex.match(item.name):
                        skills_to_archive.append(item.name)

        if not skills_to_archive:
            print("No matching active skills found to archive.")
            return

        category_name = category.strip() if category else None

        for skill_name in sorted(set(skills_to_archive)):
            active_path = self.find_active_skill(skill_name)
            if not active_path:
                print(f"[Skip] Active skill '{skill_name}' not found.")
                continue

            dest_dir = self.archive_dir / "skills" / skill_name
            dest_dir.parent.mkdir(parents=True, exist_ok=True)

            if dest_dir.exists():
                recency = compare_skill_recency(active_path, dest_dir)
                if recency < 0 and not force:
                    print(f"[Skip] L2 archive '{skill_name}' is newer than active L1 version. Preserving newer archive (use --force to overwrite).")
                    if not keep_active:
                        if skill_name in hook_protected:
                            print(f"[Protected (Hook Dependency)] Preserving active '{skill_name}' (referenced by plugin hooks/MCP; use --force to override)")
                        else:
                            compat = self.assess_skill_compat(active_path, original_path=active_path, bin_shim_targets=bin_shims)
                            if compat.get("needs_runtime_in_place"):
                                kept_rt = self._prune_skill_runtime_in_place(active_path)
                                if kept_rt and skill_name in manifest_map:
                                    manifest_map[skill_name]["runtime_dir"] = self.make_portable_path(active_path)
                                    manifest_map[skill_name]["relocation_mode"] = "runtime_in_place"
                                    print(f"[Cleaned (Runtime-in-Place)] Removed SKILL.md only; kept companion files at: {active_path}")
                            else:
                                shutil.rmtree(active_path)
                                print(f"[Cleaned] Removed older active directory: {active_path}")
                    continue
                elif recency > 0:
                    print(f"[Archived] Overwriting older L2 archive with newer active L1 version: {active_path} -> {dest_dir}")
                    shutil.rmtree(dest_dir)
                else:
                    shutil.rmtree(dest_dir)
                    print(f"[Archived] {active_path} -> {dest_dir}")
            else:
                print(f"[Archived] {active_path} -> {dest_dir}")

            shutil.copytree(active_path, dest_dir)

            existing_cat = manifest_map.get(skill_name, {}).get("category")
            inferred_cat = self.infer_category(
                skill_name,
                self.parse_skill_description(active_path / "SKILL.md"),
                active_path / "SKILL.md",
            )
            assigned_cat = category_name or existing_cat or inferred_cat

            manifest_map[skill_name] = {
                "name": skill_name,
                "category": assigned_cat,
                "original_path": self.make_portable_path(active_path),
                "archived_path": self.make_portable_path(dest_dir),
            }

            if not keep_active:
                if skill_name in hook_protected and not force:
                    print(f"[Protected (Hook Dependency)] Preserving active '{skill_name}' (referenced by plugin hooks/MCP; use --force to override)")
                else:
                    compat = self.assess_skill_compat(active_path, original_path=active_path, bin_shim_targets=bin_shims)
                    if compat.get("needs_runtime_in_place") and not force:
                        kept_rt = self._prune_skill_runtime_in_place(active_path)
                        if kept_rt:
                            manifest_map[skill_name]["runtime_dir"] = self.make_portable_path(active_path)
                            manifest_map[skill_name]["relocation_mode"] = "runtime_in_place"
                            print(f"[Cleaned (Runtime-in-Place)] Removed SKILL.md only; kept companion files at: {active_path}")
                    else:
                        shutil.rmtree(active_path)
                        print(f"[Cleaned] Removed active directory: {active_path}")

        self.save_manifest(list(manifest_map.values()))
        self.reindex()
        print("Archiving complete.")

    def recategorize(self, name=None, new_category=None, auto=False, dry_run=False):
        """Update category for an archived skill, or auto-recategorize General & Utility Skills."""
        manifest = self.load_manifest()
        manifest_map = {item["name"]: item for item in manifest}

        if auto:
            updates = []
            scanned_general = 0
            for item in manifest:
                cur_cat = item.get("category") or "General & Utility Skills"
                if cur_cat != "General & Utility Skills":
                    continue
                scanned_general += 1
                archived_path = self.resolve_portable_path(item.get("archived_path", ""))
                skill_md = archived_path / "SKILL.md"
                desc = self.parse_skill_description(skill_md) if skill_md.exists() else ""
                inferred = self.infer_category(item["name"], desc, skill_md if skill_md.exists() else None)
                if inferred and inferred != "General & Utility Skills":
                    updates.append((item["name"], cur_cat, inferred))
                    if not dry_run:
                        item["category"] = inferred

            print("==================================================")
            print("         SKILL VAULT AUTO-RECATEGORIZATION")
            print(f"  General skills scanned: {scanned_general}")
            print(f"  Improved categories:    {len(updates)}")
            print("==================================================\n")
            for sname, old_c, new_c in updates:
                print(f"  * {sname}: '{old_c}' -> '{new_c}'")

            if dry_run:
                print("\n[Dry Run] Auto-recategorization preview complete. No changes saved.")
                return 0

            if updates:
                self.save_manifest(manifest)
                self.reindex()
            print(f"\n[OK] Recategorized {len(updates)} skill(s).")
            return 0

        if not name or not new_category:
            print("[Error] Please specify skill name and new category, or pass --auto.")
            return 1

        if name not in manifest_map:
            print(f"[Error] Skill '{name}' not found in manifest.")
            return 1

        old_cat = manifest_map[name].get("category", "Uncategorized")
        manifest_map[name]["category"] = new_category.strip()
        self.save_manifest(list(manifest_map.values()))
        self.reindex()
        print(f"[Recategorized] '{name}': '{old_cat}' -> '{new_category.strip()}'")
        return 0

    def restore(self, name=None, pattern=None, category=None, restore_all=False, force=False):
        """Restore archived skills back to active locations."""
        manifest = self.load_manifest()
        if not manifest:
            print("Manifest is empty. Nothing to restore.")
            return

        targets = []
        if restore_all:
            targets = manifest
        elif name:
            targets = [m for m in manifest if m["name"] == name]
        elif pattern:
            regex = re.compile(pattern.replace("*", ".*"))
            targets = [m for m in manifest if regex.match(m["name"])]
        elif category:
            targets = [m for m in manifest if m.get("category", "").lower() == category.lower()]

        if not targets:
            print("No matching skills found to restore.")
            return

        disk_skills = self.get_archived_skill_folders()

        for item in targets:
            skill_name = item["name"]
            archived_path = self.resolve_portable_path(item.get("archived_path", ""))
            disk_cand = disk_skills.get(skill_name)
            if disk_cand and disk_cand["has_skill_md"]:
                if not (archived_path / "SKILL.md").exists() or compare_skill_recency(disk_cand["folder"], archived_path) > 0:
                    archived_path = disk_cand["folder"]

            original_path = self.resolve_original_path(item.get("original_path", ""), skill_name=skill_name)

            if not (archived_path / "SKILL.md").exists():
                print(f"[Error] Missing archive source: {archived_path}")
                continue

            if (original_path / "SKILL.md").exists():
                recency = compare_skill_recency(archived_path, original_path)
                if recency > 0 or force:
                    self._copy_skill_safely(archived_path, original_path)
                    print(f"[Restored] Updated L1 with newer L2 version: {skill_name} -> {original_path}")
                    continue
                else:
                    print(f"[Skip] Target L1 skill '{skill_name}' is already newer than or equal to L2 archive (use --force to overwrite)")
                    continue

            self._copy_skill_safely(archived_path, original_path)
            print(f"[Restored] {skill_name} -> {original_path}")

        print("Restoration complete.")

    def _find_external_harness_configs(self):
        """Return existing harness config files that contain skill-vault hook/MCP entries."""
        root_dir = self.get_root_dir().resolve()
        home = Path.home().resolve()
        candidates = [
            root_dir / ".claude" / "settings.json",
            root_dir / ".gemini" / "settings.json",
            root_dir / ".cursor" / "mcp.json",
        ]
        global_roots = {
            home,
            (home / ".gemini" / "config").resolve(),
            (home / ".claude").resolve(),
            (home / ".agents").resolve(),
        }
        if root_dir in global_roots:
            candidates.extend([
                home / ".claude" / "settings.json",
                home / ".gemini" / "settings.json",
                home / ".cursor" / "mcp.json",
            ])

        matched = []
        seen = set()
        for p in candidates:
            res = p.resolve()
            if res in seen or not p.exists():
                continue
            seen.add(res)
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
                if "skill-vault" in text or "hook_runner.py" in text or "mcp_server.py" in text:
                    matched.append(p)
            except OSError:
                pass
        return matched

    @staticmethod
    def _clean_external_harness_config(cfg_path):
        """Surgically remove skill-vault hook/MCP entries from an external harness JSON config."""
        cfg_path = Path(cfg_path)
        if not cfg_path.exists():
            return False
        try:
            data = json.loads(cfg_path.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            return False
        if not isinstance(data, dict):
            return False

        changed = False
        mcp = data.get("mcpServers")
        if isinstance(mcp, dict) and "skill-vault" in mcp:
            del mcp["skill-vault"]
            if not mcp:
                del data["mcpServers"]
            changed = True

        hooks = data.get("hooks")
        if isinstance(hooks, dict):
            for evt in list(hooks.keys()):
                groups = hooks.get(evt)
                if not isinstance(groups, list):
                    continue
                new_groups = []
                for grp in groups:
                    if not isinstance(grp, dict):
                        new_groups.append(grp)
                        continue
                    sub_hooks = grp.get("hooks")
                    if isinstance(sub_hooks, list):
                        kept = [
                            h for h in sub_hooks
                            if not (
                                isinstance(h, dict)
                                and ("hook_runner.py" in str(h.get("command", "")) or "skill-vault" in str(h.get("command", "")))
                            )
                        ]
                        if len(kept) != len(sub_hooks):
                            changed = True
                        if kept:
                            grp_copy = dict(grp)
                            grp_copy["hooks"] = kept
                            new_groups.append(grp_copy)
                    else:
                        new_groups.append(grp)
                if new_groups:
                    hooks[evt] = new_groups
                else:
                    del hooks[evt]
            if not hooks:
                del data["hooks"]

        if changed:
            tmp = cfg_path.with_name(f".{cfg_path.name}.{os.getpid()}.tmp")
            tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            os.replace(tmp, cfg_path)
        return changed

    def uninstall(self, dry_run=False, force=False, keep_archive=False, keep_skill=False):
        """Cleanly restore all archived skills to L1 without overwriting newer L1 versions and remove skill-vault."""
        root_dir = self.get_root_dir()
        sv_dir = self.get_skill_vault_dir()
        manifest = self.load_manifest()
        manifest_map = {item["name"]: item for item in manifest if "name" in item}
        disk_skills = self.get_archived_skill_folders()

        candidates = []
        manifested_arch_paths = set()
        for item in manifest:
            skill_name = item["name"]
            archived_path = self.resolve_portable_path(item.get("archived_path", ""))
            disk_cand = disk_skills.get(skill_name)
            if disk_cand and disk_cand["has_skill_md"]:
                if not (archived_path / "SKILL.md").exists() or compare_skill_recency(disk_cand["folder"], archived_path) > 0:
                    archived_path = disk_cand["folder"]
            if archived_path.exists():
                manifested_arch_paths.add(archived_path.resolve())
            original_path = self.resolve_original_path(item.get("original_path", ""), skill_name=skill_name)
            candidates.append((skill_name, archived_path, original_path, False))

        # Rescue any unmanifested skills physically sitting in the archive
        for folder_name, data in sorted(disk_skills.items()):
            if folder_name in manifest_map or not data["has_skill_md"]:
                continue
            if data["folder"].resolve() in manifested_arch_paths:
                continue
            original_path = self.resolve_original_path(f"skills/{folder_name}", skill_name=folder_name)
            candidates.append((folder_name, data["folder"], original_path, True))

        to_restore = []
        to_upgrade = []
        to_preserve = []
        missing_sources = []

        for skill_name, archived_path, original_path, unmanifested in candidates:
            has_archived = (archived_path / "SKILL.md").exists()
            has_active = (original_path / "SKILL.md").exists()

            if not has_archived:
                if has_active:
                    to_preserve.append((skill_name, archived_path, original_path, "Active L1 present; archive source missing"))
                else:
                    missing_sources.append((skill_name, archived_path, original_path))
                continue

            if has_active:
                recency = compare_skill_recency(archived_path, original_path)
                if recency > 0 or force:
                    reason = "Forced overwrite" if (force and recency <= 0) else "Newer L2 archive version"
                    to_upgrade.append((skill_name, archived_path, original_path, reason))
                else:
                    to_preserve.append((skill_name, archived_path, original_path, "L1 version is newer or equal"))
            else:
                reason = "Unmanifested archive folder rescued" if unmanifested else "Missing from active L1"
                to_restore.append((skill_name, archived_path, original_path, reason))

        print("==================================================")
        print("       SKILL VAULT CLEAN UNINSTALL / DECOMMISSION")
        print(f"  Base Directory: {self.base_dir}")
        print(f"  Root Directory: {root_dir}")
        print(f"  Archive Store:  {self.archive_dir}")
        print(f"  Skill Folder:   {sv_dir if sv_dir else '(None detected)'}")
        print("==================================================\n")

        print(f"Restoration Plan ({len(candidates)} total archived/discovered skill(s)):")
        print(f"  * Restore to active L1:                {len(to_restore)}")
        for name, _, dst, reason in to_restore:
            print(f"    [RESTORE]  {name} -> {dst} ({reason})")

        print(f"  * Upgrade active L1 (newer in L2):     {len(to_upgrade)}")
        for name, _, dst, reason in to_upgrade:
            print(f"    [UPGRADE]  {name} -> {dst} ({reason})")

        print(f"  * Preserve active L1 (newer/equal):    {len(to_preserve)}")
        for name, _, dst, reason in to_preserve:
            print(f"    [PRESERVE] {name} -> {dst} ({reason})")

        if missing_sources:
            print(f"  * Missing archive sources:             {len(missing_sources)}")
            for name, src, _ in missing_sources:
                print(f"    [ERROR]    {name} (missing {src})")

        print("\nCleanup Plan:")
        if keep_archive:
            if sv_dir and not keep_skill and self.archive_dir.exists() and (sv_dir in self.archive_dir.parents):
                print(f"  * Archive:  Relocate {self.archive_dir} -> {root_dir / 'skill_archive'}")
            else:
                print(f"  * Archive:  Keep {self.archive_dir}")
        else:
            print(f"  * Archive:  Remove {self.archive_dir}")

        sv_dirs = []
        for cand in [sv_dir, root_dir / "plugins" / "skill-vault", root_dir / "skills" / "skill-vault"]:
            if cand and cand.exists() and not (cand / ".git").exists():
                resolved_cand = cand.resolve()
                if resolved_cand not in sv_dirs:
                    sv_dirs.append(resolved_cand)

        if keep_skill or not sv_dirs:
            print(f"  * Skill:    Keep {sv_dir if sv_dir else '(None detected)'}")
        else:
            for d in sv_dirs:
                print(f"  * Skill:    Remove {d}")

        harness_targets = [] if keep_skill else self._find_external_harness_configs()
        for hpath in harness_targets:
            print(f"  * Wiring:   Remove skill-vault entries from {hpath}")
        print("")

        if missing_sources:
            print("[Abort] One or more archive sources are missing. Nothing was modified or deleted.")
            return 1

        if dry_run:
            print("[Dry Run] Uninstall preview complete. No files were modified or removed.")
            return 0

        for name, src, dst, _ in to_restore:
            self._copy_skill_safely(src, dst)
            print(f"[Restored] {name} -> {dst}")

        for name, src, dst, _ in to_upgrade:
            self._copy_skill_safely(src, dst)
            print(f"[Upgraded] {name} -> {dst}")

        # Verification gate before deleting archive or skill-vault folder
        dirs_to_delete = []
        if not keep_archive and self.archive_dir.exists():
            dirs_to_delete.append(self.archive_dir.resolve())
        if not keep_skill:
            dirs_to_delete.extend(sv_dirs)

        verification_errors = []
        for skill_name, _, original_path, _ in to_restore + to_upgrade + to_preserve:
            orig_resolved = Path(original_path).resolve()
            skill_md = orig_resolved / "SKILL.md"
            if not skill_md.exists() or skill_md.stat().st_size == 0:
                verification_errors.append(f"Missing or empty SKILL.md for '{skill_name}' at {skill_md}")
                continue
            for del_dir in dirs_to_delete:
                if orig_resolved == del_dir or del_dir in orig_resolved.parents:
                    verification_errors.append(
                        f"Destination '{orig_resolved}' for '{skill_name}' is inside '{del_dir}' which is scheduled for deletion"
                    )

        if verification_errors:
            print("\n[Abort] Verification failed. Preserving archive and skill-vault to prevent data loss:")
            for err in verification_errors:
                print(f"  [X] {err}")
            return 1

        # Relocate or delete archive
        if keep_archive:
            if sv_dir and not keep_skill and self.archive_dir.exists() and (sv_dir in self.archive_dir.parents):
                relocated = (root_dir / "skill_archive").resolve()
                if self.archive_dir.resolve() != relocated:
                    shutil.copytree(self.archive_dir, relocated, dirs_exist_ok=True)
                    cwd_resolved = Path.cwd().resolve()
                    if cwd_resolved == self.archive_dir.resolve() or self.archive_dir.resolve() in cwd_resolved.parents:
                        os.chdir(root_dir)
                    shutil.rmtree(self.archive_dir)
                    print(f"[Relocated] Archive preserved at: {relocated}")
        else:
            if self.archive_dir.exists():
                cwd_resolved = Path.cwd().resolve()
                if cwd_resolved == self.archive_dir.resolve() or self.archive_dir.resolve() in cwd_resolved.parents:
                    os.chdir(root_dir)
                shutil.rmtree(self.archive_dir)
                print(f"[Removed] Archive directory: {self.archive_dir}")

        if not keep_skill:
            for d in sv_dirs:
                if d.exists():
                    cwd_resolved = Path.cwd().resolve()
                    if cwd_resolved == d or d in cwd_resolved.parents:
                        os.chdir(root_dir)
                    shutil.rmtree(d)
                    print(f"[Removed] Skill-vault directory: {d}")
            for hpath in harness_targets:
                if self._clean_external_harness_config(hpath):
                    print(f"[Cleaned] Removed skill-vault entries from: {hpath}")

        total_safe = len(to_restore) + len(to_upgrade) + len(to_preserve)
        print(f"\n[OK] Clean uninstall complete! {total_safe} skill(s) verified safe in active L1 locations.")
        return 0

    def reindex(self):
        """Rebuild INDEX.md grouped by manifest categories with portable relative links."""
        manifest = self.load_manifest()
        manifest_by_folder = {}

        for item in manifest:
            archived_path = self.resolve_portable_path(item.get("archived_path", ""))
            if archived_path.exists() and (archived_path / "SKILL.md").exists():
                folder_name = archived_path.name
                if folder_name not in manifest_by_folder or item.get("name") == folder_name:
                    entry = {
                        "name": folder_name,
                        "category": item.get("category") or "General & Utility Skills",
                        "original_path": item.get("original_path", self.make_portable_path(self.skills_dir / folder_name)),
                        "archived_path": self.make_portable_path(archived_path),
                    }
                    if item.get("runtime_dir"):
                        rt_path = self.resolve_original_path(item["runtime_dir"], skill_name=folder_name)
                        if not rt_path.exists():
                            rt_path = self.resolve_portable_path(item["runtime_dir"])
                        if rt_path.exists() and rt_path.is_dir() and not (rt_path / "SKILL.md").exists():
                            entry["runtime_dir"] = item["runtime_dir"]
                            entry["relocation_mode"] = item.get("relocation_mode") or "runtime_in_place"
                    manifest_by_folder[folder_name] = entry

        disk_skills = self.get_archived_skill_folders()
        for name, data in disk_skills.items():
            if data["has_skill_md"] and name not in manifest_by_folder:
                manifest_by_folder[name] = {
                    "name": name,
                    "category": "General & Utility Skills",
                    "original_path": self.make_portable_path(self.skills_dir / name),
                    "archived_path": self.make_portable_path(data["folder"]),
                }

        categories = {}
        for name, item in manifest_by_folder.items():
            cat = item.get("category") or "General & Utility Skills"
            categories.setdefault(cat, []).append(item)

        total_count = len(manifest_by_folder)
        lines = ["# Skill Archive Index", "", f"Total Archived Skills: {total_count}", ""]

        for cat in sorted(categories.keys()):
            skills_in_cat = sorted(categories[cat], key=lambda x: x["name"].lower())
            lines.append(f"## {cat} ({len(skills_in_cat)} skills)")
            lines.append("")
            for s in skills_in_cat:
                skill_name = s["name"]
                archived_path = self.resolve_portable_path(s["archived_path"])
                skill_md = archived_path / "SKILL.md"
                desc = self.parse_skill_description(skill_md)

                lines.append(f"### `{skill_name}`")
                lines.append(f"- **Description**: {desc}")

                try:
                    rel_link = skill_md.relative_to(self.archive_dir).as_posix()
                    lines.append(f"- **Archived Path**: [`SKILL.md`]({rel_link})")
                except ValueError:
                    file_uri = skill_md.resolve().as_uri().replace("file:////", "file:///")
                    lines.append(f"- **Archived Path**: [`SKILL.md`]({file_uri})")
                lines.append("")

        self.archive_dir.mkdir(parents=True, exist_ok=True)
        with open(self.index_file, "w", encoding="utf-8") as f:
            f.write("\n".join(lines).strip() + "\n")

        self.save_manifest(list(manifest_by_folder.values()))
        skill_router.build_search_index(
            archive_dir=self.archive_dir,
            manifest=list(manifest_by_folder.values()),
            base_dir=self.base_dir,
            resolve_path_fn=self.resolve_portable_path,
        )
        updated_routers = self.sync_router_md()
        for r_path in updated_routers:
            print(f"[Router Synced] Updated SKILL.md frontmatter: {r_path}")
        print(f"[Reindexed] {total_count} skills across {len(categories)} categories (Base: {self.base_dir}).")

    def build_compact_router_description(self):
        """Build a minimal ~45-token frontmatter description when background hooks are active."""
        return (
            "Universal agent-agnostic skill router and tiered storage manager. "
            "Background hooks automatically inject relevant vaulted skills on demand; "
            "use MCP tools list_skills/search_skills/load_skill for mid-turn lookups."
        )

    def build_router_description(self):
        """Build a dynamic SKILL.md router description from the current archive manifest."""
        manifest = self.load_manifest()
        if not manifest:
            return (
                "Universal agent-agnostic skill router, lifecycle manager, and tiered storage engine for AI coding agents.\n"
                "  ALWAYS use this skill whenever a task involves specialized domain skills, frameworks, or tools not currently loaded in active context memory (L1), or when managing skill context bloat.\n"
                "  Search cold storage (L2) on demand via 'python scripts/skill_vault.py search \"<keyword>\"', view 'skill_archive/INDEX.md', or dynamically mount skills via 'restore', 'import', or 'optimize'."
            )

        grouped = {}
        for item in manifest:
            cat = item.get("category") or "General & Utility Skills"
            grouped.setdefault(cat, []).append(item["name"])

        sorted_cats = sorted(
            grouped.keys(),
            key=lambda c: (c == "General & Utility Skills", c.lower()),
        )
        cat_entries = []
        for idx, cat in enumerate(sorted_cats, start=1):
            samples = ", ".join(sorted(grouped[cat], key=str.lower)[:4])
            cat_entries.append(f"({idx}) {cat} ({samples})")
        formatted_categories = ",\n  ".join(cat_entries)

        return (
            f"Universal agent-agnostic skill router and tiered storage manager for {len(manifest)} specialized domain skill(s) in cold storage.\n"
            f"  ALWAYS use this skill whenever the task involves domains or tools not in active memory, including:\n"
            f"  {formatted_categories}.\n"
            f"  Search or restore skills on demand via 'python scripts/skill_vault.py search \"<keyword>\"', view 'skill_archive/INDEX.md', or run 'restore <name>'."
        )

    def _get_router_skill_md_candidates(self):
        """Locate candidate SKILL.md files belonging to skill-vault within base_dir."""
        root_dir = self.get_root_dir()
        raw_candidates = [
            self.skills_dir / "skill-vault" / "SKILL.md",
            self.base_dir / ".agents" / "skills" / "skill-vault" / "SKILL.md",
            self.base_dir / ".claude" / "skills" / "skill-vault" / "SKILL.md",
            self.base_dir / "plugins" / "skill-vault" / "skills" / "skill-vault" / "SKILL.md",
            root_dir / "plugins" / "skill-vault" / "skills" / "skill-vault" / "SKILL.md",
        ]
        if self.archive_dir.exists():
            raw_candidates.append(self.base_dir / "SKILL.md")

        seen = set()
        candidates = []
        for cand in raw_candidates:
            resolved = cand.resolve()
            if resolved not in seen:
                seen.add(resolved)
                candidates.append(cand)
        return candidates

    def sync_router_md(self, target_skill_md=None, force=False):
        """Synchronize skill-vault's SKILL.md frontmatter description with the active vault categories."""
        candidates = [Path(target_skill_md)] if target_skill_md else self._get_router_skill_md_candidates()
        routing_cfg = self.load_config().get("routing", {})
        if routing_cfg.get("compact_router_prompt"):
            new_desc = self.build_compact_router_description()
        else:
            new_desc = self.build_router_description()
        new_desc_block = f"description: >-\n  {new_desc}"
        desc_pattern = re.compile(
            r"^description:\s*(?:>[-+]?|\|[-+]?)?\s*\n?.*?(?=\n[a-zA-Z0-9_-]+:|\Z)",
            re.DOTALL | re.MULTILINE,
        )

        updated = []
        for cand in candidates:
            if not cand.exists() or self.parse_skill_name(cand) != "skill-vault":
                continue

            current_desc = self.parse_skill_description(cand)
            if not force and "Universal agent-agnostic skill router" not in current_desc:
                continue

            content = cand.read_text(encoding="utf-8", errors="replace")
            fm_match = re.match(r"^(---\s*\n)(.*?)(\n---(?:\s*\n|\s*\Z))", content, re.DOTALL)
            if not fm_match:
                continue

            fm_text = fm_match.group(2)
            if desc_pattern.search(fm_text):
                new_fm = desc_pattern.sub(lambda _: new_desc_block, fm_text, count=1)
            else:
                new_fm = fm_text.rstrip() + "\n" + new_desc_block

            new_content = fm_match.group(1) + new_fm + fm_match.group(3) + content[fm_match.end():]
            if new_content != content:
                cand.write_text(new_content, encoding="utf-8")
                updated.append(cand)

        return updated

    @staticmethod
    def _parse_routing_value(key, raw_val):
        default = skill_router.DEFAULT_ROUTING_CONFIG.get(key)
        val = str(raw_val).strip()
        if isinstance(default, bool):
            return val.lower() in {"1", "true", "yes", "on"}
        if isinstance(default, int):
            return int(val)
        if isinstance(default, float):
            return float(val)
        if isinstance(default, list):
            return [v.strip() for v in val.split(",") if v.strip()]
        return val

    def manage_config(
        self,
        show=False,
        init_config=False,
        add_core=None,
        remove_core=None,
        add_fingerprint=None,
        add_category_rule=None,
        set_routing=None,
        sync_prompt=False,
    ):
        """Inspect or update vault_config.json and dynamically synchronize the router prompt."""
        def _normalize_pairs(pairs):
            if not pairs:
                return []
            if len(pairs) == 2 and isinstance(pairs[0], str) and isinstance(pairs[1], str):
                return [pairs]
            return pairs

        fp_pairs = _normalize_pairs(add_fingerprint)
        rule_pairs = _normalize_pairs(add_category_rule)
        routing_pairs = _normalize_pairs(set_routing)
        mutating = bool(init_config or add_core or remove_core or fp_pairs or rule_pairs or routing_pairs)

        if init_config:
            effective = self.load_config()
            self.save_config(effective)
            print(f"[Config Initialized] Wrote vault configuration to: {self.config_file}")

        if add_core or remove_core or fp_pairs or rule_pairs or routing_pairs:
            raw_cfg = self._load_raw_config()

            if add_core:
                core_list = list(raw_cfg.get("core_skills", []))
                disabled_list = list(raw_cfg.get("disabled_core_skills", []))
                for skill in add_core:
                    s = skill.strip()
                    if not s:
                        continue
                    if s in disabled_list:
                        disabled_list.remove(s)
                    if s not in core_list and s not in DEFAULT_CORE_SKILLS:
                        core_list.append(s)
                    elif s not in core_list and self.config_file.exists():
                        core_list.append(s)
                raw_cfg["core_skills"] = core_list
                if disabled_list or "disabled_core_skills" in raw_cfg:
                    raw_cfg["disabled_core_skills"] = disabled_list
                print(f"[Config Updated] Added core skill(s): {', '.join(add_core)}")

            if remove_core:
                core_list = list(raw_cfg.get("core_skills", []))
                disabled_list = list(raw_cfg.get("disabled_core_skills", []))
                for skill in remove_core:
                    s = skill.strip()
                    if not s:
                        continue
                    if s in core_list:
                        core_list.remove(s)
                    if s in DEFAULT_CORE_SKILLS and s not in disabled_list:
                        disabled_list.append(s)
                raw_cfg["core_skills"] = core_list
                raw_cfg["disabled_core_skills"] = disabled_list
                print(f"[Config Updated] Removed core skill(s): {', '.join(remove_core)}")

            if fp_pairs:
                fp_map = dict(raw_cfg.get("workspace_fingerprints", {}))
                for cat, pat in fp_pairs:
                    c = cat.strip()
                    p = pat.strip()
                    if not c or not p:
                        continue
                    pats = list(fp_map.get(c, []))
                    if p not in pats:
                        pats.append(p)
                    fp_map[c] = pats
                    print(f"[Config Updated] Added workspace fingerprint: [{c}] -> '{p}'")
                raw_cfg["workspace_fingerprints"] = fp_map

            if rule_pairs:
                rule_map = dict(raw_cfg.get("category_rules", {}))
                for cat, kw in rule_pairs:
                    c = cat.strip()
                    k = kw.strip()
                    if not c or not k:
                        continue
                    kws = list(rule_map.get(c, []))
                    if k not in kws:
                        kws.append(k)
                    # Place updated custom category first so overrides take precedence
                    rule_map = {c: kws, **{existing_c: existing_kws for existing_c, existing_kws in rule_map.items() if existing_c != c}}
                    print(f"[Config Updated] Added category rule: [{c}] <- '{k}'")
                raw_cfg["category_rules"] = rule_map

            if routing_pairs:
                routing_map = dict(raw_cfg.get("routing", {}))
                for r_key, r_val in routing_pairs:
                    k = r_key.strip()
                    if k not in skill_router.DEFAULT_ROUTING_CONFIG:
                        print(f"[Warning] Unknown routing key '{k}'. Valid keys: {', '.join(sorted(skill_router.DEFAULT_ROUTING_CONFIG))}")
                        continue
                    parsed = self._parse_routing_value(k, r_val)
                    routing_map[k] = parsed
                    print(f"[Config Updated] Routing '{k}' = {parsed!r}")
                raw_cfg["routing"] = routing_map

            self.save_config(raw_cfg)

        if sync_prompt:
            updated = self.sync_router_md(force=True)
            if updated:
                for p in updated:
                    print(f"[Router Synced] Updated SKILL.md frontmatter: {p}")
            else:
                print("[Router Sync] No matching skill-vault SKILL.md found to update.")

        if show or (not mutating and not sync_prompt):
            effective = self.load_config()
            config_status = "Custom (vault_config.json present)" if self.config_file.exists() else "Built-in Universal Defaults (no vault_config.json)"
            router_cands = [str(p) for p in self._get_router_skill_md_candidates() if p.exists()]
            print("==================================================")
            print("            SKILL VAULT CONFIGURATION")
            print(f"  Base Directory: {self.base_dir}")
            print(f"  Config File:    {self.config_file}")
            print(f"  Mode:           {config_status}")
            print("==================================================\n")
            print(f"Protected Core Skills ({len(effective['core_skills'])}):")
            print(f"  {', '.join(effective['core_skills'])}\n")
            print("Background JIT Routing Settings:")
            for rk, rv in sorted(effective["routing"].items()):
                print(f"  * {rk}: {rv!r}")
            print(f"\nWorkspace Fingerprint Categories ({len(effective['workspace_fingerprints'])}):")
            for cat, pats in effective["workspace_fingerprints"].items():
                print(f"  * {cat}: {len(pats)} pattern(s)")
            print(f"\nCategory Inference Rules ({len(effective['category_rules'])}):")
            for cat, kws in effective["category_rules"].items():
                print(f"  * {cat}: {len(kws)} keyword(s)")
            print(f"\nRouter SKILL.md Candidates Found: {len(router_cands)}")
            for rc in router_cands:
                print(f"  * {rc}")
            print("")

    def verify(self, fix=False, compat=False, as_json=False):
        """Perform a bi-directional integrity check and optional L2 compatibility audit."""
        if not as_json:
            print("==================================================")
            print("       SKILL VAULT INTEGRITY AUDIT")
            print(f"  Base Directory: {self.base_dir}")
            print(f"  Archive Store:  {self.archive_dir}")
            print("==================================================\n")

        def _audit_integrity():
            disk_skills_local = self.get_archived_skill_folders()
            manifest_local = self.load_manifest()
            manifest_map_local = {m["name"]: m for m in manifest_local}
            indexed_local = self.parse_index_file()

            issues_local = []
            warnings_local = []

            for name, d in disk_skills_local.items():
                if not d["has_skill_md"]:
                    issues_local.append(f"[Disk Error] Folder '{name}' in archive is missing SKILL.md")
                elif d["size"] == 0:
                    issues_local.append(f"[Disk Error] SKILL.md in '{name}' is 0 bytes (empty file)")

            disk_names = set(disk_skills_local.keys())
            manifest_names = set(manifest_map_local.keys())

            for name in sorted(disk_names - manifest_names):
                issues_local.append(f"[Uncataloged on Disk] '{name}' exists in archive folder but NOT in backup_manifest.json")
            for name in sorted(manifest_names - disk_names):
                issues_local.append(f"[Phantom Manifest Entry] '{name}' listed in backup_manifest.json but NOT found on disk")

            for item in manifest_local:
                name = item["name"]
                archived_path = self.resolve_portable_path(item.get("archived_path", ""))
                if not archived_path.exists():
                    issues_local.append(f"[Broken Manifest Path] '{name}' archived_path does not exist: {archived_path}")
                elif not (archived_path / "SKILL.md").exists():
                    issues_local.append(f"[Missing SKILL.md] '{name}' archived_path has no SKILL.md: {archived_path}")
                if not item.get("category"):
                    warnings_local.append(f"[Missing Category] '{name}' in manifest has no category assigned")

            index_names = set(indexed_local.keys())
            for name in sorted(disk_names - index_names):
                issues_local.append(f"[Unindexed on Disk] '{name}' exists on disk but is NOT listed in INDEX.md")
            for name in sorted(index_names - disk_names):
                issues_local.append(f"[Phantom Index Entry] '{name}' listed in INDEX.md but does NOT exist on disk")
            for name in sorted(manifest_names - index_names):
                issues_local.append(f"[Manifest/Index Mismatch] '{name}' is in backup_manifest.json but NOT in INDEX.md")

            for name, data in indexed_local.items():
                link_path_str = data.get("link_path")
                if link_path_str and not link_path_str.startswith("file:///"):
                    target_file = (self.archive_dir / link_path_str).resolve()
                    if not target_file.exists():
                        issues_local.append(f"[Broken Index Link] '{name}' link target missing: {target_file}")

            return disk_skills_local, manifest_local, indexed_local, issues_local, warnings_local

        disk_skills, manifest, indexed_skills, issues, warnings = _audit_integrity()

        if not as_json:
            print("Component Counts:")
            print(f"  * Physical Folders on Disk:        {len(disk_skills)}")
            print(f"  * Entries in backup_manifest.json: {len(manifest)}")
            print(f"  * Entries in INDEX.md:             {len(indexed_skills)}\n")

            if not issues and not warnings and not compat:
                print("[OK] 100% Integrity Verified! Disk, manifest, and index are in perfect sync.\n")
                return 0

            if warnings:
                print(f"Warnings ({len(warnings)}):")
                for w in warnings:
                    print(f"  [!] {w}")
                print("")

            if issues:
                print(f"Discrepancies / Errors ({len(issues)}):")
                for iss in issues:
                    print(f"  [X] {iss}")
                print("")

        integrity_repaired = False
        if issues and fix:
            if not as_json:
                print("[Self-Healing] Applying automatic repairs (--fix enabled)...")
            self.reindex()
            integrity_repaired = True
            if not as_json:
                print("[Self-Healing] Reindexed and resynchronized successfully.\n")
            if not compat and not as_json:
                return 0
            disk_skills, manifest, indexed_skills, issues, warnings = _audit_integrity()

        if not compat:
            if as_json:
                print(
                    json.dumps(
                        {
                            "counts": {
                                "disk": len(disk_skills),
                                "manifest": len(manifest),
                                "index": len(indexed_skills),
                            },
                            "issues": issues,
                            "warnings": warnings,
                            "integrity_repaired": integrity_repaired,
                            "ok": not issues,
                        },
                        indent=2,
                    )
                )
                return 0 if not issues else 1
            if issues:
                print("Tip: Run with '--fix' (e.g. 'python skill_vault.py verify --fix') to automatically repair discrepancies.\n")
                return 1
            return 0

        # Compatibility audit across vaulted skills
        bin_shims = self._collect_bin_shim_targets()
        active_skills = self.get_active_skills()
        base_res = self.base_dir.resolve()
        root_res = self.get_root_dir().resolve()

        def _can_safely_materialize(orig_path):
            orig_res = Path(orig_path).resolve()
            anchor = None
            rel_parts = ()
            for cand_anchor in (base_res, root_res):
                try:
                    rel = orig_res.relative_to(cand_anchor)
                    anchor = cand_anchor
                    rel_parts = rel.parts
                    break
                except ValueError:
                    continue
            if anchor is None or (orig_res / "SKILL.md").exists():
                return False
            if len(rel_parts) >= 2 and rel_parts[0].lower() == "plugins":
                plugin_dir = anchor / rel_parts[0] / rel_parts[1]
                if not plugin_dir.exists() or not plugin_dir.is_dir():
                    return False
            return True

        path_dependent_broken = []
        runtime_in_place_active = []
        cross_skill_refs = []
        oversized = []
        vaulted_guardrails = []

        for item in manifest:
            name = item["name"]
            archived_path = self.resolve_portable_path(item.get("archived_path", ""))
            if not (archived_path / "SKILL.md").exists():
                continue
            orig_path = self.resolve_original_path(item.get("original_path", ""), skill_name=name)
            is_active_l1 = (orig_path / "SKILL.md").exists() or (name in active_skills)

            info = self.assess_skill_compat(archived_path, original_path=orig_path, bin_shim_targets=bin_shims)

            rt_ok = False
            rt_path = None
            if item.get("runtime_dir"):
                rt_path = self.resolve_original_path(item["runtime_dir"], skill_name=name)
                if not rt_path.exists():
                    rt_path = self.resolve_portable_path(item["runtime_dir"])
                try:
                    rt_ok = (
                        rt_path.exists()
                        and rt_path.is_dir()
                        and not (rt_path / "SKILL.md").exists()
                        and any(rt_path.iterdir())
                    )
                except OSError:
                    rt_ok = False

            if info["needs_runtime_in_place"] and not is_active_l1:
                if rt_ok:
                    runtime_in_place_active.append({
                        "name": name,
                        "runtime_dir": str(rt_path),
                        "reasons": info["path_reasons"],
                    })
                else:
                    path_dependent_broken.append({
                        "name": name,
                        "item": item,
                        "archived_path": archived_path,
                        "orig_path": orig_path,
                        "reasons": info["path_reasons"],
                    })

            if info["cross_skill_refs"]:
                cross_skill_refs.append({"name": name, "refs": info["cross_skill_refs"]})
            if info["oversized_skill_md"]:
                oversized.append({"name": name, "bytes": info["skill_md_bytes"]})
            if info["guardrail_signals"] and not is_active_l1:
                vaulted_guardrails.append({"name": name, "signals": info["guardrail_signals"]})

        repaired_compat = []
        remaining_broken = []
        if fix and path_dependent_broken:
            for entry in path_dependent_broken:
                orig_path = entry["orig_path"]
                if _can_safely_materialize(orig_path):
                    self._materialize_runtime_companions(entry["archived_path"], orig_path)
                    entry["item"]["runtime_dir"] = self.make_portable_path(orig_path)
                    entry["item"]["relocation_mode"] = "runtime_in_place"
                    repaired_compat.append({"name": entry["name"], "runtime_dir": str(orig_path)})
                    runtime_in_place_active.append({
                        "name": entry["name"],
                        "runtime_dir": str(orig_path),
                        "reasons": entry["reasons"],
                    })
                else:
                    remaining_broken.append(entry)
            if repaired_compat:
                self.save_manifest(manifest)
                if not as_json:
                    self.reindex()
                else:
                    old_stdout = sys.stdout
                    sys.stdout = io.StringIO()
                    try:
                        self.reindex()
                    finally:
                        sys.stdout = old_stdout
        else:
            remaining_broken = path_dependent_broken

        remaining_broken_pub = [
            {"name": e["name"], "original_path": str(e["orig_path"]), "reasons": e["reasons"]}
            for e in remaining_broken
        ]

        if as_json:
            print(
                json.dumps(
                    {
                        "counts": {
                            "disk": len(disk_skills),
                            "manifest": len(manifest),
                            "index": len(indexed_skills),
                        },
                        "issues": issues,
                        "warnings": warnings,
                        "integrity_repaired": integrity_repaired,
                        "compat": {
                            "path_dependent_broken": remaining_broken_pub,
                            "runtime_in_place_active": runtime_in_place_active,
                            "repaired": repaired_compat,
                            "cross_skill_refs": cross_skill_refs,
                            "oversized": oversized,
                            "vaulted_guardrails": vaulted_guardrails,
                        },
                        "ok": (not issues) and (not remaining_broken_pub),
                    },
                    indent=2,
                )
            )
            return 0 if (not issues and not remaining_broken_pub) else 1

        print("==================================================")
        print("       L2 COMPATIBILITY AUDIT SUMMARY")
        print("==================================================")
        print(f"  * Path-Dependent Skills Missing Runtime-in-Place: {len(remaining_broken_pub)}")
        for e in remaining_broken_pub:
            print(f"    [X] {e['name']} -> {e['original_path']} ({', '.join(e['reasons'][:3])})")

        if repaired_compat:
            print(f"  * Materialized Runtime-in-Place (--fix):          {len(repaired_compat)}")
            for r in repaired_compat:
                print(f"    [FIXED] {r['name']} -> {r['runtime_dir']} (companions restored without SKILL.md)")

        print(f"  * Runtime-in-Place Protected Skills:              {len(runtime_in_place_active)}")
        for r in runtime_in_place_active[:10]:
            print(f"    [OK] {r['name']} -> {r['runtime_dir']}")
        if len(runtime_in_place_active) > 10:
            print(f"    ... (+{len(runtime_in_place_active) - 10} more)")

        print(f"  * Cross-Skill / Plugin References:                {len(cross_skill_refs)}")
        for c in cross_skill_refs[:10]:
            print(f"    [!] {c['name']}: {', '.join(c['refs'][:4])}")
        if len(cross_skill_refs) > 10:
            print(f"    ... (+{len(cross_skill_refs) - 10} more)")

        print(f"  * Oversized SKILL.md (truncated on inline):       {len(oversized)}")
        for o in sorted(oversized, key=lambda x: -x["bytes"])[:10]:
            print(f"    [!] {o['name']}: {o['bytes']} bytes")
        if len(oversized) > 10:
            print(f"    ... (+{len(oversized) - 10} more)")

        print(f"  * Vaulted Always-On / Guardrail Skills:           {len(vaulted_guardrails)}")
        for g in vaulted_guardrails[:10]:
            print(f"    [!] {g['name']}: {', '.join(g['signals'])}")
        if len(vaulted_guardrails) > 10:
            print(f"    ... (+{len(vaulted_guardrails) - 10} more)")
        print("")

        if remaining_broken_pub and not fix:
            print("Tip: Run with '--compat --fix' to materialize runtime-in-place companion files without L1 SKILL.md bloat.\n")

        if issues or remaining_broken_pub:
            return 1
        print("[OK] L2 Compatibility Audit passed with no unresolved path-dependent skills.\n")
        return 0

    def search(self, query, category=None, limit=10, as_json=False):
        """Search archived skills using pre-built BM25 index with substring fallback."""
        index_data = skill_router.load_or_build_index(
            archive_dir=self.archive_dir,
            base_dir=self.base_dir,
            resolve_path_fn=self.resolve_portable_path,
        )
        results = skill_router.search_index(
            index_data=index_data,
            query=query,
            category=category,
            limit=limit,
        )

        # Fallback substring search when query is a partial fragment not captured by tokenization
        if not results and query.strip():
            q = query.strip().lower()
            for item in self.load_manifest():
                name = item["name"]
                cat = item.get("category", "General & Utility Skills")
                if category and cat.lower() != category.strip().lower():
                    continue
                archived_path = self.resolve_portable_path(item["archived_path"])
                desc = self.parse_skill_description(archived_path / "SKILL.md")
                if q in name.lower() or q in desc.lower() or q in cat.lower():
                    results.append({
                        "name": name,
                        "category": cat,
                        "score": 1.0,
                        "description": desc,
                        "resolved_path": str(archived_path),
                    })
            results = results[:limit]

        if as_json:
            print(json.dumps(results, indent=2, ensure_ascii=False))
            return

        if not results:
            print(f"No archived skills matched '{query}'.")
            return

        print(f"Found {len(results)} matching skill(s):\n")
        for r in results:
            path_str = r.get("resolved_path") or str(self.resolve_portable_path(r.get("archived_path", "")))
            desc = r.get("description", "")
            print(f"* {r['name']} [{r['category']}] (score: {r['score']})")
            desc_snippet = desc[:130] + "..." if len(desc) > 130 else desc
            print(f"  Description: {desc_snippet}")
            print(f"  Path: {path_str}\n")

    # --- JIT Router Debugging, Deduplication, Telemetry & Setup ---

    def route(self, prompt, workspace_path=None, mode=None, as_json=False):
        """Dry-run the JIT skill router against a prompt and inspect scores, tiers, and tokens."""
        index_data = skill_router.load_or_build_index(
            archive_dir=self.archive_dir,
            base_dir=self.base_dir,
            resolve_path_fn=self.resolve_portable_path,
        )
        cfg = dict(self.load_config().get("routing", {}))
        if mode:
            cfg["mode"] = mode

        ws_cats = []
        ws_target = Path(workspace_path).resolve() if workspace_path else Path.cwd().resolve()
        if ws_target.exists():
            ws_cats = sorted(self.detect_workspace_categories(ws_target).keys())

        result = skill_router.route_prompt(
            index_data=index_data,
            prompt=prompt,
            archive_dir=self.archive_dir,
            base_dir=self.base_dir,
            workspace_categories=ws_cats,
            routing_config=cfg,
        )

        if as_json:
            payload = {
                "prompt": prompt,
                "mode": cfg.get("mode", "hybrid"),
                "workspace_categories": ws_cats,
                "ambiguous": result["ambiguous"],
                "estimated_tokens": result["estimated_tokens"],
                "inline": [
                    {
                        "name": i["name"],
                        "category": i["category"],
                        "score": i["score"],
                        "matched_terms": i.get("matched_terms", []),
                        "truncated": i.get("truncated", False),
                    }
                    for i in result["inline"]
                ],
                "pointers": [
                    {
                        "name": p["name"],
                        "category": p["category"],
                        "score": p["score"],
                        "matched_terms": p.get("matched_terms", []),
                    }
                    for p in result["pointers"]
                ],
                "top_candidates": [
                    {
                        "name": c["name"],
                        "category": c["category"],
                        "score": c["score"],
                        "matched_terms": c.get("matched_terms", []),
                    }
                    for c in result.get("candidates", [])[:8]
                ],
            }
            print(json.dumps(payload, indent=2, ensure_ascii=False))
            return 0

        print("==================================================")
        print("            SKILL VAULT ROUTE DIAGNOSTIC")
        print(f"  Prompt:    {prompt}")
        print(f"  Mode:      {cfg.get('mode', 'hybrid')}")
        print(f"  Workspace: {', '.join(ws_cats) if ws_cats else '(none detected)'}")
        print(f"  Ambiguous: {result['ambiguous']}")
        print(f"  Est Tokens:{result['estimated_tokens']}")
        print("==================================================\n")

        if result["inline"]:
            print(f"INLINE ({len(result['inline'])}):")
            for i in result["inline"]:
                terms = ", ".join(i.get("matched_terms", []))
                trunc = " [TRUNCATED]" if i.get("truncated") else ""
                print(f"  * {i['name']} [{i['category']}] score={i['score']} terms=[{terms}]{trunc}")
        else:
            print("INLINE: (none)")

        if result["pointers"]:
            print(f"\nPOINTERS ({len(result['pointers'])}):")
            for p in result["pointers"]:
                terms = ", ".join(p.get("matched_terms", []))
                print(f"  * {p['name']} [{p['category']}] score={p['score']} terms=[{terms}]")
        else:
            print("\nPOINTERS: (none)")

        top_cands = result.get("candidates", [])[:8]
        if top_cands:
            print(f"\nTop Ranked Candidates:")
            for c in top_cands:
                terms = ", ".join(c.get("matched_terms", []))
                print(f"  - {c['name']} [{c['category']}] score={c['score']} terms=[{terms}]")
        print("")
        return 0

    @staticmethod
    def _inspect_dedupe_entry(idx, item, dir_path):
        """Extract canonical name, frontmatter alias, content hash, and recency metadata for dedupe."""
        canon_name = skill_router.canonicalize_skill_name(item.get("name", ""))
        fm_canon_name = None
        content_hash = None
        size_bytes = 0
        skill_md = dir_path / "SKILL.md"
        if skill_md.exists():
            try:
                raw_bytes = skill_md.read_bytes()
                size_bytes = len(raw_bytes)
                if size_bytes >= 64:
                    content_hash = hashlib.sha256(raw_bytes).hexdigest()
                content = raw_bytes.decode("utf-8", errors="ignore")
                fm_match = re.match(r"^---\s*\n(.*?)\n---(?:\s*\n|\s*\Z)", content, re.DOTALL)
                if fm_match:
                    n_match = re.search(r"^name:\s*([^\n]+)", fm_match.group(1), re.MULTILINE | re.IGNORECASE)
                    if n_match:
                        fm_raw = n_match.group(1).strip().strip("'\"")
                        if fm_raw:
                            fm_canon_name = skill_router.canonicalize_skill_name(fm_raw) or None
            except OSError:
                pass
        ver_tuple, mtime = get_skill_metadata(dir_path)
        return {
            "idx": idx,
            "item": item,
            "dir_path": dir_path,
            "canon_name": canon_name,
            "fm_canon_name": fm_canon_name,
            "content_hash": content_hash,
            "size_bytes": size_bytes,
            "ver_tuple": ver_tuple,
            "mtime": mtime,
        }

    @staticmethod
    def _dedupe_candidate_beats(cand_info, win_info):
        """Return True if cand_info is newer or preferred over win_info."""
        rec = compare_skill_recency(cand_info["dir_path"], win_info["dir_path"])
        if rec != 0:
            return rec > 0
        cand_name = cand_info["item"]["name"]
        win_name = win_info["item"]["name"]
        cand_hyphen = "-" in cand_name and "_" not in cand_name
        win_hyphen = "-" in win_name and "_" not in win_name
        if cand_hyphen != win_hyphen:
            return cand_hyphen
        if cand_info["size_bytes"] != win_info["size_bytes"]:
            return cand_info["size_bytes"] > win_info["size_bytes"]
        return cand_name.lower() < win_name.lower()

    @staticmethod
    def _format_dedupe_meta(info):
        ver_str = ".".join(map(str, info["ver_tuple"])) if info["ver_tuple"] is not None else "none"
        mtime_str = (
            datetime.fromtimestamp(info["mtime"]).strftime("%Y-%m-%d %H:%M")
            if info["mtime"] > 0
            else "unknown"
        )
        return f"[ver={ver_str}, mtime={mtime_str}]"

    def dedupe(self, dry_run=False):
        """Consolidate duplicate skills in L2 (canonical name, frontmatter name, or identical content), keeping the newest version."""
        manifest = self.load_manifest()
        infos = [
            self._inspect_dedupe_entry(i, item, self.resolve_portable_path(item.get("archived_path", "")))
            for i, item in enumerate(manifest)
        ]

        # Union-Find over manifest entries sharing canonical name, frontmatter name, or SKILL.md SHA-256
        parent = list(range(len(infos)))

        def _find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def _union(a, b):
            ra, rb = _find(a), _find(b)
            if ra != rb:
                parent[rb] = ra

        buckets = {}
        for info in infos:
            idx = info["idx"]
            keys = []
            if info["canon_name"]:
                keys.append(("name", info["canon_name"]))
            if info["fm_canon_name"]:
                keys.append(("name", info["fm_canon_name"]))
            if info["content_hash"]:
                keys.append(("sha256", info["content_hash"]))
            for key in keys:
                buckets.setdefault(key, []).append(idx)

        for key_indices in buckets.values():
            if len(key_indices) > 1:
                head = key_indices[0]
                for other in key_indices[1:]:
                    _union(head, other)

        components = {}
        for info in infos:
            components.setdefault(_find(info["idx"]), []).append(info)

        dup_components = [grp for grp in components.values() if len(grp) > 1]
        print("==================================================")
        print("           SKILL VAULT DUPLICATE CHECK")
        print(f"  Total Manifest Entries: {len(manifest)}")
        print(f"  Duplicate Groups Found: {len(dup_components)}")
        print("==================================================\n")

        if not dup_components:
            print("[OK] No duplicate skills found in vault.")
            return 0

        to_remove = []
        kept_entries = []
        prepared_groups = []
        for grp in components.values():
            if len(grp) == 1:
                kept_entries.append(grp[0]["item"])
                continue

            win_info = grp[0]
            for cand_info in grp[1:]:
                if self._dedupe_candidate_beats(cand_info, win_info):
                    win_info = cand_info
            kept_entries.append(win_info["item"])

            reasons = set()
            for i in range(len(grp)):
                for j in range(i + 1, len(grp)):
                    a, b = grp[i], grp[j]
                    if a["canon_name"] and a["canon_name"] == b["canon_name"]:
                        reasons.add("canonical-name")
                    else:
                        a_names = {n for n in (a["canon_name"], a["fm_canon_name"]) if n}
                        b_names = {n for n in (b["canon_name"], b["fm_canon_name"]) if n}
                        if a_names & b_names:
                            reasons.add("frontmatter-name")
                    if a["content_hash"] and a["content_hash"] == b["content_hash"]:
                        reasons.add("identical-content")

            group_label = win_info["canon_name"] or win_info["item"]["name"]
            losers = [c for c in grp if c["idx"] != win_info["idx"]]
            losers.sort(key=lambda c: c["item"]["name"].lower())
            prepared_groups.append((group_label, sorted(reasons), win_info, losers))

        prepared_groups.sort(key=lambda g: g[0].lower())
        for group_label, reasons, win_info, losers in prepared_groups:
            reasons_str = ", ".join(reasons) if reasons else "canonical-name"
            print(f"Group '{group_label}' (matched by: {reasons_str}):")
            win_item = win_info["item"]
            print(
                f"  [KEEP]   {win_item['name']} ({win_item.get('category', 'General & Utility Skills')}) "
                f"{self._format_dedupe_meta(win_info)} -> {win_info['dir_path']}"
            )
            for cand_info in losers:
                cand_item = cand_info["item"]
                print(
                    f"  [REMOVE] {cand_item['name']} ({cand_item.get('category', 'General & Utility Skills')}) "
                    f"{self._format_dedupe_meta(cand_info)} -> {cand_info['dir_path']}"
                )
                to_remove.append((cand_item, cand_info["dir_path"], win_info["dir_path"]))

        if dry_run:
            print(f"\n[Dry Run] Would consolidate {len(to_remove)} duplicate skill(s). No files were modified.")
            return 0

        for cand, cand_dir, winner_dir in to_remove:
            if cand_dir.exists() and cand_dir.resolve() != winner_dir.resolve():
                shutil.rmtree(cand_dir)
                print(f"[Removed] {cand_dir}")

        self.save_manifest(kept_entries)
        self.reindex()
        print(f"\n[OK] Consolidated {len(to_remove)} duplicate skill(s).")
        return 0

    def stats(self, limit=100, as_json=False):
        """Summarize local background routing telemetry from routing_log.jsonl."""
        log_file = self.archive_dir / ".state" / "routing_log.jsonl"
        records = []
        if log_file.exists():
            try:
                lines = [ln for ln in log_file.read_text(encoding="utf-8", errors="replace").splitlines() if ln.strip()]
                if limit and limit > 0:
                    lines = lines[-limit:]
                for ln in lines:
                    try:
                        records.append(json.loads(ln))
                    except Exception:
                        pass
            except OSError:
                pass

        total = len(records)
        short_circuited = sum(1 for r in records if r.get("short_circuited"))
        zero_token = sum(1 for r in records if int(r.get("estimated_tokens", 0)) == 0)
        matched = [r for r in records if int(r.get("estimated_tokens", 0)) > 0]
        latencies = sorted(float(r.get("latency_ms", 0.0)) for r in records)
        avg_latency = round(sum(latencies) / total, 2) if total else 0.0
        p95_idx = min(len(latencies) - 1, int(len(latencies) * 0.95)) if latencies else 0
        p95_latency = round(latencies[p95_idx], 2) if latencies else 0.0
        avg_tokens_matched = round(sum(int(r.get("estimated_tokens", 0)) for r in matched) / len(matched), 1) if matched else 0.0
        zero_pct = round((zero_token / total) * 100.0, 1) if total else 0.0

        skill_counts = {}
        for r in records:
            for s in r.get("matched_inline", []) + r.get("matched_pointers", []):
                skill_counts[s] = skill_counts.get(s, 0) + 1
        top_skills = sorted(skill_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:10]

        summary = {
            "total_turns": total,
            "short_circuited_turns": short_circuited,
            "zero_token_turns": zero_token,
            "zero_token_pct": zero_pct,
            "matched_turns": len(matched),
            "avg_tokens_per_matched_turn": avg_tokens_matched,
            "avg_latency_ms": avg_latency,
            "p95_latency_ms": p95_latency,
            "top_skills": [{"name": k, "count": v} for k, v in top_skills],
        }

        if as_json:
            print(json.dumps(summary, indent=2))
            return 0

        print("==================================================")
        print("            SKILL VAULT ROUTING STATS")
        print(f"  Log File: {log_file}")
        print("==================================================\n")
        if total == 0:
            print("No routing telemetry recorded yet.")
            return 0
        print(f"  * Total Routed Turns:        {total} (short-circuited: {short_circuited})")
        print(f"  * Zero-Token Turns:          {zero_token} ({zero_pct}%)")
        print(f"  * Matched Turns:             {len(matched)} (avg ~{avg_tokens_matched} tokens)")
        print(f"  * Latency (avg / p95):       {avg_latency} ms / {p95_latency} ms")
        if top_skills:
            print("\n  Top Matched Skills:")
            for name, cnt in top_skills:
                print(f"    - {name}: {cnt}")
        print("")
        return 0

    def _merge_json_config_file(self, cfg_path, mutator_fn, dry_run=False):
        cfg_path = Path(cfg_path)
        existing = {}
        if cfg_path.exists():
            try:
                existing = json.loads(cfg_path.read_text(encoding="utf-8", errors="replace"))
                if not isinstance(existing, dict):
                    existing = {}
            except Exception:
                existing = {}

        updated = mutator_fn(json.loads(json.dumps(existing)))
        if dry_run:
            return updated

        cfg_path.parent.mkdir(parents=True, exist_ok=True)
        bak_path = cfg_path.with_suffix(cfg_path.suffix + ".bak")
        if cfg_path.exists() and not bak_path.exists():
            shutil.copy2(cfg_path, bak_path)
        tmp = cfg_path.with_name(f".{cfg_path.name}.{os.getpid()}.tmp")
        tmp.write_text(json.dumps(updated, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        os.replace(tmp, cfg_path)
        return updated

    @staticmethod
    def _build_hook_command(py_exe, script_ref, harness, event_name, vault_base_dir):
        """Build a cmd /c and sh -c safe command string avoiding Windows >2 quote stripping."""
        py_str = str(py_exe)
        base_str = str(vault_base_dir)
        py_token = f'"{py_str}"' if (" " in py_str and not py_str.startswith('"')) else py_str
        script_token = f'"{script_ref}"' if (" " in str(script_ref) and '"' not in py_token) else str(script_ref)
        # Never introduce a second quoted pair on Windows cmd /c; vault_link.json carries baseDir when paths have spaces
        if " " in base_str or '"' in py_token or '"' in script_token:
            base_flag = ""
        else:
            base_flag = f" --base-dir {base_str}"
        return f"{py_token} {script_token} --harness {harness} --event {event_name}{base_flag}"

    def setup(
        self,
        agent="auto",
        scope="global",
        dry_run=False,
        migrate_archive=False,
        target_dir=None,
        python_exe=None,
    ):
        """Install background hooks, read-only MCP server, and plugin bundle for coding agents."""
        src_scripts_dir = Path(__file__).resolve().parent
        required_scripts = ["skill_vault.py", "skill_router.py", "hook_runner.py", "mcp_server.py"]
        for sname in required_scripts:
            if not (src_scripts_dir / sname).exists():
                print(f"[Error] Required script missing: {src_scripts_dir / sname}")
                return 1

        src_skill_md = None
        for cand_md in [
            src_scripts_dir.parent / "SKILL.md",
            src_scripts_dir.parent / "skills" / "skill-vault" / "SKILL.md",
        ]:
            if cand_md.exists():
                src_skill_md = cand_md
                break

        py = str(python_exe or sys.executable)
        home = Path.home()
        cwd = Path.cwd().resolve()

        if agent == "auto":
            agents = []
            if scope == "workspace":
                if (cwd / ".agents").exists():
                    agents.append("antigravity")
                if (cwd / ".claude").exists():
                    agents.append("claude")
                if (cwd / ".gemini").exists():
                    agents.append("gemini-cli")
                if (cwd / ".cursor").exists():
                    agents.append("cursor")
            else:
                if (home / ".gemini" / "config").exists():
                    agents.append("antigravity")
                if (home / ".claude").exists():
                    agents.append("claude")
                if (home / ".gemini" / "settings.json").exists():
                    agents.append("gemini-cli")
                if (home / ".cursor").exists():
                    agents.append("cursor")
            if not agents:
                agents = ["antigravity"]
        else:
            agents = [agent]

        # Determine canonical vault base directory per scope and target agent
        home_cfg = home / ".gemini" / "config"
        legacy_sv = home_cfg / "skills" / "skill-vault"
        legacy_arch = legacy_sv / "skill_archive"
        canon_arch = home_cfg / "skill_archive"
        primary_agent = agents[0]

        if self._explicit_base_dir:
            vault_base_dir = self.base_dir
        elif scope == "workspace":
            ws_existing = [
                cwd / ".agents",
                cwd / ".claude",
                cwd / ".gemini",
                cwd / ".cursor",
                cwd,
            ]
            found_ws = next((c for c in ws_existing if (c / "skill_archive").exists()), None)
            if found_ws is not None:
                vault_base_dir = found_ws
            elif primary_agent == "claude":
                vault_base_dir = cwd / ".claude"
            elif primary_agent == "gemini-cli":
                vault_base_dir = cwd / ".gemini"
            elif primary_agent == "cursor":
                vault_base_dir = (cwd / ".agents") if (cwd / ".agents").exists() else (cwd / ".cursor")
            else:
                vault_base_dir = cwd / ".agents"
        else:
            if migrate_archive and legacy_arch.exists() and not canon_arch.exists():
                vault_base_dir = home_cfg
            else:
                global_existing = [
                    home_cfg,
                    home / ".claude",
                    home / ".agents",
                    home / ".gemini",
                    home / ".cursor",
                    legacy_sv,
                ]
                found_global = next((c for c in global_existing if (c / "skill_archive").exists()), None)
                if found_global is not None:
                    vault_base_dir = found_global
                elif primary_agent == "claude":
                    vault_base_dir = home / ".claude"
                elif primary_agent == "gemini-cli":
                    vault_base_dir = home / ".gemini"
                elif primary_agent == "cursor":
                    vault_base_dir = home / ".cursor"
                else:
                    vault_base_dir = home_cfg

        print("==================================================")
        print("        SKILL VAULT ORCHESTRATION SETUP")
        print(f"  Target Agent(s): {', '.join(agents)}")
        print(f"  Scope:           {scope}")
        print(f"  Vault Base:      {vault_base_dir}")
        print(f"  Python Runtime:  {py}")
        print("==================================================\n")

        # Handle archive migration if requested
        will_migrate = (
            migrate_archive
            and scope == "global"
            and not self._explicit_base_dir
            and legacy_arch.exists()
            and not canon_arch.exists()
        )
        if will_migrate:
            print(f"[Migration Plan] {legacy_arch} -> {canon_arch}")
            print(f"                 Verify integrity before removing legacy {legacy_sv}\n")
            if not dry_run:
                src_count = len(SkillVault(base_dir=str(legacy_sv)).get_archived_skill_folders())
                shutil.copytree(legacy_arch, canon_arch, dirs_exist_ok=True)
                migrated_mgr = SkillVault(base_dir=str(home_cfg))
                if migrated_mgr.verify(fix=False) != 0:
                    print("[Error] Archive migration verification failed! Legacy archive preserved untouched.")
                    return 1
                dst_count = len(migrated_mgr.get_archived_skill_folders())
                if dst_count < src_count:
                    print(f"[Error] Migrated skill count ({dst_count}) < source ({src_count}). Legacy archive preserved untouched.")
                    return 1
                if legacy_sv.exists():
                    shutil.rmtree(legacy_sv)
                print(f"[Migrated] Verified {dst_count} skill(s) at {canon_arch} and removed legacy {legacy_sv}\n")

        # Ensure vault archive exists
        if not dry_run:
            vault_base_dir.mkdir(parents=True, exist_ok=True)
        vault_mgr = SkillVault(base_dir=str(vault_base_dir))
        if not dry_run and not vault_mgr.archive_dir.exists():
            vault_mgr.init()

        for target_agent in agents:
            if target_agent == "antigravity":
                if target_dir:
                    td = Path(target_dir).resolve()
                    if td.name == "skill-vault":
                        plugin_dir = td
                    elif td.name == "plugins":
                        plugin_dir = td / "skill-vault"
                    else:
                        plugin_dir = td / "plugins" / "skill-vault"
                elif scope == "workspace":
                    plugin_dir = cwd / ".agents" / "plugins" / "skill-vault"
                else:
                    plugin_dir = home_cfg / "plugins" / "skill-vault"

                hooks_payload = {
                    "skill-vault-session-sync": {
                        "SessionStart": [
                            {
                                "type": "command",
                                "command": self._build_hook_command(
                                    py, "scripts/hook_runner.py", "antigravity", "SessionStart", vault_base_dir
                                ),
                                "timeout": 30,
                            }
                        ]
                    },
                    "skill-vault-jit-router": {
                        "PreInvocation": [
                            {
                                "type": "command",
                                "command": self._build_hook_command(
                                    py, "scripts/hook_runner.py", "antigravity", "PreInvocation", vault_base_dir
                                ),
                                "timeout": 10,
                            }
                        ]
                    },
                }
                mcp_payload = {
                    "mcpServers": {
                        "skill-vault": {
                            "command": py,
                            "type": "stdio",
                            "args": ["scripts/mcp_server.py"],
                            "env": {"SKILL_VAULT_BASE": str(vault_base_dir)},
                        }
                    }
                }
                plugin_meta = {
                    "name": "skill-vault",
                    "displayName": "Skill Vault",
                    "version": "2.1.0",
                    "description": "Automatic background skill router, cold-storage archive, and read-only JIT MCP server.",
                    "author": "jcorpac",
                    "license": "MIT",
                }

                print(f"[Antigravity Plugin] Target: {plugin_dir}")
                if dry_run:
                    print(f"  * Would install scripts: {', '.join(required_scripts)}")
                    print("  * Would write plugin.json, hooks.json, mcp_config.json, vault_link.json, skills/skill-vault/SKILL.md")
                else:
                    scripts_dest = plugin_dir / "scripts"
                    scripts_dest.mkdir(parents=True, exist_ok=True)
                    for sname in required_scripts:
                        shutil.copy2(src_scripts_dir / sname, scripts_dest / sname)

                    if src_skill_md and src_skill_md.exists():
                        dest_md_dir = plugin_dir / "skills" / "skill-vault"
                        dest_md_dir.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(src_skill_md, dest_md_dir / "SKILL.md")

                    (plugin_dir / "plugin.json").write_text(json.dumps(plugin_meta, indent=2) + "\n", encoding="utf-8")
                    (plugin_dir / "hooks.json").write_text(json.dumps(hooks_payload, indent=2) + "\n", encoding="utf-8")
                    (plugin_dir / "mcp_config.json").write_text(json.dumps(mcp_payload, indent=2) + "\n", encoding="utf-8")
                    (plugin_dir / "vault_link.json").write_text(json.dumps({"baseDir": str(vault_base_dir)}, indent=2) + "\n", encoding="utf-8")
                    print(f"  [OK] Installed Antigravity plugin bundle to {plugin_dir}")

            elif target_agent in ("claude", "gemini-cli", "cursor"):
                # Stage permanent runtime scripts inside archive/.runtime so npx/temp paths never break
                runtime_dir = vault_mgr.archive_dir / ".runtime" / "scripts"
                hook_script = runtime_dir / "hook_runner.py"
                mcp_script = runtime_dir / "mcp_server.py"
                if not dry_run:
                    runtime_dir.mkdir(parents=True, exist_ok=True)
                    for sname in required_scripts:
                        shutil.copy2(src_scripts_dir / sname, runtime_dir / sname)
                    (runtime_dir.parent / "vault_link.json").write_text(
                        json.dumps({"baseDir": str(vault_base_dir)}, indent=2) + "\n", encoding="utf-8"
                    )

                if target_agent == "claude":
                    cfg_file = Path(target_dir).resolve() if target_dir else (
                        (cwd / ".claude" / "settings.json") if scope == "workspace" else (home / ".claude" / "settings.json")
                    )
                    evt_name = "UserPromptSubmit"
                elif target_agent == "gemini-cli":
                    cfg_file = Path(target_dir).resolve() if target_dir else (
                        (cwd / ".gemini" / "settings.json") if scope == "workspace" else (home / ".gemini" / "settings.json")
                    )
                    evt_name = "BeforeAgent"
                else:
                    cfg_file = Path(target_dir).resolve() if target_dir else (
                        (cwd / ".cursor" / "mcp.json") if scope == "workspace" else (home / ".cursor" / "mcp.json")
                    )
                    evt_name = None

                def _mutate(cfg):
                    mcp_servers = cfg.setdefault("mcpServers", {})
                    mcp_servers["skill-vault"] = {
                        "command": py,
                        "args": [str(mcp_script), "--base-dir", str(vault_base_dir)],
                        "env": {"SKILL_VAULT_BASE": str(vault_base_dir)},
                    }
                    if evt_name:
                        hooks = cfg.setdefault("hooks", {})
                        for hook_ev in ("SessionStart", evt_name):
                            groups = [
                                g for g in hooks.get(hook_ev, [])
                                if not any(
                                    "hook_runner.py" in str(h.get("command", "")) or "skill-vault" in str(h.get("command", ""))
                                    for h in (g.get("hooks", []) if isinstance(g, dict) else [])
                                )
                            ]
                            groups.append({
                                "matcher": "",
                                "hooks": [{
                                    "type": "command",
                                    "command": self._build_hook_command(
                                        py, str(hook_script), target_agent, hook_ev, vault_base_dir
                                    ),
                                }],
                            })
                            hooks[hook_ev] = groups
                    return cfg

                print(f"[{target_agent}] Config: {cfg_file}")
                self._merge_json_config_file(cfg_file, _mutate, dry_run=dry_run)
                if dry_run:
                    print(f"  * Would merge hooks/MCP into {cfg_file}")
                else:
                    print(f"  [OK] Updated {cfg_file}")
            else:
                print(f"[Error] Unsupported agent '{target_agent}'.")
                return 1

        if dry_run:
            print("\n[Dry Run] Setup preview complete. No files were modified.")
            return 0

        # Enable compact router prompt & rebuild search_index.json
        raw_cfg = vault_mgr._load_raw_config()
        routing_map = dict(raw_cfg.get("routing", {}))
        routing_map["compact_router_prompt"] = True
        raw_cfg["routing"] = routing_map
        vault_mgr.save_config(raw_cfg)
        vault_mgr.reindex()
        if "antigravity" in agents:
            vault_mgr.sync_router_md(target_skill_md=plugin_dir / "skills" / "skill-vault" / "SKILL.md", force=True)

        print("\n[OK] Skill Vault background orchestration is configured and ready.")
        return 0

    # --- Project Import Engine ---

    def resolve_vault_archive_dir(self, vault_arg=None):
        """Resolve the source vault archive directory."""
        if vault_arg:
            p = Path(vault_arg).resolve()
            if (p / "skill_archive").exists():
                return p / "skill_archive"
            return p

        env_vault = os.environ.get("SKILL_VAULT_DIR") or os.environ.get("SKILL_VAULT_ARCHIVE")
        if env_vault:
            p = Path(env_vault).resolve()
            if (p / "skill_archive").exists():
                return p / "skill_archive"
            return p

        env_base = os.environ.get("SKILL_VAULT_BASE") or os.environ.get("SKILL_BASE_DIR")
        if env_base:
            p = Path(env_base).resolve() / "skill_archive"
            if p.exists():
                return p

        # Check self.archive_dir
        if self.archive_dir.exists() and (
            (self.archive_dir / "skills").exists()
            or (self.archive_dir / "backup_manifest.json").exists()
        ):
            return self.archive_dir

        # Check standard global locations (canonical ~/.gemini/config/skill_archive first)
        candidates = [
            Path.home() / ".gemini" / "config" / "skill_archive",
            Path.home() / ".gemini" / "config" / "skills" / "skill-vault" / "skill_archive",
            Path.home() / ".gemini" / "config" / "skills" / ".skill_archive",
            Path.home() / ".agents" / "skill_archive",
            Path.home() / ".claude" / "skill_archive",
            Path.home() / ".gemini" / "skill_archive",
            Path.home() / ".cursor" / "skill_archive",
        ]
        for cand in candidates:
            if cand.exists() and (
                (cand / "skills").exists() or (cand / "backup_manifest.json").exists()
            ):
                return cand

        return self.archive_dir

    def resolve_dest_dir(self, dest_arg=None):
        """Resolve target destination directory for imported skills."""
        if dest_arg:
            p = Path(dest_arg).resolve()
            p.mkdir(parents=True, exist_ok=True)
            return p

        cwd = Path.cwd().resolve()
        if (cwd / ".agents" / "skills").exists():
            return cwd / ".agents" / "skills"
        if (cwd / "skills").exists():
            return cwd / "skills"
        if (cwd / ".claude" / "skills").exists():
            return cwd / ".claude" / "skills"
        if (cwd / ".agents").exists():
            p = cwd / ".agents" / "skills"
            p.mkdir(parents=True, exist_ok=True)
            return p

        p = cwd / "skills"
        p.mkdir(parents=True, exist_ok=True)
        return p

    def find_vault_skill(self, skill_name, vault_archive_dir, manifest_map=None):
        """Find the physical skill directory in a vault archive store."""
        vault_archive_dir = Path(vault_archive_dir).resolve()
        vault_base = (
            vault_archive_dir.parent
            if vault_archive_dir.name == "skill_archive"
            else vault_archive_dir
        )

        # 1. Check via manifest if provided
        if manifest_map and skill_name in manifest_map:
            item = manifest_map[skill_name]
            rel_archived = item.get("archived_path")
            if rel_archived:
                p1 = (vault_base / rel_archived).resolve()
                if p1.exists() and (p1 / "SKILL.md").exists():
                    return p1
                p2 = (vault_archive_dir / rel_archived).resolve()
                if p2.exists() and (p2 / "SKILL.md").exists():
                    return p2
                p3 = Path(rel_archived)
                if p3.is_absolute() and p3.exists() and (p3 / "SKILL.md").exists():
                    return p3

        # 2. Check vault_archive_dir / "skills" / skill_name
        p_std = vault_archive_dir / "skills" / skill_name
        if p_std.exists() and (p_std / "SKILL.md").exists():
            return p_std

        # 3. Check vault_archive_dir / skill_name
        p_direct = vault_archive_dir / skill_name
        if p_direct.exists() and (p_direct / "SKILL.md").exists():
            return p_direct

        # 4. Check nested plugins_*_skills subdirectories
        if vault_archive_dir.exists():
            for child in vault_archive_dir.iterdir():
                if child.is_dir():
                    candidate = child / skill_name
                    if candidate.exists() and (candidate / "SKILL.md").exists():
                        return candidate

        return None

    def import_skills(
        self,
        name=None,
        pattern=None,
        category=None,
        import_all=False,
        dest_dir=None,
        vault_dir=None,
        force=False,
        dry_run=False,
    ):
        """Import skills from a vault (global archive or specified) into a project destination."""
        vault_archive_dir = self.resolve_vault_archive_dir(vault_dir)
        dest_path = self.resolve_dest_dir(dest_dir)

        if not vault_archive_dir.exists():
            print(f"[Error] Vault archive directory does not exist: {vault_archive_dir}")
            return 1

        # Load vault manifest if present
        manifest_file = vault_archive_dir / "backup_manifest.json"
        vault_manifest = []
        if manifest_file.exists():
            try:
                with open(manifest_file, "r", encoding="utf-8") as f:
                    vault_manifest = json.load(f)
            except Exception as e:
                print(f"[Warning] Could not parse vault manifest at {manifest_file}: {e}")

        manifest_map = {item["name"]: item for item in vault_manifest if "name" in item}

        targets = []
        if import_all:
            if manifest_map:
                targets = sorted(manifest_map.keys())
            else:
                skills_base = vault_archive_dir / "skills"
                if skills_base.exists():
                    targets = sorted([d.name for d in skills_base.iterdir() if d.is_dir() and (d / "SKILL.md").exists()])
        elif category:
            cat_lower = category.strip().lower()
            if manifest_map:
                targets = sorted([n for n, item in manifest_map.items() if item.get("category", "").lower() == cat_lower])
            if not targets:
                print(f"[Warning] No skills found matching category '{category}' in vault manifest.")
        elif pattern:
            regex = re.compile(pattern.replace("*", ".*"))
            if manifest_map:
                targets = sorted([n for n in manifest_map.keys() if regex.match(n)])
            else:
                skills_base = vault_archive_dir / "skills"
                if skills_base.exists():
                    targets = sorted([d.name for d in skills_base.iterdir() if d.is_dir() and regex.match(d.name)])
        elif name:
            targets = [name.strip()]
        else:
            print("Please specify a skill name, --category, --pattern, or --all to import.")
            return 1

        if not targets:
            print("No matching skills found in vault to import.")
            return 1

        imported_count = 0
        skipped_count = 0
        error_count = 0

        print("==================================================")
        print("            SKILL VAULT PROJECT IMPORT")
        print(f"  Source Vault: {vault_archive_dir}")
        print(f"  Target Dest:  {dest_path}")
        print("==================================================\n")

        for skill_name in targets:
            source_skill_dir = self.find_vault_skill(skill_name, vault_archive_dir, manifest_map)
            if not source_skill_dir:
                print(f"[Error] Skill '{skill_name}' not found in vault ({vault_archive_dir})")
                error_count += 1
                continue

            target_skill_dir = dest_path / skill_name

            if target_skill_dir.exists():
                recency = compare_skill_recency(source_skill_dir, target_skill_dir)
                if recency <= 0 and not force:
                    print(f"[Skip] Project skill '{skill_name}' is already newer than or equal to vault version (use --force to overwrite)")
                    skipped_count += 1
                    continue
                else:
                    if dry_run:
                        print(f"[Dry Run] Would update project skill with newer vault version: {skill_name} -> {target_skill_dir}")
                    else:
                        shutil.rmtree(target_skill_dir)
                        shutil.copytree(source_skill_dir, target_skill_dir)
                        print(f"[Imported] Updated project skill with newer vault version: {skill_name} -> {target_skill_dir}")
                    imported_count += 1
            else:
                if dry_run:
                    print(f"[Dry Run] Would import: {skill_name} -> {target_skill_dir}")
                else:
                    shutil.copytree(source_skill_dir, target_skill_dir)
                    print(f"[Imported] {skill_name} -> {target_skill_dir}")
                imported_count += 1

        print(f"\n[OK] Import completed: {imported_count} imported, {skipped_count} skipped, {error_count} errors.")
        return 0 if error_count == 0 else 1


def main():
    parser = argparse.ArgumentParser(description="Skill Vault: Universal Agent Skill Lifecycle & Storage Manager")
    parser.add_argument("--base-dir", help="Explicit base directory for skills and archive")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Init
    p_init = subparsers.add_parser("init", help="Bootstrap standard skill directory structure in workspace")

    # Optimize / Auto-Tune
    p_opt = subparsers.add_parser("optimize", help="Auto-minimize active skills to essential Core + workspace stack")
    p_opt.add_argument("--workspace", help="Path to workspace directory to inspect")
    p_opt.add_argument("--protect", nargs="*", help="Additional skill names to protect from auto-archiving")
    p_opt.add_argument("--dry-run", action="store_true", help="Preview optimization changes without moving files")
    p_opt.add_argument("--force", action="store_true", help="Force overwrite during optimization regardless of recency")

    # List / Overview
    p_list = subparsers.add_parser("list", help="Present active and archived skills")
    p_list.add_argument("-a", "--active", action="store_true", help="List only active skills (L1 Context)")
    p_list.add_argument("-c", "--archived", action="store_true", help="List only archived skills (L2 Vault)")
    p_list.add_argument("--category", help="Filter by category")
    p_list.add_argument("--summary", action="store_true", help="Show compact category summary")
    p_list.add_argument("--json", action="store_true", help="Output in structured JSON format")

    # Status (alias for list --summary)
    p_stat = subparsers.add_parser("status", help="Show summary of active and archived skills")
    p_stat.add_argument("--json", action="store_true", help="Output in structured JSON format")

    # Archive
    p_arch = subparsers.add_parser("archive", help="Archive active skills into cold storage")
    p_arch.add_argument("name", nargs="?", help="Specific skill name")
    p_arch.add_argument("--pattern", help="Glob pattern (e.g. 'gcp-*')")
    p_arch.add_argument("--category", help="Category name (e.g. 'Cloud Architecture')")
    p_arch.add_argument("--keep-active", action="store_true", help="Do not delete source folder")
    p_arch.add_argument("--force", action="store_true", help="Force overwrite in archive regardless of recency")

    # Recategorize
    p_rec = subparsers.add_parser("recategorize", help="Recategorize an archived skill in metadata or auto-recategorize General skills")
    p_rec.add_argument("name", nargs="?", help="Skill name")
    p_rec.add_argument("category", nargs="?", help="New category name")
    p_rec.add_argument("--auto", action="store_true", help="Auto-recategorize skills in 'General & Utility Skills'")
    p_rec.add_argument("--dry-run", action="store_true", help="Preview auto-recategorization without modifying manifest")

    # Restore
    p_rest = subparsers.add_parser("restore", help="Restore archived skills back to active availability")
    p_rest.add_argument("name", nargs="?", help="Specific skill name")
    p_rest.add_argument("--all", action="store_true", help="Restore all archived skills")
    p_rest.add_argument("--pattern", help="Glob pattern to restore")
    p_rest.add_argument("--category", help="Category name to restore")
    p_rest.add_argument("--force", action="store_true", help="Overwrite existing active directory")

    # Reindex
    p_idx = subparsers.add_parser("reindex", help="Rebuild INDEX.md, search_index.json, and sync manifest")

    # Verify / Integrity Check
    p_ver = subparsers.add_parser("verify", help="Verify archive integrity and L2 compatibility")
    p_ver.add_argument("--fix", action="store_true", help="Automatically repair any detected discrepancies")
    p_ver.add_argument("--compat", action="store_true", help="Audit L2 compatibility (path dependencies, cross-skill refs, oversized SKILL.md, guardrails)")
    p_ver.add_argument("--json", action="store_true", help="Output structured JSON")

    # Search
    p_srch = subparsers.add_parser("search", help="Search archived skills by keyword, intent, or domain")
    p_srch.add_argument("query", help="Keyword or natural-language query to search for")
    p_srch.add_argument("--category", help="Filter search results by category")
    p_srch.add_argument("--limit", type=int, default=10, help="Maximum number of results to show")
    p_srch.add_argument("--json", action="store_true", help="Output structured JSON")

    # Route (dry-run JIT router debugger)
    p_route = subparsers.add_parser("route", help="Dry-run the background JIT skill router against a prompt")
    p_route.add_argument("prompt", help="User prompt to evaluate")
    p_route.add_argument("--workspace", help="Optional workspace path for soft stack tie-breaking")
    p_route.add_argument("--mode", choices=["hybrid", "inline", "pointer"], help="Override routing mode")
    p_route.add_argument("--json", action="store_true", help="Output structured JSON")

    # Dedupe
    p_dedupe = subparsers.add_parser(
        "dedupe",
        help="Consolidate duplicate skills in archive (canonical name, frontmatter name, or identical content), keeping the newest version",
    )
    p_dedupe.add_argument("--dry-run", action="store_true", help="Preview duplicates without deleting files")

    # Stats
    p_stats = subparsers.add_parser("stats", help="Show local background routing telemetry summary")
    p_stats.add_argument("--limit", type=int, default=100, help="Inspect most recent N turns")
    p_stats.add_argument("--json", action="store_true", help="Output structured JSON")

    # Setup
    p_setup = subparsers.add_parser("setup", help="Install background hooks, MCP server, and plugin wiring")
    p_setup.add_argument(
        "--agent",
        choices=["auto", "antigravity", "claude", "gemini-cli", "cursor"],
        default="auto",
        help="Target agent harness (default: auto)",
    )
    p_setup.add_argument(
        "--scope",
        choices=["global", "workspace"],
        default="global",
        help="Install globally or inside current workspace",
    )
    p_setup.add_argument("--dry-run", action="store_true", help="Preview installation plan without modifying files")
    p_setup.add_argument(
        "--migrate-archive",
        action="store_true",
        help="Safely migrate legacy ~/.gemini/config/skills/skill-vault/skill_archive to ~/.gemini/config/skill_archive",
    )
    p_setup.add_argument("--target-dir", help="Explicit target plugin directory or config file path")

    # Sync
    p_sync = subparsers.add_parser("sync", help="Scan plugins and active skills, ingest new/updated skills, and prune non-core skills")
    p_sync.add_argument("--dry-run", action="store_true", help="Preview sync operations without moving or deleting files")
    p_sync.add_argument("--keep-active", action="store_true", help="Keep all scanned skills active in context instead of pruning")
    p_sync.add_argument("--force", action="store_true", help="Force overwrite in vault even if vault copy is newer")
    p_sync.add_argument("--protect", nargs="*", help="Additional skill names to protect from pruning")

    # Import
    p_imp = subparsers.add_parser("import", help="Import skills from vault into project or target directory")
    p_imp.add_argument("name", nargs="?", help="Specific skill name to import")
    p_imp.add_argument("--pattern", help="Glob pattern of skills to import (e.g. 'gcp-*')")
    p_imp.add_argument("--category", help="Import all skills in a category")
    p_imp.add_argument("--all", action="store_true", help="Import all skills from the vault")
    p_imp.add_argument("--dest", help="Destination directory in project (default: ./skills or ./.agents/skills)")
    p_imp.add_argument("--vault-dir", help="Explicit source vault archive directory")
    p_imp.add_argument("--force", action="store_true", help="Overwrite existing skill in project regardless of recency")
    p_imp.add_argument("--dry-run", action="store_true", help="Preview skills that would be imported without copying")

    # Config
    p_cfg = subparsers.add_parser("config", help="Inspect or customize vault_config.json and sync SKILL.md router prompt")
    p_cfg.add_argument("--show", action="store_true", help="Show active configuration and defaults")
    p_cfg.add_argument("--init", action="store_true", dest="init_config", help="Write current configuration defaults to vault_config.json")
    p_cfg.add_argument("--add-core", nargs="+", metavar="SKILL", help="Add one or more skills to protected core skills")
    p_cfg.add_argument("--remove-core", nargs="+", metavar="SKILL", help="Remove one or more skills from protected core skills")
    p_cfg.add_argument("--add-fingerprint", nargs=2, action="append", metavar=("CATEGORY", "PATTERN"), help="Add a workspace file/glob fingerprint for a category")
    p_cfg.add_argument("--add-category-rule", nargs=2, action="append", metavar=("CATEGORY", "KEYWORD"), help="Add an inference keyword rule for a category")
    p_cfg.add_argument("--set-routing", nargs=2, action="append", metavar=("KEY", "VALUE"), help="Set a routing configuration option (e.g. mode hybrid)")
    p_cfg.add_argument("--sync-prompt", action="store_true", help="Synchronize SKILL.md router description with archived categories")

    # Uninstall / Eject
    p_uninst = subparsers.add_parser(
        "uninstall",
        aliases=["eject"],
        help="Cleanly restore all archived skills to L1 (preserving newer L1 versions) and remove skill-vault",
    )
    p_uninst.add_argument("--dry-run", action="store_true", help="Preview restoration and removal plan without modifying files")
    p_uninst.add_argument("--force", action="store_true", help="Overwrite active L1 skills even if L1 copy is newer")
    p_uninst.add_argument("--keep-archive", action="store_true", help="Preserve skill_archive (relocating it out of skill-vault if nested)")
    p_uninst.add_argument("--keep-skill", action="store_true", help="Restore all skills and remove archive, but keep the skill-vault skill folder")

    args = parser.parse_args()
    mgr = SkillVault(base_dir=args.base_dir)

    if args.command == "init":
        mgr.init()
    elif args.command == "optimize":
        mgr.optimize(workspace_path=args.workspace, protected_skills=args.protect, dry_run=args.dry_run, force=args.force)
    elif args.command == "sync":
        sys.exit(
            mgr.sync(
                dry_run=args.dry_run,
                keep_active=args.keep_active,
                force=args.force,
                protect_skills=args.protect,
            )
        )
    elif args.command == "list":
        show_active = not args.archived or args.active
        show_archived = not args.active or args.archived
        mgr.list_skills(
            show_active=show_active,
            show_archived=show_archived,
            category_filter=args.category,
            as_json=args.json,
            summary_only=args.summary,
        )
    elif args.command == "status":
        mgr.list_skills(
            show_active=True,
            show_archived=True,
            as_json=args.json,
            summary_only=True,
        )
    elif args.command == "archive":
        mgr.archive(name=args.name, pattern=args.pattern, category=args.category, keep_active=args.keep_active, force=args.force)
    elif args.command == "recategorize":
        sys.exit(mgr.recategorize(name=args.name, new_category=args.category, auto=args.auto, dry_run=args.dry_run))
    elif args.command == "restore":
        mgr.restore(name=args.name, pattern=args.pattern, category=args.category, restore_all=args.all, force=args.force)
    elif args.command == "reindex":
        mgr.reindex()
    elif args.command == "verify":
        sys.exit(mgr.verify(fix=args.fix, compat=args.compat, as_json=args.json))
    elif args.command == "search":
        mgr.search(query=args.query, category=args.category, limit=args.limit, as_json=args.json)
    elif args.command == "route":
        sys.exit(mgr.route(prompt=args.prompt, workspace_path=args.workspace, mode=args.mode, as_json=args.json))
    elif args.command == "dedupe":
        sys.exit(mgr.dedupe(dry_run=args.dry_run))
    elif args.command == "stats":
        sys.exit(mgr.stats(limit=args.limit, as_json=args.json))
    elif args.command == "setup":
        sys.exit(
            mgr.setup(
                agent=args.agent,
                scope=args.scope,
                dry_run=args.dry_run,
                migrate_archive=args.migrate_archive,
                target_dir=args.target_dir,
            )
        )
    elif args.command == "import":
        sys.exit(
            mgr.import_skills(
                name=args.name,
                pattern=args.pattern,
                category=args.category,
                import_all=args.all,
                dest_dir=args.dest,
                vault_dir=args.vault_dir,
                force=args.force,
                dry_run=args.dry_run,
            )
        )
    elif args.command == "config":
        mgr.manage_config(
            show=args.show,
            init_config=args.init_config,
            add_core=args.add_core,
            remove_core=args.remove_core,
            add_fingerprint=args.add_fingerprint,
            add_category_rule=args.add_category_rule,
            set_routing=args.set_routing,
            sync_prompt=args.sync_prompt,
        )
    elif args.command in ("uninstall", "eject"):
        sys.exit(
            mgr.uninstall(
                dry_run=args.dry_run,
                force=args.force,
                keep_archive=args.keep_archive,
                keep_skill=args.keep_skill,
            )
        )


if __name__ == "__main__":
    main()
