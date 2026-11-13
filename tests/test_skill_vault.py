#!/usr/bin/env python3
"""Comprehensive Test Suite & Test Harness for skill_vault.py.

Runs in an isolated sandbox without modifying real user skills or archives.
Validates:
1. Path resolution across environments
2. Workspace bootstrapping (init)
3. Presenting active and archived skills (list & status)
4. Workspace detection & automated optimization (optimize)
5. Archiving with LLM categories & preservation of SKILL.md
6. Restoring skills (single, pattern, category, overwrite)
7. Recategorization in manifest & index
8. Reindexing & relative link generation
9. Search matching
10. Bi-directional integrity audit & self-healing (--fix)
11. CLI command execution
"""

import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

# Import SkillVault from the parent scripts directory
SCRIPT_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))
from skill_vault import SkillVault, resolve_base_dir, parse_version_tuple, compare_skill_recency


class TestSkillVault(unittest.TestCase):
    def setUp(self):
        """Create an isolated sandbox for testing."""
        self.test_dir = tempfile.TemporaryDirectory()
        self.base_dir = Path(self.test_dir.name).resolve()

        # Create standard layout
        self.skills_dir = self.base_dir / "skills"
        self.archive_dir = self.base_dir / "skill_archive"
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        self.archive_dir.mkdir(parents=True, exist_ok=True)

        # Initialize manager targeting the sandbox base_dir
        self.mgr = SkillVault(base_dir=str(self.base_dir))

    def tearDown(self):
        """Clean up the sandbox."""
        self.test_dir.cleanup()

    def _create_mock_skill(self, base_path, name, description="A test skill description.", version=None, extra_files=None):
        """Helper to create a valid mock skill folder."""
        skill_dir = base_path / name
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_md = skill_dir / "SKILL.md"
        ver_header = f"version: {version}\n" if version else ""
        content = f"---\nname: {name}\n{ver_header}description: {description}\n---\n\n# {name}\n\nInstructions."
        skill_md.write_text(content, encoding="utf-8")

        if extra_files:
            for rel_file, file_content in extra_files.items():
                target_file = skill_dir / rel_file
                target_file.parent.mkdir(parents=True, exist_ok=True)
                target_file.write_text(file_content, encoding="utf-8")
        return skill_dir

    # --- 1. Base Directory Resolution Tests ---

    def test_base_dir_resolution(self):
        """Test base directory resolution via CLI argument, env var, and default."""
        # 1. Explicit CLI argument
        resolved = resolve_base_dir(cli_base=str(self.base_dir))
        self.assertEqual(resolved, self.base_dir)

        # 2. Environment variable
        os.environ["SKILL_VAULT_BASE"] = str(self.base_dir)
        try:
            resolved_env = resolve_base_dir()
            self.assertEqual(resolved_env, self.base_dir)
        finally:
            del os.environ["SKILL_VAULT_BASE"]

    def test_init_command(self):
        """Test initializing a fresh workspace."""
        empty_sandbox = tempfile.TemporaryDirectory()
        try:
            vault = SkillVault(base_dir=empty_sandbox.name)
            vault.init()
            self.assertTrue((Path(empty_sandbox.name) / "skills").exists())
            self.assertTrue((Path(empty_sandbox.name) / "skill_archive" / "backup_manifest.json").exists())
            self.assertTrue((Path(empty_sandbox.name) / "skill_archive" / "INDEX.md").exists())
        finally:
            empty_sandbox.cleanup()

    # --- 2. List & Status Presentation Tests ---

    def test_list_and_status_skills(self):
        """Test listing active and archived skills and status summary."""
        self._create_mock_skill(self.skills_dir, "active-skill-1", "Active skill description.")
        self._create_mock_skill(self.skills_dir, "archived-skill-1", "Archived skill description.")
        self.mgr.archive(name="archived-skill-1", category="Analytics")

        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            self.mgr.list_skills(show_active=True, show_archived=True)
            output = sys.stdout.getvalue()
            self.assertIn("L1 ACTIVE SKILLS", output)
            self.assertIn("active-skill-1", output)
            self.assertIn("L2 ARCHIVED SKILLS", output)
            self.assertIn("archived-skill-1", output)
            self.assertIn("[Analytics]", output)
        finally:
            sys.stdout = old_stdout

    # --- 3. Workspace Detection & Auto-Optimization Tests ---

    def test_detect_workspace_categories(self):
        """Test scanning files to fingerprint workspace stack."""
        ws = tempfile.TemporaryDirectory()
        try:
            ws_path = Path(ws.name)
            (ws_path / "dbt_project.yml").write_text("name: my_dbt_project", encoding="utf-8")
            (ws_path / "models").mkdir(parents=True, exist_ok=True)
            (ws_path / "models" / "query.sql").write_text("SELECT 1;", encoding="utf-8")

            detected = self.mgr.detect_workspace_categories(ws_path)
            self.assertIn("BigQuery & Data Warehouse", detected)
        finally:
            ws.cleanup()

    def test_optimize_minimization(self):
        """Test auto-minimization keeping core + matched skills, archiving unrelated skills."""
        # 1. Setup Active Skills
        self._create_mock_skill(self.skills_dir, "skill-vault", "Vault Core.")
        self._create_mock_skill(self.skills_dir, "accidental-data-loss-prevention", "Safety Core.")
        self._create_mock_skill(self.skills_dir, "unrelated-bio-skill", "Bio skill in active memory.")
        self._create_mock_skill(self.skills_dir, "bigquery-helper", "BigQuery tool in active memory.")

        # 2. Setup Archive Vault
        manifest = [
            {
                "name": "unrelated-bio-skill",
                "category": "Science & Biomedicine",
                "original_path": "skills/unrelated-bio-skill",
                "archived_path": "skill_archive/skills/unrelated-bio-skill",
            },
            {
                "name": "bigquery-helper",
                "category": "BigQuery & Data Warehouse",
                "original_path": "skills/bigquery-helper",
                "archived_path": "skill_archive/skills/bigquery-helper",
            },
            {
                "name": "vaulted-sql-tool",
                "category": "BigQuery & Data Warehouse",
                "original_path": "skills/vaulted-sql-tool",
                "archived_path": "skill_archive/skills/vaulted-sql-tool",
            },
        ]
        self.mgr.save_manifest(manifest)
        # Create vaulted skill folder
        self._create_mock_skill(self.archive_dir / "skills", "vaulted-sql-tool", "Vaulted SQL tool.")

        # 3. Create a SQL workspace
        ws = tempfile.TemporaryDirectory()
        try:
            ws_path = Path(ws.name)
            (ws_path / "query.sql").write_text("SELECT * FROM table;", encoding="utf-8")

            # Run optimize
            self.mgr.optimize(workspace_path=ws_path)

            # Core skills must remain active
            self.assertTrue((self.skills_dir / "skill-vault").exists())
            self.assertTrue((self.skills_dir / "accidental-data-loss-prevention").exists())

            # Matched BigQuery skills must be active
            self.assertTrue((self.skills_dir / "bigquery-helper").exists())
            self.assertTrue((self.skills_dir / "vaulted-sql-tool").exists())

            # Unrelated bio skill must be evicted to cold storage
            self.assertFalse((self.skills_dir / "unrelated-bio-skill").exists())
            self.assertTrue((self.archive_dir / "skills" / "unrelated-bio-skill").exists())
        finally:
            ws.cleanup()

    # --- 4. Archive Tests ---

    def test_archive_single_skill_with_category(self):
        """Test archiving a single active skill with category."""
        self._create_mock_skill(self.skills_dir, "cloud-sql-backup", "Manages database backups.")
        
        self.mgr.archive(name="cloud-sql-backup", category="Cloud Database")

        self.assertFalse((self.skills_dir / "cloud-sql-backup").exists())

        archived_skill = self.archive_dir / "skills" / "cloud-sql-backup"
        self.assertTrue((archived_skill / "SKILL.md").exists())

        content = (archived_skill / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("name: cloud-sql-backup", content)
        self.assertNotIn("Cloud Database", content)

        manifest = self.mgr.load_manifest()
        self.assertEqual(len(manifest), 1)
        self.assertEqual(manifest[0]["name"], "cloud-sql-backup")
        self.assertEqual(manifest[0]["category"], "Cloud Database")

        index_content = self.mgr.index_file.read_text(encoding="utf-8")
        self.assertIn("## Cloud Database (1 skills)", index_content)
        self.assertIn("### `cloud-sql-backup`", index_content)

    def test_archive_pattern_and_keep_active(self):
        """Test archiving multiple skills with pattern matching and --keep-active."""
        self._create_mock_skill(self.skills_dir, "gcp-spanner", "Spanner tools.")
        self._create_mock_skill(self.skills_dir, "gcp-pubsub", "PubSub tools.")
        self._create_mock_skill(self.skills_dir, "aws-s3", "S3 tools.")

        self.mgr.archive(pattern="gcp-*", category="Google Cloud", keep_active=True)

        self.assertTrue((self.skills_dir / "gcp-spanner").exists())
        self.assertTrue((self.skills_dir / "gcp-pubsub").exists())
        self.assertTrue((self.archive_dir / "skills" / "gcp-spanner").exists())
        self.assertTrue((self.archive_dir / "skills" / "gcp-pubsub").exists())
        self.assertFalse((self.archive_dir / "skills" / "aws-s3").exists())

    # --- 5. Recategorize Tests ---

    def test_recategorize_skill(self):
        """Test updating a category without touching SKILL.md."""
        self._create_mock_skill(self.skills_dir, "data-cleaner", "Cleans raw datasets.")
        self.mgr.archive(name="data-cleaner", category="Initial Category")

        self.mgr.recategorize(name="data-cleaner", new_category="Data Engineering")

        manifest = self.mgr.load_manifest()
        self.assertEqual(manifest[0]["category"], "Data Engineering")

        index_content = self.mgr.index_file.read_text(encoding="utf-8")
        self.assertIn("## Data Engineering (1 skills)", index_content)
        self.assertNotIn("Initial Category", index_content)

    # --- 6. Restore Tests ---

    def test_restore_single_and_category(self):
        """Test restoring archived skills back to active locations."""
        self._create_mock_skill(self.skills_dir, "bigquery-optimizer", "Optimizes SQL.")
        self._create_mock_skill(self.skills_dir, "bigquery-partitioning", "Handles partitioning.")
        self.mgr.archive(pattern="bigquery-*", category="Data Warehouse")

        self.assertFalse((self.skills_dir / "bigquery-optimizer").exists())
        self.assertFalse((self.skills_dir / "bigquery-partitioning").exists())

        self.mgr.restore(name="bigquery-optimizer")
        self.assertTrue((self.skills_dir / "bigquery-optimizer" / "SKILL.md").exists())
        self.assertFalse((self.skills_dir / "bigquery-partitioning").exists())

        self.mgr.restore(category="Data Warehouse")
        self.assertTrue((self.skills_dir / "bigquery-partitioning" / "SKILL.md").exists())

    # --- 7. Search Tests ---

    def test_search_skills(self):
        """Test keyword searching in names, descriptions, and categories."""
        self._create_mock_skill(self.skills_dir, "alphafold-protein", "Analyzes 3D protein structures.")
        self.mgr.archive(name="alphafold-protein", category="Biomedical")

        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            self.mgr.search("protein")
            output = sys.stdout.getvalue()
            self.assertIn("alphafold-protein", output)
            self.assertIn("Biomedical", output)
        finally:
            sys.stdout = old_stdout

    # --- 8. Integrity Verification & Self-Healing Tests ---

    def test_integrity_audit_clean(self):
        """Test verify returns 0 when archive is in 100% sync."""
        self._create_mock_skill(self.skills_dir, "skill-a", "Skill A description.")
        self.mgr.archive(name="skill-a", category="Category A")

        ret = self.mgr.verify(fix=False)
        self.assertEqual(ret, 0)

    def test_integrity_audit_detection_and_self_healing(self):
        """Test verify detects discrepancies and --fix heals them."""
        self._create_mock_skill(self.skills_dir, "skill-valid", "Valid skill.")
        self.mgr.archive(name="skill-valid", category="Category Valid")

        manifest = self.mgr.load_manifest()
        manifest.append({
            "name": "phantom-skill",
            "category": "Ghost",
            "original_path": "skills/phantom-skill",
            "archived_path": "skill_archive/skills/phantom-skill"
        })
        self.mgr.save_manifest(manifest)

        unindexed = self.archive_dir / "skills" / "unindexed-skill"
        unindexed.mkdir(parents=True, exist_ok=True)
        (unindexed / "SKILL.md").write_text("---\nname: unindexed-skill\ndescription: Unindexed.\n---\n", encoding="utf-8")

        ret_fail = self.mgr.verify(fix=False)
        self.assertEqual(ret_fail, 1)

        ret_fix = self.mgr.verify(fix=True)
        self.assertEqual(ret_fix, 0)

        ret_clean = self.mgr.verify(fix=False)
        self.assertEqual(ret_clean, 0)

        final_manifest = self.mgr.load_manifest()
        names = [m["name"] for m in final_manifest]
        self.assertNotIn("phantom-skill", names)
        self.assertIn("unindexed-skill", names)
        self.assertIn("skill-valid", names)

    # --- 9. End-to-End CLI Invocation Test ---

    def test_cli_execution(self):
        """Test running skill_vault.py directly via subprocess CLI."""
        script_path = SCRIPT_DIR / "skill_vault.py"
        
        self._create_mock_skill(self.skills_dir, "cli-test-skill", "CLI test description.")

        # Archive via CLI
        res = subprocess.run(
            [sys.executable, str(script_path), "--base-dir", str(self.base_dir), "archive", "cli-test-skill", "--category", "CLI Tests"],
            capture_output=True,
            text=True
        )
        self.assertEqual(res.returncode, 0)
        self.assertIn("[Archived]", res.stdout)

        # Optimize via CLI
        res_opt = subprocess.run(
            [sys.executable, str(script_path), "--base-dir", str(self.base_dir), "optimize", "--dry-run"],
            capture_output=True,
            text=True
        )
        self.assertEqual(res_opt.returncode, 0)
        self.assertIn("SKILL VAULT AUTO-OPTIMIZATION", res_opt.stdout)

        # Verify via CLI
        res_verify = subprocess.run(
            [sys.executable, str(script_path), "--base-dir", str(self.base_dir), "verify"],
            capture_output=True,
            text=True
        )
        self.assertEqual(res_verify.returncode, 0)
        self.assertIn("[OK] 100% Integrity Verified!", res_verify.stdout)

    # --- 10. Recency & Version Prioritization Tests ---

    def test_parse_version_tuple(self):
        """Test parsing diverse version formats into comparable tuples."""
        self.assertEqual(parse_version_tuple("v1"), (1,))
        self.assertEqual(parse_version_tuple("v20"), (20,))
        self.assertEqual(parse_version_tuple("1.2.3"), (1, 2, 3))
        self.assertEqual(parse_version_tuple("v0.9.1"), (0, 9, 1))
        self.assertIsNone(parse_version_tuple(""))
        self.assertIsNone(parse_version_tuple(None))
        self.assertIsNone(parse_version_tuple("unversioned"))

    def test_compare_skill_recency_version_and_mtime(self):
        """Test compare_skill_recency with semantic version and mtime fallback."""
        skill_a = self._create_mock_skill(self.skills_dir, "skill-a", version="v2")
        skill_b = self._create_mock_skill(self.archive_dir / "skills", "skill-b", version="v1")
        self.assertEqual(compare_skill_recency(skill_a, skill_b), 1)
        self.assertEqual(compare_skill_recency(skill_b, skill_a), -1)

        # Equal versions compare identical
        skill_c = self._create_mock_skill(self.skills_dir, "skill-c", version="v1")
        self.assertEqual(compare_skill_recency(skill_b, skill_c), 0)

    def test_archive_prioritizes_newer_version(self):
        """Test archiving overwrites older archive if active is newer, but preserves newer archive if active is older."""
        # 1. Active is newer (v2) than Archive (v1) -> Archive must be upgraded to v2
        self._create_mock_skill(self.skills_dir, "evolving-skill", version="v2")
        self._create_mock_skill(self.archive_dir / "skills", "evolving-skill", version="v1")
        manifest = [{
            "name": "evolving-skill",
            "category": "Testing",
            "original_path": "skills/evolving-skill",
            "archived_path": "skill_archive/skills/evolving-skill",
        }]
        self.mgr.save_manifest(manifest)

        self.mgr.archive(name="evolving-skill")
        archived_md = (self.archive_dir / "skills" / "evolving-skill" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("version: v2", archived_md)

        # 2. Active is older (v1) than Archive (v2) -> Archive must be preserved at v2, not overwritten
        self._create_mock_skill(self.skills_dir, "evolving-skill", version="v1")
        self.mgr.archive(name="evolving-skill")
        archived_md_after = (self.archive_dir / "skills" / "evolving-skill" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("version: v2", archived_md_after)

    def test_restore_prioritizes_newer_version(self):
        """Test restore updates active skill if archive is newer, but skips if active is already newer."""
        # 1. Archive is newer (v2) than Active (v1) -> Active must be updated to v2
        self._create_mock_skill(self.skills_dir, "restorable-skill", version="v1")
        self._create_mock_skill(self.archive_dir / "skills", "restorable-skill", version="v2")
        manifest = [{
            "name": "restorable-skill",
            "category": "Testing",
            "original_path": "skills/restorable-skill",
            "archived_path": "skill_archive/skills/restorable-skill",
        }]
        self.mgr.save_manifest(manifest)

        self.mgr.restore(name="restorable-skill")
        active_md = (self.skills_dir / "restorable-skill" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("version: v2", active_md)

        # 2. Active is newer (v3) than Archive (v2) -> Active must remain at v3
        (self.skills_dir / "restorable-skill" / "SKILL.md").write_text("---\nname: restorable-skill\nversion: v3\ndescription: Test.\n---\n", encoding="utf-8")
        self.mgr.restore(name="restorable-skill")
        active_md_preserved = (self.skills_dir / "restorable-skill" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("version: v3", active_md_preserved)

    def test_force_overwrites_regardless_of_recency(self):
        """Test --force flag forces overwrite even when target is newer."""
        self._create_mock_skill(self.skills_dir, "forced-skill", version="v1")
        self._create_mock_skill(self.archive_dir / "skills", "forced-skill", version="v2")
        manifest = [{
            "name": "forced-skill",
            "category": "Testing",
            "original_path": "skills/forced-skill",
            "archived_path": "skill_archive/skills/forced-skill",
        }]
        self.mgr.save_manifest(manifest)

        # Forcing archive of older v1 over newer v2
        self.mgr.archive(name="forced-skill", force=True)
        archived_md = (self.archive_dir / "skills" / "forced-skill" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("version: v1", archived_md)

    # --- 8. Project Import Engine Tests ---

    def test_import_single_skill_to_project(self):
        """Test importing a single skill from vault into a project directory."""
        self._create_mock_skill(self.archive_dir / "skills", "gcp-spanner", description="Spanner skill.", version="1.0.0")
        manifest = [{
            "name": "gcp-spanner",
            "category": "GCP & Data Engineering",
            "original_path": "skills/gcp-spanner",
            "archived_path": "skill_archive/skills/gcp-spanner",
        }]
        self.mgr.save_manifest(manifest)

        project_dir = self.base_dir / "mock_project"
        project_skills = project_dir / ".agents" / "skills"

        exit_code = self.mgr.import_skills(
            name="gcp-spanner",
            dest_dir=str(project_skills),
            vault_dir=str(self.archive_dir),
        )
        self.assertEqual(exit_code, 0)
        imported_skill_md = project_skills / "gcp-spanner" / "SKILL.md"
        self.assertTrue(imported_skill_md.exists())
        self.assertIn("version: 1.0.0", imported_skill_md.read_text(encoding="utf-8"))

    def test_import_category_to_project(self):
        """Test importing all skills in a category from vault into a project."""
        self._create_mock_skill(self.archive_dir / "skills", "bq-query", description="BigQuery query tool.", version="1.0")
        self._create_mock_skill(self.archive_dir / "skills", "bq-export", description="BigQuery export tool.", version="1.0")
        self._create_mock_skill(self.archive_dir / "skills", "chembl-tool", description="ChEMBL drug lookup.", version="1.0")

        manifest = [
            {"name": "bq-query", "category": "BigQuery & Data Warehouse", "archived_path": "skill_archive/skills/bq-query"},
            {"name": "bq-export", "category": "BigQuery & Data Warehouse", "archived_path": "skill_archive/skills/bq-export"},
            {"name": "chembl-tool", "category": "Science & Biomedicine", "archived_path": "skill_archive/skills/chembl-tool"},
        ]
        self.mgr.save_manifest(manifest)

        project_skills = self.base_dir / "project2" / "skills"
        exit_code = self.mgr.import_skills(
            category="BigQuery & Data Warehouse",
            dest_dir=str(project_skills),
            vault_dir=str(self.archive_dir),
        )
        self.assertEqual(exit_code, 0)
        self.assertTrue((project_skills / "bq-query" / "SKILL.md").exists())
        self.assertTrue((project_skills / "bq-export" / "SKILL.md").exists())
        self.assertFalse((project_skills / "chembl-tool").exists())

    def test_import_recency_and_force(self):
        """Test importing checks recency and skips older versions unless --force is passed."""
        self._create_mock_skill(self.archive_dir / "skills", "versioned-tool", version="1.0")
        manifest = [{"name": "versioned-tool", "category": "Tools", "archived_path": "skill_archive/skills/versioned-tool"}]
        self.mgr.save_manifest(manifest)

        project_skills = self.base_dir / "project3" / "skills"
        self._create_mock_skill(project_skills, "versioned-tool", version="2.0")

        # Without force -> skip
        self.mgr.import_skills(name="versioned-tool", dest_dir=str(project_skills), vault_dir=str(self.archive_dir))
        content = (project_skills / "versioned-tool" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("version: 2.0", content)

        # With force -> overwrite
        self.mgr.import_skills(name="versioned-tool", dest_dir=str(project_skills), vault_dir=str(self.archive_dir), force=True)
        content_forced = (project_skills / "versioned-tool" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("version: 1.0", content_forced)

    def test_import_cli(self):
        """Test import command via CLI subprocess."""
        self._create_mock_skill(self.archive_dir / "skills", "cli-import-skill", description="CLI imported.", version="1.2.3")
        manifest = [{"name": "cli-import-skill", "category": "General", "archived_path": "skill_archive/skills/cli-import-skill"}]
        self.mgr.save_manifest(manifest)

        dest_dir = self.base_dir / "cli_project" / "skills"
        script_path = SCRIPT_DIR / "skill_vault.py"

        res = subprocess.run(
            [
                sys.executable,
                str(script_path),
                "--base-dir",
                str(self.base_dir),
                "import",
                "cli-import-skill",
                "--dest",
                str(dest_dir),
                "--vault-dir",
                str(self.archive_dir),
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(res.returncode, 0, f"CLI stderr: {res.stderr}")
        self.assertIn("[Imported] cli-import-skill", res.stdout)
        self.assertTrue((dest_dir / "cli-import-skill" / "SKILL.md").exists())

    # --- 9. Auto-Sync & Ingestion Engine Tests ---

    def test_sync_ingests_and_prunes_plugins(self):
        """Test sync ingests new plugin skills into vault and prunes active non-core copies."""
        plugins_dir = self.base_dir / "plugins"
        # 1. Standard plugin with nested skill
        mock_tool_dir = plugins_dir / "my-tool-plugin" / "skills" / "my-tool"
        self._create_mock_skill(mock_tool_dir.parent, "my-tool", description="A special tool.")

        # 2. Single-skill plugin layout
        single_plugin_dir = plugins_dir / "single-plugin" / "skills"
        single_plugin_dir.mkdir(parents=True, exist_ok=True)
        (single_plugin_dir / "SKILL.md").write_text("---\nname: single-skill\ndescription: Single plugin.\n---\n# single\n", encoding="utf-8")

        # 3. Core foundation skill in active skills
        core_dir = self.base_dir / "skills"
        self._create_mock_skill(core_dir, "skill-vault", description="Core skill.")

        exit_code = self.mgr.sync()
        self.assertEqual(exit_code, 0)

        # Verify vault contains ingested skills
        manifest = self.mgr.load_manifest()
        manifest_names = {m["name"] for m in manifest}
        self.assertIn("my-tool", manifest_names)
        self.assertIn("single-skill", manifest_names)

        # Verify core skill was kept active
        self.assertTrue((core_dir / "skill-vault" / "SKILL.md").exists())

        # Verify non-core plugin skills were pruned
        self.assertFalse(mock_tool_dir.exists())
        self.assertFalse((single_plugin_dir / "SKILL.md").exists())
        self.assertTrue(single_plugin_dir.exists())  # Directory preserved, contents emptied

    def test_sync_dry_run(self):
        """Test sync with --dry-run does not modify active files or vault."""
        plugins_dir = self.base_dir / "plugins"
        p_dir = plugins_dir / "dry-plugin" / "skills" / "dry-skill"
        self._create_mock_skill(p_dir.parent, "dry-skill", description="Dry run test.")

        exit_code = self.mgr.sync(dry_run=True)
        self.assertEqual(exit_code, 0)

        # File should still exist
        self.assertTrue((p_dir / "SKILL.md").exists())
        # Vault should not contain it
        manifest = self.mgr.load_manifest()
        manifest_names = {m["name"] for m in manifest}
        self.assertNotIn("dry-skill", manifest_names)

    def test_sync_cli(self):
        """Test sync command execution via subprocess CLI."""
        script_path = SCRIPT_DIR / "skill_vault.py"
        res = subprocess.run(
            [
                sys.executable,
                str(script_path),
                "--base-dir",
                str(self.base_dir),
                "sync",
                "--dry-run",
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(res.returncode, 0, f"CLI stderr: {res.stderr}")
        self.assertIn("SKILL VAULT AUTO-SYNC & INGEST", res.stdout)

    # --- 10. Universal Stack, Config & Dynamic Router Sync Tests ---

    def test_universal_category_inference_across_stacks(self):
        """Test infer_category across diverse ecosystems and explicit SKILL.md frontmatter category."""
        self.assertEqual(
            self.mgr.infer_category("react-nextjs-ui", "Builds accessible frontend components."),
            "Frontend & Web Development",
        )
        self.assertEqual(
            self.mgr.infer_category("fastapi-microservice", "REST API service with FastAPI."),
            "Backend & APIs",
        )
        self.assertEqual(
            self.mgr.infer_category("kubernetes-helm-deploy", "Deploys Helm charts to k8s."),
            "Cloud & DevOps",
        )
        self.assertEqual(
            self.mgr.infer_category("prisma-postgres-orm", "Manages Prisma schema and migrations."),
            "Databases & Storage",
        )
        self.assertEqual(
            self.mgr.infer_category("flutter-ios-widget", "Cross-platform mobile UI."),
            "Mobile & Cross-Platform",
        )
        self.assertEqual(
            self.mgr.infer_category("playwright-e2e-runner", "Automated browser tests."),
            "Testing, QA & Security",
        )
        self.assertEqual(
            self.mgr.infer_category("pytorch-rag-pipeline", "Embeddings and RAG training."),
            "AI, LLM & Machine Learning",
        )

        # Explicit category in SKILL.md frontmatter must override keyword heuristics
        pinned_dir = self.skills_dir / "custom-react-skill"
        pinned_dir.mkdir(parents=True, exist_ok=True)
        (pinned_dir / "SKILL.md").write_text(
            "---\nname: custom-react-skill\ncategory: Design Systems\ndescription: React UI tokens.\n---\n# Custom\n",
            encoding="utf-8",
        )
        self.assertEqual(
            self.mgr.infer_category("custom-react-skill", "React UI tokens."),
            "Design Systems",
        )

    def test_vault_config_customization(self):
        """Test vault_config.json creation, core skill updates, fingerprints, and custom category rules."""
        self.mgr.manage_config(init_config=True)
        self.assertTrue(self.mgr.config_file.exists())

        self.mgr.manage_config(
            add_core=["my-custom-core"],
            remove_core=["find-skills"],
            add_fingerprint=("Custom Blockchain", "*.sol"),
            add_category_rule=("Custom Payments", "stripe"),
        )

        core_set = self.mgr.get_core_skills()
        self.assertIn("my-custom-core", core_set)
        self.assertNotIn("find-skills", core_set)

        # Custom category rule must take precedence over built-in Backend rule for 'stripe'
        self.assertEqual(
            self.mgr.infer_category("stripe-webhook-handler", "Handles Stripe billing events."),
            "Custom Payments",
        )

        # Custom workspace fingerprint must be detected and mounted during optimize
        self._create_mock_skill(self.archive_dir / "skills", "solidity-auditor", "Audits smart contracts.")
        self.mgr.save_manifest([
            {
                "name": "solidity-auditor",
                "category": "Custom Blockchain",
                "original_path": "skills/solidity-auditor",
                "archived_path": "skill_archive/skills/solidity-auditor",
            }
        ])

        ws = tempfile.TemporaryDirectory()
        try:
            ws_path = Path(ws.name)
            (ws_path / "Token.sol").write_text("pragma solidity ^0.8.0;", encoding="utf-8")
            detected = self.mgr.detect_workspace_categories(ws_path)
            self.assertIn("Custom Blockchain", detected)

            self.mgr.optimize(workspace_path=ws_path)
            self.assertTrue((self.skills_dir / "solidity-auditor" / "SKILL.md").exists())
        finally:
            ws.cleanup()

    def test_frontmatter_core_skill_protection(self):
        """Test that skills marked with core: true in SKILL.md frontmatter are protected in sync and optimize."""
        pinned_dir = self.skills_dir / "company-policy-guard"
        pinned_dir.mkdir(parents=True, exist_ok=True)
        (pinned_dir / "SKILL.md").write_text(
            "---\nname: company-policy-guard\ncore: true\ndescription: Enforces org rules.\n---\n# Policy\n",
            encoding="utf-8",
        )
        self._create_mock_skill(self.skills_dir, "disposable-react-skill", "React component helper.")

        # 1. sync() should ingest both, prune disposable, and retain core-pinned skill
        exit_code = self.mgr.sync()
        self.assertEqual(exit_code, 0)
        self.assertTrue((self.skills_dir / "company-policy-guard" / "SKILL.md").exists())
        self.assertFalse((self.skills_dir / "disposable-react-skill").exists())

        # 2. optimize() on an empty generic workspace must also retain core-pinned skill
        self._create_mock_skill(self.skills_dir, "another-temp-skill", "Temporary skill.")
        ws = tempfile.TemporaryDirectory()
        try:
            self.mgr.optimize(workspace_path=Path(ws.name))
            self.assertTrue((self.skills_dir / "company-policy-guard" / "SKILL.md").exists())
            self.assertFalse((self.skills_dir / "another-temp-skill").exists())
        finally:
            ws.cleanup()

    def test_dynamic_router_skill_md_sync(self):
        """Test that reindex dynamically updates skill-vault SKILL.md frontmatter from archived categories."""
        router_dir = self.skills_dir / "skill-vault"
        router_dir.mkdir(parents=True, exist_ok=True)
        router_md = router_dir / "SKILL.md"
        router_md.write_text(
            "---\n"
            "name: skill-vault\n"
            "description: >-\n"
            "  Universal agent-agnostic skill router, lifecycle manager, and tiered storage engine for AI coding agents.\n"
            "---\n\n"
            "# Skill Vault\n",
            encoding="utf-8",
        )

        self._create_mock_skill(self.skills_dir, "react-ui", "Builds React interfaces.")
        self._create_mock_skill(self.skills_dir, "k8s-helper", "Manages Kubernetes clusters.")
        self.mgr.archive(name="react-ui", category="Frontend & Web Development")
        self.mgr.archive(name="k8s-helper", category="Cloud & DevOps")

        updated_text = router_md.read_text(encoding="utf-8")
        self.assertIn("2 specialized domain skill(s) in cold storage", updated_text)
        self.assertIn("(1) Cloud & DevOps (k8s-helper)", updated_text)
        self.assertIn("(2) Frontend & Web Development (react-ui)", updated_text)
        self.assertIn("# Skill Vault", updated_text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
