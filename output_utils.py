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
            if c.get("total_stars") is not None:
                f.write(f"   Total stars (matched repos): {c.get('total_stars', 0)}\n")
            if seed:
                repo_url = seed.get("html_url") or ""
                f.write(
                    f"   Notable repo: {seed['full_name']} (⭐ {seed.get('stargazers_count',0)}) "
                    f"{repo_url}\n"
                )
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


def print_preview(reqs, ranked, limit=5):
    print("Dry run preview")
    print(f"Languages: {', '.join(reqs['languages']) or '(none)'}")
    print(f"Frameworks: {', '.join(reqs['frameworks']) or '(none)'}")
    print(f"Keywords: {', '.join(reqs['keywords']) or '(none)'}")
    print("Top candidates:")
    for c in ranked[:limit]:
        print(f"  - {c['name'] or c['login']} ({c['score']}) — {c['html_url']}")
