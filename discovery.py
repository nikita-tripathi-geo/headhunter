from collections import Counter
from datetime import datetime, timedelta

from github_api import (
    GITHUB_API,
    gh_get,
    fetch_top_contributors,
)
from telemetry import inc


def build_repo_query(reqs, page):
    langs = [l for l in reqs["languages"] if l]
    kws = [w for w in (reqs["frameworks"] + reqs["keywords"]) if w]

    def qword(s):
        s = s.strip()
        return f'"{s}"' if " " in s else s

    lang_clause = " ".join(f"language:{qword(l)}" for l in langs[:6])
    pushed_since = (datetime.utcnow() - timedelta(days=365)).date().isoformat()
    gates = f"stars:>20 pushed:>={pushed_since}"
    picked_kws = [qword(w) for w in kws[:6]] or []
    kw_clause = ""
    if picked_kws:
        kw_clause = "(" + " OR ".join(picked_kws) + ") in:description,readme"

    parts = [p for p in [lang_clause, gates, kw_clause] if p]
    q = " ".join(parts)
    return {
        "q": q,
        "sort": "stars",
        "order": "desc",
        "per_page": 50,
        "page": page,
    }


def discover_candidates_from_repos(session, reqs, max_candidates=50, max_pages=3):
    owners = Counter()
    owner_repos = {}
    org_contrib_additions = 0
    max_org_contribs = max_candidates
    stop = False
    for page in range(1, max_pages + 1):
        if stop:
            break
        params = build_repo_query(reqs, page)
        data = gh_get(session, f"{GITHUB_API}/search/repositories", params=params)
        if not data or "items" not in data:
            break
        for repo in data["items"]:
            inc("repos_examined")
            if len(owners) >= max_candidates:
                stop = True
                break
            if repo.get("fork"):
                continue
            owner_info = repo["owner"]
            weight = 1 + min(5, int(repo.get("stargazers_count", 0) / 1000))
            if owner_info["type"] == "User":
                inc("user_owned_repos")
                owner = owner_info["login"]
                owners[owner] += weight
                if owner not in owner_repos:
                    owner_repos[owner] = {
                        "full_name": repo.get("full_name"),
                        "html_url": repo.get("html_url"),
                        "stargazers_count": repo.get("stargazers_count", 0),
                        "total_stars": 0,
                        "owner": owner_info,
                        "repositories": [],
                    }
                owner_repos[owner]["repositories"].append(repo)
                owner_repos[owner]["total_stars"] += repo.get("stargazers_count", 0)
            else:
                inc("org_repos_examined")
                contributors = fetch_top_contributors(session, repo.get("full_name", ""), limit=3)
                for contrib in contributors:
                    if not contrib or contrib.get("type") != "User":
                        continue
                    login = contrib["login"]
                    is_new = login not in owner_repos
                    if is_new and org_contrib_additions >= max_org_contribs:
                        continue
                    owners[login] += weight
                    if is_new:
                        owner_repos[login] = {
                            "full_name": repo.get("full_name"),
                            "html_url": repo.get("html_url"),
                            "stargazers_count": repo.get("stargazers_count", 0),
                            "total_stars": 0,
                            "owner": contrib,
                            "repositories": [],
                        }
                        org_contrib_additions += 1
                        inc("org_contrib_candidates")
                    owner_repos[login]["repositories"].append(repo)
                    owner_repos[login]["total_stars"] += repo.get("stargazers_count", 0)
                    if len(owners) >= max_candidates or org_contrib_additions >= max_org_contribs:
                        break
                if len(owners) >= max_candidates:
                    stop = True
                    break
        if len(owners) >= max_candidates:
            break
    top = [u for u, _ in owners.most_common(max_candidates)]
    return top, owner_repos
