"""Generate the #213 packet-page mockup from the ledger and the evidence files.

    uv run python docs/design/packet-page/gen_packet_page.py [out.html]

Reads ~/.ytk/ledger.db, ~/.ytk/evidence/{views,attempts,drafts,frames}. Replays the
window T0..T1 second by second with station_at(), the same reconstruction the hub
route needs server-side. Writes one self-contained HTML page next to the template.
Design record: docs/design/packet-page/README.md.
"""
import glob
import json
import os
import re
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta

HOME = os.path.expanduser("~")
HERE = os.path.dirname(os.path.abspath(__file__))
import base64
import sys
con = sqlite3.connect(f"{HOME}/.ytk/ledger.db")
con.row_factory = sqlite3.Row

STATIONS = ["runner", "proctor", "student", "spell-checker", "teacher", "librarian", "owner"]
T0 = datetime.fromisoformat("2026-09-06T22:12:00+00:00")
T1 = datetime.fromisoformat("2026-09-06T22:38:00+00:00")
DET = ("bounce: concept grounding", "bounce: key moment", "bounce: tag", "bounce: banned")


def ts(s):
    return datetime.fromisoformat(s)


ITEMS = {r["id"]: (r["title"] or "untitled", r["source"]) for r in con.execute("select id, title, source from items")}
ACT = defaultdict(list)
for r in con.execute("select * from activity order by item_id, id"):
    ACT[r["item_id"]].append(dict(r))
ATT = defaultdict(list)
for p in glob.glob(f"{HOME}/.ytk/evidence/attempts/*.json"):
    a = json.load(open(p))
    ATT[a["item_id"]].append(a)
for v in ATT.values():
    v.sort(key=lambda a: a["n"])
ANSWERS = defaultdict(list)
for r in con.execute("select a.item_id, a.created_at, n.at, n.choice from asks a join answers n on n.ask_id=a.id order by a.id"):
    ANSWERS[r["item_id"]].append((ts(r["created_at"]), ts(r["at"]), r["choice"]))


def station_at(item, t):
    rows = [r for r in ACT[item] if ts(r["at"]) <= t]
    if not rows or (len(rows) == 1 and rows[0]["action"] == "grandfather"):
        return None, 0, ""
    for a in ATT[item]:
        if ts(a["opened_at"]) <= t and (a["closed_at"] is None or t < ts(a["closed_at"])):
            return "student", (t - ts(a["opened_at"])).total_seconds(), f"attempt {a['n']}"
    last = rows[-1]
    later = [r for r in ACT[item] if ts(r["at"]) > t]
    if last["actor"] == "enricher":
        nxt = next((r for r in later if r["actor"] == "grader" and r["action"] == "grade"), None)
        if nxt and nxt["duration_ms"] and ts(nxt["at"]) - timedelta(milliseconds=nxt["duration_ms"]) <= t:
            start = ts(nxt["at"]) - timedelta(milliseconds=nxt["duration_ms"])
            return "teacher", (t - start).total_seconds(), "marking"
        return "spell-checker", (t - ts(last["at"])).total_seconds(), "checking"
    st = last["to_state"]
    if st == "asking":
        ans = next((x for x in ANSWERS[item] if x[0] <= t and x[1] <= t and x[0] >= ts(last["at"]) - timedelta(seconds=2)), None)
        if ans:
            return "proctor", (t - ans[1]).total_seconds(), "answered, waiting"
        kind = ""
        for r in reversed(rows):
            if r["action"] == "ask":
                kind = (r["reason"] or "").split(":")[0].strip().lower()
                break
        if kind.startswith("why this"):
            kind = "intent missing"
        return "owner", (t - ts(last["at"])).total_seconds(), "ask · " + kind[:32]
    if st == "answered":
        return "proctor", (t - ts(last["at"])).total_seconds(), "answered, waiting"
    if st in ("captured", "read"):
        return "runner", (t - ts(last["at"])).total_seconds(), st
    if st == "enriched":
        return "proctor", (t - ts(last["at"])).total_seconds(), "passed, filing"
    if last["actor"] == "connect":
        return "filed", (t - ts(last["at"])).total_seconds(), "kept, no links"
    if st == "kept":
        nxt = next((r for r in later if r["actor"] == "connect"), None)
        if nxt and nxt["duration_ms"] and ts(nxt["at"]) - timedelta(milliseconds=nxt["duration_ms"]) <= t:
            return "librarian", 0, "arguing links"
        if nxt:
            return "proctor", (t - ts(last["at"])).total_seconds(), "kept, connect pending"
        return "filed", (t - ts(last["at"])).total_seconds(), "kept"
    if st == "connected":
        return "filed", (t - ts(last["at"])).total_seconds(), "linked"
    if last["action"] == "loop-error":
        return "proctor", (t - ts(last["at"])).total_seconds(), "error, retrying"
    if last["actor"] == "grader":
        return "student", (t - ts(last["at"])).total_seconds(), "next round"
    return "proctor", (t - ts(last["at"])).total_seconds(), st or ""


# ---------- transitions per item over the window, sampled per second and collapsed
items_out = []
for item, (title, source) in sorted(ITEMS.items()):
    trans = []
    prev = None
    t = T0
    while t <= T1:
        st, since, note = station_at(item, t)
        key = (st, note)
        if key != prev:
            idx = STATIONS.index(st) if st in STATIONS else -1
            trans.append([int((t - T0).total_seconds()), idx, note, int((t - T0).total_seconds() - since)])
            prev = key
        t += timedelta(seconds=1)
    if all(tr[1] == -1 for tr in trans):
        continue
    trail = []
    for r in ACT[item]:
        who = {"loop": "proctor", "operator": "runner", "enricher": "student", "connect": "librarian", "owner": "owner"}.get(r["actor"], r["actor"])
        reason = r["reason"] or ""
        act = r["action"]
        if r["actor"] == "grader":
            who = "spell-checker" if reason.startswith(DET) else "teacher"
            if act == "ask":
                who = "proctor"
        if act in ("capture", "read"):
            who = "runner"
        what = {"grandfather": "grandfather", "capture": "capture", "read": "read", "ask": "ask, " + (reason.split(":")[0].lower() if reason else ""), "answer": reason or "answer", "loop-error": "error, structured output", "enrich": reason, "grade": reason.replace("bounce: ", "bounce, ").lower(), "keep": "keep", "connect": reason, "connect-apply": "apply links"}.get(act, act)
        right = f'{r["tokens"]:,} tok · {round(r["duration_ms"] / 1000)} s' if r["model"] else (r["to_state"] or "")
        trail.append([r["at"][11:19], int((ts(r["at"]) - T0).total_seconds()), f"{who} · {what}", right, 1 if act == "loop-error" else 0, 1 if r["model"] else 0, r["tokens"] or 0])
    attempts = []
    for a in ATT[item]:
        vo = a.get("verdict_out") or {}
        draft = {}
        dp = a.get("draft_out")
        if dp and os.path.exists(dp):
            d = json.load(open(dp))
            draft = {"thesis": d.get("thesis") or "", "summary": d.get("summary") or "", "concepts": len(d.get("key_concepts") or []), "insights": len(d.get("insights") or []), "moments": len(d.get("key_moments") or []), "tags": d.get("interest_tags") or []}
        enr = next((r for r in ACT[item] if r["actor"] == "enricher" and (r["reason"] or "").startswith(f"attempt {a['n']}")), None)
        grd = None
        if enr:
            grd = next((r for r in ACT[item] if r["actor"] == "grader" and r["action"] == "grade" and r["id"] > enr["id"]), None)
        attempts.append({
            "n": a["n"], "open": int((ts(a["opened_at"]) - T0).total_seconds()), "close": int((ts(a["closed_at"]) - T0).total_seconds()) if a["closed_at"] else None,
            "findings": len(a["findings_in"]), "fin": [[f["check"].lower(), (f.get("where") or "")[:70], (f.get("detail") or "")[:220]] for f in a["findings_in"]],
            "passed": bool(vo.get("passed")), "layer": vo.get("layer"), "bounces": [b["check"].lower() for b in vo.get("bounces", [])],
            "bdet": [[b["check"].lower(), (b.get("where") or "")[:70], (b.get("detail") or "")[:220]] for b in vo.get("bounces", [])],
            "spots": [[1 if s["grounded"] else 0, " ".join(re.findall(r"t:\d+(?:-\d+)?|frame:\d+", s.get("where") or "")), (s.get("claim") or "")[:140]] for s in vo.get("spot_checks", [])],
            "hash": a["view_hash"], "draft": draft, "take": (a.get("take") or {}).get("kind"),
            "enr": [enr["model"], enr["tokens"], round((enr["duration_ms"] or 0) / 1000), int((ts(enr["at"]) - T0).total_seconds())] if enr else None,
            "grd": [grd["model"], grd["tokens"], round((grd["duration_ms"] or 0) / 1000), (grd["inputs"] and json.loads(grd["inputs"]).get("view_hash")), int((ts(grd["at"]) - T0).total_seconds())] if grd else None,
        })
    take = None
    if ATT[item]:
        tk = ATT[item][-1].get("take") or {}
        if tk.get("text"):
            take = {"kind": tk.get("kind", "take"), "text": tk["text"]}
    asks_out = []
    for r in con.execute("select a.id, a.kind, a.proposal, a.created_at, n.choice, n.text, n.at from asks a left join answers n on n.ask_id=a.id where a.item_id=? order by a.id", (item,)):
        prop = json.loads(r["proposal"]) if r["proposal"] else {}
        asks_out.append({"id": r["id"], "kind": r["kind"], "why": (prop.get("why") or "")[:160], "options": prop.get("options") or [], "t": int((ts(r["created_at"]) - T0).total_seconds()), "at": r["created_at"][11:19],
                         "links": [{"title": l.get("target_title") or l.get("target"), "why": (l.get("why") or l.get("reason") or "")[:140]} for l in (prop.get("links") or [])],
                         "answer": {"choice": r["choice"], "text": r["text"], "at": r["at"][11:19], "t": int((ts(r["at"]) - T0).total_seconds())} if r["choice"] else None,
                         "view_hash": prop.get("view_hash"), "attempt": prop.get("attempt")})
    items_out.append({"id": item, "title": title, "source": source, "trans": trans, "trail": trail, "attempts": attempts, "take": take, "asks": asks_out})

ink_rows = [[int((ts(r["at"]) - T0).total_seconds()), r["tokens"]] for r in con.execute("select at, tokens from activity where tokens is not null and at >= '2026-09-06' order by at")]
ink_before = sum(v for t, v in ink_rows if t < 0)
ink_window = [[t, v] for t, v in ink_rows if 0 <= t <= (T1 - T0).total_seconds()]

instants = [["22:15:15", 195, "student writing"], ["22:16:40", 280, "librarian asked"], ["22:22:30", 630, "489 in its second round"], ["22:24:00", 720, "534 filed"], ["22:34:59", 1379, "489 accepted at the cap"], ["22:36:38", 1478, "all seven landed"]]
ink_hours = [0] * 24
for r in con.execute("select at, tokens from activity where tokens is not null and at >= '2026-09-06' and at < '2026-09-06T22:12:00'"):
    ink_hours[int(r["at"][11:13])] += r["tokens"]
DATA = {"inkHours": ink_hours, "t0": "2026-09-06T22:12:00Z", "seconds": int((T1 - T0).total_seconds()), "stations": STATIONS, "items": items_out, "inkBefore": ink_before, "ink": ink_window, "instants": instants}
# ---------- per-view summaries and a transcript excerpt round every cited second
cites = defaultdict(set)
for a_list in ATT.values():
    for a in a_list:
        vo = a.get("verdict_out") or {}
        for x in vo.get("spot_checks", []) + vo.get("bounces", []):
            for m in re.findall(r"t:(\d+)", x.get("where") or ""):
                cites[a["item_id"]].add(int(m))
VIEWS = {}
for p in glob.glob(f"{HOME}/.ytk/evidence/views/*.json"):
    v = json.load(open(p))
    tr = v["transcript"]
    nframes = None
    for s in v["not_shown"]:
        m = re.search(r"frames \d+ to (\d+)", s)
        if m:
            nframes = int(m.group(1))
    if nframes is None:
        nframes = sum(1 for u in v["shown"] if u["kind"] == "frame")
    lines = []
    if tr:
        keep = set(range(min(14, len(tr))))
        for c in cites.get(v["item_id"], ()):
            idx = min(range(len(tr)), key=lambda i: abs(tr[i]["start"] - c))
            keep.update(range(max(0, idx - 2), min(len(tr), idx + 3)))
        last = -1
        for i in sorted(keep):
            if last >= 0 and i != last + 1:
                lines.append(["…", f"{i - last - 1} lines folded", 0])
            hit = any(abs(tr[i]["start"] - c) <= 1.5 for c in cites.get(v["item_id"], ()))
            lines.append([int(tr[i]["start"]), tr[i]["text"], 1 if hit else 0])
            last = i
        if last < len(tr) - 1:
            lines.append(["…", f"{len(tr) - 1 - last} lines folded", 0])
    VIEWS[v["item_id"]] = {"hash": v["view_hash"], "bundle": v["bundle_hash"], "source": v["source"], "origin": v["transcript_origin"], "lines": lines, "nlines": len(tr), "dur": (tr[-1]["start"] + 2) if tr else None, "shown": [u["id"] for u in v["shown"]], "not_shown": v["not_shown"], "budget": v["budget"], "tokenizer": v["tokenizer"], "nframes": nframes, "gaps": v["gaps"]}

# the two frames the packet of 534 shows, embedded; other items say so on the page
IMGS = {}
v534 = next((json.load(open(p)) for p in glob.glob(f"{HOME}/.ytk/evidence/views/534-*.json")), None)
if v534:
    for u in v534["shown"]:
        if u["kind"] == "frame" and os.path.exists(u["path"]):
            IMGS[u["id"].replace("frame:", "frame-") + ".jpg"] = "data:image/jpeg;base64," + base64.b64encode(open(u["path"], "rb").read()).decode("ascii")

out_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "packet-page.html")
tpl = open(os.path.join(HERE, "packet-page.template.html")).read()
html = tpl.replace("__DATA__", json.dumps(DATA, separators=(",", ":"))).replace("__VIEWS__", json.dumps(VIEWS, separators=(",", ":"))).replace("__IMGS__", json.dumps(IMGS))
open(out_path, "w").write(html)
print("wrote", out_path, len(html), "bytes ·", len(items_out), "items ·", sum(len(i["trans"]) for i in items_out), "transitions")
