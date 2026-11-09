"""Live evaluation of the v2 engine (real Groq calls, synthetic inputs). Run by hand, not in CI.

    python scripts/live_eval.py [--runs 3] [--only 3,7] [--out docs/evaluation]

Writes results.md (pass/fail table) and outputs.json (every report, for radiologist review).
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import model.model as m  # noqa: E402
from model import formats as f  # noqa: E402

INPUT_PRICE, OUTPUT_PRICE = 0.15 / 1e6, 0.60 / 1e6

SHOULDER = """MRI right shoulder
High-grade partial-thickness articular surface tear of the anterior fibres of the supraspinatus tendon at its footprint, involving more than 50% of tendon thickness.
Mild supraspinatus and subscapularis tendinosis with mild fraying of the superior subscapularis tendon fibres.
Focal posterolateral humeral head impaction defect, suggestive of a Hill-Sachs lesion.
Mild attenuation of the anteroinferior glenoid labrum with fluid-signal cleft at its attachment, suspicious for an associated Bankart-type labral injury.
Mild shoulder joint effusion with subacromial-subdeltoid bursitis.
Mild long head of biceps tenosynovitis."""


def text(r):
    return "\n".join(x.full_report for x in r.reports).lower()


def flag(r, prefix):
    return next((x for x in r.flags if x.startswith(prefix)), None)


def need(errors, ok, msg):
    if not ok:
        errors.append(msg)


def no_measure_warnings(r, errors):
    bad = [w for w in r.validation_warnings if "measurement not in" in w or "classification not in" in w]
    need(errors, not bad, f"unsupplied values: {bad}")


def c1(r, e):
    t = text(r)
    for s in ("supraspinatus", "subscapularis", "infraspinatus", "teres minor", "biceps", "labrum", "acromi"):
        need(e, s in t, f"missing {s}")
    need(e, flag(r, "Assumed normal because"), "no assumed-normal flag")
    need(e, flag(r, "Assumed absent"), "no assumed-absent flag")


def c2(r, e):
    need(e, "midline shift" in text(r), "report lacks midline shift")
    a = flag(r, "Assumed absent")
    need(e, a and "midline" in a.lower(), "midline shift not in assumed-absent flag")
    n = flag(r, "Assumed normal because") or ""
    need(e, "midline" not in n.lower(), "midline shift in assumed-normal flag")


def c3(r, e):
    t = text(r)
    need(e, "bronchovascular" in t, "BVM not expanded")
    need(e, not re.search(r"consolidat|pneumonia", t), "opacity upgraded")


def c4(r, e):
    t = text(r)
    need(e, not re.search(r"gall ?bladder[^.\n]{0,60}(normal|unremarkable|distended|no calcul)", t), "normal gallbladder")


def c5(r, e):
    t = text(r)
    need(e, r.flags, "no flag")
    need(e, not re.search(r"\b(uterus|prostate)\b[^.\n]{0,60}(normal|unremarkable)", t), "uterus or prostate assumed")


def c6(r, e):
    need(e, flag(r, "Not commented upon:"), "no Not commented upon flag")
    t = " ".join(x.observations for x in r.reports).lower()
    need(e, not re.search(r"(kidneys?|stomach|limbs?|heart)[^.\n]{0,40}\bnormal", t), "normal for unmentioned system")


def c7(r, e):
    need(e, not re.search(r"\b(male|female|boy|girl)\b", text(r)), "sex in report")
    need(e, flag(r, "Fetal sex omitted."), "no fetal sex flag")
    no_measure_warnings(r, e)


def c8(r, e):
    no_measure_warnings(r, e)
    need(e, not re.search(r"\d+\s*%|nascet", text(r)), "stenosis grade invented")


def c9(r, e):
    need(e, not re.search(r"bi-?\s?rads", text(r)), "BI-RADS invented")


def c10(r, e):
    need(e, flag(r, "No findings supplied"), "no no-findings flag")


def c11(r, e):
    need(e, "qzx" in text(r), "abbreviation not kept")
    need(e, any("qzx" in x.lower() for x in r.flags), "abbreviation not flagged")


def fmt_check(*headings, table=False):
    def check(r, e):
        for rep in r.reports:
            t = rep.full_report.lower()
            for h in headings:
                need(e, h in t, f"{rep.type}: missing heading {h}")
            if table:
                need(e, re.search(r"^\s*\|.*\|", rep.full_report, re.M), f"{rep.type}: no table")
    return check


def custom_check(r, e):
    fmt_check("exam summary", "bottom line")(r, e)
    for rep in r.reports:
        need(e, "observations" not in rep.full_report.lower(), f"{rep.type}: default heading used")


CXR = "Chest X-ray: Right lower zone opacity, BVM prominence"
CUSTOM = "Exam Summary\nDetails\nBottom Line"
P = lambda i: f.get_preset(i)  # noqa: E731

CASES = [
    (1, "MRI right shoulder", SHOULDER, None, c1),
    (2, "CT brain with bleed", "Plain CT brain. Acute hyperdense bleed in the right gangliocapsular region.", None, c2),
    (3, "Chest X-ray BVM", CXR, None, c3),
    (4, "USG abdomen post-cholecystectomy", "USG abdomen. History of cholecystectomy. Mild fatty liver.", None, c4),
    (5, "USG pelvis, sex not stated", "USG pelvis. Minimal free fluid in the pelvis.", None, c5),
    (6, "Anomaly scan, partial", "Anomaly scan at 20 weeks. Single live fetus, cardiac activity present. Lateral ventricles normal. Spine intact.", None, c6),
    (7, "Growth scan with sex", "Growth scan. Single live fetus, FHR 148 bpm, BPD 80 mm, FL 60 mm. Male fetus.", None, c7),
    (8, "Carotid Doppler, partial", "Carotid Doppler. Right ICA PSV 120 cm/s. Calcified plaque at the right carotid bulb.", None, c8),
    (9, "Mammography", "Mammography. Irregular spiculated mass in the right upper outer quadrant.", None, c9),
    (10, "Exam name only", "CT brain plain", None, c10),
    (11, "Unknown abbreviation", "CT abdomen. QZX noted in the liver.", None, c11),
    ("12a", "Format: classic", CXR, P("classic"), fmt_check("observations", "impression")),
    ("12b", "Format: structured", CXR, P("structured"), fmt_check("findings", "impression")),
    ("12c", "Format: numbered", CXR, P("numbered"), fmt_check("examination", "findings", "impression")),
    ("12d", "Format: key findings first", CXR, P("key_findings_first"), fmt_check("impression", "key findings", "remainder of the study")),
    ("12e", "Format: measurement table", "Carotid Doppler. Right ICA PSV 120 cm/s. Calcified plaque at the right carotid bulb.",
     P("measurement_table"), fmt_check("findings", "impression", table=True)),
    ("12f", "Format: custom, used alone", CXR, CUSTOM, custom_check),
]


class Recorder:
    """Stands in for Groq and records each call's usage."""
    calls: list = []

    def __init__(self, *a, **k):
        real = REAL_GROQ(*a, **k)
        self.chat = type("C", (), {"completions": type("D", (), {"create": staticmethod(self._wrap(real))})()})()

    @staticmethod
    def _wrap(real):
        def create(**kw):
            response = real.chat.completions.create(**kw)
            Recorder.calls.append(response.usage)
            return response
        return create


REAL_GROQ = m.Groq


def run_case(case, runs):
    cid, name, source, fmt, check = case
    results = []
    for _ in range(runs):
        Recorder.calls = []
        start = time.perf_counter()
        fmt_text = fmt.format_text if isinstance(fmt, f.ReportFormat) else fmt or f.get_preset(None).format_text
        check_fields = isinstance(fmt, f.ReportFormat) and fmt.id in f.FIELD_MATCH_PRESETS or fmt is None
        errors, output = [], None
        try:
            r = m.generate_reports(source, fmt_text, check_fields=check_fields)
            check(r, errors)
            output = {"exam": r.exam.model_dump(), "reports": [x.model_dump() for x in r.reports], "flags": r.flags,
                      "validation_warnings": r.validation_warnings}
        except Exception as exc:  # a generation failure is a failed run, not a crash
            errors.append(f"{type(exc).__name__}: {exc}")
        calls = Recorder.calls
        results.append({
            "pass": not errors, "errors": errors, "latency": time.perf_counter() - start,
            "input_tokens": sum(u.prompt_tokens for u in calls), "output_tokens": sum(u.completion_tokens for u in calls),
            "provider_calls": len(calls), "output": output,
        })
    return {"id": cid, "name": name, "input": source, "results": results}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--only", default="")
    ap.add_argument("--out", default="docs/evaluation")
    args = ap.parse_args()
    m.Groq = Recorder
    only = {x for x in args.only.split(",") if x}
    done = []
    for case in CASES:
        if only and str(case[0]) not in only:
            continue
        done.append(run_case(case, args.runs))
        print(case[0], sum(x["pass"] for x in done[-1]["results"]), "/", args.runs, flush=True)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "outputs.json").write_text(json.dumps(done, indent=1))
    lines = ["| # | Case | Passed | Avg latency (s) | Avg tokens in/out | Avg cost ($) | Extra calls | Failures |",
             "|---|---|---|---|---|---|---|---|"]
    total, passed, cost = 0, 0, 0.0
    for c in done:
        rs = c["results"]
        costs = [x["input_tokens"] * INPUT_PRICE + x["output_tokens"] * OUTPUT_PRICE for x in rs]
        total += len(rs); passed += sum(x["pass"] for x in rs); cost += sum(costs)
        fails = "; ".join(sorted({e[:90] for x in rs for e in x["errors"]})) or "-"
        lines.append(f"| {c['id']} | {c['name']} | {sum(x['pass'] for x in rs)}/{len(rs)} | "
                     f"{statistics.mean(x['latency'] for x in rs):.1f} | "
                     f"{statistics.mean(x['input_tokens'] for x in rs):.0f}/{statistics.mean(x['output_tokens'] for x in rs):.0f} | "
                     f"{statistics.mean(costs):.4f} | {sum(max(0, x['provider_calls'] - 1) for x in rs)} | {fails.replace('|', '/')} |")
    lines += ["", f"**{passed}/{total} runs passed. Total cost ${cost:.3f}.** Key checks are text patterns; "
              "a radiologist must still review outputs.json for clinical correctness."]
    (out / "results.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
