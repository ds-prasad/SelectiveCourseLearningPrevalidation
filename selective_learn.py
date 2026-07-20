#!/usr/bin/env python3
"""selective_learn - extract a Udemy course curriculum for selective learning.

Give it a course URL; it pulls the full curriculum (sections, lectures,
durations, lecture descriptions) from Udemy's public API and writes an
AI-ready learn plan so you can decide which lectures to watch, skim, or
skip instead of consuming the whole course.

Usage:
    python selective_learn.py <course-url> [<course-url> ...] [-o OUTPUT_DIR]

Outputs per course (named after the course slug):
    <slug>.learnplan.md   - Markdown: course name, URL, overview, then every
                            section and lecture with durations, descriptions,
                            and a [TBD] verdict slot for an AI to fill with
                            watch / skim / skip.
    <slug>.learnplan.csv  - same data flat: one row per lecture, verdict
                            column pre-filled with TBD.
"""

import argparse
import csv
import html
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

import requests

API = "https://www.udemy.com/api-2.0"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}
COURSE_FIELDS = "id,title,headline,description,url,num_lectures,estimated_content_length,last_update_date"
CURRICULUM_PARAMS = {
    "page_size": "100",
    "fields[chapter]": "title,sort_order",
    "fields[lecture]": "title,description,asset,sort_order",
    "fields[quiz]": "title,sort_order",
    "fields[asset]": "asset_type,length",
}
VERDICT_NOTE = (
    "> **Note to AI:** every lecture line below ends with a `[TBD]` verdict slot. "
    "Replace each `[TBD]` with `[WATCH]`, `[SKIM]`, or `[SKIP]` based on the "
    "learner's goals, using the lecture descriptions to judge relevance."
)
VERDICT_NOTE_NO_DESC = (
    "> **Note to AI:** every lecture line below ends with a `[TBD]` verdict slot. "
    "Replace each `[TBD]` with `[WATCH]`, `[SKIM]`, or `[SKIP]` based on the "
    "learner's goals. This course has no lecture descriptions on Udemy, so judge "
    "from section names, lecture titles, durations, and the course overview; when "
    "a title alone is ambiguous, prefer `[SKIM]` over `[SKIP]`."
)


def slug_of(url_or_slug: str) -> str:
    """Accept a full Udemy course URL or a bare slug; return the slug."""
    path = urlsplit(url_or_slug).path or url_or_slug
    m = re.search(r"/course/([^/?#]+)", path)
    return m.group(1) if m else path.strip("/")


DESC_MAX_CHARS = 250


def shorten(text: str, limit: int = DESC_MAX_CHARS) -> str:
    """Collapse whitespace and truncate; keeps learn plans token-efficient."""
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit].rstrip() + "..."


def strip_html(fragment: str) -> str:
    text = html.unescape(fragment)
    text = re.sub(r"<br\s*/?>", "\n", text)
    text = re.sub(r"</p>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def fmt_duration(seconds: int) -> str:
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    return f"{h}h {m:02d}m" if h else f"{m}m {s:02d}s"


def fmt_hms(seconds: int) -> str:
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def get_json(session: requests.Session, url: str, params: dict | None = None) -> tuple[int, dict | None]:
    """GET a Udemy API URL; return (status, parsed json or None)."""
    resp = session.get(url, params=params, timeout=30)
    if "application/json" not in resp.headers.get("Content-Type", ""):
        return resp.status_code, None
    return resp.status_code, resp.json()


def fetch_course(session: requests.Session, slug: str) -> tuple[int, dict | None]:
    return get_json(session, f"{API}/courses/{slug}/", {"fields[course]": COURSE_FIELDS})


def fetch_curriculum(session: requests.Session, course_id: int) -> list[dict]:
    """Return all curriculum items in display order (chapters + lectures + quizzes)."""
    items: list[dict] = []
    url = f"{API}/courses/{course_id}/public-curriculum-items/"
    params: dict | None = CURRICULUM_PARAMS
    while url:
        status, data = get_json(session, url, params)
        if status != 200 or data is None:
            raise RuntimeError(f"curriculum fetch failed (HTTP {status})")
        items.extend(data["results"])
        url = data.get("next")
        params = None  # the next-link already carries the query string
        if url:
            time.sleep(0.4)
    return items


def build_sections(items: list[dict]) -> list[dict]:
    """Group flat curriculum items into sections with their lectures."""
    sections: list[dict] = []
    for item in items:
        if item["_class"] == "chapter":
            sections.append({"title": item["title"], "lectures": []})
            continue
        if not sections:  # course content before any chapter (rare)
            sections.append({"title": "(no section)", "lectures": []})
        asset = item.get("asset") or {}
        kind = asset.get("asset_type") or item["_class"].capitalize()
        sections[-1]["lectures"].append(
            {
                "title": item["title"],
                "type": kind,
                "seconds": asset.get("length") or 0,
                "description": shorten(strip_html(item.get("description") or "")),
            }
        )
    return sections


def write_markdown(path: Path, course: dict, sections: list[dict], totals: str) -> None:
    with_desc = sum(1 for s in sections for l in s["lectures"] if l["description"])
    md = [
        f"# {course['title']}",
        "",
        f"**URL:** https://www.udemy.com{course['url']}",
        f"**Headline:** {course.get('headline', '')}",
        f"**Totals:** {totals}",
        "",
        VERDICT_NOTE if with_desc else VERDICT_NOTE_NO_DESC,
        "",
        "## Course overview",
        "",
        strip_html(course.get("description") or ""),
        "",
        "## Curriculum",
    ]
    for s_idx, sec in enumerate(sections, 1):
        lecs = sec["lectures"]
        sec_secs = sum(l["seconds"] for l in lecs)
        md += ["", f"### Section {s_idx}: {sec['title']} ({len(lecs)} lectures, {fmt_duration(sec_secs)})", ""]
        for lec in lecs:
            note = "" if lec["type"] == "Video" else f" [{lec['type']}]"
            md.append(f"- [{fmt_hms(lec['seconds'])}] {lec['title']}{note} [TBD]")
            if lec["description"]:
                md.append("\n".join(f"  > {line}" if line else "  >" for line in lec["description"].splitlines()))
    path.write_text("\n".join(md) + "\n", encoding="utf-8")


def write_csv(path: Path, sections: list[dict]) -> Path:
    try:
        f = path.open("w", newline="", encoding="utf-8-sig")
    except PermissionError:
        # Excel keeps the file locked while it is open - write next to it instead.
        path = path.with_name(path.stem + " (new).csv")
        f = path.open("w", newline="", encoding="utf-8-sig")
        print(f"NOTE: target csv is locked (open in Excel?) - writing {path.name} instead.")
    with f:
        writer = csv.writer(f)
        writer.writerow(
            ["section_no", "section_title", "section_duration", "lecture_no",
             "lecture_title", "lecture_type", "duration_seconds", "duration", "verdict", "description"]
        )
        for s_idx, sec in enumerate(sections, 1):
            sec_dur = fmt_duration(sum(l["seconds"] for l in sec["lectures"]))
            for l_idx, lec in enumerate(sec["lectures"], 1):
                writer.writerow(
                    [s_idx, sec["title"], sec_dur, l_idx, lec["title"], lec["type"],
                     lec["seconds"], fmt_hms(lec["seconds"]), "TBD", lec["description"]]
                )
    return path


def process(session: requests.Session, url: str, out_dir: Path) -> bool:
    slug = slug_of(url)
    display_url = f"https://www.udemy.com/course/{slug}/"

    status, course = fetch_course(session, slug)
    if status != 200 or course is None:
        reason = "not JSON (blocked?)" if course is None and status == 200 else "course not found" if status == 404 else "request failed"
        print(f"{display_url} - {status} - {reason}")
        return False
    print(f"{display_url} - {status} - OK")

    try:
        items = fetch_curriculum(session, course["id"])
    except RuntimeError as exc:
        print(f"{display_url} - {exc}")
        return False

    sections = build_sections(items)
    lectures = [l for s in sections for l in s["lectures"]]
    total_secs = sum(l["seconds"] for l in lectures)
    with_desc = sum(1 for l in lectures if l["description"])
    totals = (
        f"{len(sections)} sections • {len(lectures)} lectures • "
        f"{fmt_duration(total_secs)} • {with_desc} lectures with descriptions"
    )
    print(f"Course:  {course['title']}")
    print(f"Content: {totals}")
    if not with_desc:
        print("Note:    this course has no lecture descriptions on Udemy (instructor did not provide them)")

    md_path = out_dir / f"{slug}.learnplan.md"
    write_markdown(md_path, course, sections, totals)
    print(f"Wrote:   {md_path.name}")
    csv_path = write_csv(out_dir / f"{slug}.learnplan.csv", sections)
    print(f"Wrote:   {csv_path.name}")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("urls", nargs="+", help="Udemy course URL(s) or slug(s)")
    parser.add_argument("-o", "--output-dir", type=Path, default=Path("."), help="where to write the learn plans")
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers.update(HEADERS)

    ok = True
    for i, url in enumerate(args.urls):
        if i:
            print()
        ok &= process(session, url, args.output_dir)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
