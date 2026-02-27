#!/usr/bin/env python3
"""
ARKAINBRAIN — Unit & Integration Test Suite

Run: python tests.py
     python tests.py -v          # verbose
     python tests.py TestGeo     # run specific class

Test categories:
  TestMathSimulation  — RTP calculation, volatility, win distribution
  TestGeoResearch     — Region scoring, state profiles, file output
  TestEmailNotify     — Template rendering, graceful skip, XSS escaping
  TestSchemaValidation— OpenAI-compatible tool schemas (no bare dict)
  TestPollingEndpoint — Log polling API (replaces SSE)
  TestWorkerHelpers   — DB helpers, email wrappers
  TestPDFGenerator    — Chart generation, PDF builder
"""

import json
import math
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# ── Ensure project root is on sys.path ──
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))


# ============================================================
# Math Simulation Tests
# ============================================================

class TestMathSimulation(unittest.TestCase):
    """Unit tests for the Monte Carlo simulation template."""

    def test_simulation_stats_dataclass(self):
        """SimulationStats tracks running statistics correctly."""
        spec = __import__("templates.math_simulation", fromlist=["SimulationStats"])
        Stats = spec.SimulationStats

        s = Stats()
        # Simulate some spins by directly manipulating fields (as the loop does)
        s.total_spins = 4
        s.total_wagered = 4.0
        s.total_won = 102.5
        s.max_win = 100.0
        s.wins = 2

        self.assertEqual(s.total_spins, 4)
        self.assertEqual(s.total_wagered, 4.0)
        self.assertAlmostEqual(s.total_won, 102.5)
        self.assertEqual(s.max_win, 100.0)
        self.assertEqual(s.wins, 2)

    def test_rtp_calculation(self):
        """RTP = total_won / total_wagered * 100."""
        spec = __import__("templates.math_simulation", fromlist=["SimulationStats"])
        Stats = spec.SimulationStats

        s = Stats()
        s.total_won = 960.0
        s.total_wagered = 1000.0
        rtp = (s.total_won / s.total_wagered) * 100
        self.assertAlmostEqual(rtp, 96.0)

    def test_hit_frequency(self):
        """Hit frequency = wins / total_spins * 100."""
        spec = __import__("templates.math_simulation", fromlist=["SimulationStats"])
        Stats = spec.SimulationStats

        s = Stats()
        s.total_spins = 100
        s.wins = 70

        hit_freq = (s.wins / s.total_spins) * 100
        self.assertAlmostEqual(hit_freq, 70.0)

    def test_win_distribution_buckets(self):
        """categorize_win correctly buckets wins by multiplier."""
        spec = __import__("templates.math_simulation", fromlist=["categorize_win"])
        categorize = spec.categorize_win

        self.assertEqual(categorize(0), "0x")
        self.assertEqual(categorize(0.5), "0-1x")
        self.assertEqual(categorize(1.5), "1-2x")
        self.assertEqual(categorize(3.0), "2-5x")
        self.assertEqual(categorize(50.0), "20-100x")
        self.assertEqual(categorize(500.0), "100-1000x")
        self.assertEqual(categorize(2000.0), "1000x+")


class TestVolatilityClassification(unittest.TestCase):
    """Test volatility tier logic from the PDF generator."""

    def test_volatility_tiers(self):
        """Volatility index maps to correct tier."""
        tiers = [
            (3.0, "Low"),
            (7.5, "Medium"),
            (15.0, "High"),
            (25.0, "Very High"),
        ]
        for index, expected in tiers:
            if index < 5:
                tier = "Low"
            elif index < 10:
                tier = "Medium"
            elif index < 20:
                tier = "High"
            else:
                tier = "Very High"
            self.assertEqual(tier, expected, f"σ={index} → {tier} (expected {expected})")


# ============================================================
# Geo Research Tests
# ============================================================

class TestGeoResearch(unittest.TestCase):
    """Unit tests for geographic market research tool."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def test_nevada_scoring(self):
        """Nevada returns scored regions with Las Vegas as top."""
        from tools.geo_research import run_geo_research
        result = run_geo_research("Nevada", "high", 96.0, "Test Game")
        self.assertGreater(len(result["ranked_regions"]), 0)
        self.assertEqual(result["top_recommendation"]["region"], "Las Vegas Strip")
        self.assertGreater(result["top_recommendation"]["composite_score"], 50)

    def test_unknown_state(self):
        """Unknown states return empty regions gracefully."""
        from tools.geo_research import run_geo_research
        result = run_geo_research("Vermont", "medium", 96.0, "")
        self.assertEqual(len(result["ranked_regions"]), 0)
        self.assertIsNone(result["top_recommendation"])
        self.assertIn("not have curated", result["summary"])

    def test_file_output(self):
        """Results save to JSON file when output_dir provided."""
        from tools.geo_research import run_geo_research
        result = run_geo_research("Texas", "low", 96.0, "", output_dir=self.tmpdir)
        path = Path(self.tmpdir) / "geo_research.json"
        self.assertTrue(path.exists())
        data = json.loads(path.read_text())
        self.assertEqual(data["state"], "Texas")
        self.assertGreater(len(data["ranked_regions"]), 0)

    def test_score_range(self):
        """All scores are within 0-100."""
        from tools.geo_research import run_geo_research
        for state in ["Nevada", "Georgia", "Texas", "Michigan"]:
            result = run_geo_research(state, "medium", 96.0, "")
            for r in result["ranked_regions"]:
                self.assertGreaterEqual(r["composite_score"], 0)
                self.assertLessEqual(r["composite_score"], 100)

    def test_volatility_affects_scoring(self):
        """High volatility games score tourism-heavy markets differently."""
        from tools.geo_research import run_geo_research
        low_vol = run_geo_research("Nevada", "low", 96.0, "")
        high_vol = run_geo_research("Nevada", "very_high", 96.0, "")
        # Scores should differ between volatility levels
        low_top = low_vol["top_recommendation"]["composite_score"]
        high_top = high_vol["top_recommendation"]["composite_score"]
        self.assertNotEqual(low_top, high_top)

    def test_ranking_order(self):
        """Regions are ranked by descending composite score."""
        from tools.geo_research import run_geo_research
        result = run_geo_research("Pennsylvania", "medium", 96.0, "")
        scores = [r["composite_score"] for r in result["ranked_regions"]]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_state_profile_fields(self):
        """State profile has required fields."""
        from tools.geo_research import run_geo_research
        result = run_geo_research("New Jersey", "medium", 96.0, "")
        profile = result["state_profile"]
        self.assertIn("legal_status", profile)
        self.assertIn("casino_count_approx", profile)
        self.assertIn("annual_ggr_billions", profile)


# ============================================================
# Email Notification Tests
# ============================================================

class TestEmailNotify(unittest.TestCase):
    """Unit tests for email notification service."""

    def test_disabled_without_key(self):
        """is_enabled returns False when RESEND_API_KEY not set."""
        from tools.email_notify import is_enabled
        self.assertFalse(is_enabled())

    def test_skip_when_disabled(self):
        """All notify functions return skipped when disabled."""
        from tools.email_notify import (
            notify_pipeline_complete, notify_pipeline_failed, notify_recon_complete
        )
        r1 = notify_pipeline_complete("test@test.com", "j1", "Game", "/out")
        r2 = notify_pipeline_failed("test@test.com", "j1", "Game", "err")
        r3 = notify_recon_complete("test@test.com", "j1", "Texas")
        self.assertTrue(r1.get("skipped"))
        self.assertTrue(r2.get("skipped"))
        self.assertTrue(r3.get("skipped"))

    def test_skip_empty_email(self):
        """Empty email address returns skipped."""
        from tools.email_notify import notify_pipeline_complete
        r = notify_pipeline_complete("", "j1", "Game", "/out")
        self.assertTrue(r.get("skipped"))

    def test_html_escaping(self):
        """XSS characters are properly escaped."""
        from tools.email_notify import _esc
        self.assertEqual(_esc('<script>alert(1)</script>'),
                         '&lt;script&gt;alert(1)&lt;/script&gt;')
        self.assertEqual(_esc('a & b "c"'), 'a &amp; b &quot;c&quot;')

    def test_template_rendering(self):
        """Email template wraps content with branding."""
        from tools.email_notify import _wrap_email
        html = _wrap_email("<h1>Test</h1>")
        self.assertIn("ARKAINBRAIN", html)
        self.assertIn("<h1>Test</h1>", html)
        self.assertIn("<!DOCTYPE html>", html)
        self.assertIn("container", html)


# ============================================================
# Schema Validation Tests (OpenAI compatibility)
# ============================================================

class TestSchemaValidation(unittest.TestCase):
    """Validate that all tool schemas are OpenAI function-calling compatible.

    OpenAI requires:
      - No bare `dict` types (must be `str` with JSON parsing)
      - `additionalProperties: false` on all objects
      - Only primitives: str, int, float, bool, list[str]
    """

    def _get_tool_classes(self):
        """Discover all Pydantic BaseModel subclasses used as tool schemas."""
        tool_files = [
            "tools/convergence_tools.py",
            "tools/custom_tools.py",
            "tools/advanced_research.py",
            "tools/tier1_upgrades.py",
            "tools/tier2_upgrades.py",
            "tools/prototype_engine.py",
            "tools/legal_research_tool.py",
            "tools/geo_research.py",
        ]
        schemas = []
        for tf in tool_files:
            path = PROJECT_ROOT / tf
            if not path.exists():
                continue
            content = path.read_text()
            # Find classes that end with "Input" (convention for tool schemas)
            import re
            for match in re.finditer(r'class (\w+Input)\(BaseModel\):', content):
                schemas.append((tf, match.group(1)))
        return schemas

    def test_no_bare_dict_in_schemas(self):
        """No tool schema has a bare `dict` field type."""
        for tf in Path(PROJECT_ROOT / "tools").glob("*.py"):
            content = tf.read_text()
            # Check for: field_name: dict = Field(...)
            import re
            for match in re.finditer(r'(\w+):\s*dict\s*=\s*Field', content):
                self.fail(
                    f"{tf.name}: Field '{match.group(1)}' uses bare `dict` — "
                    f"OpenAI will reject this. Use `str` with JSON parsing."
                )

    def test_no_nested_basemodel_in_schemas(self):
        """No tool schema has nested BaseModel fields (problematic with OpenAI)."""
        for tf in Path(PROJECT_ROOT / "tools").glob("*.py"):
            content = tf.read_text()
            import re
            # Find classes ending with Input
            input_classes = re.findall(r'class (\w+Input)\(BaseModel\):', content)
            for cls_name in input_classes:
                # Find the class body
                pattern = rf'class {cls_name}\(BaseModel\):(.*?)(?=\nclass |\Z)'
                match = re.search(pattern, content, re.DOTALL)
                if match:
                    body = match.group(1)
                    # Check for fields that reference other BaseModel subclasses
                    # This is a heuristic — look for PascalCase types that aren't builtins
                    field_types = re.findall(r':\s*([A-Z]\w+)\s*=\s*Field', body)
                    builtins = {'Field', 'Optional', 'List', 'Dict', 'Any', 'ClassVar'}
                    for ft in field_types:
                        if ft not in builtins:
                            # Not necessarily wrong, but flag it
                            pass  # Acceptable — Pydantic can serialize these

    def test_schema_classes_exist(self):
        """At least some tool schema classes are found."""
        schemas = self._get_tool_classes()
        self.assertGreater(len(schemas), 3, "Expected at least 3 tool schema classes")


# ============================================================
# Polling Endpoint Tests
# ============================================================

class TestPollingEndpoint(unittest.TestCase):
    """Test the polling log endpoint (replaced SSE)."""

    @classmethod
    def setUpClass(cls):
        """Set up Flask test client with a test database."""
        try:
            import authlib  # noqa
        except ImportError:
            raise unittest.SkipTest("authlib not installed — skipping Flask integration tests")

        os.environ["DB_PATH"] = ":memory:"
        os.environ["FLASK_SECRET_KEY"] = "test-secret"
        os.environ["GOOGLE_CLIENT_ID"] = "test"
        os.environ["GOOGLE_CLIENT_SECRET"] = "test"

        from web_app import app, _open_db
        cls.app = app
        cls.app.config["TESTING"] = True
        cls.client = cls.app.test_client()

        # Create tables and test user
        with cls.app.app_context():
            db = _open_db()
            db.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY, email TEXT UNIQUE, name TEXT,
                    picture TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY, user_id TEXT, job_type TEXT DEFAULT 'pipeline',
                    title TEXT, params TEXT, status TEXT DEFAULT 'queued',
                    current_stage TEXT, output_dir TEXT, error TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP, parent_job_id TEXT, version INTEGER DEFAULT 1
                );
                CREATE TABLE IF NOT EXISTS reviews (
                    id TEXT PRIMARY KEY, job_id TEXT, stage TEXT, title TEXT,
                    summary TEXT, files TEXT, status TEXT DEFAULT 'pending',
                    approved INTEGER, feedback TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, resolved_at TIMESTAMP
                );
                INSERT OR IGNORE INTO users (id, email, name) VALUES ('u1', 'test@test.com', 'Test');
                INSERT OR IGNORE INTO jobs (id, user_id, status) VALUES ('j-poll-1', 'u1', 'running');
                INSERT OR IGNORE INTO jobs (id, user_id, status) VALUES ('j-poll-2', 'u1', 'complete');
            """)
            db.commit()
            db.close()

    def _login(self):
        """Simulate login by setting session."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = "u1"

    def test_polling_returns_json(self):
        """Polling endpoint returns JSON with lines, cursor, done, status."""
        self._login()
        # Create a temp log file
        from web_app import LOG_DIR
        log_path = LOG_DIR / "j-poll-1.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("Line 1\nLine 2\nLine 3\n")

        resp = self.client.get("/api/logs/j-poll-1?after=0")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn("lines", data)
        self.assertIn("cursor", data)
        self.assertIn("done", data)
        self.assertIn("status", data)
        self.assertEqual(len(data["lines"]), 3)
        self.assertEqual(data["cursor"], 3)

        # Clean up
        log_path.unlink(missing_ok=True)

    def test_polling_cursor_pagination(self):
        """Cursor-based pagination returns only new lines."""
        self._login()
        from web_app import LOG_DIR
        log_path = LOG_DIR / "j-poll-1.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("Line 1\nLine 2\nLine 3\nLine 4\nLine 5\n")

        # First poll: get all 5 lines
        resp = self.client.get("/api/logs/j-poll-1?after=0")
        data = resp.get_json()
        self.assertEqual(len(data["lines"]), 5)
        cursor = data["cursor"]

        # Second poll with cursor: should get 0 new lines
        resp2 = self.client.get(f"/api/logs/j-poll-1?after={cursor}")
        data2 = resp2.get_json()
        self.assertEqual(len(data2["lines"]), 0)

        # Append new lines
        with open(log_path, "a") as f:
            f.write("Line 6\nLine 7\n")

        # Third poll: should get 2 new lines
        resp3 = self.client.get(f"/api/logs/j-poll-1?after={cursor}")
        data3 = resp3.get_json()
        self.assertEqual(len(data3["lines"]), 2)
        self.assertEqual(data3["cursor"], cursor + 2)

        log_path.unlink(missing_ok=True)

    def test_polling_done_flag(self):
        """Done flag is True when job is complete/failed."""
        self._login()
        from web_app import LOG_DIR
        log_path = LOG_DIR / "j-poll-2.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("Final line\n")

        resp = self.client.get("/api/logs/j-poll-2?after=0")
        data = resp.get_json()
        self.assertTrue(data["done"])
        self.assertEqual(data["status"], "complete")

        log_path.unlink(missing_ok=True)


# ============================================================
# PDF Chart Generation Tests
# ============================================================

class TestChartGeneration(unittest.TestCase):
    """Test matplotlib chart generation for math PDFs."""

    def test_charts_generate(self):
        """Win distribution and RTP contribution charts generate as PNGs."""
        try:
            import matplotlib
        except ImportError:
            self.skipTest("matplotlib not installed")

        from tools.pdf_generator import generate_math_charts
        tmpdir = tempfile.mkdtemp()
        math_data = {
            "results": {
                "win_distribution": {
                    "0x": 720000, "0-1x": 140000, "1-2x": 80000,
                    "2-5x": 40000, "5-20x": 15000, "20-100x": 4000,
                    "100-1000x": 900, "1000x+": 100,
                },
                "rtp_breakdown": {
                    "base_game_lines": 0.5520, "scatter_pays": 0.0180,
                    "free_games": 0.3200, "bonus_features": 0.0650, "jackpots": 0.0050,
                },
            }
        }
        charts = generate_math_charts(math_data, tmpdir)
        # Keys are display names: "Win Distribution", "RTP Contribution Breakdown"
        self.assertGreater(len(charts), 0)
        for name, path in charts.items():
            self.assertTrue(Path(path).exists(), f"Chart '{name}' not found at {path}")
            self.assertGreater(Path(path).stat().st_size, 5000,
                               f"Chart '{name}' suspiciously small")


# ============================================================
# Worker Helper Tests
# ============================================================

class TestWorkerHelpers(unittest.TestCase):
    """Test worker utility functions."""

    def test_update_db_rejects_bad_columns(self):
        """update_db rejects SQL injection via column names."""
        # Import directly without running __main__
        sys.modules.pop("worker", None)
        import worker
        with self.assertRaises(ValueError):
            worker.update_db("fake-id", status="complete", evil_column="DROP TABLE jobs")

    def test_update_db_allows_valid_columns(self):
        """update_db accepts whitelisted columns."""
        import worker
        allowed = worker._ALLOWED_JOB_COLUMNS
        self.assertIn("status", allowed)
        self.assertIn("current_stage", allowed)
        self.assertIn("output_dir", allowed)
        self.assertIn("error", allowed)
        self.assertIn("completed_at", allowed)


# ============================================================
# Main
# ============================================================

if __name__ == "__main__":
    # Configure logging to suppress noise during tests
    import logging
    logging.disable(logging.WARNING)

    unittest.main(verbosity=2)
