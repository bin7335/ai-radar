import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import main


class PipelineTests(unittest.TestCase):
    def test_weekly_stars_and_old_repository_are_collected(self):
        html = """
        <article class="Box-row">
          <h2><a href="/old-org/agent-tools">old-org / agent-tools</a></h2>
          <p>AI agent tools</p>
          <a href="/old-org/agent-tools/stargazers">12,345</a>
          <span>1,234 stars this week</span>
        </article>
        <article class="Box-row">
          <h2><a href="/other/cookbook">other / cookbook</a></h2>
          <p>Recipes</p><span>22 stars this week</span>
        </article>
        """
        items = main.parse_github_trending(html)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["title"], "old-org/agent-tools")
        self.assertEqual(items[0]["weekly_stars"], 1234)
        self.assertEqual(items[0]["total_stars"], 12345)
        self.assertEqual(items[0]["points"], 1234)

    def test_existing_trending_item_is_refreshed_without_losing_summary(self):
        old = [{
            "title": "old-org/agent-tools",
            "url": "https://github.com/old-org/agent-tools",
            "source": "GitHub Trending",
            "points": 12000,
            "published_at": "2026-09-20T00:00:00+00:00",
            "fetched_at": "2026-09-20T00:00:00+00:00",
            "summary_status": "ok",
            "summary_md": "카테고리: 오픈소스\n> - **한 줄 요약**: 기존 요약",
        }]
        current = [{
            "title": "old-org/agent-tools",
            "url": old[0]["url"],
            "source": "GitHub Trending",
            "points": 4321,
            "weekly_stars": 4321,
            "published_at": "2026-10-04T00:00:00+00:00",
        }]
        feed, pending, new_count = main.update_feed(old, current, "2026-10-04T00:00:00+00:00")
        self.assertEqual((new_count, len(pending)), (0, 0))
        self.assertEqual(feed[0]["weekly_stars"], 4321)
        self.assertEqual(feed[0]["last_seen_at"], "2026-10-04T00:00:00+00:00")
        self.assertEqual(feed[0]["first_seen_at"], "2026-09-20T00:00:00+00:00")
        self.assertEqual(feed[0]["published_at"], "2026-09-20T00:00:00+00:00")
        self.assertIn("기존 요약", feed[0]["summary_md"])

    def test_pending_summary_is_retried_after_leaving_source_top_list(self):
        old = [{
            "title": "Older item", "url": "https://example.com/older",
            "source": "TechCrunch AI", "summary_status": "pending",
            "published_at": "2026-10-03T00:00:00+00:00",
        }]
        _, pending, new_count = main.update_feed(old, [], "2026-10-04T00:00:00+00:00")
        self.assertEqual(new_count, 0)
        self.assertEqual([item["url"] for item in pending], ["https://example.com/older"])

    def test_rss_dates_and_stale_github_items_expire(self):
        self.assertEqual(
            main.parse_date("Sun, 27 Sep 2026 19:57:30 +0000").isoformat(),
            "2026-09-27T19:57:30+00:00",
        )
        feed = [
            {"url": "https://example.com/old", "source": "TechCrunch AI", "published_at": "Sun, 01 Aug 2026 19:57:30 +0000"},
            {"url": "https://github.com/a/agent", "source": "GitHub Trending", "last_seen_at": "2026-09-23T00:00:00+00:00", "summary_md": "카테고리: 오픈소스"},
            {"url": "https://example.com/new", "source": "TechCrunch AI", "published_at": "Sun, 04 Oct 2026 00:00:00 +0000"},
        ]
        result = main.prune_feed(feed, "2026-10-04T03:00:00+00:00")
        self.assertEqual([item["url"] for item in result], ["https://example.com/new"])

    def test_summary_uses_ids_and_retries_missing_items(self):
        class FakeCompletions:
            def create(self, **_):
                message = type("Message", (), {"content": '[{"id":1,"category":"뉴스","one_line":"둘째 요약","insight":"확인"}]'})()
                choice = type("Choice", (), {"message": message})()
                return type("Response", (), {"choices": [choice]})()

        fake_client = type("Client", (), {"chat": type("Chat", (), {"completions": FakeCompletions()})()})()
        items = [
            {"title": "첫째", "url": "https://example.com/1", "source": "TechCrunch AI"},
            {"title": "둘째", "url": "https://example.com/2", "source": "TechCrunch AI"},
        ]
        with patch.object(main, "or_client", fake_client), patch.object(main, "gemini_client", None), patch.dict(main.os.environ, {"OPENROUTER_MODELS": "test-model"}):
            results = main.summarize_batch(items)
        self.assertEqual(set(results), {1})
        self.assertEqual(results[1]["one_line"], "둘째 요약")

    def test_pipeline_updates_feed_and_health_without_repeating_summary(self):
        github_item = {
            "title": "org/agent-tools", "url": "https://github.com/org/agent-tools",
            "source": "GitHub Trending", "points": 75, "weekly_stars": 75,
            "published_at": "2026-10-04T00:00:00+00:00",
        }
        hn_item = {
            "title": "Agent release", "url": "https://example.com/agent",
            "source": "Hacker News", "points": 10,
            "published_at": "2026-10-04T00:00:00+00:00",
        }
        tc_item = {
            "title": "AI release", "url": "https://example.com/ai",
            "source": "TechCrunch AI", "points": 0,
            "published_at": "2026-10-04T00:00:00+00:00",
        }
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            with patch.object(main, "OUTPUT_FILE", directory / "feed.json"), \
                 patch.object(main, "STATUS_FILE", directory / "status.json"), \
                 patch.object(main, "scrape_hackernews", return_value=[hn_item]), \
                 patch.object(main, "scrape_github_trending", return_value=[github_item]), \
                 patch.object(main, "scrape_techcrunch_ai", return_value=[tc_item]), \
                 patch.object(main, "scrape_dcinside", return_value=[]), \
                 patch.object(main, "now_iso", return_value="2026-10-04T03:00:00+00:00"), \
                 patch.object(main, "summarize_batch", return_value={
                     0: {"category": "뉴스", "one_line": "확인된 내용", "insight": "검토 가능"},
                     1: {"category": "오픈소스", "one_line": "확인된 내용", "insight": "검토 가능"},
                     2: {"category": "뉴스", "one_line": "확인된 내용", "insight": "검토 가능"},
                 }) as summarize:
                first = main.run_pipeline()
                self.assertTrue(first["healthy"])
                self.assertEqual(first["new_items"], 3)
                self.assertEqual(first["summaries_pending"], 0)
                self.assertEqual(first["feed_count"], 3)
                second = main.run_pipeline()
                self.assertTrue(second["healthy"])
                self.assertEqual(second["new_items"], 0)
                self.assertEqual(summarize.call_count, 1)


if __name__ == "__main__":
    unittest.main()
