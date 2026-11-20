#!/usr/bin/env python3
"""Integration tests for hook_runner.py, mcp_server.py, and v2.0 CLI commands."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

SCRIPT_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from skill_vault import SkillVault  # noqa: E402
import mcp_server  # noqa: E402
import skill_router  # noqa: E402


class TestHooksAndMCP(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base_dir = Path(self.tmp.name).resolve()
        self.skills_dir = self.base_dir / "skills"
        self.archive_dir = self.base_dir / "skill_archive"
        self.mgr = SkillVault(base_dir=str(self.base_dir))
        self.mgr.init()

        # Seed two domain skills in L2
        self._add_archived_skill(
            "cloud-sql-postgres-monitor",
            "Cloud SQL",
            "Optimize slow PostgreSQL queries and analyze pg_stat_statements locks.",
            version="1.0.0",
            extras={"references/queries.md": "# Slow Query Recipes\nSELECT * FROM pg_stat_activity;"},
        )
        self._add_archived_skill(
            "mujoco-mjcf-author",
            "Robotics & MuJoCo",
            "Author and validate MuJoCo MJCF XML joints, actuators, and collision meshes.",
            version="1.0.0",
        )
        self.mgr.reindex()

    def tearDown(self):
        self.tmp.cleanup()

    def _add_archived_skill(self, name, category, description, version="1.0", extras=None):
        sdir = self.archive_dir / "skills" / name
        sdir.mkdir(parents=True, exist_ok=True)
        (sdir / "SKILL.md").write_text(
            f"---\nname: {name}\nversion: {version}\ndescription: {description}\n---\n\n# {name}\n\n{description}\n",
            encoding="utf-8",
        )
        if extras:
            for rel, body in extras.items():
                fp = sdir / rel
                fp.parent.mkdir(parents=True, exist_ok=True)
                fp.write_text(body, encoding="utf-8")
        manifest = self.mgr.load_manifest()
        manifest.append({
            "name": name,
            "category": category,
            "original_path": f"skills/{name}",
            "archived_path": f"skill_archive/skills/{name}",
        })
        self.mgr.save_manifest(manifest)

    def _run_hook(self, payload_str, event=None, harness="auto"):
        cmd = [sys.executable, str(SCRIPT_DIR / "hook_runner.py"), "--base-dir", str(self.base_dir), "--harness", harness]
        if event:
            cmd.extend(["--event", event])
        res = subprocess.run(cmd, input=payload_str, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(res.returncode, 0, f"Hook stderr: {res.stderr}")
        return json.loads(res.stdout)

    # --- Antigravity PreInvocation Tests ---

    def test_antigravity_preinvocation_injection_dedup_and_shortcircuit(self):
        """Test PreInvocation injects on domain turn, short-circuits repeat invocation, and skips re-injection."""
        # 1. Turn 1, invocation 1: domain prompt -> injects cloud-sql-postgres-monitor
        out1 = self._run_hook(json.dumps({
            "hookEventName": "PreInvocation",
            "conversationId": "conv-abc",
            "invocationNum": 1,
            "initialNumSteps": 2,
            "lastUserInput": "Help me optimize a slow postgres query in Cloud SQL",
            "workspacePaths": [str(self.base_dir)],
        }))
        self.assertIn("injectSteps", out1)
        sys_msg = out1["injectSteps"][0]["systemMessage"]["systemMessage"]
        self.assertIn("cloud-sql-postgres-monitor", sys_msg)
        self.assertIn("references/queries.md", sys_msg)
        self.assertEqual(out1["injectSteps"][0]["systemMessage"]["metadata"], {})

        # 2. Turn 1, invocation 2 (tool loop on same input) -> short-circuits to {}
        out2 = self._run_hook(json.dumps({
            "hookEventName": "PreInvocation",
            "conversationId": "conv-abc",
            "invocationNum": 2,
            "initialNumSteps": 2,
            "lastUserInput": "Help me optimize a slow postgres query in Cloud SQL",
            "workspacePaths": [str(self.base_dir)],
        }))
        self.assertEqual(out2, {})

        # 3. Turn 2, same conversation, same domain -> already injected skill is deduplicated out
        out3 = self._run_hook(json.dumps({
            "hookEventName": "PreInvocation",
            "conversationId": "conv-abc",
            "invocationNum": 1,
            "initialNumSteps": 8,
            "lastUserInput": "How do I check pg_stat_statements for that slow postgres query?",
            "workspacePaths": [str(self.base_dir)],
        }))
        self.assertEqual(out3, {})

        # 4. Separate conversationId -> gets fresh injection
        out4 = self._run_hook(json.dumps({
            "hookEventName": "PreInvocation",
            "conversationId": "conv-other",
            "invocationNum": 1,
            "initialNumSteps": 1,
            "lastUserInput": "Optimize slow postgres query",
            "workspacePaths": [str(self.base_dir)],
        }))
        self.assertIn("injectSteps", out4)

    def test_protojson_zero_indexed_repeat_and_pointer_dedup(self):
        """Protojson omits invocationNum=0 on first call; repeat call and pointer re-surfacing must dedup."""
        # Turn 1, call 0 (invocationNum omitted as in protojson)
        p_txt = "Debug mujoco mjcf joints"
        out0 = self._run_hook(json.dumps({
            "hookEventName": "PreInvocation",
            "conversationId": "conv-proto",
            "initialNumSteps": 1,
            "lastUserInput": p_txt,
        }))
        self.assertIn("injectSteps", out0)

        # Turn 1, call 1 (invocationNum=1, identical prompt after tool call) -> must short-circuit!
        out1 = self._run_hook(json.dumps({
            "hookEventName": "PreInvocation",
            "conversationId": "conv-proto",
            "invocationNum": 1,
            "initialNumSteps": 1,
            "lastUserInput": p_txt,
        }))
        self.assertEqual(out1, {})

        # Cross-turn pointer dedup: switch to pointer mode on fresh conv
        self.mgr.manage_config(set_routing=[["mode", "pointer"]])
        ptr1 = self._run_hook(json.dumps({
            "hookEventName": "PreInvocation",
            "conversationId": "conv-ptr",
            "lastUserInput": "Optimize slow postgres query",
        }))
        self.assertIn("injectSteps", ptr1)
        self.assertIn("cloud-sql-postgres-monitor", ptr1["injectSteps"][0]["systemMessage"]["systemMessage"])

        ptr2 = self._run_hook(json.dumps({
            "hookEventName": "PreInvocation",
            "conversationId": "conv-ptr",
            "lastUserInput": "Check pg_stat_statements for postgres query",
        }))
        self.assertEqual(ptr2, {})

    def test_antigravity_generic_and_corrupt_inputs_fail_safe(self):
        """Generic prompts and corrupt stdin JSON always return {} with exit code 0."""
        out_generic = self._run_hook(json.dumps({
            "hookEventName": "PreInvocation",
            "conversationId": "conv-gen",
            "invocationNum": 1,
            "lastUserInput": "Refactor this Python function to be cleaner",
        }))
        self.assertEqual(out_generic, {})

        out_corrupt = self._run_hook("{this is not valid json!!")
        self.assertEqual(out_corrupt, {})

        # Missing archive fails safe
        empty_dir = Path(self.tmp.name) / "no_archive"
        empty_dir.mkdir(exist_ok=True)
        res = subprocess.run(
            [sys.executable, str(SCRIPT_DIR / "hook_runner.py"), "--base-dir", str(empty_dir)],
            input=json.dumps({"hookEventName": "PreInvocation", "lastUserInput": "alloydb"}),
            capture_output=True,
            text=True,
        )
        self.assertEqual(res.returncode, 0)
        self.assertEqual(json.loads(res.stdout), {})

    def test_antigravity_ui_notice_option(self):
        """Setting show_ui_notice=true adds user_markdown note without breaking model message."""
        self.mgr.manage_config(set_routing=[["show_ui_notice", "true"]])
        out = self._run_hook(json.dumps({
            "hookEventName": "PreInvocation",
            "conversationId": "conv-ui",
            "invocationNum": 1,
            "lastUserInput": "Debug mujoco mjcf joints",
        }))
        self.assertIn("injectSteps", out)
        meta = out["injectSteps"][0]["systemMessage"]["metadata"]
        self.assertIn("user_markdown", meta)
        self.assertIn("mujoco-mjcf-author", meta["user_markdown"])

    # --- SessionStart + Hook Dependency Protection Tests ---

    def test_session_start_sync_and_hook_dependency_protection(self):
        """SessionStart ingests new plugin skills, prunes non-core, protects hook deps, and outputs {}."""
        plugins_dir = self.base_dir / "plugins"
        dak_dir = plugins_dir / "data-agent-kit-plugin"
        (dak_dir / "skills" / "dak-setup" / "scripts").mkdir(parents=True, exist_ok=True)
        (dak_dir / "skills" / "dak-setup" / "SKILL.md").write_text(
            "---\nname: dak-setup\ndescription: Setup hook helper.\n---\n# dak-setup\n", encoding="utf-8"
        )
        (dak_dir / "skills" / "dak-setup" / "scripts" / "dak-setup.js").write_text("// hook", encoding="utf-8")
        (dak_dir / "hooks.json").write_text(
            json.dumps({"dak-sync": {"SessionStart": [{"type": "command", "command": "node skills/dak-setup/scripts/dak-setup.js sync"}]}}),
            encoding="utf-8",
        )

        # Unprotected plugin skill
        extra_skill = plugins_dir / "data-agent-kit-plugin" / "skills" / "bigquery-extra"
        extra_skill.mkdir(parents=True, exist_ok=True)
        (extra_skill / "SKILL.md").write_text(
            "---\nname: bigquery-extra\ndescription: BigQuery helper.\n---\n# bq\n", encoding="utf-8"
        )

        out = self._run_hook(json.dumps({
            "hookEventName": "SessionStart",
            "conversationId": "conv-ss",
            "workspacePaths": [str(self.base_dir)],
        }))
        self.assertEqual(out, {})

        # Non-core skill was ingested into archive and pruned from active L1
        self.assertFalse(extra_skill.exists())
        self.assertTrue((self.archive_dir / "skills" / "bigquery-extra" / "SKILL.md").exists())
        # Hook-referenced dak-setup was preserved on disk!
        self.assertTrue((dak_dir / "skills" / "dak-setup" / "scripts" / "dak-setup.js").exists())
        # Pre-built search_index.json was updated
        self.assertTrue((self.archive_dir / "search_index.json").exists())

    # --- Claude Code & Gemini CLI Harnesses ---

    def test_claude_and_gemini_cli_hook_formats(self):
        """Claude Code UserPromptSubmit and Gemini CLI BeforeAgent return native hookSpecificOutput."""
        claude_out = self._run_hook(json.dumps({
            "hook_event_name": "UserPromptSubmit",
            "session_id": "claude-1",
            "prompt": "Validate mujoco mjcf joint limits",
            "cwd": str(self.base_dir),
        }))
        self.assertEqual(claude_out["hookSpecificOutput"]["hookEventName"], "UserPromptSubmit")
        self.assertIn("mujoco-mjcf-author", claude_out["hookSpecificOutput"]["additionalContext"])

        gemini_out = self._run_hook(json.dumps({
            "hook_event_name": "BeforeAgent",
            "session_id": "gem-1",
            "prompt": "Validate mujoco mjcf joint limits",
            "cwd": str(self.base_dir),
        }))
        self.assertEqual(gemini_out["hookSpecificOutput"]["hookEventName"], "BeforeAgent")
        self.assertIn("mujoco-mjcf-author", gemini_out["hookSpecificOutput"]["additionalContext"])

    # --- Read-Only MCP Stdio Server Tests ---

    def _communicate_mcp_newline(self, messages, base_dir=None):
        stdin_payload = "".join(json.dumps(m) + "\n" for m in messages).encode("utf-8")
        proc = subprocess.run(
            [sys.executable, str(SCRIPT_DIR / "mcp_server.py"), "--base-dir", str(base_dir or self.base_dir)],
            input=stdin_payload,
            capture_output=True,
        )
        self.assertEqual(proc.returncode, 0, f"MCP stderr: {proc.stderr.decode('utf-8', errors='replace')}")
        lines = [ln for ln in proc.stdout.decode("utf-8").splitlines() if ln.strip()]
        return [json.loads(ln) for ln in lines]

    def _communicate_mcp_content_length(self, messages):
        chunks = []
        for m in messages:
            body = json.dumps(m).encode("utf-8")
            chunks.append(f"Content-Length: {len(body)}\r\n\r\n".encode("ascii") + body)
        proc = subprocess.run(
            [sys.executable, str(SCRIPT_DIR / "mcp_server.py"), "--base-dir", str(self.base_dir)],
            input=b"".join(chunks),
            capture_output=True,
        )
        self.assertEqual(proc.returncode, 0, f"MCP stderr: {proc.stderr.decode('utf-8', errors='replace')}")
        raw = proc.stdout
        responses = []
        idx = 0
        while idx < len(raw):
            hdr_end = raw.find(b"\r\n\r\n", idx)
            self.assertNotEqual(hdr_end, -1, f"Missing Content-Length header end in {raw[idx:]!r}")
            hdr = raw[idx:hdr_end].decode("ascii")
            clen = int(hdr.split(":", 1)[1].strip())
            body_start = hdr_end + 4
            body = raw[body_start : body_start + clen]
            responses.append(json.loads(body.decode("utf-8")))
            idx = body_start + clen
        return responses

    def test_mcp_server_newline_and_content_length(self):
        """Test initialize, tools/list, search_skills, load_skill, companion files, and traversal defense."""
        requests = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05"}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "search_skills", "arguments": {"query": ""}}},
            {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "search_skills", "arguments": {"query": "postgres slow query"}}},
            {"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "load_skill", "arguments": {"name": "cloud-sql-postgres-monitor"}}},
            {"jsonrpc": "2.0", "id": 6, "method": "tools/call", "params": {"name": "load_skill", "arguments": {"name": "cloud-sql-postgres-monitor", "file": "references/queries.md"}}},
            {"jsonrpc": "2.0", "id": 7, "method": "tools/call", "params": {"name": "load_skill", "arguments": {"name": "cloud-sql-postgres-monitor", "file": "../mujoco-mjcf-author/SKILL.md"}}},
        ]

        for label, runner in [("newline", self._communicate_mcp_newline), ("content_length", self._communicate_mcp_content_length)]:
            with self.subTest(framing=label):
                resps = runner(requests)
                # Notification produces no response -> 7 responses expected
                self.assertEqual(len(resps), 7)
                by_id = {r["id"]: r for r in resps}

                # 1. initialize
                self.assertEqual(by_id[1]["result"]["serverInfo"]["name"], "skill-vault")
                # 2. tools/list
                tools = by_id[2]["result"]["tools"]
                self.assertEqual([t["name"] for t in tools], ["search_skills", "list_skills", "load_skill"])
                for t in tools:
                    self.assertTrue(t["annotations"]["readOnlyHint"])
                    self.assertFalse(t["annotations"]["destructiveHint"])
                # 3. search_skills empty query -> categories summary
                cat_data = json.loads(by_id[3]["result"]["content"][0]["text"])
                self.assertEqual(cat_data["total_skills"], 2)
                # 4. search_skills query
                srch_data = json.loads(by_id[4]["result"]["content"][0]["text"])
                self.assertEqual(srch_data["results"][0]["name"], "cloud-sql-postgres-monitor")
                # 5. load_skill main SKILL.md
                self.assertFalse(by_id[5]["result"]["isError"])
                self.assertIn("pg_stat_statements", by_id[5]["result"]["content"][0]["text"])
                # 6. load_skill companion file
                self.assertFalse(by_id[6]["result"]["isError"])
                self.assertIn("pg_stat_activity", by_id[6]["result"]["content"][0]["text"])
                # 7. path traversal rejected
                self.assertTrue(by_id[7]["result"]["isError"])
                self.assertIn("traversal", by_id[7]["result"]["content"][0]["text"].lower())

    def test_mcp_list_skills_and_search_pagination(self):
        """list_skills returns >25 skills in one compact call; search_skills supports offset pagination."""
        list_base = Path(self.tmp.name) / "list_vault"
        list_base.mkdir(parents=True, exist_ok=True)
        list_mgr = SkillVault(base_dir=str(list_base))
        list_mgr.init()
        manifest = []
        for i in range(30):
            name = f"big-skill-{i:02d}"
            sdir = list_base / "skill_archive" / "skills" / name
            sdir.mkdir(parents=True, exist_ok=True)
            (sdir / "SKILL.md").write_text(
                f"---\nname: {name}\nversion: 1.0\ndescription: Description for {name}.\n---\n\n# {name}\n",
                encoding="utf-8",
            )
            manifest.append({
                "name": name,
                "category": "Big Category",
                "original_path": f"skills/{name}",
                "archived_path": f"skill_archive/skills/{name}",
            })
        for i in range(2):
            name = f"small-skill-{i:02d}"
            sdir = list_base / "skill_archive" / "skills" / name
            sdir.mkdir(parents=True, exist_ok=True)
            (sdir / "SKILL.md").write_text(
                f"---\nname: {name}\nversion: 1.0\ndescription: Description for {name}.\n---\n\n# {name}\n",
                encoding="utf-8",
            )
            manifest.append({
                "name": name,
                "category": "Small Category",
                "original_path": f"skills/{name}",
                "archived_path": f"skill_archive/skills/{name}",
            })
        list_mgr.save_manifest(manifest)
        list_mgr.reindex()

        requests = [
            {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "list_skills", "arguments": {}}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "list_skills", "arguments": {"category": "big category", "include_descriptions": True}}},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "list_skills", "arguments": {"category": "NoSuchCategory"}}},
            {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "search_skills", "arguments": {"query": "", "category": "Big Category", "limit": 25, "offset": 25}}},
        ]
        resps = self._communicate_mcp_newline(requests, base_dir=list_base)
        by_id = {r["id"]: json.loads(r["result"]["content"][0]["text"]) for r in resps}

        self.assertEqual(by_id[1]["total_skills"], 32)
        self.assertEqual(by_id[1]["category_count"], 2)
        big_cat = next(c for c in by_id[1]["categories"] if c["category"] == "Big Category")
        self.assertEqual(big_cat["count"], 30)
        self.assertEqual(len(big_cat["skills"]), 30)
        self.assertIsInstance(big_cat["skills"][0], str)

        self.assertEqual(by_id[2]["total_skills"], 30)
        self.assertEqual(len(by_id[2]["categories"][0]["skills"]), 30)
        self.assertIsInstance(by_id[2]["categories"][0]["skills"][0], dict)
        self.assertIn("name", by_id[2]["categories"][0]["skills"][0])
        self.assertIn("description", by_id[2]["categories"][0]["skills"][0])

        self.assertEqual(by_id[3]["total_skills"], 0)
        self.assertEqual(by_id[3]["available_categories"], ["Big Category", "Small Category"])

        self.assertEqual(by_id[4]["total_matches"], 30)
        self.assertEqual(by_id[4]["offset"], 25)
        self.assertEqual(by_id[4]["count"], 5)

    def test_mcp_short_query_and_fallback_ranking(self):
        """Short queries like 'uv' match accurately, unknown short queries return 0, and fallback ranks name > description."""
        self._add_archived_skill("uv", "Science & Biomedicine", "Install uv Python package manager.")
        self._add_archived_skill("alpha-protein", "Science & Biomedicine", "Analyze proteins with no short token.")
        self._add_archived_skill("xy-tool", "Science & Biomedicine", "Helper tool.")
        self._add_archived_skill("beta-tool", "Science & Biomedicine", "Contains proxy fragment.")
        self.mgr.reindex()

        requests = [
            {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "search_skills", "arguments": {"query": "uv", "category": "Science & Biomedicine"}}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "search_skills", "arguments": {"query": "zx", "category": "Science & Biomedicine"}}},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "search_skills", "arguments": {"query": "xy", "category": "Science & Biomedicine"}}},
        ]
        resps = self._communicate_mcp_newline(requests)
        by_id = {r["id"]: json.loads(r["result"]["content"][0]["text"]) for r in resps}

        uv_names = [r["name"] for r in by_id[1]["results"]]
        self.assertGreaterEqual(len(uv_names), 1)
        self.assertEqual(uv_names[0], "uv")
        self.assertNotIn("alpha-protein", uv_names)

        self.assertEqual(by_id[2]["count"], 0)
        self.assertEqual(by_id[2]["results"], [])

        xy_names = [r["name"] for r in by_id[3]["results"]]
        self.assertEqual(xy_names, ["xy-tool", "beta-tool"])

    def test_mcp_index_memory_cache_and_invalidation(self):
        """_load_index caches parsed index in memory and invalidates when search_index.json changes on disk."""
        mcp_server.clear_index_cache()
        orig_loader = skill_router.load_or_build_index
        with mock.patch.object(skill_router, "load_or_build_index", wraps=orig_loader) as spy:
            d1 = mcp_server._load_index(self.base_dir, self.archive_dir)
            d2 = mcp_server._load_index(self.base_dir, self.archive_dir)
            self.assertEqual(spy.call_count, 1)
            self.assertEqual(len(d1["skills"]), 2)
            self.assertIs(d1, d2)

            self._add_archived_skill("bigquery-sql", "BigQuery & Data Warehouse", "Optimize BigQuery SQL queries.")
            self.mgr.reindex()

            d3 = mcp_server._load_index(self.base_dir, self.archive_dir)
            self.assertEqual(spy.call_count, 2)
            self.assertEqual(len(d3["skills"]), 3)
        mcp_server.clear_index_cache()

    # --- CLI Commands: recategorize --auto, dedupe, route, stats, setup -> uninstall ---

    def test_recategorize_auto_and_dedupe(self):
        """Test recategorize --auto and dedupe consolidation."""
        self._add_archived_skill("gmail", "General & Utility Skills", "Send emails via Gmail.")
        self._add_archived_skill("firebase_auth_basics", "General & Utility Skills", "Firebase authentication setup.")
        self._add_archived_skill("bigquery-sql", "BigQuery & Data Warehouse", "BigQuery SQL v2.", version="v2")
        self._add_archived_skill("bigquery_sql", "BigQuery & Data Warehouse", "BigQuery SQL v1.", version="v1")

        self.assertEqual(self.mgr.recategorize(auto=True), 0)
        manifest_map = {m["name"]: m["category"] for m in self.mgr.load_manifest()}
        self.assertEqual(manifest_map["gmail"], "Google Workspace")
        self.assertEqual(manifest_map["firebase_auth_basics"], "Firebase")

        self.assertEqual(self.mgr.dedupe(), 0)
        manifest_after = {m["name"] for m in self.mgr.load_manifest()}
        self.assertIn("bigquery-sql", manifest_after)
        self.assertNotIn("bigquery_sql", manifest_after)
        self.assertFalse((self.archive_dir / "skills" / "bigquery_sql").exists())

    def test_dedupe_extended_matching_and_newer_version_selection(self):
        """dedupe catches separator-stripped, frontmatter-name, identical-content, and nested metadata.version duplicates."""
        dedupe_base = Path(self.tmp.name) / "dedupe_vault"
        dedupe_base.mkdir(parents=True, exist_ok=True)
        dmgr = SkillVault(base_dir=str(dedupe_base))
        dmgr.init()
        arch_skills = dedupe_base / "skill_archive" / "skills"

        def _write_skill(folder, body, mtime_val):
            sdir = arch_skills / folder
            sdir.mkdir(parents=True, exist_ok=True)
            md = sdir / "SKILL.md"
            md.write_text(body, encoding="utf-8")
            os.utime(md, (mtime_val, mtime_val))
            return {
                "name": folder,
                "category": "Testing",
                "original_path": f"skills/{folder}",
                "archived_path": f"skill_archive/skills/{folder}",
            }

        t0 = 1760000000.0
        manifest = [
            # 1. Separator-stripped (older vs newer mtime)
            _write_skill("science_skills_common", "---\nname: science_skills_common\ndescription: Common package.\n---\n# Old\n", t0),
            _write_skill("scienceskillscommon", "---\nname: scienceskillscommon\ndescription: Common package.\n---\n# New\n", t0 + 10),
            # 2. Frontmatter name alias across different folder names
            _write_skill("legacy-bq-copy", "---\nname: bigquery-helper\nversion: 1.0\ndescription: Old helper.\n---\n# Old\n", t0 + 20),
            _write_skill("modern-bq", "---\nname: bigquery-helper\nversion: 2.0\ndescription: New helper.\n---\n# New\n", t0),
            # 3. Identical SKILL.md content hash (>= 64 bytes, no frontmatter name)
            _write_skill("notes-old", "# Shared Notes\nThis identical reference body is well over sixty-four bytes in length for deduplication.\n", t0),
            _write_skill("notes-new", "# Shared Notes\nThis identical reference body is well over sixty-four bytes in length for deduplication.\n", t0 + 10),
            # 4. Nested metadata.version (v24 older mtime vs v14 newer mtime)
            _write_skill("gcp_spark", "---\nname: gcp-spark\nmetadata:\n  version: v14\ndescription: Spark v14.\n---\n# v14\n", t0 + 20),
            _write_skill("gcp-spark", "---\nname: gcp-spark\nmetadata:\n  version: v24\ndescription: Spark v24.\n---\n# v24\n", t0),
        ]
        dmgr.save_manifest(manifest)
        dmgr.reindex()

        # Dry run preserves all 8 folders
        self.assertEqual(dmgr.dedupe(dry_run=True), 0)
        self.assertEqual(len(dmgr.load_manifest()), 8)
        for item in manifest:
            self.assertTrue((arch_skills / item["name"] / "SKILL.md").exists())

        # Live dedupe keeps only the 4 newer winners
        self.assertEqual(dmgr.dedupe(dry_run=False), 0)
        kept = {m["name"] for m in dmgr.load_manifest()}
        self.assertEqual(kept, {"scienceskillscommon", "modern-bq", "notes-new", "gcp-spark"})
        for winner in kept:
            self.assertTrue((arch_skills / winner / "SKILL.md").exists())
        for loser in ("science_skills_common", "legacy-bq-copy", "notes-old", "gcp_spark"):
            self.assertFalse((arch_skills / loser).exists())

        idx = json.loads((dedupe_base / "skill_archive" / "search_index.json").read_text(encoding="utf-8"))
        self.assertEqual(len(idx["skills"]), 4)

    def test_route_stats_and_setup_uninstall_roundtrip(self):
        """Test sandboxed setup -> PreInvocation -> stats -> route -> uninstall cleanup."""
        plugin_target = self.base_dir / "plugins" / "skill-vault"

        # Dry run first must not create plugin directory
        self.assertEqual(
            self.mgr.setup(agent="antigravity", dry_run=True, target_dir=str(plugin_target)),
            0,
        )
        self.assertFalse(plugin_target.exists())

        # Real setup into sandbox
        self.assertEqual(
            self.mgr.setup(agent="antigravity", dry_run=False, target_dir=str(plugin_target)),
            0,
        )
        self.assertTrue((plugin_target / "plugin.json").exists())
        self.assertTrue((plugin_target / "hooks.json").exists())
        self.assertTrue((plugin_target / "mcp_config.json").exists())
        self.assertTrue((plugin_target / "scripts" / "hook_runner.py").exists())
        self.assertTrue((plugin_target / "skills" / "skill-vault" / "SKILL.md").exists())
        self.assertLess(
            len((plugin_target / "skills" / "skill-vault" / "SKILL.md").read_text(encoding="utf-8")),
            3000,
        )

        # Test route & stats
        self.assertEqual(self.mgr.route("optimize slow postgres query"), 0)
        self._run_hook(json.dumps({
            "hookEventName": "PreInvocation",
            "conversationId": "conv-stats",
            "invocationNum": 1,
            "lastUserInput": "optimize slow postgres query",
        }))
        self.assertEqual(self.mgr.stats(), 0)

        # Sandboxed Claude setup check
        claude_cfg = self.base_dir / ".claude" / "settings.json"
        self.assertEqual(
            self.mgr.setup(agent="claude", scope="workspace", target_dir=str(claude_cfg)),
            0,
        )
        claude_data = json.loads(claude_cfg.read_text(encoding="utf-8"))
        self.assertIn("skill-vault", claude_data["mcpServers"])
        self.assertIn("UserPromptSubmit", claude_data["hooks"])

        # Uninstall restores L2 skills to L1 and cleans plugin + Claude wiring
        self.assertEqual(self.mgr.uninstall(), 0)
        self.assertFalse(plugin_target.exists())
        self.assertTrue((self.skills_dir / "cloud-sql-postgres-monitor" / "SKILL.md").exists())
        claude_after = json.loads(claude_cfg.read_text(encoding="utf-8"))
        self.assertNotIn("skill-vault", claude_after.get("mcpServers", {}))
        self.assertNotIn("UserPromptSubmit", claude_after.get("hooks", {}))

    def test_v2_cli_subcommands(self):
        """Test route, recategorize --auto, dedupe --dry-run, and stats via subprocess CLI."""
        cli = [sys.executable, str(SCRIPT_DIR / "skill_vault.py"), "--base-dir", str(self.base_dir)]

        r_route = subprocess.run(
            cli + ["route", "optimize slow postgres query", "--json"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(r_route.returncode, 0, r_route.stderr)
        route_data = json.loads(r_route.stdout)
        self.assertEqual(route_data["inline"][0]["name"], "cloud-sql-postgres-monitor")

        r_recat = subprocess.run(cli + ["recategorize", "--auto", "--dry-run"], capture_output=True, text=True)
        self.assertEqual(r_recat.returncode, 0, r_recat.stderr)
        self.assertIn("AUTO-RECATEGORIZATION", r_recat.stdout)

        r_dedupe = subprocess.run(cli + ["dedupe", "--dry-run"], capture_output=True, text=True)
        self.assertEqual(r_dedupe.returncode, 0, r_dedupe.stderr)
        self.assertIn("DUPLICATE CHECK", r_dedupe.stdout)

        r_stats = subprocess.run(cli + ["stats", "--json"], capture_output=True, text=True)
        self.assertEqual(r_stats.returncode, 0, r_stats.stderr)
        stats_data = json.loads(r_stats.stdout)
        self.assertIn("total_turns", stats_data)

    def test_node_launchers_and_claude_workspace_isolation(self):
        """Test cross-OS bin/hook.js & bin/mcp.js launchers and workspace isolation for Claude setup."""
        ws_dir = Path(self.tmp.name) / "isolated_claude_ws"
        ws_dir.mkdir(parents=True, exist_ok=True)
        res = subprocess.run(
            [sys.executable, str(SCRIPT_DIR / "skill_vault.py"), "setup", "--agent", "claude", "--scope", "workspace"],
            cwd=str(ws_dir),
            capture_output=True,
            text=True,
        )
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertTrue((ws_dir / ".claude" / "settings.json").exists())
        self.assertTrue((ws_dir / ".claude" / "skill_archive" / "search_index.json").exists())

        if shutil.which("node"):
            repo_root = SCRIPT_DIR.parent
            hook_res = subprocess.run(
                ["node", str(repo_root / "bin" / "hook.js"), "--harness", "antigravity", "--event", "PreInvocation", "--base-dir", str(self.base_dir)],
                input=json.dumps({"hookEventName": "PreInvocation", "conversationId": "conv-node", "lastUserInput": "Optimize slow postgres query"}),
                capture_output=True,
                text=True,
            )
            self.assertEqual(hook_res.returncode, 0, hook_res.stderr)
            self.assertIn("cloud-sql-postgres-monitor", hook_res.stdout)

            mcp_req = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05"}}) + "\n"
            mcp_res = subprocess.run(
                ["node", str(repo_root / "bin" / "mcp.js"), "--base-dir", str(self.base_dir)],
                input=mcp_req,
                capture_output=True,
                text=True,
            )
            self.assertEqual(mcp_res.returncode, 0, mcp_res.stderr)
            self.assertIn("skill-vault", mcp_res.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
