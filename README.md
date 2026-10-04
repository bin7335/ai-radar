# AI Radar

[Live site](https://bin7335.github.io/ai-radar/)

AI Radar collects AI and developer news from GitHub Trending, Hacker News, TechCrunch AI, and DCInside. GitHub Actions updates a static JSON feed, and GitHub Pages displays it.

## How updates work

The [scraper workflow](.github/workflows/scraper.yml) runs at 00:17, 06:17, 12:17, and 18:17 KST. It can also be started with `workflow_dispatch`. It runs unit tests, collects each source, summarizes new or previously unsummarized items, commits `data/feed.json` and `data/status.json`, and checks the run's health.

- GitHub Trending uses the weekly page's **stars this week** as its score. Total stars are stored separately. Existing repositories keep their summary while their score and `last_seen_at` are refreshed. A repository need not be newly created to qualify. Entries unseen for seven days expire.
- Hacker News searches recent `AI agent` stories by date. TechCrunch AI reads its RSS feed, including the article description and publication date. DCInside collects recommended posts from two galleries.
- New items are summarized in batches with OpenRouter free models, falling back to Gemini. Model output is matched by item ID. If summarization fails, the item remains visible with `summary_status: pending` and is retried in later runs, even if it leaves the source's current top entries. At most 24 items are attempted per run. Summaries use only titles and source descriptions; they do not claim to have read the article body.
- News and community entries expire after 30 days. The feed keeps up to 20 entries per category, prioritizing recent dates and then source scores.
- Open-Jev is intentionally not part of the production scraper. Its evaluation can proceed separately without blocking feed updates.

## Monitoring and failure alerts

`data/status.json` records the last run, last healthy run, source counts and last successful source times, plus pending summaries. The site shows a warning when the last healthy run is more than 12 hours old or a critical source fails. The workflow fails if GitHub Trending, Hacker News, or TechCrunch AI returns no entries, or if every attempted summary fails.

On a failed workflow run, GitHub Actions opens one `AI Radar 자동 갱신 실패` issue; a later healthy run closes it. GitHub's Actions notification preferences also apply to scheduled run failures. The DCInside source is optional and does not fail the entire workflow.

## Local development

Use Python 3.11 or newer:

```bash
python -m venv .venv
python -m pip install -r src/requirements.txt
python -m unittest discover -s tests -v
```

Set `OPENROUTER_API_KEY` and optionally `GEMINI_API_KEY`, then run `python src/main.py` from the repository root. `OPENROUTER_MODELS` (comma-separated) and `GEMINI_MODEL` can override the model defaults. To inspect the last run's health, use `python src/main.py --check-health`. Serve `index.html` and `data/` with any local static HTTP server.

Do not commit API keys. The workflow reads them from GitHub Actions secrets.
