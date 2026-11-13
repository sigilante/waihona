#!/usr/bin/env python3
"""waihona: archive every URL a manuscript cites and link the snapshots.

Stdlib only.  Subcommands (run in the manuscript directory):

  scan     list URLs found in .tex and .bib files (no network)
  archive  find or create an archive.org snapshot for each URL; write the lockfile
  apply    rewrite sources from the lockfile (.bib fields, \\url -> \\aurl, waihona.def)
  check    re-verify that every snapshot in the lockfile still resolves; exit 1 if not
  report   print the lockfile as a table

Typical release:  waihona.py scan; archive; apply --write; check

State lives in waihona.lock.json (commit it).  See INSTRUCTIONS.md.
"""
import argparse, datetime as dt, hashlib, json, re, sys, time
import urllib.error, urllib.parse, urllib.request
from pathlib import Path

TOP_ONLY = False
LOCK = "waihona.lock.json"
DEF = "waihona.def"
UA = "waihona/0.1 (manuscript link archiver)"
SKIP_SCHEMES = ("mailto:", "doi:", "file:")
MONTHS = ["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]

# ---------------------------------------------------------------- extraction

def strip_comments(tex):
    """Drop % comments (not \\%) so commented-out URLs are ignored."""
    return "\n".join(re.sub(r"(?<!\\)%.*", "", ln) for ln in tex.split("\n"))

URL_RE = re.compile(r"\\(?:url|aurl(?:\[[^\]]*\])?)\{([^}]*)\}")
HREF_RE = re.compile(r"\\(?:href|ahref(?:\[[^\]]*\])?)\{([^}]*)\}")
BIBURL_RE = re.compile(r"^\s*url\s*=\s*[{\"]([^}\"]*)[}\"]", re.I | re.M)

def tex_urls(text):
    t = strip_comments(text)
    return [u for u in URL_RE.findall(t) + HREF_RE.findall(t)]

def bib_urls(text):
    return BIBURL_RE.findall(text)

def find_sources(root):
    skip = {"build", ".git", "node_modules"}
    g = root.glob if TOP_ONLY else root.rglob
    tex = [p for p in g("*.tex") if not skip & set(p.parts)]
    bib = [p for p in g("*.bib") if not skip & set(p.parts)]
    return sorted(tex), sorted(bib)

def collect(root):
    tex, bib = find_sources(root)
    urls = {}
    for p in tex:
        for u in tex_urls(p.read_text(errors="replace")):
            urls.setdefault(norm(u), set()).add(str(p.relative_to(root)))
    for p in bib:
        for u in bib_urls(p.read_text(errors="replace")):
            urls.setdefault(norm(u), set()).add(str(p.relative_to(root)))
    return {u: sorted(f) for u, f in urls.items()
            if u.startswith("http") and not u.startswith(SKIP_SCHEMES)}

MON = "|".join(MONTHS)
DATE_RES = [
    (re.compile(rf"(\d{{1,2}})\s+({MON})\s+(\d{{4}})"), lambda m: (m[3], m[2], m[1])),
    (re.compile(rf"({MON})\s+(\d{{1,2}}),?\s+(\d{{4}})"), lambda m: (m[3], m[1], m[2])),
    (re.compile(r"(\d{4})-(\d{2})-(\d{2})"), lambda m: (m[1], m[2], m[3])),
]

def parse_date(s):
    for rx, pick in DATE_RES:
        m = rx.search(s)
        if m:
            y, mo, d = pick(m)
            try:
                mo = MONTHS.index(mo) + 1 if mo in MONTHS else int(mo)
                return dt.date(int(y), mo, int(d))
            except ValueError:
                pass
    return None

def access_dates_tex(text):
    """url -> date, from 'accessed D' within 120 chars after the URL (comments stripped)."""
    out = {}
    t = strip_comments(text)
    for rx in (URL_RE, HREF_RE):
        for m in rx.finditer(t):
            win = t[m.end(): m.end() + 120]
            k = re.search(r"(?i)accessed|retrieved|visited|cited", win)
            d = parse_date(win[k.end():]) if k else None
            if d:
                out.setdefault(norm(m.group(1)), d)
    return out

def access_dates_bib(text):
    out = {}
    for chunk in re.split(r"(?m)^(?=@)", text):
        m = BIBURL_RE.search(chunk)
        if not m:
            continue
        for f in ("urldate", "lastchecked", "note", "howpublished"):
            fm = re.search(rf"(?mi)^\s*{f}\s*=\s*\{{([^}}]*)\}}", chunk)
            d = parse_date(fm.group(1)) if fm else None
            if d and (f != "note" and f != "howpublished" or re.search(r"(?i)access|retriev|visit|cited", fm.group(1))):
                out[norm(m.group(1))] = d
                break
    return out

def source_dates(root):
    tex, bib = find_sources(root)
    out = {}
    for p in bib:
        out.update(access_dates_bib(p.read_text(errors="replace")))
    for p in tex:
        out.update(access_dates_tex(p.read_text(errors="replace")))
    return out

def norm(u):
    return u.strip().replace("\\%", "%").replace("\\_", "_").replace("\\#", "#")

def uid(u):
    return hashlib.sha1(u.encode()).hexdigest()[:8]

# ---------------------------------------------------------------- wayback

def get(url, timeout=60, method="GET"):
    req = urllib.request.Request(url, headers={"User-Agent": UA}, method=method)
    return urllib.request.urlopen(req, timeout=timeout)

def closest_snapshot(url, near):
    """Wayback availability API: closest snapshot to `near` (a date), or None."""
    q = urllib.parse.urlencode({"url": url, "timestamp": near.strftime("%Y%m%d")})
    try:
        with get("https://archive.org/wayback/available?" + q, 30) as r:
            j = json.load(r)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None
    c = j.get("archived_snapshots", {}).get("closest")
    if c and c.get("available") and str(c.get("status", "")).startswith(("2", "3")):
        return c["timestamp"], c["url"].replace("http://", "https://", 1)
    return None

def save_now(url):
    """Save Page Now (anonymous).  Returns (timestamp, archive_url) or None."""
    try:
        with get("https://web.archive.org/save/" + url, 180) as r:
            loc = r.headers.get("Content-Location") or ""
            final = r.geturl()
    except (urllib.error.URLError, TimeoutError):
        return None
    for s in (loc, final):
        m = re.search(r"/web/(\d{14})/", s)
        if m:
            return m.group(1), f"https://web.archive.org/web/{m.group(1)}/{url}"
    return None

def parse_ts(ts):
    return dt.datetime.strptime(ts[:8], "%Y%m%d").date()

def resolve(url, urldate, max_age, save_ok, pause):
    snap = closest_snapshot(url, urldate)
    if snap and abs((parse_ts(snap[0]) - urldate).days) <= max_age:
        return snap + ("existing",)
    if save_ok:
        time.sleep(pause)
        s = save_now(url)
        if s:
            return s + ("saved",)
    if snap:  # outside the window but better than nothing; flagged
        return snap + ("stale",)
    return None

# ---------------------------------------------------------------- lockfile

def load_lock(root):
    p = root / LOCK
    return json.loads(p.read_text()) if p.exists() else {}

def save_lock(root, lock):
    (root / LOCK).write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n")

def longdate(d):
    return f"{d.day} {MONTHS[d.month - 1]} {d.year}"

# ---------------------------------------------------------------- commands

def cmd_scan(a):
    urls = collect(a.root)
    lock = load_lock(a.root)
    for u, files in sorted(urls.items()):
        print(f"{'ok ' if u in lock and lock[u].get('archive_url') else 'NEW'}  {u}  [{', '.join(files)}]")
    new = [u for u in urls if u not in lock or not lock[u].get("archive_url")]
    print(f"\n{len(urls)} URLs, {len(new)} unarchived", file=sys.stderr)

def cmd_archive(a):
    urls = collect(a.root)
    lock = load_lock(a.root)
    today = dt.date.today()
    dates = source_dates(a.root)
    todo = [u for u in sorted(urls) if a.force or not lock.get(u, {}).get("archive_url")]
    if a.limit:
        todo = todo[: a.limit]
    for i, u in enumerate(todo, 1):
        old = lock.get(u, {})
        # precedence: date written in the manuscript > date already in the lockfile > today
        urldate = dates.get(u) or (dt.date.fromisoformat(old["urldate"]) if old.get("urldate") else today)
        r = resolve(u, urldate, a.max_age, not a.no_save, a.pause)
        if r:
            ts, au, how = r
            lock[u] = {"id": uid(u), "urldate": urldate.isoformat(), "timestamp": ts,
                       "archive_url": au, "how": how, "checked": today.isoformat(),
                       "date_from": "source" if u in dates else "today"}
            print(f"[{i}/{len(todo)}] {how:8} {ts[:8]} (access {urldate})  {u}")
        else:
            lock[u] = {"id": uid(u), "urldate": urldate.isoformat(), "how": "FAILED",
                       "checked": today.isoformat()}
            print(f"[{i}/{len(todo)}] FAILED          {u}")
        save_lock(a.root, lock)  # incremental: safe to interrupt
    bad = [u for u in urls if not lock.get(u, {}).get("archive_url")]
    stale = [u for u in urls if lock.get(u, {}).get("how") == "stale"]
    print(f"\n{len(urls) - len(bad)}/{len(urls)} archived; {len(stale)} stale; {len(bad)} failed")
    return 1 if bad else 0

def short(entry):
    return entry["timestamp"][:8]

def bib_patch(text, lock):
    """Insert/replace urldate, lastchecked, archiveurl, archivedate after each url field."""
    out, n = [], 0
    for chunk in re.split(r"(?m)^(?=@)", text):
        m = BIBURL_RE.search(chunk)
        e = lock.get(norm(m.group(1))) if m else None
        if not e or not e.get("archive_url"):
            out.append(chunk); continue
        for f in ("urldate", "lastchecked", "archiveurl", "archivedate"):
            chunk = re.sub(rf"(?mi)^\s*{f}\s*=\s*\{{[^}}]*\}},?[ \t]*\n", "", chunk)
        m = BIBURL_RE.search(chunk)
        line_end = chunk.index("\n", m.start()) if "\n" in chunk[m.start():] else len(chunk)
        indent = re.match(r"[ \t]*", m.group(0).lstrip("\n")).group(0)
        pre = chunk[:line_end].rstrip()
        had_comma = pre.endswith(",")
        d = e["urldate"]
        add = (f"\n{indent}urldate = {{{d}}},\n{indent}lastchecked = {{{longdate(dt.date.fromisoformat(d))}}},"
               f"\n{indent}archiveurl = {{{e['archive_url']}}},\n{indent}archivedate = {{{short(e)}}}")
        rest = chunk[line_end:]
        out.append(pre.rstrip(",") + "," + add + ("," if had_comma else "") + rest)
        n += 1
    return "".join(out), n

def tex_patch(text, lock):
    """\\url{X} -> \\aurl[id]{X};  \\href{X}{...} -> \\ahref[id]{X}{...}.  Comments untouched."""
    n = 0
    def sub(kind):
        def f(m):
            nonlocal n
            e = lock.get(norm(m.group(1)))
            if not e or not e.get("archive_url"):
                return m.group(0)
            n += 1
            return f"\\a{kind}[{e['id']}]{{{m.group(1)}}}"
        return f
    lines = []
    for ln in text.split("\n"):
        k = re.search(r"(?<!\\)%", ln)
        code, com = (ln[:k.start()], ln[k.start():]) if k else (ln, "")
        code = re.sub(r"\\url\{([^}]*)\}", sub("url"), code)
        code = re.sub(r"\\href\{([^}]*)\}", sub("href"), code)
        lines.append(code + com)
    return "\n".join(lines), n

def write_def(root, lock):
    rows = []  # no comment lines: waihona.sty reads this with % at catcode 12
    for u, e in sorted(lock.items(), key=lambda kv: kv[1]["id"]):
        if not e.get("archive_url"):
            continue
        d = longdate(dt.date.fromisoformat(e["urldate"]))
        rows.append(f"\\waihonaadd{{{e['id']}}}{{{d}}}{{{short(e)}}}{{{e['archive_url']}}}")
    (root / DEF).write_text("\n".join(rows) + "\n")

def cmd_apply(a):
    lock = load_lock(a.root)
    tex, bib = find_sources(a.root)
    for p in bib:
        new, n = bib_patch(p.read_text(), lock)
        print(f"{p.name}: {n} entries")
        if a.write and n:
            p.write_text(new)
    for p in tex:
        if p.name == "waihona.def":
            continue
        new, n = tex_patch(p.read_text(), lock)
        print(f"{p.name}: {n} links")
        if a.write and n:
            p.write_text(new)
    if a.write:
        write_def(a.root, lock)
        print(f"wrote {DEF}")
    else:
        print("(dry run; pass --write)")

def probe(url, tries=3):
    """'ok' (200/206), 'dead' (404/410), or 'unverified' (timeout, 202, 5xx, 429)."""
    for i in range(tries):
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Range": "bytes=0-0"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                if r.status in (200, 206):
                    return "ok"
        except urllib.error.HTTPError as e:
            if e.code in (404, 410):
                return "dead"
        except (urllib.error.URLError, TimeoutError):
            pass
        time.sleep(3 * (i + 1))
    return "unverified"

def cmd_check(a):
    lock = load_lock(a.root)
    urls = collect(a.root)
    dead = unver = 0
    for u in sorted(urls):
        e = lock.get(u)
        if not e or not e.get("archive_url"):
            print(f"MISSING     {u}"); dead += 1; continue
        r = probe(e["archive_url"])
        if r == "dead":
            print(f"DEAD        {e['archive_url']}"); dead += 1
        elif r == "unverified":
            print(f"UNVERIFIED  {e['archive_url']}"); unver += 1
        elif e.get("how") == "stale":
            print(f"STALE       {u}")
    print(f"{len(urls) - dead - unver}/{len(urls)} verified; {unver} unverified (retry later); {dead} missing or dead")
    return 1 if dead else 0

def cmd_report(a):
    for u, e in sorted(load_lock(a.root).items()):
        print(f"{e.get('how','?'):8} {e.get('urldate','')}  {e.get('timestamp','-')[:8]:8}  {u}")

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, default=Path("."))
    ap.add_argument("--top-only", action="store_true", help="ignore subdirectories (e.g. booklets/)")
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("scan").set_defaults(f=cmd_scan)
    s = sp.add_parser("archive"); s.set_defaults(f=cmd_archive)
    s.add_argument("--max-age", type=int, default=180, help="max days between access date and snapshot")
    s.add_argument("--no-save", action="store_true", help="never trigger Save Page Now")
    s.add_argument("--force", action="store_true", help="redo URLs already in the lockfile")
    s.add_argument("--limit", type=int, default=0)
    s.add_argument("--pause", type=float, default=5.0, help="seconds between Save Page Now requests")
    s = sp.add_parser("apply"); s.set_defaults(f=cmd_apply)
    s.add_argument("--write", action="store_true")
    sp.add_parser("check").set_defaults(f=cmd_check)
    sp.add_parser("report").set_defaults(f=cmd_report)
    a = ap.parse_args()
    a.root = a.root.resolve()
    global TOP_ONLY
    TOP_ONLY = a.top_only
    sys.exit(a.f(a) or 0)

if __name__ == "__main__":
    main()
