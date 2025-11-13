# Headhunter
Author: Nikita Tripathi

Email: ntripathi99@gmail.com

## Overview
`finder.py` takes an engineering job posting (software, security, reliability, etc.) and generates a list of *exceptional* candidates for this job.
I believe we can find some of the *best software engineers in the world* by looking at the best GitHub repositories - *the perfect candidate* either owns such a project or is one of the top contributors to it.

At a high level, `finder.py` (a) extracts key tech requirements from a job posting, (b) queries GitHub for relevant repos and users, and (c) produces a ranked shortlist of individual engineers (never org accounts) + contact details and notable repos.
The goal is to deliver a fast, API-efficient script that sources strong candidates directly from widely used open-source work.

## Features & Architecture
- **Phase 0 input**: The user provides a job posting, required experience level (in years), account activity, and number of initial and final candidates.
- **Phase 1 discovery**: builds GitHub Search queries, pages through starred/active repos, and harvests owners (individual users) and top contributors (org-owned projects). Ignores forks (often derivative works) and archived repos (abandoned projects).
- **Phase 2 ranking**: looks up each candidate's public profile and a list of top 10 repositories. It applies experience/activity filters and scores them using a set of **heuristics**.
- **Phase 3 output**: writes a detailed text report (or dry-run preview) with scores, repo summaries, and contact info.

> **Module split**:  
>  - `posting_parser.py` handles text normalization + requirement extraction.  
>  - `github_api.py` centralizes authenticated GitHub calls and memoized fetch helpers.  
>  - `discovery.py` owns query construction and repo → candidate harvesting (including org contributors).  
>  - `scoring.py` packages repo heuristics, candidate hydration, and ranking with an optional progress bar.  
>  - `output_utils.py` controls text reports and dry-run previews, while `telemetry.py` standardizes counters.  
>  - `finder.py` is an entry point for Headhunter.


## Setup & Usage
1. **Prerequisites**
   - Python 3.13+ (project uses `.venv`).
   - `requests`; `alive-progress` is optional if you want a progress bar.
   - A GitHub personal access token in `GITHUB_TOKEN` (fine-grained or classic with repo read rights) to avoid low rate limits.
      - Low rate limits = script takes too long.
2. **Environment**
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt  # or pip install requests alive-progress
   export GITHUB_TOKEN=ghp_yourtoken
   ```
3. **Running**
   - Instructions:
     ```bash
     source .venv/bin/activate
     python finder.py --help
     ```
   - Basic run:  
     ```bash
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
   Output defaults to `top_candidates.txt`; change output file with `--out FILENAME`.

## Headhunter Logic

### Discovery
I start every run by forcing the job posting through `posting_parser`.
It aggressively normalizes the text (lowercasing, trimming whitespace) and runs a curated lexicon over it.
This let's us pull out the required languages, frameworks, technologies, etc. without relying on some finicky NLP.
If the posting is vague, the script will fall back to scanning for popular tokens so we still get a reasonable search profile.

Using these requirements, I build GitHub search queries: stack the required `language:` clauses, enforce minimum quality via `stars:>20` and recency via `pushed:>=YYYY-MM-DD`. Finally, I add the top 6 keywords - can't have more, GitHub API limitations.
The idea is to bias toward repos that are both relevant and alive.

When the search API returns the repositories, *I deliberately skip forks and archived projects because they rarely tell me anything about the owner’s original work*.
Human-owned repos go straight into the candidate pool with a weight that takes the number of stars (likes) into account.
For org-owned repos I don’t want to lose track of great engineers, so I fetch the top 2–3 contributors and treat them as individual candidates.
I cap how many org contributors I add so we don’t explode API usage, but it still gives us a list of high-impact projects.

### Ranking
Once I have the seed pool, I investigate each candidate and their top work.
I look at each candidate's account age (to gauge their experience level and enforce `--min-years`), *quality* of repositories (measured using heuristics described below), community support, etc. For recency, I peek at the repos we already collected in discovery and ensure at least one has been pushed within `--max-inactive-days` (unless the user opted out). These gates keep the expensive scoring logic focused on viable humans.

For each remaining candidate I compute a set of heuristics to assign an ***EXCELLENCE SCORE***: language overlap with the job posting (so we reward relevance), repo quality (directory structure, README quality, tests, CI, and stars/community engagement).
I also look at the top three repo scores to capture standout projects, and I give a +0.05 boost if the seed repo had ≥500 stars because that usually indicates significant adoption.

The heuristic weights (0.30 language match, 0.28 repo quality, 0.17 activity, 0.15 followers, 0.10 top repo bonus) were tuned to keep relevance and code quality front and center, with social proof as a secondary factor. Every candidate gets a compact contact bundle (email/blog/X/company/location) so recruiters have something actionable. Finally I sort by the excellence score, cap the list at `--max-candidates`, and either print a dry-run preview or hand the results to the output module for the full report.


## Limitations & Future Work
- The script will take a long time (~2 mins) for a large pool of initial applicants (>200).
- Requires network/DNS access to `api.github.com` and a valid token.
- Experience estimation is still based on account age + repo recency.
   - Can eventually improve by looking at contribution graphs and cross-referencing with X or LinkedIn.
   - This is a future work.

### Workforce optimization using QUBO
**While this project is interesting, it does not look for candidates from first principles.**
It assumes we know the number of candidates we want, their seniority/experience level, and core skill-set. 
There is a better way, which would take significantly longer to implement: *workforce optimization*.

Workforce optimization assumes a set of experts and a task. Each expert has a set of skills and the task has some requirements.
**The objective is to find a set of experts that maximizes skill coverage and at the same time minimize the costs associated with the experts.**
This is a much more rigorous approach, which let's us build an optimal team of engineers from first principles - by crafting a set of job postings from a given requirement and reaching out to exceptional individuals based on these postings.

It is possible to solve this problem using the QUBO algorithm, which can be further optimized using quantum computing.
I believe this project can change the game for tech recruiting.

<!--
## License
TBD – replace this line with the appropriate license notice once finalized.
-->
