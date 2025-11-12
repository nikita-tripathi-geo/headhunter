#!/usr/bin/env python3
# finder.py
import argparse
import os
import sys
import time
import math
import re
from datetime import datetime, timezone, timedelta
from collections import Counter, defaultdict

import requests

GITHUB_API = "https://api.github.com"

# ----------- Lightweight skill lexicon -----------
LANGUAGES = {
    "python","java","javascript","typescript","go","rust","c","c++","c#",
    "scala","kotlin","ruby","php","swift","objective-c","r"
}
FRAMEWORKS = {
    # backend
    "django","flask","fastapi","spring","spring boot","quarkus","express","nestjs","laravel","rails",
    # frontend
    "react","next.js","nextjs","vue","nuxt","angular","svelte",
    # data/ml
    "pandas","numpy","scikit-learn","sklearn","pytorch","tensorflow","keras","xgboost","lightgbm",
    # devops
    "docker","kubernetes","k8s","terraform","ansible","pulumi","helm","github actions","circleci","travis","gitlab ci",
    # systems
    "grpc","protobuf","thrift","postgres","mysql","redis","kafka","rabbitmq","elasticsearch","clickhouse"
}
GENERAL_KEYWORDS = {
    "distributed systems","microservices","rest","grpc","event-driven","real-time",
    "low-latency","concurrency","multithreading","testing","unit tests","integration tests",
    "ci","cd","observability","monitoring","tracing","profiling","performance","scalability",
    "security","cryptography","oauth","oidc","sso","tls",
}

# Normalize helper
def norm(txt: str) -> str:
    return re.sub(r"\s+", " ", txt.lower()).strip()

def extract_requirements(job_text: str):
    t = norm(job_text)
    found_langs = {w for w in LANGUAGES if re.search(rf"\b{re.escape(w)}\b", t)}
    found_fw = {w for w in FRAMEWORKS if re.search(rf"\b{re.escape(w)}\b", t)}
    found_kw = {w for w in GENERAL_KEYWORDS if re.search(rf"\b{re.escape(w)}\b", t)}

    # rough fallback: pull common tech-looking tokens
    tokens = set(re.findall(r"[a-zA-Z][a-zA-Z0-9\-\.\+]{1,30}", t))
    # collapse variants
    if "nextjs" in tokens or "next.js" in tokens:
        found_fw.add("next.js")
    if "k8s" in tokens or "kubernetes" in tokens:
        found_fw.add("kubernetes")
    if "ci" in tokens or "cd" in tokens:
        found_kw.update({"ci","cd"})

    # pick top languages if none found
    if not found_langs:
        # crude inference by popularity
        for l in ["python","javascript","typescript","java","go"]:
            if l in tokens:
                found_langs.add(l)
    return {
        "languages": sorted(found_langs),
        "frameworks": sorted(found_fw),
        "keywords": sorted(found_kw)
    }

# GitHub session with auth + simple retry
def gh_session():
    s = requests.Session()
    tok = os.environ.get("GITHUB_TOKEN","").strip()
    if tok:
        s.headers.update({"Authorization": f"Bearer {tok}"})
    s.headers.update({"Accept": "application/vnd.github+json"})
    return s

def gh_get(s: requests.Session, url: str, params=None, preview=False):
    headers = {}
    if preview:
        headers["Accept"] = "application/vnd.github.cloak-preview+json"
    for attempt in range(5):
        r = s.get(url, params=params, headers=headers)
        if r.status_code == 403 and "rate limit" in r.text.lower():
            reset = int(r.headers.get("X-RateLimit-Reset", str(int(time.time())+60)))
            sleep_for = max(1, reset - int(time.time()) + 1)
            time.sleep(min(sleep_for, 60))  # cap sleep
            continue
        if r.status_code in (502, 503, 504):
            time.sleep(1.5 * (attempt+1))
            continue
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()
    return None

def iso_to_age_days(iso_str):
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z","+00:00"))
        return (datetime.now(timezone.utc) - dt).days
    except Exception:
        return 9999

# ----------- Candidate discovery -----------
def build_repo_query(reqs, page):
    """
    Build a GitHub search query that matches the pattern the web UI accepts well:
    language:Go language:Python stars:>20 pushed:>=YYYY-MM-DD (kw1 OR kw2 ...) in:description,readme
    """

    langs = [l for l in reqs["languages"] if l]
    kws = [w for w in (reqs["frameworks"] + reqs["keywords"]) if w]

    # Quote multi-word terms ("github actions") but leave single tokens bare
    def qword(s: str) -> str:
        s = s.strip()
        return f'"{s}"' if " " in s else s

    # 1) languages: just list them; GitHub treats multiple language: as OR
    lang_clause = " ".join(f"language:{qword(l)}" for l in langs[:6])

    # 2) quality/recency gates
    pushed_since = (datetime.utcnow() - timedelta(days=365)).date().isoformat()
    gates = f"stars:>20 pushed:>={pushed_since}"

    # 3) keywords OR-group, then one in: qualifier applied to the group
    picked_kws = [qword(w) for w in kws[:6]] or []
    kw_clause = ""
    if picked_kws:
        kw_clause = "(" + " OR ".join(picked_kws) + ") in:description,readme"

    # Assemble; omit blanks cleanly
    parts = [p for p in [lang_clause, gates, kw_clause] if p]
    q = " ".join(parts)  # let requests handle URL encoding

    return {
        "q": q,
        "sort": "stars",
        "order": "desc",
        "per_page": 50,   # 50 is plenty and friendlier to rate limits
        "page": page
    }

# def build_repo_query(reqs, page):
#     # Bias: stars>20, pushed recently, match any of languages & some keywords in name/desc/readme
#     langs = reqs["languages"] or []
#     kws = reqs["frameworks"] + reqs["keywords"]
#     print(reqs)

#     q_parts = []
#     if langs:
#         lang_clause = " OR ".join([f"language:{l}" for l in langs])
#         q_parts.append(lang_clause)
#     # prefer actively maintained repos
#     q_parts.append("stars:>1") # TODO reset stars back to 20
#     # GitHub search has size limits; include generic keywords lightly
#     for w in kws[:6]:
#         # search in name/description/readme
#         q_parts.append(f"{w} in:name,description,readme")

#     q = "+".join([re.sub(r"\s+", "+", p) for p in q_parts if p])
#     return {
#         "q": q,
#         "sort": "stars",
#         "order": "desc",
#         "per_page": 100,
#         "page": page
#     }

def discover_candidates_from_repos(s, reqs, max_candidates=50, max_pages=3):
    owners = Counter()
    owner_repos = {}
    for page in range(1, max_pages+1):
        params = build_repo_query(reqs, page)
        # print(params)
        data = gh_get(s, f"{GITHUB_API}/search/repositories", params=params)
        # print(data)
        if not data or "items" not in data:
            break
        for repo in data["items"]:
            owner = repo["owner"]["login"]
            if repo.get("fork") or repo["owner"]["type"] != "User":
                continue
            owners[owner] += 1 + min(5, int(repo.get("stargazers_count",0)/1000))

            if owner not in owner_repos:
                owner_repos[owner] = {
                    "full_name": repo.get("full_name"),
                    "html_url": repo["owner"]["url"],
                    "stargazers_count": repo.get("stargazers_count",0),
                    "owner": repo.get("owner"),      # HACK maybe remove
                    "repositories": []
                }
            owner_repos[owner]["repositories"].append(repo)
            # Track total stars
            owner_repos[owner]["stargazers_count"] += repo.get("stargazers_count",0)
        if len(owners) >= max_candidates:
            break
    # pick top owners
    top = [u for u,_ in owners.most_common(max_candidates)]
    return top, owner_repos

# ----------- Scoring heuristics -----------
def language_match_score(user_langs, req_langs):
    if not req_langs:
        return 0.2  # small baseline if job didn’t specify
    inter = len(set(u.lower() for u in user_langs) & set(l.lower() for l in req_langs))
    return inter / max(1, len(set(req_langs)))

def repo_quality_heuristics(repo):
    # Inputs: /users/:u/repos item
    stars = repo.get("stargazers_count",0)
    forks = repo.get("forks_count",0)
    open_issues = repo.get("open_issues_count",0)
    pushed_age = iso_to_age_days(repo.get("pushed_at") or repo.get("updated_at") or repo.get("created_at") or "")
    recently_active = 1.0 if pushed_age <= 90 else 0.0
    # Penalize forks and archived
    if repo.get("fork") or repo.get("archived"):
        return 0.0
    # Cheap signals for tests/ci/readme based on file/directory hints in description/name
    desc = norm((repo.get("description") or "") + " " + (repo.get("name") or ""))
    readme_hint = 0.2  # we’ll bump later if we actually check readme (skipped to cut API calls)
    has_test_hint = 0.3 if re.search(r"\btest(s)?\b", desc) else 0.0
    ci_hint = 0.3 if any(k in desc for k in ["github actions","ci","travis","circleci"]) else 0.0

    # star curve: diminishing returns
    star_score = math.log10(max(1, stars))
    fork_score = 0.2 * math.log10(max(1, forks))
    issue_penalty = 0.0
    if open_issues > 100 and stars < 1000:
        issue_penalty = 0.2

    score = (
        0.45 * min(1.5, star_score) +
        0.10 * min(1.0, fork_score) +
        0.20 * recently_active +
        0.10 * has_test_hint +
        0.10 * ci_hint +
        0.05 * readme_hint
    ) - issue_penalty
    return max(0.0, score)

def collect_user_features(s, u, reqs, max_repos=10):

    # Pull owned repos (updated first)
    repos = gh_get(s, f"{GITHUB_API}/users/{u["login"]}/repos", params={"per_page": 100, "type":"owner","sort":"updated"})
    if repos is None:
        repos = []

    # Filter noise
    clean = [r for r in repos if not r.get("fork") and not r.get("archived")]
    # take top N by stars
    clean.sort(key=lambda r: r.get("stargazers_count",0), reverse=True)
    top_repos = clean[:max_repos]

    # Language distribution
    lang_counter = Counter()
    for r in top_repos:
        if r.get("language"):
            lang_counter[r["language"]] += 1
    user_langs = [l for l,_ in lang_counter.most_common(8)]

    # Repo quality stats
    repo_scores = [repo_quality_heuristics(r) for r in top_repos] or [0.0]
    avg_repo_quality = sum(repo_scores)/len(repo_scores)
    top3_sum = sum(sorted(repo_scores, reverse=True)[:3])

    # Activity recency
    pushed_ages = [iso_to_age_days(r.get("pushed_at") or "") for r in top_repos] or [9999]
    recent_activity = 1.0 if min(pushed_ages) <= 30 else (0.5 if min(pushed_ages) <= 90 else 0.0)

    followers = u.get("followers",0)
    followers_score = min(1.0, math.log10(max(1, followers))/3.0)  # ~1.0 at 1000+

    lang_match = language_match_score(user_langs, reqs["languages"])

    # Final score (weights tuned for “first cut”)
    score = (
        0.30 * lang_match +
        0.28 * avg_repo_quality +
        0.17 * recent_activity +
        0.15 * followers_score +
        0.10 * min(1.0, top3_sum/3.0)
    )

    contact = {
        "email": (u.get("email") or "")[:120],
        "blog": (u.get("blog") or "")[:200],
        "x": f"https://x.com/{u['twitter_username']}" if u.get("twitter_username") else "",
        "company": (u.get("company") or "")[:120],
        "location": (u.get("location") or "")[:120],
    }

    return {
        "login": u["login"],
        "html_url": u["html_url"],
        "name": u.get("name") or "",
        "followers": followers,
        "public_repos": u.get("public_repos",0),
        "score": round(score, 4),
        "languages": user_langs,
        "top_repo_names": [r.get("full_name","") for r in top_repos[:3]],
        "contact": contact
    }

def rank_candidates(s, usernames, reqs, owner_repos, limit):
    results = []
    for i, u in enumerate(usernames):
        user = owner_repos[u]["owner"]
        # print(user)
        feat = collect_user_features(s, user, reqs)
        if not feat:
            continue
        # small bump if their “seed” repo was strong
        seed = owner_repos.get(u)
        if seed and seed.get("stargazers_count",0) >= 500:
            feat["score"] = round(min(1.0, feat["score"] + 0.05), 4)
        results.append(feat)
        # Be polite to API
        if (i+1) % 8 == 0:
            time.sleep(0.6)
    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:limit]

def write_text_output(path, reqs, ranked, owner_toprepo):
    with open(path, "w", encoding="utf-8") as f:
        f.write("Top candidates (GitHub-only, heuristic v0.1)\n")
        f.write("Requirements inferred:\n")
        f.write(f"  Languages: {', '.join(reqs['languages']) or '(none)'}\n")
        f.write(f"  Frameworks: {', '.join(reqs['frameworks']) or '(none)'}\n")
        f.write(f"  Keywords: {', '.join(reqs['keywords']) or '(none)'}\n")
        f.write("\n")

        for idx, c in enumerate(ranked, 1):
            seed = owner_toprepo.get(c["login"])
            f.write(f"{idx}. {c['name'] or c['login']} — score {c['score']}\n")
            f.write(f"   GitHub: {c['html_url']}\n")
            if seed:
                f.write(f"   Notable repo: {seed['full_name']} (⭐ {seed.get('stargazers_count',0)}) {seed['html_url']}\n")
            if c["top_repo_names"]:
                f.write(f"   Top repos: {', '.join(c['top_repo_names'])}\n")
            if c["languages"]:
                f.write(f"   Languages: {', '.join(c['languages'])}\n")
            contact = c["contact"]
            contact_lines = []
            if contact.get("email"):
                contact_lines.append(f"email: {contact['email']}")
            if contact.get("blog"):
                contact_lines.append(f"site: {contact['blog']}")
            if contact.get("x"):
                contact_lines.append(f"X: {contact['x']}")
            if contact.get("company"):
                contact_lines.append(f"company: {contact['company']}")
            if contact.get("location"):
                contact_lines.append(f"location: {contact['location']}")
            if contact_lines:
                f.write("   Contact: " + " | ".join(contact_lines) + "\n")
            f.write("\n")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--job-file", required=True, help="Path to job posting text")
    ap.add_argument("--out", default="top_candidates.txt")
    ap.add_argument("--max-candidates", type=int, default=10)
    ap.add_argument("--seed-pool", type=int, default=120, help="Max initial candidate pool before scoring")
    args = ap.parse_args()

    with open(args.job_file, "r", encoding="utf-8") as fh:
        job_text = fh.read()

    reqs = extract_requirements(job_text)
    s = gh_session()

    # Phase 1: discover owners via repo search
    print("Phase 1 - Discover candidates via top-rated GitHub repositories.")

    owners, owner_repos = discover_candidates_from_repos(
        s, reqs, max_candidates=max(args.seed_pool, args.max_candidates*8), max_pages=3
    )

    if not owners:
        print("No candidates discovered from GitHub search. Loosen requirements.", file=sys.stderr)
        sys.exit(2)

    print(f"Phase 1 complete. Identified {len(owners)} initial candidates.")
    # print(owners)
    # print(owner_repos)

    # Phase 2: rank
    print("Phase 2 - Rank candidates using a heuristic (code quality, experience level, adoption).")
    ranked = rank_candidates(s, owners, reqs, owner_repos, args.max_candidates)
    print("Phase 2 complete.")

    # Phase 3: output
    print("Phase 3 - Output the top candidates.")

    write_text_output(args.out, reqs, ranked, owner_repos)
    print(f"Wrote {len(ranked)} candidates to {args.out}")

    print("Phase 3 complete.")

if __name__ == "__main__":
    main()
