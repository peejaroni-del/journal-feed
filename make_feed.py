#!/usr/bin/env python3
"""Build feed.xml (RSS 2.0) of recent articles for a list of journals via Crossref.

Edit JOURNALS below. Use either the print or electronic ISSN; Crossref accepts both.
"""
import datetime as dt
import re
import sys
from email.utils import format_datetime
from html import unescape
from xml.sax.saxutils import escape

import requests

# ---- EDIT THIS ------------------------------------------------------------
JOURNALS = {
    "ACS Nano": "1936-086X",
    # "Journal name": "XXXX-XXXX",
}
CONTACT_EMAIL = ""      # optional; any address (a throwaway is fine) or leave empty
DAYS_BACK = 14          # how far back the feed reaches
SKIP_PREFIXES = ("Correction to", "Correction:", "Addition to", "Retraction of")
FEED_TITLE = "ACS ASAP (via Crossref)"
# ---------------------------------------------------------------------------

SUB = str.maketrans("0123456789+-=()", "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎")
SUP = str.maketrans("0123456789+-=()", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾")


def clean(text: str) -> str:
    """Strip markup from Crossref strings; render <sub>/<sup> as unicode."""
    text = re.sub(r"<(?:jats:)?sub>(.*?)</(?:jats:)?sub>",
                  lambda m: m.group(1).translate(SUB), text, flags=re.S)
    text = re.sub(r"<(?:jats:)?sup>(.*?)</(?:jats:)?sup>",
                  lambda m: m.group(1).translate(SUP), text, flags=re.S)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"^\s*Abstract\s*", "", unescape(text))
    return re.sub(r"\s+", " ", text).strip()


def fetch(issn: str, since: str, session: requests.Session):
    params = {
        "filter": f"from-created-date:{since},type:journal-article",
        "sort": "created", "order": "desc", "rows": 500,
        "select": "DOI,title,author,created,abstract,container-title",
    }
    if CONTACT_EMAIL:
        params["mailto"] = CONTACT_EMAIL
    r = session.get(f"https://api.crossref.org/journals/{issn}/works",
                    params=params, timeout=60)
    r.raise_for_status()
    return r.json()["message"]["items"]


def main() -> int:
    since = (dt.date.today() - dt.timedelta(days=DAYS_BACK)).isoformat()
    session = requests.Session()
    items, failed = [], 0
    for name, issn in JOURNALS.items():
        try:
            works = fetch(issn, since, session)
        except Exception as e:  # keep going if one journal fails
            print(f"WARN {name} ({issn}): {e}", file=sys.stderr)
            failed += 1
            continue
        print(f"{name} ({issn}): {len(works)} items since {since}")
        for w in works:
            title = clean((w.get("title") or ["(untitled)"])[0])
            if title.startswith(SKIP_PREFIXES):
                continue
            authors = ", ".join(
                f"{a.get('given', '')} {a.get('family', '')}".strip()
                for a in w.get("author", [])[:8])
            if len(w.get("author", [])) > 8:
                authors += ", et al."
            abstract = clean(w.get("abstract", ""))
            desc = f"{authors}\n\n{abstract}".strip() or name
            created = dt.datetime.fromisoformat(
                w["created"]["date-time"].replace("Z", "+00:00"))
            doi = w["DOI"]
            items.append((created, (
                f"<item><title>{escape(name)}: {escape(title)}</title>"
                f"<link>https://doi.org/{escape(doi)}</link>"
                f"<guid isPermaLink=\"false\">{escape(doi)}</guid>"
                f"<pubDate>{format_datetime(created)}</pubDate>"
                f"<description>{escape(desc)}</description></item>")))

    if failed == len(JOURNALS):
        print("All journals failed; leaving existing feed.xml untouched.",
              file=sys.stderr)
        return 1

    items.sort(key=lambda x: x[0], reverse=True)
    now = format_datetime(dt.datetime.now(dt.timezone.utc))
    xml = ('<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0"><channel>'
           f"<title>{escape(FEED_TITLE)}</title><link>https://pubs.acs.org</link>"
           "<description>Recent articles from Crossref</description>"
           f"<lastBuildDate>{now}</lastBuildDate>"
           + "\n".join(i[1] for i in items) + "</channel></rss>\n")
    with open("feed.xml", "w", encoding="utf-8") as f:
        f.write(xml)
    print(f"Wrote feed.xml with {len(items)} items")
    return 0


if __name__ == "__main__":
    sys.exit(main())
