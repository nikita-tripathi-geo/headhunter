import os
import time
from datetime import datetime, timezone

import requests

from telemetry import inc

GITHUB_API = "https://api.github.com"
USER_CACHE = {}
REPO_CACHE = {}
CONTRIB_CACHE = {}


def gh_session():
    s = requests.Session()
    tok = os.environ.get("GITHUB_TOKEN", "").strip()
    if tok:
        s.headers.update({"Authorization": f"Bearer {tok}"})
    s.headers.update({"Accept": "application/vnd.github+json"})
    return s


def gh_get(session, url, params=None, preview=False):
    headers = {}
    if preview:
        headers["Accept"] = "application/vnd.github.cloak-preview+json"
    for attempt in range(5):
        r = session.get(url, params=params, headers=headers)
        if r.status_code == 403 and "rate limit" in r.text.lower():
            reset = int(r.headers.get("X-RateLimit-Reset", str(int(time.time()) + 60)))
            sleep_for = max(1, reset - int(time.time()) + 1)
            time.sleep(min(sleep_for, 60))
            continue
        if r.status_code in (502, 503, 504):
            time.sleep(1.5 * (attempt + 1))
            continue
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()
    return None


def fetch_user(session, login):
    if login in USER_CACHE:
        inc("user_cache_hits")
        return USER_CACHE[login]
    inc("user_fetches")
    data = gh_get(session, f"{GITHUB_API}/users/{login}")
    USER_CACHE[login] = data
    return data


def fetch_user_repos(session, login):
    if login in REPO_CACHE:
        inc("repo_cache_hits")
        return REPO_CACHE[login]
    inc("repo_fetches")
    repos = gh_get(
        session,
        f"{GITHUB_API}/users/{login}/repos",
        params={"per_page": 100, "type": "owner", "sort": "updated"},
    )
    REPO_CACHE[login] = repos or []
    return REPO_CACHE[login]


def fetch_top_contributors(session, full_name, limit=3):
    if not full_name:
        return []
    if full_name in CONTRIB_CACHE:
        inc("contrib_cache_hits")
        return CONTRIB_CACHE[full_name]
    inc("contrib_fetches")
    data = gh_get(
        session,
        f"{GITHUB_API}/repos/{full_name}/contributors",
        params={"per_page": limit, "anon": "false"},
    )
    CONTRIB_CACHE[full_name] = data[:limit] if isinstance(data, list) else []
    return CONTRIB_CACHE[full_name]


def iso_to_age_days(iso_str):
    try:
        dt = datetime.fromisoformat((iso_str or "").replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - dt).days
    except Exception:
        return 9999
