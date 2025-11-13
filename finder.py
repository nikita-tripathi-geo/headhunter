#!/usr/bin/env python3
import argparse
import sys

from discovery import discover_candidates_from_repos
from github_api import gh_session
from output_utils import print_preview, write_text_output
from posting_parser import extract_requirements
from scoring import rank_candidates
from telemetry import discovery_summary, ranking_summary


def format_summary(label, data):
    parts = [f"{k}={v}" for k, v in data.items()]
    print(f"{label}: " + ", ".join(parts))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--job-file", required=True, help="Path to job posting text")
    ap.add_argument("--out", default="top_candidates.txt")
    ap.add_argument("--max-candidates", type=int, default=10)
    ap.add_argument("--seed-pool", type=int, default=120, help="Max initial candidate pool before scoring")
    ap.add_argument("--min-years", type=float, default=3.0, help="Minimum account age in years")
    ap.add_argument("--max-inactive-days", type=int, default=180, help="Maximum days since last repo push (<=0 disables)")
    ap.add_argument("--dry-run", action="store_true", help="Print results instead of writing output file")
    args = ap.parse_args()

    with open(args.job_file, "r", encoding="utf-8") as fh:
        job_text = fh.read()

    reqs = extract_requirements(job_text)
    session = gh_session()

    print("Phase 1 - Discover candidates via top-rated GitHub repositories.")
    owners, owner_repos = discover_candidates_from_repos(
        session,
        reqs,
        max_candidates=max(args.seed_pool, args.max_candidates * 4),
        max_pages=3,
    )
    if not owners:
        print("No candidates discovered from GitHub search. Loosen requirements.", file=sys.stderr)
        sys.exit(2)
    print(f"Phase 1 complete. Identified {len(owners)} initial candidates.")
    format_summary("Discovery telemetry", discovery_summary())

    print("Phase 2 - Rank candidates using a heuristic (code quality, experience level, adoption).")
    max_inactive_days = args.max_inactive_days if args.max_inactive_days > 0 else None
    ranked = rank_candidates(
        session,
        owners,
        reqs,
        owner_repos,
        args.max_candidates,
        args.min_years,
        max_inactive_days,
    )
    print("Phase 2 complete.")
    format_summary("Ranking telemetry", ranking_summary())

    print("Phase 3 - Output the top candidates.")
    if args.dry_run:
        print_preview(reqs, ranked, limit=args.max_candidates)
    else:
        write_text_output(args.out, reqs, ranked, owner_repos)
        print(f"Wrote {len(ranked)} candidates to {args.out}")
    print("Phase 3 complete.")


if __name__ == "__main__":
    main()
