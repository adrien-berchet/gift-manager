# ruff: noqa: T201, INP001, EM101, TRY003 - command-line QA scripts, not app code
"""Check what one ordinary user can open of another user's pages.

Crawls both users, then requests every URL with an object id that only the other user reaches.
A 200 is not automatically a leak (create forms ignore foreign query values): the script
prints the names it finds in those pages so the agent can confirm or dismiss each one.

Usage: python3 skills/qa-pass/scripts/cross_user_access.py alice bob --names "Mom" "Novel"
Never use a superuser here: it bypasses permissions.
"""

import argparse

from crawl import crawl
from qa_common import BASE_URL
from qa_common import SUPERUSERS
from qa_common import UUID_RE
from qa_common import login
from qa_common import visible_text


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("first")
    parser.add_argument("second")
    parser.add_argument("--names", nargs="*", default=[], help="private names to look for")
    args = parser.parse_args()
    if {args.first, args.second} & SUPERUSERS:
        raise SystemExit("Use two ordinary users: a superuser bypasses permission checks")

    sessions = {user: login(user) for user in (args.first, args.second)}
    reached = {user: crawl(session, "/en/", 600)[0] for user, session in sessions.items()}
    for owner, visitor in ((args.first, args.second), (args.second, args.first)):
        foreign = sorted(u for u in reached[owner] - reached[visitor] if UUID_RE.search(u))
        print(f"{visitor} requesting {len(foreign)} URLs only {owner} reaches:")
        for url in foreign:
            response = sessions[visitor].get(BASE_URL + url, allow_redirects=False, timeout=60)
            if response.status_code != 200:
                continue
            text = visible_text(response.text)
            found = [name for name in args.names if name in text]
            print(f"  200 {url}" + (f"  contains: {', '.join(found)}" if found else ""))


if __name__ == "__main__":
    main()
