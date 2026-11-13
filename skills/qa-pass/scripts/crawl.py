# ruff: noqa: T201, INP001 - command-line QA scripts, not app code
"""Follow every in-app link as each user and report error pages and broken links.

Usage: python3 skills/qa-pass/scripts/crawl.py alice bob --langs en fr [--limit 600]
Run it alone: the debug toolbar raises spurious 500s under parallel requests.
"""

import argparse
import re
from collections import deque
from urllib.parse import urldefrag
from urllib.parse import urljoin
from urllib.parse import urlparse

from qa_common import BASE_URL
from qa_common import login

# Side effects, assets and template literals left in inline scripts
SKIP = re.compile(
    r"logout|unsubscribe|/static|/media/|__debug__|\.ics|/admin/|regenerate|disable|/i18n/|\$\{"
)


def crawl(session, start: str, limit: int) -> tuple[set[str], list[tuple[str, str]]]:
    seen, queue, problems = set(), deque([start]), []
    host = urlparse(BASE_URL).netloc
    while queue and len(seen) < limit:
        url = queue.popleft()
        if url in seen:
            continue
        seen.add(url)
        response = session.get(BASE_URL + url, allow_redirects=False, timeout=60)
        location = response.headers.get("Location", "")
        if response.status_code >= 400 or "/accounts/login/" in location:
            problems.append((url, f"{response.status_code} {location}".strip()))
        if response.status_code != 200 or "text/html" not in response.headers.get(
            "Content-Type", ""
        ):
            continue
        for href in re.findall(r'(?:href|hx-get)="([^"]+)"', response.text):
            target = urlparse(urldefrag(urljoin(BASE_URL + url, href.replace("&amp;", "&")))[0])
            if target.netloc == host and not SKIP.search(target.path):
                path = target.path + (f"?{target.query}" if target.query else "")
                if path not in seen:
                    queue.append(path)
    return seen, problems


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("users", nargs="+")
    parser.add_argument("--langs", nargs="+", default=["en", "fr"])
    parser.add_argument("--limit", type=int, default=600)
    args = parser.parse_args()
    for user in args.users:
        session = login(user)
        for lang in args.langs:
            seen, problems = crawl(session, f"/{lang}/", args.limit)
            print(f"{user} [{lang}]: {len(seen)} pages, {len(problems)} problems")
            for url, detail in problems:
                print(f"  {detail}  {url}")


if __name__ == "__main__":
    main()
