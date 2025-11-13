from collections import defaultdict

TELEMETRY = defaultdict(int)


def inc(key, amount=1):
    TELEMETRY[key] += amount


def snapshot(*keys):
    return {k: TELEMETRY.get(k, 0) for k in keys}


def discovery_summary():
    keys = [
        "repos_examined",
        "user_owned_repos",
        "org_repos_examined",
        "org_contrib_candidates",
        "contrib_fetches",
        "contrib_cache_hits",
    ]
    return snapshot(*keys)


def ranking_summary():
    keys = [
        "user_fetches",
        "user_cache_hits",
        "repo_fetches",
        "repo_cache_hits",
    ]
    return snapshot(*keys)
