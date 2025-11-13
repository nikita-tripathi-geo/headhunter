# GitHub Talent Finder

## Overview
`finder.py` ingests a plain-text job posting, auto-extracts the key tech requirements, queries GitHub for relevant repos and users, and produces a ranked shortlist of individual engineers (never org accounts) including contact details and notable repos. The goal is to deliver a fast, API-efficient first pass at sourcing strong candidates directly from open-source work.

## Features & Architecture
- **Requirements extraction**: lightweight lexicon + regex fallbacks to pull languages, frameworks, and core keywords from any posting.
- **Phase 1 discovery**: builds GitHub Search queries, pages through starred/active repos, and now harvests top contributors from org-owned projects to widen the funnel without touching forks or archived repos.
- **Phase 2 ranking**: hydrates each candidate with full `/users/{login}` + repo lists (memoized), applies experience/recency filters, and scores them using deterministic heuristics; telemetry counters make API usage transparent.
- **Phase 3 output**: writes a detailed text report (or dry-run preview) with scores, repo summaries, and contact info.
- **Operational helpers**: memoization layers to avoid redundant calls, optional dry-run preview, and simple telemetry summaries printed after each phase.

## Setup & Usage
1. **Prerequisites**
   - Python 3.11+ (project uses `.venv`).
   - `requests` (installed in the venv); `alive-progress` is optional if you want a progress bar.
   - A GitHub personal access token in `GITHUB_TOKEN` (fine-grained or classic with repo read rights) to avoid low rate limits.
2. **Environment**
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt  # or pip install requests alive-progress
   export GITHUB_TOKEN=ghp_yourtoken
   ```
3. **Running**
   - Basic run:  
     ```bash
     source .venv/bin/activate
     python finder.py --job-file posting1.txt
     ```
   - Tune candidate pool / experience filters:  
     ```bash
     python finder.py --job-file posting2.txt --seed-pool 200 --max-candidates 15 --min-years 4 --max-inactive-days 120
     ```
   - Dry-run preview (no file write):  
     ```bash
     python finder.py --job-file posting2.txt --max-candidates 5 --dry-run
     ```
   Output defaults to `top_candidates.txt`; override with `--out`.

## Headhunter Logic

### Discovery
1. Normalize the job posting and extract languages/frameworks/keywords via lexicons + regex helpers (with fallbacks for popular tokens).
2. Construct GitHub Search query strings like `language:Go language:Python stars:>20 pushed:>=YYYY-MM-DD (kw1 OR kw2) in:description,readme`.
3. Page through repo results (default 3×50), skipping forks. Human-owned repos immediately seed the candidate pool; org-owned repos trigger a `/contributors?per_page=3` fetch to pull the top individual contributors.
4. Maintain per-owner structures with notable repo, cumulative stars, and the repo list to reuse later. Memoization and early-stop logic limit API calls once the `--seed-pool` threshold is hit.

### Ranking
1. Hydrate each candidate via `/users/{login}` (cached) and enforce human-only criteria plus account-age (`--min-years`) and recent-activity (`--max-inactive-days`) thresholds using the repo metadata captured earlier.
2. Fetch each user’s owner repos (cached, sorted by stars), discard forks/archived, and compute:
   - Language frequency for requirement overlap.
   - Repo quality heuristics (log stars/forks, recency, CI/test hints).
   - Recent activity signal based on push dates.
   - Follower score (log10 curve).
   - Top-repo strength bonus and seed-repo star bonus (≥500 stars).
3. Aggregate the weighted score, capture contact fields, and sort descending, returning the top `--max-candidates`. Results are either written to disk or printed in dry-run mode.

## Telemetry & Performance
After Phase 1 and Phase 2 the script prints counters such as repos examined, org repos processed, contributor candidates added, and cache hits vs. fetches for user/repo hydration. These snapshots make it easy to see whether the run was org-heavy (and thus API-expensive), whether caches are effective, and where bottlenecks appear without adding external tooling.

## Limitations & Future Work
- REST-only implementation; no GraphQL batching yet, so large org-heavy runs can still be API-bound.
- Requires network/DNS access to `api.github.com` and a valid PAT; failures are surfaced but not retried beyond the current simple backoff.
- Experience estimation is still based on account age + repo recency; deeper contribution graphs remain future work.
- Remaining roadmap items from the design doc: richer output (total stars per candidate, inline repo URLs already added but more polish desired), smarter contributor sourcing, optional telemetry persistence, and eventual GraphQL-based hydration.

## License
TBD – replace this line with the appropriate license notice once finalized.
