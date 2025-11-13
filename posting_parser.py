import re

# ----------- Lightweight skill lexicon -----------
LANGUAGES = {
    "python","java","javascript","typescript","go","rust","c","c++","c#",
    "scala","kotlin","ruby","php","swift","objective-c","r"
}
FRAMEWORKS = {
    # backend
    "django","flask","fastapi","spring","spring boot","quarkus",
    "express","nestjs","laravel","rails",
    # frontend
    "react","next.js","nextjs","vue","nuxt","angular","svelte",
    # data/ml
    "pandas","numpy","scikit-learn","sklearn","pytorch","tensorflow",
    "keras","xgboost","lightgbm",
    # devops
    "docker","kubernetes","k8s","terraform","ansible","pulumi","helm",
    "github actions","circleci","travis","gitlab ci",
    # systems
    "grpc","protobuf","thrift","postgres","mysql","redis","kafka","rabbitmq",
    "elasticsearch","clickhouse"
}
GENERAL_KEYWORDS = {
    "distributed systems","microservices","rest","grpc","event-driven","real-time",
    "low-latency","concurrency","multithreading","testing","unit tests","integration tests",
    "ci","cd","observability","monitoring","tracing","profiling","performance","scalability",
    "security","cryptography","oauth","oidc","sso","tls",
}


def norm(txt: str) -> str:
    return re.sub(r"\s+", " ", txt.lower()).strip()


def extract_requirements(job_text: str):
    t = norm(job_text)
    found_langs = {w for w in LANGUAGES if re.search(rf"\b{re.escape(w)}\b", t)}
    found_fw = {w for w in FRAMEWORKS if re.search(rf"\b{re.escape(w)}\b", t)}
    found_kw = {w for w in GENERAL_KEYWORDS if re.search(rf"\b{re.escape(w)}\b", t)}

    tokens = set(re.findall(r"[a-zA-Z][a-zA-Z0-9\-\.\+]{1,30}", t))
    if "nextjs" in tokens or "next.js" in tokens:
        found_fw.add("next.js")
    if "k8s" in tokens or "kubernetes" in tokens:
        found_fw.add("kubernetes")
    if "ci" in tokens or "cd" in tokens:
        found_kw.update({"ci","cd"})

    if not found_langs:
        for l in ["python","javascript","typescript","java","go"]:
            if l in tokens:
                found_langs.add(l)
    return {
        "languages": sorted(found_langs),
        "frameworks": sorted(found_fw),
        "keywords": sorted(found_kw)
    }
