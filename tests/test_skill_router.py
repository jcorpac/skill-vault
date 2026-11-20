#!/usr/bin/env python3
"""Unit tests for scripts/skill_router.py (BM25 index, precision/recall, ambiguity, budgets, dedup)."""

from pathlib import Path
import json
import os
import sys
import tempfile
import unittest

SCRIPT_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import skill_router  # noqa: E402
from skill_vault import SkillVault  # noqa: E402


CORPUS_SPECS = [
    ("alloydb-omni-container", "AlloyDB", "Expert in AlloyDB Omni running in a container: start, stop, inspect container logs, and debug container memory leaks.", "v1", {"references/container-logs.md": "# Container Logs\nCheck docker logs."}),
    ("alloydb-omni-monitor", "AlloyDB", "Troubleshoot AlloyDB Omni production locks and transactions.", "v1", None),
    ("alloydb-omni-performance", "AlloyDB", "Analyze AlloyDB Omni query performance and execution plans.", "v1", None),
    ("alloydb-omni-replication", "AlloyDB", "Monitor AlloyDB Omni replication sync state across nodes.", "v1", None),
    ("alloydb-omni-health", "AlloyDB", "Audit AlloyDB Omni storage bloat and broken indexes.", "v1", None),
    ("alloydb-omni-kubernetes", "AlloyDB", "Manage AlloyDB Omni Operator DBClusters on Kubernetes.", "v1", None),
    ("cloud-sql-postgres-monitor", "Cloud SQL", "Optimize slow postgres query performance, inspect pg_stat_statements, and debug Cloud SQL PostgreSQL locks.", "v1", None),
    ("cloud-sql-mysql-admin", "Cloud SQL", "Administer Cloud SQL MySQL instances and debug replication lag.", "v1", None),
    ("bigquery-sql", "BigQuery & Data Warehouse", "Author and tune BigQuery SQL analytics queries and partitioned tables.", "v1", None),
    ("bigquery-ai-ml", "BigQuery & Data Warehouse", "Build BigQuery ML models and generative AI inference pipelines.", "v2", None),
    ("bigquery_ai_ml", "BigQuery & Data Warehouse", "Legacy BigQuery ML skill.", "v1", None),
    ("flutter-fix-layout-issues", "Mobile & Cross-Platform", "Fix Flutter widget RenderFlex overflow and responsive layout bugs.", "v1", None),
    ("dart-add-unit-test", "Mobile & Cross-Platform", "Write Dart unit tests and generate test mocks using mockito.", "v1", None),
    ("firebase_security_rules_auditor", "Firebase", "Audit firestore.rules and Firebase Storage security rules for access control leaks.", "v1", None),
    ("firestore_rules_creation", "Firebase", "Author Cloud Firestore security rules in firestore.rules.", "v1", None),
    ("mujoco-mjcf-author", "Robotics & MuJoCo", "Author and debug MuJoCo MJCF XML models, joints, actuators, and collision meshes.", "v1", None),
    ("fr3-duo-control", "Robotics & MuJoCo", "Control dual Franka FR3 robotics arms and parallel grippers.", "v1", None),
    ("alphafold_database_fetch_and_analyze", "Science & Biomedicine", "Fetch AlphaFold 3D protein structures in PDB/mmCIF format and analyze pLDDT scores.", "v1", None),
    ("pymol-visualization", "Science & Biomedicine", "Render publication protein structure figures in PyMOL.", "v1", None),
    ("chrome-devtools", "Chrome DevTools & Web Performance", "Inspect DOM, console, network, and performance traces in Chrome DevTools.", "v1", None),
    ("memory-leak-debugging", "Chrome DevTools & Web Performance", "Diagnose JavaScript heap snapshots and Chrome memory leaks.", "v1", None),
    ("debug-optimize-lcp", "Chrome DevTools & Web Performance", "Debug and optimize Largest Contentful Paint (LCP) Core Web Vitals in Chrome.", "v1", None),
    ("gmail", "Google Workspace", "Search, draft, and send Gmail messages via workspace tools.", "v1", None),
    ("gcalendar", "Google Workspace", "Schedule Google Calendar meetings and check attendee availability via gcalendar.", "v1", None),
    ("gcp_composer_troubleshooting", "GCP & Data Engineering", "Troubleshoot Cloud Composer Airflow DAG failures and task logs.", "v1", None),
    ("bigtable-basics", "GCP & Data Engineering", "Design Cloud Bigtable rowkey schemas and run cbt scans.", "v1", None),
    ("fastapi-microservice", "Backend & APIs", "Build REST API microservices using FastAPI and Python Pydantic models.", "v1", None),
]


class TestSkillRouter(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base_dir = Path(self.tmp.name).resolve()
        self.archive_dir = self.base_dir / "skill_archive"
        self.mgr = SkillVault(base_dir=str(self.base_dir))
        self.mgr.init()

        manifest = []
        for name, cat, desc, ver, extras in CORPUS_SPECS:
            sdir = self.archive_dir / "skills" / name
            sdir.mkdir(parents=True, exist_ok=True)
            (sdir / "SKILL.md").write_text(
                f"---\nname: {name}\nversion: {ver}\ndescription: {desc}\n---\n\n# {name}\n\n{desc}\n",
                encoding="utf-8",
            )
            if extras:
                for rel, body in extras.items():
                    fp = sdir / rel
                    fp.parent.mkdir(parents=True, exist_ok=True)
                    fp.write_text(body, encoding="utf-8")
            manifest.append({
                "name": name,
                "category": cat,
                "original_path": f"skills/{name}",
                "archived_path": f"skill_archive/skills/{name}",
            })

        # Add an oversized 25 KB skill to verify strict budget truncation
        oversized_dir = self.archive_dir / "skills" / "oversized-handbook-skill"
        oversized_dir.mkdir(parents=True, exist_ok=True)
        long_body = "\n".join(f"Section {i}: Detailed oversized handbook instruction line." for i in range(600))
        (oversized_dir / "SKILL.md").write_text(
            "---\nname: oversized-handbook-skill\ndescription: Exhaustive oversized handbook reference for stress testing.\n---\n\n"
            + long_body,
            encoding="utf-8",
        )
        manifest.append({
            "name": "oversized-handbook-skill",
            "category": "Testing, QA & Security",
            "original_path": "skills/oversized-handbook-skill",
            "archived_path": "skill_archive/skills/oversized-handbook-skill",
        })

        self.mgr.save_manifest(manifest)
        self.index = skill_router.build_search_index(
            archive_dir=self.archive_dir,
            manifest=manifest,
            base_dir=self.base_dir,
            resolve_path_fn=self.mgr.resolve_portable_path,
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_canonical_deduplication_prefers_newer_version(self):
        """Duplicate hyphen/underscore skills collapse to newest canonical entry in index."""
        names = {s["name"]: s for s in self.index["skills"]}
        self.assertIn("bigquery-ai-ml", names)
        self.assertNotIn("bigquery_ai_ml", names)
        self.assertIn("bigquery_ai_ml", names["bigquery-ai-ml"]["aliases"])

    def test_domain_prompt_recall_top2(self):
        """15 realistic domain queries must surface the exact target skill in top 1-2."""
        cases = [
            ("optimize slow postgres query", {"cloud-sql-postgres-monitor"}),
            ("alloydb omni container memory leak", {"alloydb-omni-container"}),
            ("fix flutter widget layout bug", {"flutter-fix-layout-issues"}),
            ("audit firestore.rules security", {"firebase_security_rules_auditor", "firestore_rules_creation"}),
            ("analyze protein pdb with alphafold", {"alphafold_database_fetch_and_analyze"}),
            ("debug mujoco mjcf joint", {"mujoco-mjcf-author"}),
            ("check chrome memory leak lcp", {"memory-leak-debugging", "debug-optimize-lcp"}),
            ("troubleshoot airflow composer dag failure", {"gcp_composer_troubleshooting"}),
            ("send gmail draft and schedule gcalendar meeting", {"gmail", "gcalendar"}),
            ("render protein structure in pymol", {"pymol-visualization"}),
            ("write dart unit test mocks", {"dart-add-unit-test"}),
            ("run bigtable rowkey scan", {"bigtable-basics"}),
            ("control fr3 robotics gripper", {"fr3-duo-control"}),
            ("debug mysql admin replication lag", {"cloud-sql-mysql-admin"}),
            ("run bigquery sql analytics query", {"bigquery-sql"}),
        ]
        for query, expected_any in cases:
            with self.subTest(query=query):
                res = skill_router.route_prompt(
                    index_data=self.index,
                    prompt=query,
                    archive_dir=self.archive_dir,
                    base_dir=self.base_dir,
                )
                top2 = [item["name"] for item in (res["inline"] + res["pointers"])[:2]]
                self.assertTrue(
                    any(name in expected_any for name in top2),
                    f"Expected one of {expected_any} in top 2 for {query!r}, got {top2} (candidates: {[(c['name'], c['score']) for c in res['candidates'][:4]]})",
                )
                self.assertGreater(res["estimated_tokens"], 0)

    def test_generic_prompts_inject_zero_tokens(self):
        """10 generic conversational/coding prompts must inject 0 skills and 0 tokens."""
        generic_prompts = [
            "Hi",
            "Hello, how are you?",
            "Refactor this Python function to be cleaner",
            "Write a git commit message",
            "Rename variable foo to bar",
            "Examine this project and create a plan",
            "What is 2+2?",
            "Thanks, looks good!",
            "Please help me understand this error in my code",
            "Create a clean helper method for parsing dates",
            "Help me write a clean helper script to parse JSON",
            "How much of this new system is dependent on my current setup? I want this to be able to be distributed as a skill and installed on other systems?",
            "Yes. My intention is for other users to be able to install the skill for use with the skills in their workspaces without being influenced by mine.",
            "Can you explain why this module is slow and suggest architectural improvements?",
            "Does this work on macOS and Linux without extra dependencies?",
            "What changes do we need to make this safe to publish to npm?",
        ]
        for prompt in generic_prompts:
            with self.subTest(prompt=prompt):
                res = skill_router.route_prompt(
                    index_data=self.index,
                    prompt=prompt,
                    archive_dir=self.archive_dir,
                    base_dir=self.base_dir,
                )
                self.assertEqual(res["inline"], [], f"Unexpected inline for {prompt!r}: {res['inline']}")
                self.assertEqual(res["pointers"], [], f"Unexpected pointers for {prompt!r}: {res['pointers']}")
                self.assertEqual(res["estimated_tokens"], 0)
                self.assertEqual(res["injection_text"], "")

        # Verify Chrome memory leak domain query still hits memory-leak-debugging cleanly
        res_mem = skill_router.route_prompt(
            index_data=self.index,
            prompt="Check why my memory leak is happening in Chrome",
            archive_dir=self.archive_dir,
            base_dir=self.base_dir,
        )
        self.assertTrue(res_mem["inline"])
        self.assertEqual(res_mem["inline"][0]["name"], "memory-leak-debugging")

    def test_broad_ambiguity_demotes_to_pointers(self):
        """Broad category query matching >=4 peers closely must demote to pointers instead of full inline."""
        res = skill_router.route_prompt(
            index_data=self.index,
            prompt="Tell me about AlloyDB",
            archive_dir=self.archive_dir,
            base_dir=self.base_dir,
        )
        self.assertTrue(res["ambiguous"])
        self.assertEqual(res["inline"], [])
        self.assertGreaterEqual(len(res["pointers"]), 2)
        self.assertIn("<available_vault_skills>", res["injection_text"])

    def test_workspace_soft_tie_breaker(self):
        """Workspace stack boosts matching skills without causing unrelated generic prompts to trigger."""
        res_domain = skill_router.route_prompt(
            index_data=self.index,
            prompt="renderflex overflow layout",
            archive_dir=self.archive_dir,
            base_dir=self.base_dir,
            workspace_categories={"Mobile & Cross-Platform"},
        )
        self.assertTrue(res_domain["inline"])
        self.assertEqual(res_domain["inline"][0]["name"], "flutter-fix-layout-issues")

        # Unrelated prompt in same Flutter workspace must still inject 0 tokens
        res_generic = skill_router.route_prompt(
            index_data=self.index,
            prompt="Rename variable foo to bar",
            archive_dir=self.archive_dir,
            base_dir=self.base_dir,
            workspace_categories={"Mobile & Cross-Platform"},
        )
        self.assertEqual(res_generic["estimated_tokens"], 0)

    def test_oversized_skill_respects_char_budget(self):
        """Oversized SKILL.md is cleanly truncated within max_single_skill_chars and max_inline_chars."""
        res = skill_router.route_prompt(
            index_data=self.index,
            prompt="Run oversized-handbook-skill stress test",
            archive_dir=self.archive_dir,
            base_dir=self.base_dir,
        )
        self.assertEqual(len(res["inline"]), 1)
        self.assertTrue(res["inline"][0]["truncated"])
        self.assertLessEqual(len(res["injection_text"]), 10500)
        self.assertIn("load_skill", res["inline"][0]["content"])

    def test_short_query_with_category_does_not_dump_category(self):
        """Non-empty short/stopword query inside a category returns [] instead of dumping all category skills."""
        empty_res = skill_router.search_index(self.index, query="", category="AlloyDB", limit=None)
        self.assertEqual(len(empty_res), 6)
        short_res = skill_router.search_index(self.index, query="zx", category="AlloyDB", limit=None)
        self.assertEqual(short_res, [])

    def test_load_or_build_index_does_not_downgrade_newer_schema(self):
        """load_or_build_index accepts schema_version >= INDEX_SCHEMA_VERSION without overwriting it."""
        index_path = self.archive_dir / "search_index.json"
        data = json.loads(index_path.read_text(encoding="utf-8"))
        newer_ver = skill_router.INDEX_SCHEMA_VERSION + 1
        data["schema_version"] = newer_ver
        index_path.write_text(json.dumps(data), encoding="utf-8")

        loaded = skill_router.load_or_build_index(archive_dir=self.archive_dir, base_dir=self.base_dir)
        self.assertEqual(loaded["schema_version"], newer_ver)
        on_disk = json.loads(index_path.read_text(encoding="utf-8"))
        self.assertEqual(on_disk["schema_version"], newer_ver)

    def test_canonical_dedup_separator_stripped_and_nested_metadata_version(self):
        """build_search_index collapses separator-stripped duplicates and respects nested metadata.version."""
        tmp = tempfile.TemporaryDirectory()
        try:
            base = Path(tmp.name).resolve()
            arch = base / "skill_archive"
            mgr = SkillVault(base_dir=str(base))
            mgr.init()

            # 1. Separator-stripped: science_skills_common (older) vs scienceskillscommon (newer)
            d1 = arch / "skills" / "science_skills_common"
            d2 = arch / "skills" / "scienceskillscommon"
            d1.mkdir(parents=True, exist_ok=True)
            d2.mkdir(parents=True, exist_ok=True)
            md1 = d1 / "SKILL.md"
            md2 = d2 / "SKILL.md"
            md1.write_text("---\nname: science_skills_common\ndescription: Common science helpers.\n---\n# Old\n", encoding="utf-8")
            md2.write_text("---\nname: scienceskillscommon\ndescription: Common science helpers.\n---\n# New\n", encoding="utf-8")
            t_base = md1.stat().st_mtime - 20
            os.utime(md1, (t_base, t_base))
            os.utime(md2, (t_base + 10, t_base + 10))

            # 2. Nested metadata.version: gcp_spark (v14, newer mtime) vs gcp-spark (v24, older mtime)
            d3 = arch / "skills" / "gcp_spark"
            d4 = arch / "skills" / "gcp-spark"
            d3.mkdir(parents=True, exist_ok=True)
            d4.mkdir(parents=True, exist_ok=True)
            md3 = d3 / "SKILL.md"
            md4 = d4 / "SKILL.md"
            md3.write_text("---\nname: gcp-spark\nmetadata:\n  version: v14\ndescription: Spark v14.\n---\n# Spark 14\n", encoding="utf-8")
            md4.write_text("---\nname: gcp-spark\nmetadata:\n  version: v24\ndescription: Spark v24.\n---\n# Spark 24\n", encoding="utf-8")
            os.utime(md4, (t_base, t_base))
            os.utime(md3, (t_base + 10, t_base + 10))

            manifest = [
                {"name": "science_skills_common", "category": "Science & Biomedicine", "original_path": "skills/science_skills_common", "archived_path": "skill_archive/skills/science_skills_common"},
                {"name": "scienceskillscommon", "category": "Science & Biomedicine", "original_path": "skills/scienceskillscommon", "archived_path": "skill_archive/skills/scienceskillscommon"},
                {"name": "gcp_spark", "category": "GCP & Data Engineering", "original_path": "skills/gcp_spark", "archived_path": "skill_archive/skills/gcp_spark"},
                {"name": "gcp-spark", "category": "GCP & Data Engineering", "original_path": "skills/gcp-spark", "archived_path": "skill_archive/skills/gcp-spark"},
            ]
            mgr.save_manifest(manifest)
            idx = skill_router.build_search_index(archive_dir=arch, manifest=manifest, base_dir=base, resolve_path_fn=mgr.resolve_portable_path)
            by_name = {s["name"]: s for s in idx["skills"]}

            self.assertEqual(len(by_name), 2)
            self.assertIn("scienceskillscommon", by_name)
            self.assertCountEqual(by_name["scienceskillscommon"]["aliases"], ["science_skills_common", "scienceskillscommon"])
            self.assertIn("gcp-spark", by_name)
            self.assertEqual(by_name["gcp-spark"]["version_tuple"], [24])
            self.assertCountEqual(by_name["gcp-spark"]["aliases"], ["gcp_spark", "gcp-spark"])
        finally:
            tmp.cleanup()


if __name__ == "__main__":
    unittest.main(verbosity=2)
