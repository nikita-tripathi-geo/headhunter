import math
import re
import time
from collections import Counter
from contextlib import contextmanager

try:
    from alive_progress import alive_bar
except ImportError:
    alive_bar = None

from github_api import fetch_user, fetch_user_repos, iso_to_age_days


def language_match_score(user_langs, req_langs):
    if not req_langs:
        return 0.2
    inter = len(set(u.lower() for u in user_langs) & set(l.lower() for l in req_langs))
    return inter / max(1, len(set(req_langs)))


def repo_quality_heuristics(repo):
    stars = repo.get("stargazers_count", 0)
    forks = repo.get("forks_count", 0)
    open_issues = repo.get("open_issues_count", 0)
    pushed_age = iso_to_age_days(
        repo.get("pushed_at") or repo.get("updated_at") or repo.get("created_at") or ""
    )
    recently_active = 1.0 if pushed_age <= 90 else 0.0
    if repo.get("fork") or repo.get("archived"):
        return 0.0
    desc = ((repo.get("description") or "") + " " + (repo.get("name") or "")).lower()
    readme_hint = 0.2
    has_test_hint = 0.3 if re.search(r"\btest(s)?\b", desc) else 0.0
    ci_hint = 0.3 if any(k in desc for k in ["github actions", "ci", "travis", "circleci"]) else 0.0
    star_score = math.log10(max(1, stars))
    fork_score = 0.2 * math.log10(max(1, forks))
    issue_penalty = 0.2 if open_issues > 100 and stars < 1000 else 0.0
    score = (
        0.45 * min(1.5, star_score)
        + 0.10 * min(1.0, fork_score)
        + 0.20 * recently_active
        + 0.10 * has_test_hint
        + 0.10 * ci_hint
        + 0.05 * readme_hint
    ) - issue_penalty
    return max(0.0, score)


def collect_user_features(session, user, reqs, max_repos=10):
    repos = fetch_user_repos(session, user["login"])
    clean = [r for r in repos if not r.get("fork") and not r.get("archived")]
    clean.sort(key=lambda r: r.get("stargazers_count", 0), reverse=True)
    top_repos = clean[:max_repos]

    lang_counter = Counter()
    for r in top_repos:
        if r.get("language"):
            lang_counter[r["language"]] += 1
    user_langs = [l for l, _ in lang_counter.most_common(8)]

    repo_scores = [repo_quality_heuristics(r) for r in top_repos] or [0.0]
    avg_repo_quality = sum(repo_scores) / len(repo_scores)
    top3_sum = sum(sorted(repo_scores, reverse=True)[:3])

    pushed_ages = [iso_to_age_days(r.get("pushed_at") or "") for r in top_repos] or [9999]
    recent_activity = 1.0 if min(pushed_ages) <= 30 else (0.5 if min(pushed_ages) <= 90 else 0.0)

    followers = user.get("followers", 0)
    followers_score = min(1.0, math.log10(max(1, followers)) / 3.0)

    lang_match = language_match_score(user_langs, reqs["languages"])

    score = (
        0.30 * lang_match
        + 0.28 * avg_repo_quality
        + 0.17 * recent_activity
        + 0.15 * followers_score
        + 0.10 * min(1.0, top3_sum / 3.0)
    )

    contact = {
        "email": (user.get("email") or "")[:120],
        "blog": (user.get("blog") or "")[:200],
        "x": f"https://x.com/{user['twitter_username']}" if user.get("twitter_username") else "",
        "company": (user.get("company") or "")[:120],
        "location": (user.get("location") or "")[:120],
    }

    return {
        "login": user["login"],
        "html_url": user["html_url"],
        "name": user.get("name") or "",
        "followers": followers,
        "public_repos": user.get("public_repos", 0),
        "score": round(score, 4),
        "languages": user_langs,
        "top_repo_names": [r.get("full_name", "") for r in top_repos[:3]],
        "contact": contact,
    }


@contextmanager
def noop_bar(total, title=""):
    def step():
        return None

    yield step


def rank_candidates(session, usernames, reqs, owner_repos, limit, min_years, max_inactive_days):
    if not usernames:
        return []
    bar_factory = alive_bar if alive_bar else noop_bar
    results = []
    with bar_factory(len(usernames), title="Ranking candidates") as bar:
        for i, login in enumerate(usernames):
            seed = owner_repos.get(login)
            if not seed:
                bar()
                continue
            user = fetch_user(session, login)
            if not user or user.get("type") != "User":
                bar()
                continue
            account_age_days = iso_to_age_days(user.get("created_at", ""))
            if account_age_days < int(min_years * 365):
                bar()
                continue
            if max_inactive_days is not None:
                repo_push_ages = [
                    iso_to_age_days(
                        r.get("pushed_at") or r.get("updated_at") or r.get("created_at") or ""
                    )
                    for r in seed.get("repositories", [])
                    if r
                ]
                if repo_push_ages and min(repo_push_ages) > max_inactive_days:
                    bar()
                    continue
            feat = collect_user_features(session, user, reqs)
            if not feat:
                bar()
                continue
            if seed and seed.get("stargazers_count", 0) >= 500:
                feat["score"] = round(min(1.0, feat["score"] + 0.05), 4)
            feat["total_stars"] = seed.get("total_stars", 0)
            results.append(feat)
            if (i + 1) % 8 == 0:
                time.sleep(0.6)
            bar()
    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:limit]
