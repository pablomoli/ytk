"""Section 57: Jev as a bouncer before the Opus grade (docs/assets/57-jev-grader-bouncer).

Commands run in order: fig01 (the record, ledger only), collect (every Opus
grade with its draft, packet and owner ruling), run (one Jev request per
draft, then the stability re-send), score, fig02, fig03.
"""

from __future__ import annotations

import json
import os
import random
import sqlite3
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[1]
OUTDIR = ROOT / "docs" / "assets" / "57-jev-grader-bouncer"
PAIRS = OUTDIR / "pairs.json"
ARMS = OUTDIR / "jev-arms.json"
SCORES = OUTDIR / "scores.json"
LEDGER = Path(os.path.expanduser("~/.ytk/ledger.db"))

SEED = 57
THETA = 0.8
STATE_CAP = 80_000  # chars; the largest state section 56 sent
STABILITY_N = 20
SECTIONS = [
    "Thesis",
    "Summary",
    "Response to my take",
    "Key concepts",
    "Insights",
    "Key moments",
    "Visual sources",
    "Grounding",
    "Tags",
    "What I do not want",
    "What I enjoy reading",
]
N_RULES = 13
BARS = {"B1_max_false_blocks": 1, "B2_min_blocks": 28, "B2_named_share": 2 / 3, "B3_opus": 32 / 48, "B4_wall_s": 2.0, "stability": 18}


def commit_sha() -> str:
    return subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(str(LEDGER))
    c.row_factory = sqlite3.Row
    return c


def _plot_imports():
    sys.path.insert(0, str(ROOT / "scripts"))
    import plot_assets as pa

    return pa


# --- fig01: the record ------------------------------------------------------


def _record() -> list[dict]:
    c = _conn()
    items: dict[int, dict] = {}
    for r in c.execute(
        "SELECT item_id, at, action, model, duration_ms, reason, detail FROM activity "
        "WHERE action IN ('enrich','grade') ORDER BY id"
    ):
        try:
            d = json.loads(r["detail"] or "{}")
        except json.JSONDecodeError:
            d = {}
        passed = d.get("passed")
        if r["action"] == "grade" and r["model"] and passed is None:
            passed = (r["reason"] or "").startswith("pass")
        it = items.setdefault(r["item_id"], {"item_id": r["item_id"], "rows": [], "asks": []})
        it["rows"].append(
            {
                "at": r["at"],
                "action": r["action"],
                "model": r["model"],
                "ms": r["duration_ms"],
                "passed": passed,
                "checks": [b.get("check") for b in d.get("bounces", []) if isinstance(b, dict)],
            }
        )
    titles = {r["id"]: r["title"] for r in c.execute("SELECT id, title FROM items")}
    for a in c.execute(
        "SELECT a.item_id, a.kind, a.created_at, b.choice FROM asks a LEFT JOIN answers b ON b.ask_id=a.id ORDER BY a.id"
    ):
        if a["item_id"] in items:
            items[a["item_id"]]["asks"].append({"kind": a["kind"], "at": a["created_at"], "choice": a["choice"]})
    out = [dict(it, title=titles.get(k) or f"item {k}") for k, it in items.items()]
    return [it for it in out if any(r["action"] == "grade" and r["model"] for r in it["rows"])]


def _lanes(items: list[dict]) -> list[dict]:
    lanes = []
    for it in items:
        segs, t = [], 0.0
        for r in it["rows"]:
            if r["action"] == "enrich" and r["model"]:
                s = (r["ms"] or 0) / 1000
                segs.append(("enrich", t, s, None))
                t += s
            elif r["action"] == "grade" and r["model"]:
                s = (r["ms"] or 0) / 1000
                segs.append(("grade", t, s, "pass" if r["passed"] else "bounce"))
                t += s
            elif r["action"] == "grade":
                segs.append(("det", t, 0.0, "det"))
        ruling = None
        for a in it["asks"]:
            if a["kind"] == "grader bounce, twice" and a["choice"]:
                ruling = a["choice"]
        lanes.append({"item_id": it["item_id"], "title": it["title"], "segs": segs, "total": t, "ruling": ruling})
    lanes.sort(key=lambda L: -L["total"])
    return lanes


def draw01() -> Path:
    pa = _plot_imports()
    items = _record()
    lanes = _lanes(items)
    grades = [s for L in lanes for s in L["segs"] if s[0] == "grade"]
    drafts = [s for L in lanes for s in L["segs"] if s[0] == "enrich"]
    opus_s, sonnet_s = sum(s[2] for s in grades), sum(s[2] for s in drafts)
    n_pass = sum(s[3] == "pass" for s in grades)
    n_det = sum(s[0] == "det" for L in lanes for s in L["segs"])
    rounds = sorted(sum(s[0] == "grade" for s in L["segs"]) for L in lanes)
    cross: Counter = Counter()
    rulings: Counter = Counter()
    for it in items:
        for a in it["asks"]:
            if a["kind"] != "grader bounce, twice" or not a["choice"]:
                continue
            rulings[a["choice"]] += 1
            before = [r for r in it["rows"] if r["action"] == "grade" and r["checks"] and r["at"] <= a["at"]]
            for ch in set(before[-1]["checks"]) if before else {"?"}:
                cross[(ch, a["choice"])] += 1
    sections = sorted({k[0] for k in cross}, key=lambda s: -sum(v for (ss, _c), v in cross.items() if ss == s))
    n_accept = rulings["accept as is"]
    n_wrong = rulings["say what is wrong"] + rulings["drop"]

    fig, top = pa.figure(
        16,
        10,
        1,
        "section 57 · the grader slot · the record before any arm",
        "Every curated item's rounds on one clock: the writer's draft, then Opus's grade, until a pass or the owner",
        meta=(
            f"{len(lanes)} items graded by the model layer · {len(grades)} Opus grades ({opus_s / 60:.0f} min, mean {opus_s / len(grades):.0f} s) · "
            f"{len(drafts)} Sonnet drafts ({sonnet_s / 60:.0f} min, mean {sonnet_s / len(drafts):.0f} s) · rounds per item: median {rounds[len(rounds) // 2]}, max {rounds[-1]} · "
            f"grades: {n_pass} pass, {len(grades) - n_pass} bounce, {n_det} caught by the deterministic layer at no cost · "
            f"owner rulings after two bounces: {n_accept} accept as is, {n_wrong} say what is wrong · ledger ~/.ytk/ledger.db · commit {commit_sha()}"
        ),
    )
    bottom, h = 0.075, top - 0.075 - 0.03
    gutter_w = 380
    xmax = max(L["total"] for L in lanes) * 1.04
    ax = fig.add_axes([pa.MARGIN + 0.015, bottom, 0.60, h])
    pa.style_axes(ax)
    col = {"enrich": pa.PURPLE, "pass": pa.GOLD, "bounce": pa.RED}
    for i, L in enumerate(lanes):
        ax.text(-gutter_w + 8, i, L["title"][:46], color=pa.TEXT, fontsize=7.8, va="center", ha="left")
        for kind, t0, dur, out in L["segs"]:
            if kind == "det":
                ax.plot([t0, t0], [i - 0.42, i + 0.42], color=pa.MUTED, lw=1.4, zorder=5)
                continue
            ax.barh(i, dur, left=t0, height=0.72, color=col["enrich"] if kind == "enrich" else col[out], edgecolor=pa.BG, lw=0.4, zorder=3)
        if L["ruling"] == "accept as is":
            ax.scatter(L["total"] + 18, i, s=58, facecolors="none", edgecolors=pa.GOLD, lw=1.5, zorder=6)
        elif L["ruling"] in ("say what is wrong", "drop"):
            ax.scatter(L["total"] + 18, i, s=52, marker="x", color=pa.RED if L["ruling"] != "drop" else pa.MUTED, lw=1.5, zorder=6)
    ax.plot([0, 0], [-0.5, len(lanes) - 0.5], color=pa.FRAME, lw=1.0, zorder=2)
    ax.set_xlim(-gutter_w, xmax + 40)
    ax.set_ylim(len(lanes) - 0.5, -0.5)
    ax.set_yticks([])
    ticks = [t for t in range(0, 2700, 300) if t <= xmax]
    ax.set_xticks(ticks)
    ax.set_xticklabels([f"{t // 60} min" for t in ticks])
    ax.tick_params(axis="x", colors=pa.MUTED, labelsize=8.5)
    ax.set_xlabel("model time spent on the item, in order (seconds the owner waits)", color=pa.MUTED, fontsize=9)
    pa.panel_title(
        ax,
        "purple = Sonnet writes the draft · gold = Opus passes · red = Opus bounces · grey tick = deterministic bounce, free · "
        "after two bounces the owner rules: hollow gold = accept as is, red x = say what is wrong",
        width=92,
    )
    ax2 = fig.add_axes([pa.MARGIN + 0.655, bottom, 1 - 2 * pa.MARGIN - 0.655, h])
    pa.style_axes(ax2)
    for k, s in enumerate(sections):
        a = cross[(s, "accept as is")]
        w = cross[(s, "say what is wrong")] + cross[(s, "drop")]
        ax2.barh(k, a, left=0, height=0.68, color=pa.GOLD, zorder=3)
        ax2.barh(k, w, left=a, height=0.68, color=pa.RED, zorder=3)
        ax2.text(-0.3, k, s[:26], color=pa.TEXT, fontsize=8.4, va="center", ha="right")
        ax2.text(a + w + 0.3, k, f"{a}/{a + w}", color=pa.GOLD if a else pa.MUTED, fontsize=8.2, va="center", ha="left")
    ax2.set_xlim(-9.5, max(cross[(s, "accept as is")] + cross[(s, "say what is wrong")] + cross[(s, "drop")] for s in sections) + 3.5)
    ax2.set_ylim(len(sections) - 0.5, -0.5)
    ax2.set_yticks([])
    ax2.set_xticks([0, 5, 10, 15, 20, 25])
    ax2.tick_params(axis="x", colors=pa.MUTED, labelsize=8.5)
    ax2.set_xlabel("owner rulings whose preceding bounce named this section", color=pa.MUTED, fontsize=9)
    pa.panel_title(
        ax2,
        "what the grader bounced on, and what the owner then said · one count per section a bounce named · gold = accepted the draft as is "
        "(the bounce cost a round for nothing) · red = agreed something was wrong · n/total = overruled",
        width=60,
    )
    pa.verdict(
        fig,
        f"Opus spends {opus_s / len(grades):.0f} s a grade and the median item takes {rounds[len(rounds) // 2]} grades; "
        f"the owner overruled {n_accept} of {n_accept + n_wrong} double bounces, {cross[('Grounding', 'accept as is')]} of "
        f"{cross[('Grounding', 'accept as is')] + cross[('Grounding', 'say what is wrong')]} on grounding",
    )
    pa.frame_panels(fig)
    out = OUTDIR / "01-the-graders-bill.png"
    fig.savefig(out, dpi=pa.DPI, facecolor=pa.BG)
    return out


# --- collect ----------------------------------------------------------------


def _norm_section(check: str) -> str:
    c = (check or "").strip().casefold()
    for s in SECTIONS:
        if c == s.casefold():
            return s
    return check


def _resolve_packet(item_id: int, view_hash: str | None, payload_ref: str | None):
    from ytk import view as V

    v = V.view_by_hash(item_id, view_hash) if view_hash else None
    if v is not None:
        return v, "hash"
    v = V.latest_view(item_id)
    if v is not None:
        return v, "latest"
    if payload_ref and Path(payload_ref).exists():
        return V.build_view(item_id, payload_ref), "rebuilt"
    return None, "none"


def collect() -> dict:
    from ytk import attempt as A

    c = _conn()
    rows = c.execute(
        "SELECT id, item_id, at, inputs, output_ref, reason, detail FROM activity WHERE action='grade' AND model IS NOT NULL ORDER BY id"
    ).fetchall()
    titles = {r["id"]: (r["title"], r["payload_ref"]) for r in c.execute("SELECT id, title, payload_ref FROM items")}
    # Owner ruling -> the Opus grade the owner saw (the last one before the ask).
    ruled: dict[int, list[str]] = {}
    for a in c.execute(
        "SELECT a.item_id, a.created_at, b.choice FROM asks a JOIN answers b ON b.ask_id=a.id WHERE a.kind='grader bounce, twice'"
    ):
        g = c.execute(
            "SELECT id FROM activity WHERE item_id=? AND action='grade' AND model IS NOT NULL AND at<=? ORDER BY id DESC LIMIT 1",
            (a["item_id"], a["created_at"]),
        ).fetchone()
        if g:
            ruled.setdefault(g["id"], []).append("should_pass" if a["choice"] == "accept as is" else "should_block")
    grades = []
    for r in rows:
        inp = json.loads(r["inputs"] or "{}")
        d = json.loads(r["detail"] or "{}")
        passed = d.get("passed")
        if passed is None:
            passed = (r["reason"] or "").startswith("pass")
        sections = sorted({_norm_section(b.get("check", "")) for b in d.get("bounces", []) if isinstance(b, dict)})
        title, payload_ref = titles.get(r["item_id"], (None, None))
        v, src = _resolve_packet(r["item_id"], inp.get("view_hash"), payload_ref)
        n = inp.get("attempt")
        att = A.load_attempt(r["item_id"], int(n)) if n is not None else None
        grades.append(
            {
                "grade_id": r["id"],
                "item_id": r["item_id"],
                "title": title,
                "at": r["at"],
                "attempt": n,
                "draft_path": r["output_ref"],
                "view_hash": inp.get("view_hash"),
                "packet_source": src,
                "packet_chars": len(v.rendered) if v else 0,
                "attempt_header": att.rendered() if att else None,
                "opus_passed": bool(passed),
                "opus_sections": sections,
                "owner": ruled.get(r["id"], []),
            }
        )
    data = {"grades": grades, "sections": SECTIONS, "n_rules": N_RULES, "theta": THETA, "state_cap": STATE_CAP, "commit": commit_sha()}
    OUTDIR.mkdir(parents=True, exist_ok=True)
    PAIRS.write_text(json.dumps(data, indent=1))
    src = Counter(g["packet_source"] for g in grades)
    own = Counter(lab for g in grades for lab in g["owner"])
    print(f"{len(grades)} grades · packets {dict(src)} · opus passed {sum(g['opus_passed'] for g in grades)} · owner labels {dict(own)}")
    return data


# --- run --------------------------------------------------------------------


def _state_and_questions(g: dict) -> tuple[dict, dict, bool]:
    from ytk import view as V  # noqa: F401
    from ytk.writer_rules import HOUSE_RULES

    sys.path.insert(0, str(ROOT / "scripts"))
    from jev_client import noul

    rubric = Path(os.path.expanduser("~/.ytk/rubric.md")).read_text()
    _c = _conn()
    payload_ref = _c.execute("SELECT payload_ref FROM items WHERE id=?", (g["item_id"],)).fetchone()[0]
    v, _src = _resolve_packet(g["item_id"], g["view_hash"], payload_ref)
    packet = v.rendered if v else ""
    draft = json.loads(Path(g["draft_path"]).read_text())
    header = g["attempt_header"] or f"Attempt {g['attempt']} for item {g['item_id']}. No findings from an earlier round."
    fixed = len(rubric) + len(HOUSE_RULES) + len(header) + len(json.dumps(draft)) + 200
    cut = False
    if fixed + len(packet) > STATE_CAP:
        packet = packet[: max(0, STATE_CAP - fixed)] + "\n[packet cut here to fit the state cap]"
        cut = True
    state = {"rubric": rubric, "house_rules": HOUSE_RULES, "packet": packet, "attempt": header, "draft": draft}
    q: dict[str, dict] = {}
    for s in SECTIONS:
        key = "s_" + s.casefold().replace(" ", "_")
        q[key] = noul(
            f"Does `draft` fall short of rubric section `rubric` '## {s}', judged by that section's own words against `packet`?",
            "The draft fails what the section asks; a grader reading this section would bounce the draft on it.",
            "The draft meets the section, or the section does not apply to this item.",
        )
    for n in range(1, N_RULES + 1):
        q[f"h_{n:02d}"] = noul(
            f"Does `draft` break house rule {n} in `house_rules`?",
            "A sentence in the draft does what the rule rejects.",
            "No sentence does, or the rule does not apply.",
        )
    return state, q, cut


def _one(g: dict, tag: str) -> dict:
    sys.path.insert(0, str(ROOT / "scripts"))
    from jev_client import system_one

    state, q, cut = _state_and_questions(g)
    reply = system_one(state, q, tag=tag)
    return {
        "grade_id": g["grade_id"],
        "p": {k: float(a["noul"]) for k, a in reply.answers.items()},
        "wall_s": round(reply.latency_s, 3),
        "input_tokens": reply.input_tokens,
        "cut": cut,
    }


def run() -> dict:
    data = json.loads(PAIRS.read_text())
    out = {"primary": [], "stability": []}
    t0 = time.time()
    for i, g in enumerate(data["grades"]):
        out["primary"].append(_one(g, "jev57-grade"))
        if i % 10 == 9:
            print(f"  {i + 1}/{len(data['grades'])} · {time.time() - t0:.0f}s")
    rng = random.Random(SEED)
    picks = rng.sample(data["grades"], STABILITY_N)
    first = {r["grade_id"]: r for r in out["primary"]}
    for g in picks:
        r = _one(g, "jev57-stability")
        out["stability"].append({"grade_id": g["grade_id"], "p1": first[g["grade_id"]]["p"], "p2": r["p"], "wall_s": r["wall_s"]})
    ARMS.write_text(json.dumps(out, indent=1))
    print(f"{len(out['primary'])} drafts, {len(out['stability'])} re-sent · {sum(r['input_tokens'] for r in out['primary']):,} input tokens")
    return out


# --- score ------------------------------------------------------------------


def _decide(p: dict, prefix: str, theta: float) -> tuple[bool, str | None, float]:
    sub = {k: v for k, v in p.items() if k.startswith(prefix)}
    if not sub:
        return False, None, 0.0
    k, v = max(sub.items(), key=lambda kv: kv[1])
    return v >= theta, k, v


def _key_to_section(key: str) -> str:
    want = key[2:].replace("_", " ")
    for s in SECTIONS:
        if s.casefold() == want:
            return s
    return want


def _arm_metrics(grades: list[dict], P: dict[int, dict], prefix: str, theta: float, rng: random.Random | None = None) -> dict:
    blocks = {g["grade_id"]: _decide(P[g["grade_id"]], prefix, theta) for g in grades}
    passed = [g for g in grades if g["opus_passed"]]
    bounced = [g for g in grades if not g["opus_passed"]]
    false_blocks = sum(blocks[g["grade_id"]][0] for g in passed)
    caught = [g for g in bounced if blocks[g["grade_id"]][0]]
    named_ok = sum(_key_to_section(blocks[g["grade_id"]][1]) in g["opus_sections"] for g in caught) if prefix == "s_" else None
    ruled = [(g, lab) for g in grades for lab in g["owner"]]
    correct = sum((lab == "should_block") == blocks[g["grade_id"]][0] for g, lab in ruled)
    acc = correct / len(ruled) if ruled else None
    out = {
        "theta": theta,
        "false_blocks_on_opus_passes": false_blocks,
        "n_opus_passes": len(passed),
        "caught_opus_bounces": len(caught),
        "n_opus_bounces": len(bounced),
        "named_section_agrees": named_ok,
        "owner_accuracy": acc,
        "n_owner_rulings": len(ruled),
        "opus_seconds_saved": sum(_grade_seconds(g) for g in caught),
    }
    if rng is not None and ruled:
        accs = []
        for _ in range(1000):
            samp = [ruled[rng.randrange(len(ruled))] for _ in ruled]
            accs.append(sum((lab == "should_block") == blocks[g["grade_id"]][0] for g, lab in samp) / len(samp))
        accs.sort()
        out["owner_accuracy_ci"] = [accs[25], accs[974]]
    return out


_SECONDS: dict[int, float] = {}


def _grade_seconds(g: dict) -> float:
    if not _SECONDS:
        for r in _conn().execute("SELECT id, duration_ms FROM activity WHERE action='grade' AND model IS NOT NULL"):
            _SECONDS[r["id"]] = (r["duration_ms"] or 0) / 1000
    return _SECONDS.get(g["grade_id"], 0.0)


def _auc(pos: list[float], neg: list[float]) -> float | None:
    if not pos or not neg:
        return None
    wins = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
    return wins / (len(pos) * len(neg))


def score() -> dict:
    data = json.loads(PAIRS.read_text())
    arms = json.loads(ARMS.read_text())
    grades = data["grades"]
    P = {r["grade_id"]: r["p"] for r in arms["primary"]}
    rng = random.Random(SEED)
    rubric = _arm_metrics(grades, P, "s_", THETA, rng)
    house = _arm_metrics(grades, P, "h_", THETA, random.Random(SEED))
    curve = {
        arm: [_arm_metrics(grades, P, pre, t / 20) for t in range(1, 20)] for arm, pre in (("rubric", "s_"), ("house", "h_"))
    }
    # Rate null: the bouncer's block decisions shuffled across drafts.
    dec = [_decide(P[g["grade_id"]], "s_", THETA)[0] for g in grades]
    null = {"false_blocks": [], "caught": [], "owner_accuracy": []}
    for _ in range(1000):
        rng.shuffle(dec)
        fb = sum(d for d, g in zip(dec, grades, strict=True) if g["opus_passed"])
        ca = sum(d for d, g in zip(dec, grades, strict=True) if not g["opus_passed"])
        ruled = [(d, lab) for d, g in zip(dec, grades, strict=True) for lab in g["owner"]]
        acc = sum((lab == "should_block") == d for d, lab in ruled) / len(ruled)
        null["false_blocks"].append(fb)
        null["caught"].append(ca)
        null["owner_accuracy"].append(acc)
    # Per-section: Jev's P on drafts Opus bounced for that section vs the rest.
    per_section = {}
    for s in SECTIONS:
        key = "s_" + s.casefold().replace(" ", "_")
        pos = [P[g["grade_id"]][key] for g in grades if s in g["opus_sections"]]
        neg = [P[g["grade_id"]][key] for g in grades if s not in g["opus_sections"]]
        per_section[s] = {"n_opus_bounced": len(pos), "auc": _auc(pos, neg), "median_p_bounced": median(pos) if pos else None, "median_p_rest": median(neg) if neg else None}
    walls = sorted(r["wall_s"] for r in arms["primary"])
    stab = arms["stability"]
    same_dec = sum(_decide(s["p1"], "s_", THETA)[0] == _decide(s["p2"], "s_", THETA)[0] for s in stab)
    blocked_both = [s for s in stab if _decide(s["p1"], "s_", THETA)[0] and _decide(s["p2"], "s_", THETA)[0]]
    same_name = sum(_decide(s["p1"], "s_", THETA)[1] == _decide(s["p2"], "s_", THETA)[1] for s in blocked_both)
    bars = {
        "B1_safety": rubric["false_blocks_on_opus_passes"] <= BARS["B1_max_false_blocks"],
        "B2_worth": rubric["caught_opus_bounces"] >= BARS["B2_min_blocks"]
        and (rubric["caught_opus_bounces"] == 0 or rubric["named_section_agrees"] / rubric["caught_opus_bounces"] >= BARS["B2_named_share"]),
        "B3_owner": rubric["owner_accuracy"] is not None and rubric["owner_accuracy_ci"][0] > BARS["B3_opus"],
        "B4_speed": walls[len(walls) // 2] <= BARS["B4_wall_s"],
        "stability": same_dec >= BARS["stability"] and (not blocked_both or same_name >= len(blocked_both) - 2),
    }
    out = {
        "theta": THETA,
        "rubric": rubric,
        "house": house,
        "curve": curve,
        "rate_null": {k: {"mean": sum(v) / len(v), "p05": sorted(v)[50], "p95": sorted(v)[949]} for k, v in null.items()},
        "per_section": per_section,
        "speed": {"median_wall_s": walls[len(walls) // 2], "p95_wall_s": walls[int(len(walls) * 0.95)], "max_wall_s": walls[-1], "input_tokens": sum(r["input_tokens"] for r in arms["primary"]), "cut": sum(r["cut"] for r in arms["primary"])},
        "stability": {"n": len(stab), "same_decision": same_dec, "blocked_both": len(blocked_both), "same_named_section": same_name},
        "bars": bars,
        "verdict": {"worth_wiring": bars["B1_safety"] and bars["B2_worth"] and bars["B4_speed"] and bars["stability"], "sides_with_owner": bars["B3_owner"]},
        "packet_groups": {
            src: _arm_metrics([g for g in grades if g["packet_source"] == src], P, "s_", THETA) for src in sorted({g["packet_source"] for g in grades})
        },
        "commit": commit_sha(),
    }
    SCORES.write_text(json.dumps(out, indent=1))
    print(json.dumps({k: out[k] for k in ("rubric", "house", "speed", "stability", "bars", "verdict")}, indent=1))
    return out


# --- figures ----------------------------------------------------------------


def draw02() -> Path:
    import numpy as np

    pa = _plot_imports()
    data = json.loads(PAIRS.read_text())
    arms = json.loads(ARMS.read_text())
    sc = json.loads(SCORES.read_text())
    grades = data["grades"]
    P = {r["grade_id"]: r["p"] for r in arms["primary"]}
    pmax = {g["grade_id"]: _decide(P[g["grade_id"]], "s_", THETA)[2] for g in grades}
    r = sc["rubric"]
    fig, top = pa.figure(
        16,
        10,
        2,
        "section 57 · the bouncer at the door · J-rubric, every Opus grade",
        "Jev's strongest section score per draft, against what Opus did and what the owner later ruled",
        meta=(
            f"{len(grades)} drafts, one request each, {len(SECTIONS)} rubric sections + {N_RULES} house rules as Noul questions · jev-1.14.0 · "
            f"block at P >= {THETA} (registered) · Opus passed {r['n_opus_passes']}, bounced {r['n_opus_bounces']} · "
            f"bouncer: {r['false_blocks_on_opus_passes']} false blocks, {r['caught_opus_bounces']} bounces caught ({r['opus_seconds_saved'] / 60:.0f} min of Opus), "
            f"named section agrees {r['named_section_agrees']}/{r['caught_opus_bounces']} · owner ruler {r['owner_accuracy']:.3f} "
            f"[{r['owner_accuracy_ci'][0]:.3f}, {r['owner_accuracy_ci'][1]:.3f}] vs Opus {BARS['B3_opus']:.3f} · "
            f"median wall {sc['speed']['median_wall_s']:.2f} s · commit {commit_sha()}"
        ),
    )
    bottom, h = 0.075, top - 0.075 - 0.03
    ax = fig.add_axes([pa.MARGIN + 0.015, bottom, 0.56, h])
    pa.style_axes(ax)
    rng = np.random.default_rng(SEED)
    strips = [
        ("Opus passed", [g for g in grades if g["opus_passed"]], pa.GOLD),
        ("Opus bounced", [g for g in grades if not g["opus_passed"]], pa.RED),
        ("owner: accept as is", [g for g in grades for lab in g["owner"] if lab == "should_pass"], pa.GOLD),
        ("owner: say what is wrong", [g for g in grades for lab in g["owner"] if lab == "should_block"], pa.RED),
    ]
    for k, (label, gs, col) in enumerate(strips):
        xs = [pmax[g["grade_id"]] for g in gs]
        ys = k + rng.uniform(-0.26, 0.26, len(xs))
        ax.scatter(xs, ys, s=54, color=col, alpha=0.85, zorder=3, edgecolors=pa.BG, lw=0.4)
        blocked = sum(x >= THETA for x in xs)
        ax.text(0.012, k - 0.38, label, color=col, fontsize=9.4, ha="left", va="center")
        ax.text(0.988, k - 0.38, f"n={len(xs)} · blocked {blocked}", color=col, fontsize=8.8, ha="right", va="center")
        if k == 1:
            ax.plot([0, 1], [k + 0.5, k + 0.5], color=pa.FRAME, lw=0.8)
    ax.axvline(THETA, color=pa.TEXT, lw=1.2, ls="--", zorder=4)
    ax.text(THETA + 0.008, -0.45, f"block at {THETA}", color=pa.TEXT, fontsize=8.5, ha="left", va="center")
    ax.set_xlim(0, 1)
    ax.set_ylim(len(strips) - 0.5, -0.5)
    ax.set_yticks([])
    ax.set_xticks([0, 0.2, 0.4, 0.6, 0.8, 1.0])
    ax.tick_params(axis="x", colors=pa.MUTED, labelsize=8.5)
    ax.set_xlabel("Jev's highest section probability on the draft (max over the eleven rubric sections)", color=pa.MUTED, fontsize=9)
    pa.panel_title(ax, "one mark per draft · top two strips: the Opus ruler · bottom two: the owner's ruler on the drafts behind the 59 rulings · right of the line = the bouncer blocks", width=86)

    ax2 = fig.add_axes([pa.MARGIN + 0.615, bottom, 1 - 2 * pa.MARGIN - 0.615, h])
    pa.style_axes(ax2)
    secs = sorted(SECTIONS, key=lambda s: -(sc["per_section"][s]["n_opus_bounced"]))
    for k, s in enumerate(secs):
        key = "s_" + s.casefold().replace(" ", "_")
        pos = [P[g["grade_id"]][key] for g in grades if s in g["opus_sections"]]
        neg = [P[g["grade_id"]][key] for g in grades if s not in g["opus_sections"]]
        ax2.scatter(neg, k + 0.16 + rng.uniform(-0.1, 0.1, len(neg)), s=14, color=pa.DIM, zorder=2)
        ax2.scatter(pos, k - 0.16 + rng.uniform(-0.1, 0.1, len(pos)), s=26, color=pa.RED, zorder=3)
        auc = sc["per_section"][s]["auc"]
        ax2.text(-0.02, k, s[:20], color=pa.TEXT, fontsize=8.4, ha="right", va="center")
        ax2.text(1.02, k, f"{len(pos)} · AUC {auc:.2f}" if auc is not None else f"{len(pos)}", color=pa.RED if pos else pa.MUTED, fontsize=8.2, ha="left", va="center")
    ax2.axvline(THETA, color=pa.TEXT, lw=1.0, ls="--", zorder=4)
    ax2.set_xlim(-0.42, 1.36)
    ax2.set_ylim(len(secs) - 0.5, -0.5)
    ax2.set_yticks([])
    ax2.set_xticks([0, 0.5, 1.0])
    ax2.tick_params(axis="x", colors=pa.MUTED, labelsize=8.5)
    ax2.set_xlabel("Jev's probability that the draft fails this section", color=pa.MUTED, fontsize=9)
    pa.panel_title(ax2, "per section · red = drafts Opus bounced on that section · grey = the rest · n and rank AUC at right", width=56)
    v = sc["verdict"]
    pa.verdict(
        fig,
        f"worth wiring: {'PASS' if v['worth_wiring'] else 'FAIL'} · sides with the owner: {'PASS' if v['sides_with_owner'] else 'FAIL'} · "
        f"{r['false_blocks_on_opus_passes']}/{r['n_opus_passes']} false blocks, {r['caught_opus_bounces']}/{r['n_opus_bounces']} caught, owner {r['owner_accuracy']:.2f} vs Opus {BARS['B3_opus']:.2f}",
    )
    pa.frame_panels(fig)
    out = OUTDIR / "02-the-bouncer-at-the-door.png"
    fig.savefig(out, dpi=pa.DPI, facecolor=pa.BG)
    return out


def draw03() -> Path:
    pa = _plot_imports()
    sc = json.loads(SCORES.read_text())
    data = json.loads(PAIRS.read_text())
    arms = json.loads(ARMS.read_text())
    P = {r["grade_id"]: r["p"] for r in arms["primary"]}
    thetas = [t / 20 for t in range(1, 20)]
    fig, top = pa.figure(
        16,
        9,
        3,
        "section 57 · the threshold, and the bill with the bouncer in place",
        "What each operating point buys and costs, and the record's clock replayed with the caught Opus grades removed",
        meta=(
            f"left: every threshold from 0.05 to 0.95 on both arms, registered point {THETA} marked · DIM band = rate null (shuffled blocks, 5th to 95th percentile) · "
            f"right: the 34 items' clocks from figure 01 with Opus grades the bouncer would have caught at {THETA} removed, J-rubric · "
            f"input tokens {sc['speed']['input_tokens']:,} · states cut to the 80k cap: {sc['speed']['cut']} · commit {commit_sha()}"
        ),
    )
    bottom, h = 0.085, top - 0.085 - 0.03
    ax = fig.add_axes([pa.MARGIN + 0.015, bottom, 0.43, h])
    pa.style_axes(ax)
    for arm, col, lw in (("rubric", pa.GOLD, 2.2), ("house", pa.CYAN, 1.4)):
        pts = sc["curve"][arm]
        ax.plot(thetas, [p["caught_opus_bounces"] / p["n_opus_bounces"] for p in pts], color=col, lw=lw, zorder=4, label=f"J-{arm}: share of Opus bounces caught")
        ax.plot(thetas, [p["false_blocks_on_opus_passes"] / p["n_opus_passes"] for p in pts], color=col, lw=lw, ls=":", zorder=4, label=f"J-{arm}: share of Opus passes wrongly blocked")
        ax.plot(thetas, [p["owner_accuracy"] for p in pts], color=col, lw=lw, ls="--", zorder=4, label=f"J-{arm}: accuracy on the owner's 59 rulings")
    ax.axhline(BARS["B3_opus"], color=pa.RED, lw=1.0, ls="--", zorder=3)
    ax.text(0.06, BARS["B3_opus"] + 0.015, f"Opus on the owner's ruler {BARS['B3_opus']:.2f}", color=pa.RED, fontsize=8.2, ha="left")
    n0 = sc["rate_null"]
    ax.axhspan(n0["owner_accuracy"]["p05"], n0["owner_accuracy"]["p95"], color=pa.DIM, alpha=0.5, zorder=1)
    ax.text(0.06, n0["owner_accuracy"]["p95"] + 0.015, "rate null, owner accuracy", color=pa.MUTED, fontsize=8, ha="left")
    ax.axvline(THETA, color=pa.TEXT, lw=1.0, ls="--", zorder=3)
    ax.text(THETA + 0.01, 0.97, f"registered {THETA}", color=pa.TEXT, fontsize=8.4, ha="left", va="top")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1.0)
    ax.set_xticks([0, 0.2, 0.4, 0.6, 0.8, 1.0])
    ax.set_yticks([0, 0.25, 0.5, 0.75, 1.0])
    ax.tick_params(colors=pa.MUTED, labelsize=8.5)
    ax.set_xlabel("block threshold on Jev's probability", color=pa.MUTED, fontsize=9)
    leg = ax.legend(loc="center left", fontsize=7.6, frameon=False, labelcolor=pa.TEXT, bbox_to_anchor=(0.0, 0.42))
    for t in leg.get_texts():
        t.set_color(pa.TEXT)
    pa.panel_title(ax, "solid = bounces caught early (each is 58 s and an Opus call saved) · dotted = passes wrongly blocked (a 42 s writer round wasted) · dashed = the owner's ruler", width=70)

    ax2 = fig.add_axes([pa.MARGIN + 0.475, bottom, 1 - 2 * pa.MARGIN - 0.475, h])
    pa.style_axes(ax2)
    items = _record()
    lanes = _lanes(items)
    caught = {g["grade_id"] for g in data["grades"] if not g["opus_passed"] and _decide(P[g["grade_id"]], "s_", THETA)[0]}
    gid_by_item_at = {(g["item_id"], g["at"]): g["grade_id"] for g in data["grades"]}
    saved_total = 0.0
    gutter = 300
    for i, L in enumerate(lanes):
        it = next(x for x in items if x["item_id"] == L["item_id"])
        before = L["total"]
        after = 0.0
        for r in it["rows"]:
            if r["action"] == "enrich" and r["model"]:
                after += (r["ms"] or 0) / 1000
            elif r["action"] == "grade" and r["model"]:
                gid = gid_by_item_at.get((it["item_id"], r["at"]))
                if gid not in caught:
                    after += (r["ms"] or 0) / 1000
        saved_total += before - after
        ax2.barh(i, before, left=0, height=0.34, color=pa.DIM, zorder=2)
        ax2.barh(i - 0.36, after, left=0, height=0.34, color=pa.GOLD, zorder=3)
        ax2.text(-gutter + 6, i - 0.18, L["title"][:34], color=pa.TEXT, fontsize=7.2, va="center", ha="left")
    ax2.plot([0, 0], [-0.7, len(lanes) - 0.3], color=pa.FRAME, lw=1.0)
    xmax = max(L["total"] for L in lanes) * 1.04
    ticks = [t for t in range(0, 2700, 300) if t <= xmax]
    ax2.set_xlim(-gutter, xmax)
    ax2.set_ylim(len(lanes) - 0.3, -0.7)
    ax2.set_yticks([])
    ax2.set_xticks(ticks)
    ax2.set_xticklabels([f"{t // 60} min" for t in ticks])
    ax2.tick_params(axis="x", colors=pa.MUTED, labelsize=8.5)
    ax2.set_xlabel("model seconds per item: as recorded (grey) and with the caught Opus grades removed (gold)", color=pa.MUTED, fontsize=9)
    pa.panel_title(ax2, f"the bill replayed · {saved_total / 60:.0f} min of {sum(L['total'] for L in lanes) / 60:.0f} removed across 34 items · the writer rounds stay, only the caught Opus grades go", width=70)
    r = sc["rubric"]
    pa.verdict(fig, f"at {THETA}: {r['caught_opus_bounces']} of {r['n_opus_bounces']} Opus bounces caught, {r['false_blocks_on_opus_passes']} of {r['n_opus_passes']} passes wrongly blocked, {saved_total / 60:.0f} min saved on the record")
    pa.frame_panels(fig)
    out = OUTDIR / "03-threshold-and-the-bill.png"
    fig.savefig(out, dpi=pa.DPI, facecolor=pa.BG)
    return out


def main(argv: list[str]) -> None:
    cmd = argv[1] if len(argv) > 1 else "help"
    if cmd == "fig01":
        print(draw01())
    elif cmd == "collect":
        collect()
    elif cmd == "run":
        run()
    elif cmd == "score":
        score()
    elif cmd == "fig02":
        print(draw02())
    elif cmd == "fig03":
        print(draw03())
    else:
        print("commands: fig01 collect run score fig02 fig03")


if __name__ == "__main__":
    main(sys.argv)
