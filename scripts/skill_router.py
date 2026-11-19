#!/usr/bin/env python3
"""Skill Router: Pre-built BM25 + Multi-Signal Search Index and JIT Context Router.

Pure Python 3 standard library only (compatible with Python 3.10+ on Windows, macOS, Linux).
Provides fast (<50ms) precision-first skill discovery and confidence-tiered injection
directly from cold storage (L2) without modifying SKILL.md files or bloating L1.
"""

from collections import Counter
import hashlib
import json
import math
import os
from pathlib import Path
import re
import time

INDEX_SCHEMA_VERSION = 3

DEFAULT_ROUTING_CONFIG = {
    "enabled": True,
    "mode": "hybrid",  # "hybrid" | "inline" | "pointer"
    "max_inline_skills": 2,
    "max_inline_chars": 12000,
    "max_single_skill_chars": 9000,
    "max_pointer_skills": 4,
    "min_score_inline": 5.5,
    "min_score_pointer": 2.8,
    "inline_margin_ratio": 1.15,
    "workspace_boost": 1.35,
    "auto_sync_on_session_start": True,
    "auto_prune_on_session_start": True,
    "compact_router_prompt": False,
    "show_ui_notice": False,
    "always_exclude": [],
}

FIELD_WEIGHTS = {
    "name_terms": 4.0,
    "tag_terms": 2.8,
    "desc_terms": 2.2,
    "heading_terms": 1.5,
    "body_terms": 0.7,
}

# English stopwords + generic coding/chat verbs and nouns that carry no domain signal alone
STOPWORDS = {
    "a", "about", "above", "after", "again", "against", "all", "also", "am", "an", "and",
    "any", "are", "aren", "arent", "as", "at", "be", "because", "been", "before", "being",
    "below", "between", "both", "but", "by", "can", "cannot", "could", "couldn", "did",
    "didn", "do", "does", "doesn", "doing", "don", "dont", "down", "during", "each", "few",
    "for", "from", "further", "get", "got", "had", "has", "have", "having", "he", "hello",
    "help", "her", "here", "hers", "herself", "hey", "hi", "him", "himself", "his", "how",
    "i", "if", "in", "into", "is", "isn", "it", "its", "itself", "just", "know", "let",
    "like", "ll", "look", "looks", "make", "may", "me", "might", "more", "most", "must",
    "my", "myself", "need", "new", "no", "nor", "not", "now", "of", "off", "ok", "okay",
    "on", "once", "only", "or", "other", "our", "ours", "ourselves", "out", "over", "own",
    "please", "re", "really", "right", "same", "see", "she", "should", "shouldn", "so",
    "some", "such", "sure", "tell", "than", "thank", "thanks", "that", "the", "their",
    "theirs", "them", "themselves", "then", "there", "these", "they", "thing", "things",
    "this", "those", "through", "to", "too", "under", "understand", "understood", "until",
    "up", "use", "used", "using", "ve", "very", "want", "was", "wasn", "way", "we", "well",
    "were", "weren", "what", "whats", "when", "where", "which", "while", "who", "whom",
    "why", "will", "with", "won", "would", "wouldn", "yes", "yet", "you", "your", "yours",
    "yourself", "yourselves",
    # Generic coding & conversation words
    "add", "agent", "agents", "always", "another", "app", "apps", "apply", "ask", "based",
    "best", "better", "bug", "bugs", "build", "building", "call", "change", "changed",
    "changes", "check", "checking", "class", "classes", "clean", "cleaner", "code", "coding",
    "command", "commands", "commit", "common", "config", "configure", "context", "continue",
    "create", "creating", "current", "currently", "data", "date", "dates", "default",
    "delete", "detail", "details", "dir", "directory", "doc", "docs", "document", "done",
    "edit", "end", "ensure", "error", "errors", "etc", "every", "everything", "example",
    "examples", "examine", "exist", "existing", "explain", "failing", "fails", "fail",
    "feature", "features", "file", "files", "find", "fix", "fixing", "flag", "flags",
    "folder", "folders", "follow", "following", "format", "full", "function", "functions",
    "general", "generate", "give", "goal", "good", "great", "guide", "handle", "implement",
    "implementation", "include", "including", "info", "information", "input", "inside",
    "install", "installed", "instead", "into", "issue", "issues", "item", "items", "keep",
    "key", "line", "lines", "list", "load", "local", "loop", "main", "manage", "management",
    "match", "matching", "message", "method", "methods", "mode", "model", "models", "modify",
    "module", "multiple", "name", "named", "names", "need", "needed", "needs", "next", "nice",
    "note", "notes", "number", "numbers", "object", "open", "option", "options", "order",
    "output", "overview", "page", "pages", "part", "path", "paths", "pattern", "plan",
    "planning", "point", "possible", "print", "problem", "problems", "process", "project",
    "projects", "prompt", "prompts", "provide", "provided", "purpose", "question", "quick",
    "read", "reading", "real", "related", "remove", "rename", "repo", "report", "repository",
    "request", "require", "required", "requires", "result", "results", "return", "returns",
    "review", "run", "running", "runs", "save", "script", "scripts", "search", "section",
    "see", "select", "send", "server", "service", "services", "session", "set", "setting",
    "settings", "setup", "show", "showing", "simple", "single", "skill", "skills", "small",
    "solution", "solve", "something", "source", "specific", "staged", "standard", "start",
    "state", "step", "steps", "still", "stop", "structure", "style", "support", "supported",
    "system", "target", "task", "tasks", "test", "testing", "tests", "text", "time", "tool",
    "tools", "topic", "try", "type", "types", "unit", "update", "updated", "updates", "usage",
    "user", "users", "utility", "valid", "value", "values", "variable", "variables", "verify",
    "version", "view", "work", "working", "works", "workspace", "write", "writing", "written",
    "refactor", "refactored", "refactoring", "rewrite", "rewriting", "simplify", "simplified",
    "helper", "helpers", "snippet", "snippets", "codebase", "parse", "parsed", "parsing",
    "convert", "converting", "converted", "sort", "sorting", "filter", "filtering",
    "string", "strings", "array", "arrays", "dict", "dictionary", "lists", "regex", "regexp",
    "loops", "formatting", "formatted",
    "able", "actually", "already", "although", "around", "away", "back", "become", "becomes",
    "beyond", "big", "come", "comes", "different", "either", "else", "enough", "even", "ever",
    "extra", "far", "feel", "first", "found", "free", "getting", "given", "goes", "going",
    "gone", "hard", "however", "important", "influence", "influenced", "influences", "intention",
    "intentions", "kind", "known", "large", "last", "later", "least", "less", "likely", "little",
    "long", "lot", "made", "mainly", "makes", "making", "many", "maybe", "mean", "means", "mine",
    "much", "neither", "never", "nothing", "often", "old", "ones", "others", "overall",
    "particular", "perhaps", "probably", "put", "quite", "rather", "said", "say", "says",
    "second", "seem", "seems", "seen", "several", "shall", "short", "since", "somehow", "someone",
    "sometimes", "somewhere", "soon", "suggest", "suggested", "suggesting", "suggestions",
    "systems", "take", "taken", "takes", "taking", "think", "thinking", "though", "thought",
    "three", "thus", "together", "told", "toward", "towards", "tried", "tries", "true", "trying",
    "two", "unable", "unless", "upon", "useful", "usually", "various", "wants", "ways", "went",
    "whatever", "whether", "whole", "whose", "within", "without", "workspaces",
}

# High-signal 2-character domain tokens to retain
SHORT_DOMAIN_TOKENS = {
    "ai", "ml", "db", "ui", "ux", "ci", "cd", "qa", "tf", "go",
    "ik", "js", "ts", "py", "bq", "vm", "os", "io", "ip", "pr",
}

# Broad tech terms that should not trigger skill injection on their own as a solo 1-token query
GENERIC_SINGLE_TOKENS = {
    "python", "javascript", "typescript", "java", "golang", "rust", "ruby", "php", "csharp",
    "cpp", "html", "css", "json", "yaml", "toml", "xml", "csv", "sql", "bash", "shell",
    "powershell", "pwsh", "markdown", "linux", "windows", "macos", "git", "github", "cloud",
    "database", "databases", "storage", "query", "queries", "table", "tables", "schema",
    "debug", "debugging", "optimize", "optimization", "performance", "security", "audit",
    "monitor", "monitoring", "health", "access", "admin", "backup", "layout", "widget",
    "widgets", "component", "components", "container", "containers", "cluster", "clusters",
    "deploy", "deployment", "pipeline", "pipelines", "notebook", "notebooks", "graph",
    "report", "draft", "resolve", "mobile", "web", "frontend", "backend", "api", "apis",
    "server", "client", "network", "auth", "authentication", "replication", "migration",
    "analysis", "analyze", "analytics", "extension", "extensions", "preview", "device",
    "rules", "rule", "slow", "fast", "faster", "practices", "practice",
    "distributed", "distribute", "distribution", "dependent", "depends", "depend",
    "dependencies", "dependency", "architecture", "architectural", "improvement", "improvements",
    "publish", "published", "publishing", "npm", "safe", "safely", "safety",
    "package", "packages", "install", "library", "libraries", "framework", "frameworks",
}

_STEM_SUFFIXES = (
    ("ization", "ize"),
    ("ations", "ate"),
    ("ation", "ate"),
    ("ities", "ity"),
    ("ments", "ment"),
    ("iness", "y"),
    ("ies", "y"),
    ("ing", ""),
    ("ers", "er"),
    ("ed", ""),
    ("es", ""),
    ("s", ""),
)


def _light_stem(token):
    """Apply conservative suffix normalization for English plurals/verb forms."""
    if len(token) < 5 or any(ch in token for ch in (".", "-", "_")) or any(ch.isdigit() for ch in token):
        return token
    if token.endswith(("ss", "us", "is", "os", "gres", "etes", "ias")):
        return token
    for suffix, repl in _STEM_SUFFIXES:
        if token.endswith(suffix):
            stem = token[: -len(suffix)] + repl
            if len(stem) >= 4:
                return stem
            break
    return token


def _is_valid_token(tok):
    """Return True if token carries meaningful domain signal."""
    if not tok or tok in STOPWORDS:
        return False
    has_alpha = any("a" <= ch <= "z" for ch in tok)
    if not has_alpha:
        return False
    if len(tok) >= 3:
        return True
    if tok in SHORT_DOMAIN_TOKENS:
        return True
    if any(ch.isdigit() for ch in tok) and len(tok) >= 2:
        return True
    return False


def tokenize(text, include_stems=True):
    """Extract normalized domain tokens from text while preserving compound identifiers."""
    if not text:
        return []

    lowered = text.lower()
    raw_chunks = re.findall(r"[a-z0-9]+(?:[._/-][a-z0-9]+)*", lowered)
    tokens = []

    for chunk in raw_chunks:
        chunk_clean = chunk.strip("._/-")
        if not chunk_clean:
            continue

        # Preserve compound filenames/commands/identifiers like firestore.rules, alloydb-omni
        if any(sep in chunk_clean for sep in (".", "-", "_")) and "/" not in chunk_clean:
            if _is_valid_token(chunk_clean):
                tokens.append(chunk_clean)

        parts = re.split(r"[._/\-]+", chunk_clean)
        for part in parts:
            if _is_valid_token(part):
                tokens.append(part)
                if include_stems:
                    stemmed = _light_stem(part)
                    if stemmed != part and _is_valid_token(stemmed):
                        tokens.append(stemmed)

    return tokens


def canonicalize_skill_name(name):
    """Return canonical deduplication key normalizing case and underscore/hyphen differences."""
    return str(name or "").strip().lower().replace("_", "-")


def _parse_version_tuple(ver_str):
    if not ver_str:
        return None
    cleaned = str(ver_str).strip().strip("'\"").lstrip("vV")
    nums = re.findall(r"\d+", cleaned)
    return tuple(int(n) for n in nums) if nums else None


def _parse_frontmatter(content):
    """Parse YAML frontmatter fields from SKILL.md without external YAML dependencies."""
    fm_match = re.match(r"^---\s*\n(.*?)\n---(?:\s*\n|\s*\Z)", content, re.DOTALL)
    if not fm_match:
        return {}, content

    fm_text = fm_match.group(1)
    body = content[fm_match.end():]
    meta = {}

    # Scalar fields
    for field in ("name", "version", "category"):
        m = re.search(rf"^{field}:\s*([^\n]+)", fm_text, re.MULTILINE | re.IGNORECASE)
        if m:
            val = m.group(1).strip().strip("'\"")
            if val:
                meta[field] = val

    # Description (supports folded/literal YAML blocks and inline scalars)
    desc_match = re.search(
        r"^description:\s*(?:>[-+]?|\|[-+]?)?\s*\n?(.*?)(?=\n[a-zA-Z0-9_-]+:|\Z)",
        fm_text,
        re.DOTALL | re.MULTILINE | re.IGNORECASE,
    )
    if desc_match:
        raw_desc = desc_match.group(1).strip()
        meta["description"] = " ".join(
            line.strip().strip("'\"") for line in raw_desc.splitlines() if line.strip()
        )

    # List or comma-separated fields: tags, triggers, globs
    for list_field in ("tags", "triggers", "globs"):
        block_match = re.search(
            rf"^{list_field}:\s*(.*?)(?=\n[a-zA-Z0-9_-]+:|\Z)",
            fm_text,
            re.DOTALL | re.MULTILINE | re.IGNORECASE,
        )
        if block_match:
            raw_val = block_match.group(1).strip()
            raw_val = raw_val.strip("[]")
            items = []
            for part in re.split(r"[\n,]+", raw_val):
                cleaned = re.sub(r"^\s*-\s*", "", part).strip().strip("'\"")
                if cleaned:
                    items.append(cleaned)
            if items:
                meta[list_field] = items

    return meta, body


def _list_companion_files(skill_dir, max_files=30):
    """List companion files (references/, scripts/, examples/, resources/) in POSIX relative form."""
    skill_dir = Path(skill_dir)
    if not skill_dir.exists():
        return []
    companions = []
    for root, dirs, files in os.walk(skill_dir):
        root_path = Path(root)
        dirs[:] = sorted(
            d for d in dirs
            if d not in {"__pycache__", ".git", "node_modules"}
            and not (root_path / d / "SKILL.md").exists()
        )
        for fname in sorted(files):
            fpath = root_path / fname
            if root_path == skill_dir and fname == "SKILL.md":
                continue
            try:
                rel = fpath.relative_to(skill_dir).as_posix()
                companions.append(rel)
                if len(companions) >= max_files:
                    return companions
            except ValueError:
                pass
    return companions


def _extract_skill_fields(skill_name, category, skill_dir, skill_md_path):
    """Extract weighted token frequency maps and metadata from a skill's SKILL.md."""
    try:
        content = Path(skill_md_path).read_text(encoding="utf-8", errors="replace")
    except Exception:
        content = ""

    meta, body = _parse_frontmatter(content)
    description = meta.get("description") or "No description available."
    ver_tuple = _parse_version_tuple(meta.get("version"))

    # 1. Name terms (deduplicate skill_name vs meta['name'] to avoid artificial tf=2 inflation)
    meta_name = meta.get("name", "")
    name_input = skill_name if not meta_name or meta_name.strip().lower() == skill_name.strip().lower() else f"{skill_name} {meta_name}"
    name_tokens = tokenize(name_input)
    name_tf = dict(Counter(name_tokens))

    # 2. Explicit author-declared frontmatter tag / trigger / glob terms ONLY
    tag_inputs = []
    for lf in ("tags", "triggers", "globs"):
        if lf in meta:
            tag_inputs.extend(meta[lf])
    tag_tf = dict(Counter(tokenize(" ".join(tag_inputs))))

    # 3. Description terms
    desc_tf = dict(Counter(tokenize(description)))

    # 4. Headings + Category terms
    headings = re.findall(r"^#{1,3}\s+(.+)$", body, re.MULTILINE)
    heading_text = f"{category} " + " ".join(headings)
    heading_tf = dict(Counter(tokenize(heading_text)))

    # 5. Distinctive body terms + selective technical inline code identifiers (top 60)
    inline_code = re.findall(r"`([^`\n]{2,60})`", body)
    code_tokens = tokenize(" ".join(inline_code))
    seen_code = []
    seen_code_set = set()
    for tok in code_tokens:
        is_distinctive = (
            any(ch in tok for ch in (".", "-", "_"))
            or any(ch.isdigit() for ch in tok)
            or tok not in GENERIC_SINGLE_TOKENS
        )
        if is_distinctive and tok not in seen_code_set:
            seen_code_set.add(tok)
            seen_code.append(tok)
            if len(seen_code) >= 40:
                break

    body_clean = re.sub(r"```.*?```", " ", body, flags=re.DOTALL)
    body_counts = Counter(tokenize(body_clean) + seen_code)
    body_tf = dict(body_counts.most_common(60))

    # Compute mtime safely without bleeding nested sibling skills
    latest_mtime = 0.0
    try:
        skill_dir_path = Path(skill_dir)
        mtimes = []
        if Path(skill_md_path).exists():
            mtimes.append(Path(skill_md_path).stat().st_mtime)
        if skill_dir_path.exists():
            for root, dirs, files in os.walk(skill_dir_path):
                rp = Path(root)
                dirs[:] = [d for d in dirs if not (rp / d / "SKILL.md").exists()]
                for fn in files:
                    try:
                        mtimes.append((rp / fn).stat().st_mtime)
                    except OSError:
                        pass
        if mtimes:
            latest_mtime = max(mtimes)
    except OSError:
        pass

    skill_md_bytes = 0
    try:
        skill_md_bytes = Path(skill_md_path).stat().st_size
    except OSError:
        skill_md_bytes = len(content.encode("utf-8", errors="ignore"))

    return {
        "name": skill_name,
        "canonical_key": canonicalize_skill_name(skill_name),
        "category": category or "General & Utility Skills",
        "description": description,
        "version_tuple": list(ver_tuple) if ver_tuple is not None else None,
        "mtime": latest_mtime,
        "skill_md_bytes": skill_md_bytes,
        "companion_files": _list_companion_files(skill_dir),
        "fields": {
            "name_terms": name_tf,
            "tag_terms": tag_tf,
            "desc_terms": desc_tf,
            "heading_terms": heading_tf,
            "body_terms": body_tf,
        },
    }


def _is_newer_entry(cand, existing):
    """Return True if cand entry is strictly newer/preferred over existing entry."""
    va = cand.get("version_tuple")
    vb = existing.get("version_tuple")
    if va is not None and vb is not None and va != vb:
        return tuple(va) > tuple(vb)
    if va is not None and vb is None:
        return True
    if va is None and vb is not None:
        return False

    ma = cand.get("mtime", 0.0)
    mb = existing.get("mtime", 0.0)
    if abs(ma - mb) > 1.0:
        return ma > mb

    # Tie-breaker: prefer hyphenated names over underscored names
    cand_hyphen = "-" in cand["name"] and "_" not in cand["name"]
    exist_hyphen = "-" in existing["name"] and "_" not in existing["name"]
    if cand_hyphen != exist_hyphen:
        return cand_hyphen
    return cand["name"] < existing["name"]


def _resolve_archived_skill_dir(base_dir, archive_dir, raw_archived_path):
    """Resolve an archived_path stored in manifest across relative/absolute layouts."""
    p = Path(raw_archived_path)
    if p.is_absolute():
        return p
    if base_dir is not None:
        cand = (Path(base_dir) / p).resolve()
        if cand.exists():
            return cand
    cand2 = (Path(archive_dir).parent / p).resolve()
    if cand2.exists():
        return cand2
    return (Path(archive_dir) / p).resolve()


def build_search_index(archive_dir, manifest, base_dir=None, resolve_path_fn=None):
    """Build and atomically persist search_index.json from backup_manifest.json."""
    archive_path = Path(archive_dir).resolve()
    archive_path.mkdir(parents=True, exist_ok=True)
    manifest_file = archive_path / "backup_manifest.json"
    manifest_mtime = manifest_file.stat().st_mtime if manifest_file.exists() else time.time()

    deduped = {}
    for item in manifest:
        name = item.get("name")
        raw_arch = item.get("archived_path", "")
        if not name or not raw_arch:
            continue
        if resolve_path_fn is not None:
            skill_dir = Path(resolve_path_fn(raw_arch))
        else:
            skill_dir = _resolve_archived_skill_dir(base_dir, archive_path, raw_arch)

        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            continue

        entry = _extract_skill_fields(
            skill_name=name,
            category=item.get("category") or "General & Utility Skills",
            skill_dir=skill_dir,
            skill_md_path=skill_md,
        )
        entry["archived_path"] = raw_arch
        entry["resolved_path"] = str(skill_dir)
        entry["aliases"] = [name]

        ckey = entry["canonical_key"]
        if ckey not in deduped:
            deduped[ckey] = entry
        else:
            existing = deduped[ckey]
            aliases = list(dict.fromkeys(existing.get("aliases", []) + [name]))
            if _is_newer_entry(entry, existing):
                entry["aliases"] = aliases
                deduped[ckey] = entry
            else:
                existing["aliases"] = aliases

    skills_list = sorted(deduped.values(), key=lambda x: x["name"].lower())
    doc_count = len(skills_list)

    # Compute document frequency (across any field per skill) and average field lengths
    df = Counter()
    field_totals = {f: 0 for f in FIELD_WEIGHTS}

    for entry in skills_list:
        seen_terms = set()
        for fname in FIELD_WEIGHTS:
            tf_map = entry["fields"].get(fname, {})
            field_totals[fname] += sum(tf_map.values())
            seen_terms.update(tf_map.keys())
        for term in seen_terms:
            df[term] += 1

    avg_len = {
        fname: (field_totals[fname] / doc_count) if doc_count > 0 else 1.0
        for fname in FIELD_WEIGHTS
    }
    for fname in avg_len:
        if avg_len[fname] <= 0:
            avg_len[fname] = 1.0

    index_data = {
        "schema_version": INDEX_SCHEMA_VERSION,
        "built_at": time.time(),
        "manifest_mtime": manifest_mtime,
        "doc_count": doc_count,
        "avg_len": avg_len,
        "df": dict(df),
        "skills": skills_list,
    }

    index_file = archive_path / "search_index.json"
    tmp_file = archive_path / f".search_index.{os.getpid()}.tmp"
    with open(tmp_file, "w", encoding="utf-8") as f:
        json.dump(index_data, f, ensure_ascii=False)
    os.replace(tmp_file, index_file)
    return index_data


def load_or_build_index(archive_dir, base_dir=None, resolve_path_fn=None):
    """Load pre-built search_index.json in <5ms, or rebuild lazily if missing/stale."""
    archive_path = Path(archive_dir).resolve()
    index_file = archive_path / "search_index.json"
    manifest_file = archive_path / "backup_manifest.json"
    manifest_mtime = manifest_file.stat().st_mtime if manifest_file.exists() else 0.0

    if index_file.exists():
        try:
            with open(index_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if (
                isinstance(data, dict)
                and data.get("schema_version") == INDEX_SCHEMA_VERSION
                and float(data.get("manifest_mtime", 0.0)) >= manifest_mtime - 0.5
            ):
                return data
        except Exception:
            pass

    manifest = []
    if manifest_file.exists():
        try:
            with open(manifest_file, "r", encoding="utf-8") as f:
                manifest = json.load(f)
        except Exception:
            manifest = []

    return build_search_index(
        archive_dir=archive_path,
        manifest=manifest,
        base_dir=base_dir,
        resolve_path_fn=resolve_path_fn,
    )


def _normalized_idf(df_val, doc_count):
    """Compute corpus-size-normalized BM25 IDF so thresholds stay calibrated from N=10 to N=1000+."""
    if doc_count <= 0:
        return 0.0
    raw = math.log((doc_count - df_val + 0.5) / (df_val + 0.5) + 1.0)
    scale = 3.2 / math.log(max(doc_count, 5) + 1.0)
    return raw * scale


def search_index(
    index_data,
    query,
    category=None,
    workspace_categories=None,
    exclude_names=None,
    limit=10,
    routing_config=None,
):
    """Score indexed skills using multi-field BM25 + exact-name + coverage + workspace tie-breaker."""
    cfg = dict(DEFAULT_ROUTING_CONFIG)
    if routing_config:
        cfg.update(routing_config)

    skills = index_data.get("skills", [])
    doc_count = index_data.get("doc_count", len(skills))
    avg_len = index_data.get("avg_len", {f: 1.0 for f in FIELD_WEIGHTS})
    df_map = index_data.get("df", {})

    exclude_canon = {canonicalize_skill_name(n) for n in (exclude_names or []) if n}
    ws_cats = set(workspace_categories or [])
    ws_boost = float(cfg.get("workspace_boost", 1.35))

    raw_query = (query or "").strip().lower()
    raw_query_norm = re.sub(r"[-_]+", " ", raw_query)
    # Extract distinct semantic concepts without summing base + stem duplicates
    concept_tokens = list(dict.fromkeys(tokenize(query, include_stems=False)))

    if not concept_tokens and not category:
        return []

    specific_concepts = [
        c for c in concept_tokens
        if c not in GENERIC_SINGLE_TOKENS
        and (df_map.get(c, 0) > 0 or df_map.get(_light_stem(c), 0) > 0)
    ]

    k1 = 1.2
    results = []

    for entry in skills:
        ckey = entry.get("canonical_key") or canonicalize_skill_name(entry.get("name"))
        if ckey in exclude_canon:
            continue

        entry_cat = entry.get("category", "General & Utility Skills")
        if category and entry_cat.lower() != category.strip().lower():
            continue

        if not concept_tokens and category:
            results.append({
                "name": entry["name"],
                "canonical_key": ckey,
                "category": entry_cat,
                "score": 10.0,
                "matched_terms": [],
                "description": entry.get("description", ""),
                "archived_path": entry.get("archived_path", ""),
                "resolved_path": entry.get("resolved_path", ""),
                "skill_md_bytes": entry.get("skill_md_bytes", 0),
                "companion_files": entry.get("companion_files", []),
                "aliases": entry.get("aliases", [entry["name"]]),
                "exact_name_hit": False,
            })
            continue

        fields = entry.get("fields", {})
        cat_tokens = set(tokenize(entry_cat, include_stems=False))
        bm25_score = 0.0
        matched_terms = []
        matched_in_name = False
        matched_in_tags = False
        matched_in_desc_or_head = False
        matched_concepts = set()
        matched_specific = 0
        high_signal_hits = 0
        matched_name_concepts = 0
        matched_non_generic_in_name_or_tag = False
        matched_category_token = False
        matched_non_generic_desc = 0

        for ctok in concept_tokens:
            forms = list(dict.fromkeys([ctok, _light_stem(ctok)]))
            best_form_score = 0.0
            form_name = False
            form_tag = False
            form_desc_or_head = False
            form_high = False

            for f_tok in forms:
                df_val = df_map.get(f_tok, 0)
                if df_val == 0:
                    continue
                idf = _normalized_idf(df_val, doc_count)
                field_scores = []

                for fname, weight in FIELD_WEIGHTS.items():
                    tf_map = fields.get(fname, {})
                    tf = tf_map.get(f_tok, 0)
                    if tf <= 0:
                        continue
                    if fname == "name_terms":
                        form_name = True
                        form_high = True
                    elif fname == "tag_terms":
                        form_tag = True
                        form_high = True
                    elif fname in ("desc_terms", "heading_terms"):
                        form_desc_or_head = True
                        form_high = True

                    dl = max(sum(tf_map.values()), 1)
                    adl = max(float(avg_len.get(fname, 1.0)), 1.0)
                    b_val = 0.25 if fname == "name_terms" else 0.75
                    tf_norm = (tf * (k1 + 1.0)) / (tf + k1 * (1.0 - b_val + b_val * dl / adl))
                    field_scores.append(weight * idf * tf_norm)

                if field_scores:
                    field_scores.sort(reverse=True)
                    blended = min(
                        field_scores[0] * 1.35,
                        field_scores[0] + 0.20 * sum(field_scores[1:]),
                    )
                    if idf >= 2.0 and (form_name or form_tag):
                        blended *= 1.15
                    if blended > best_form_score:
                        best_form_score = blended

            if best_form_score > 0.0:
                bm25_score += best_form_score
                matched_terms.append(ctok)
                matched_concepts.add(ctok)
                is_non_generic = ctok not in GENERIC_SINGLE_TOKENS
                if ctok in specific_concepts:
                    matched_specific += 1
                if form_name:
                    matched_in_name = True
                    matched_name_concepts += 1
                if form_tag:
                    matched_in_tags = True
                if is_non_generic and (form_name or form_tag):
                    matched_non_generic_in_name_or_tag = True
                if is_non_generic and ctok in cat_tokens:
                    matched_category_token = True
                if is_non_generic and form_desc_or_head:
                    matched_non_generic_desc += 1
                if form_high:
                    if not (form_name or form_tag):
                        matched_in_desc_or_head = True
                    high_signal_hits += 1

        # Exact skill name / alias hit check
        exact_name_hit = False
        for alias in entry.get("aliases", [entry["name"]]):
            alias_l = alias.lower()
            alias_spaces = re.sub(r"[-_]+", " ", alias_l)
            if (
                len(alias_l) >= 4
                and (
                    re.search(rf"(?<![a-z0-9]){re.escape(alias_l)}(?![a-z0-9])", raw_query)
                    or re.search(rf"(?<![a-z0-9]){re.escape(alias_spaces)}(?![a-z0-9])", raw_query_norm)
                )
            ):
                exact_name_hit = True
                break

        if exact_name_hit:
            bm25_score += 10.0

        # Multi-term coverage bonus when >=2 distinct prompt concepts hit high-signal fields
        if high_signal_hits >= 2:
            bm25_score += 1.5 * (high_signal_hits - 1)

        # Dominant-concept gate & identity-anchor guards to keep unrelated conversational prompts at 0 tokens
        if not exact_name_hit and specific_concepts and matched_specific == 0:
            bm25_score *= 0.20
        elif not exact_name_hit and len(matched_concepts) <= 1 and bm25_score > 0:
            only_tok = next(iter(matched_concepts)) if matched_concepts else ""
            df_ratio = (df_map.get(only_tok, 0) / doc_count) if doc_count > 0 else 0.0
            only_body = not (matched_in_name or matched_in_tags or matched_in_desc_or_head)
            not_name_or_tag = not (matched_in_name or matched_in_tags)

            if only_tok in GENERIC_SINGLE_TOKENS and only_tok != ckey:
                bm25_score *= 0.15
            elif only_body:
                bm25_score *= 0.25
            elif df_ratio > 0.35 or (df_ratio > 0.20 and not matched_in_name):
                bm25_score *= 0.30
            elif not_name_or_tag and len(concept_tokens) >= 2:
                bm25_score *= 0.45
        elif not exact_name_hit and matched_concepts and all(c in GENERIC_SINGLE_TOKENS for c in matched_concepts):
            if matched_name_concepts < 2:
                bm25_score *= 0.20
        elif (
            not exact_name_hit
            and matched_concepts
            and not matched_non_generic_in_name_or_tag
            and not matched_category_token
            and matched_non_generic_desc < 2
            and matched_name_concepts < 2
        ):
            bm25_score *= 0.30

        # Soft workspace tie-breaker ONLY when prompt already has real signal
        if bm25_score > 0.5 and entry_cat in ws_cats:
            bm25_score *= ws_boost

        if bm25_score > 0.0:
            results.append({
                "name": entry["name"],
                "canonical_key": ckey,
                "category": entry_cat,
                "score": round(bm25_score, 3),
                "matched_terms": list(dict.fromkeys(matched_terms)),
                "description": entry.get("description", ""),
                "archived_path": entry.get("archived_path", ""),
                "resolved_path": entry.get("resolved_path", ""),
                "skill_md_bytes": entry.get("skill_md_bytes", 0),
                "companion_files": entry.get("companion_files", []),
                "aliases": entry.get("aliases", [entry["name"]]),
                "exact_name_hit": exact_name_hit,
            })

    results.sort(key=lambda r: (-r["score"], r["name"].lower()))
    return results[:limit] if limit else results


def _resolve_skill_md_for_candidate(cand, archive_dir, base_dir=None):
    """Locate readable SKILL.md path for a ranked candidate."""
    raw_res = cand.get("resolved_path")
    if raw_res:
        p = Path(raw_res) / "SKILL.md"
        if p.exists():
            return p, Path(raw_res)
    raw_arch = cand.get("archived_path")
    if raw_arch:
        skill_dir = _resolve_archived_skill_dir(base_dir, archive_dir, raw_arch)
        p = skill_dir / "SKILL.md"
        if p.exists():
            return p, skill_dir
    return None, None


def _truncate_skill_body(text, max_chars, skill_name):
    """Truncate overly long SKILL.md cleanly on a line boundary with MCP load hint."""
    if len(text) <= max_chars:
        return text, False
    cutoff = max(max_chars - 240, 500)
    snippet = text[:cutoff]
    last_nl = snippet.rfind("\n")
    if last_nl > cutoff * 0.6:
        snippet = snippet[:last_nl]
    notice = (
        f"\n\n[... truncated at {len(snippet)} chars to preserve context budget; "
        f"call MCP load_skill(name=\"{skill_name}\") if remaining sections are needed ...]"
    )
    return snippet + notice, True


def route_prompt(
    index_data,
    prompt,
    archive_dir,
    base_dir=None,
    workspace_categories=None,
    exclude_names=None,
    routing_config=None,
):
    """Select confidence-tiered skills (inline / pointer / none) and format injection text."""
    cfg = dict(DEFAULT_ROUTING_CONFIG)
    if routing_config:
        cfg.update(routing_config)

    empty_result = {
        "inline": [],
        "pointers": [],
        "candidates": [],
        "estimated_tokens": 0,
        "injection_text": "",
        "ui_notice": "",
        "ambiguous": False,
    }

    if not cfg.get("enabled", True) or not (prompt or "").strip():
        return empty_result

    mode = str(cfg.get("mode", "hybrid")).lower()
    min_pointer = float(cfg.get("min_score_pointer", 2.8))
    min_inline = float(cfg.get("min_score_inline", 5.5))
    max_inline = int(cfg.get("max_inline_skills", 2))
    max_pointers = int(cfg.get("max_pointer_skills", 4))
    max_inline_chars = int(cfg.get("max_inline_chars", 12000))
    max_single_chars = int(cfg.get("max_single_skill_chars", 9000))
    margin_ratio = float(cfg.get("inline_margin_ratio", 1.15))

    always_excl = set(cfg.get("always_exclude", []) or [])
    combined_excl = set(exclude_names or []) | always_excl

    candidates = search_index(
        index_data=index_data,
        query=prompt,
        workspace_categories=workspace_categories,
        exclude_names=combined_excl,
        limit=max(12, max_inline + max_pointers + 4),
        routing_config=cfg,
    )

    viable = [c for c in candidates if c["score"] >= min_pointer]
    if not viable:
        empty_result["candidates"] = candidates
        return empty_result

    # Relative score floor: prune trailing weak noise far below the top match
    top = viable[0]
    rel_floor = max(min_pointer, top["score"] * 0.30)
    viable = [c for c in viable if c["score"] >= rel_floor]

    # Ambiguity check: if >=4 peers in the top skill's category tie closely without exact-name hit,
    # demote all to compact pointers instead of guessing 2 arbitrary skills.
    ambiguous = False
    if not top.get("exact_name_hit"):
        floor = top["score"] / max(margin_ratio, 1.01)
        close_peers = [
            c for c in viable
            if c["category"] == top["category"] and c["score"] >= floor
        ]
        if len(close_peers) >= 4:
            ambiguous = True

    inline_items = []
    pointer_items = []

    if mode == "pointer" or ambiguous:
        pointer_items = viable[: max_pointers + (max_inline if mode == "pointer" else 0)]
    else:
        remaining_chars = max_inline_chars
        for cand in viable:
            passes_inline_floor = cand["score"] >= min_inline or mode == "inline"
            if len(inline_items) > 0 and cand["score"] < top["score"] * 0.45:
                passes_inline_floor = False
            should_try_inline = (
                len(inline_items) < max_inline
                and passes_inline_floor
                and remaining_chars >= 600
            )
            if should_try_inline:
                md_path, skill_dir = _resolve_skill_md_for_candidate(cand, archive_dir, base_dir)
                if md_path and md_path.exists():
                    try:
                        raw_text = md_path.read_text(encoding="utf-8", errors="replace").strip()
                    except Exception:
                        raw_text = ""
                    if raw_text:
                        budget = min(max_single_chars, remaining_chars)
                        body_text, truncated = _truncate_skill_body(raw_text, budget, cand["name"])
                        item = dict(cand)
                        item["skill_dir"] = str(skill_dir)
                        item["skill_md_path"] = str(md_path)
                        item["content"] = body_text
                        item["truncated"] = truncated
                        inline_items.append(item)
                        remaining_chars -= len(body_text)
                        continue
            if len(pointer_items) < max_pointers:
                item = dict(cand)
                _, skill_dir = _resolve_skill_md_for_candidate(cand, archive_dir, base_dir)
                item["skill_dir"] = str(skill_dir) if skill_dir else cand.get("resolved_path", "")
                pointer_items.append(item)

    if not inline_items and not pointer_items:
        empty_result["candidates"] = candidates
        return empty_result

    # Format compact injection block
    sections = ["<skill_vault_context>"]
    if inline_items:
        sections.append(
            "Relevant skills automatically loaded from cold storage (L2) for this request:"
        )
        for item in inline_items:
            companions = item.get("companion_files", [])
            comp_str = ", ".join(companions[:12])
            if len(companions) > 12:
                comp_str += f", ... (+{len(companions) - 12} more)"
            sections.append(
                f'<skill name="{item["name"]}" category="{item["category"]}" base_dir="{item["skill_dir"]}">'
            )
            if comp_str:
                sections.append(
                    f"[Companion files inside base_dir (load via MCP load_skill or read_file): {comp_str}]"
                )
            sections.append(item["content"])
            sections.append("</skill>")

    if pointer_items:
        sections.append("<available_vault_skills>")
        sections.append(
            "Additional matching vaulted skills (call MCP load_skill(name) or read SKILL.md if needed):"
        )
        for item in pointer_items:
            desc = item.get("description", "").strip()
            short_desc = desc[:130] + "..." if len(desc) > 130 else desc
            skill_md_loc = str(Path(item["skill_dir"]) / "SKILL.md") if item.get("skill_dir") else item.get("archived_path", "")
            sections.append(
                f'- **{item["name"]}** [{item["category"]}]: {short_desc} (`{skill_md_loc}`)'
            )
        sections.append("</available_vault_skills>")

    sections.append("</skill_vault_context>")
    injection_text = "\n".join(sections)
    est_tokens = max(1, len(injection_text) // 4)

    inlined_names = [i["name"] for i in inline_items]
    pointed_names = [p["name"] for p in pointer_items]
    notice_parts = []
    if inlined_names:
        notice_parts.append("Loaded: " + ", ".join(f"`{n}`" for n in inlined_names))
    if pointed_names:
        notice_parts.append("Available: " + ", ".join(f"`{n}`" for n in pointed_names))
    ui_notice = f"*Skill Vault:* {' | '.join(notice_parts)}" if notice_parts else ""

    return {
        "inline": inline_items,
        "pointers": pointer_items,
        "candidates": candidates,
        "estimated_tokens": est_tokens,
        "injection_text": injection_text,
        "ui_notice": ui_notice,
        "ambiguous": ambiguous,
    }


# --- Per-Conversation State, Workspace Cache & Telemetry ---


def _state_dir(archive_dir):
    d = Path(archive_dir).resolve() / ".state"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _atomic_write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, path)


class ConversationState:
    """Manages per-conversation routing state for same-turn short-circuit & cross-turn dedup."""

    def __init__(self, archive_dir, conversation_id):
        self.state_dir = _state_dir(archive_dir)
        cid = str(conversation_id or "default")
        digest = hashlib.sha256(cid.encode("utf-8", errors="ignore")).hexdigest()[:16]
        self.path = self.state_dir / f"conv_{digest}.json"
        self.data = self._load()

    def _load(self):
        if self.path.exists():
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    return data
            except Exception:
                pass
        return {
            "last_input_hash": None,
            "last_initial_steps": None,
            "injected_skills": [],
            "pointed_skills": [],
            "updated_at": 0.0,
        }

    def save(self):
        self.data["updated_at"] = time.time()
        _atomic_write_json(self.path, self.data)

    def should_short_circuit(self, input_hash, invocation_num=None, initial_num_steps=None):
        """Return True if this PreInvocation call repeats the same user input."""
        return self.data.get("last_input_hash") == input_hash

    def get_excluded_skills(self):
        return set(self.data.get("injected_skills", [])) | set(self.data.get("pointed_skills", []))

    def record_turn(self, input_hash, initial_num_steps, inline_keys, pointer_keys):
        self.data["last_input_hash"] = input_hash
        self.data["last_initial_steps"] = initial_num_steps
        injected = list(dict.fromkeys(list(self.data.get("injected_skills", [])) + list(inline_keys)))
        pointed = list(dict.fromkeys(list(self.data.get("pointed_skills", [])) + list(pointer_keys)))
        self.data["injected_skills"] = injected
        self.data["pointed_skills"] = pointed
        self.save()


def prune_old_states(archive_dir, max_age_days=7):
    """Remove stale conversation state files older than max_age_days."""
    state_dir = Path(archive_dir).resolve() / ".state"
    if not state_dir.exists():
        return 0
    cutoff = time.time() - (max_age_days * 86400.0)
    removed = 0
    for f in state_dir.glob("conv_*.json"):
        try:
            if f.stat().st_mtime < cutoff:
                f.unlink()
                removed += 1
        except OSError:
            pass
    return removed


def get_cached_workspace_categories(archive_dir, workspace_paths, ttl_seconds=600):
    """Retrieve cached workspace categories if still within TTL."""
    if not workspace_paths:
        return None
    state_dir = _state_dir(archive_dir)
    key = hashlib.sha256("|".join(sorted(str(p) for p in workspace_paths)).encode("utf-8")).hexdigest()[:16]
    cache_file = state_dir / "ws_cache.json"
    if not cache_file.exists():
        return None
    try:
        with open(cache_file, "r", encoding="utf-8") as f:
            cache = json.load(f)
        entry = cache.get(key)
        if entry and (time.time() - float(entry.get("ts", 0.0))) <= ttl_seconds:
            return list(entry.get("categories", []))
    except Exception:
        pass
    return None


def cache_workspace_categories(archive_dir, workspace_paths, categories):
    """Persist detected workspace categories for fast lookup in PreInvocation."""
    if not workspace_paths:
        return
    state_dir = _state_dir(archive_dir)
    key = hashlib.sha256("|".join(sorted(str(p) for p in workspace_paths)).encode("utf-8")).hexdigest()[:16]
    cache_file = state_dir / "ws_cache.json"
    cache = {}
    if cache_file.exists():
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                cache = loaded
        except Exception:
            cache = {}

    now = time.time()
    cache = {k: v for k, v in cache.items() if now - float(v.get("ts", 0.0)) < 86400}
    cache[key] = {"ts": now, "categories": sorted(set(categories))}
    _atomic_write_json(cache_file, cache)


def log_routing_event(archive_dir, record, max_lines=1000):
    """Append a privacy-preserving telemetry record (no raw prompts) to routing_log.jsonl."""
    state_dir = _state_dir(archive_dir)
    log_file = state_dir / "routing_log.jsonl"
    line = json.dumps(record, ensure_ascii=False)
    try:
        lines = []
        if log_file.exists():
            with open(log_file, "r", encoding="utf-8", errors="replace") as f:
                lines = f.read().splitlines()
        lines.append(line)
        if len(lines) > max_lines:
            lines = lines[-max_lines:]
        tmp = state_dir / f".routing_log.{os.getpid()}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        os.replace(tmp, log_file)
    except OSError:
        pass
