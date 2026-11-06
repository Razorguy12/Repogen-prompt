"""Live prompt regression set (calls the real Groq model; inputs are synthetic).

    python scripts/prompt_regression.py            # all cases
    python scripts/prompt_regression.py bvm cyst   # cases whose name contains a term

Exit code 0 when every assertion passes. LLM output varies, so treat a single
failure as a signal to inspect rather than proof of a regression.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import model.model as m  # noqa: E402
from model import comparison as cmp  # noqa: E402


def all_text(res: m.ReportAlternatives) -> str:
    return "\n".join(r.full_report for r in res.reports).lower()


def check(cond: bool, msg: str, errors: list[str]):
    if not cond:
        errors.append(msg)


# ---------------------------------------------------------------- generation cases

def case_bvm(errors):
    res = m.generate_reports("xray - Right lower zone opacity, BVM prominence, Left peri-hilar infiltrates")
    text = all_text(res)
    check("bronchovascular" in text, "missing 'bronchovascular'", errors)
    check("bag-valve" not in text and "bony vascular" not in text, "BVM mis-expanded", errors)
    check(res.exam.modality == "XR", f"modality {res.exam.modality} != XR", errors)


def case_fetal_sex(errors):
    res = m.generate_reports(
        "USG obstetric: single live intrauterine fetus, cardiac activity present, FHR 148 bpm. "
        "BPD 48 mm, FL 33 mm, ~20 weeks. Placenta posterior, liquor adequate. Male fetus.")
    text = all_text(res)
    check(not re.search(r"\b(male|female|boy|girl)\b", text), "fetal sex appears in a report", errors)
    check(len(res.flags) > 0, "no flag raised for omitted fetal sex", errors)


def case_anomaly_partial(errors):
    res = m.generate_reports(
        "Anomaly scan (TIFFA): single live fetus, 20 weeks, cardiac activity present. "
        "Brain: lateral ventricles 6 mm, cerebellum normal. Spine: intact.")
    flags = " ".join(res.flags).lower()
    check(any(w in flags for w in ("heart", "cardiac", "kidney", "renal", "abdomen", "face", "limb", "system")),
          f"no flag listing unmentioned systems: {res.flags}", errors)
    obs = " ".join(r.observations for r in res.reports).lower()
    check(not re.search(r"(kidneys?|four[- ]chamber|stomach|limbs?)[^.]{0,40}\bnormal", obs),
          "normal statements for unmentioned systems", errors)
    check(res.reports[0].word_limit.replace(" ", "") == "120-180",
          f"anomaly scan concise word_limit {res.reports[0].word_limit} (expected extended 120-180)", errors)


def case_doppler_no_velocities(errors):
    res = m.generate_reports(
        "Arterial doppler right lower limb: triphasic waveforms in CFA, SFA, popliteal, ATA, PTA. "
        "No stenosis or occlusion.")
    for r in res.reports:
        check(not re.search(r"\d", r.observations), f"numbers in {r.type} observations", errors)


def case_no_modality(errors):
    res = m.generate_reports("Brain: 2 cm well-defined lesion in the right frontal lobe with perilesional oedema.")
    check(res.exam.modality == "UNSPECIFIED", f"modality {res.exam.modality} != UNSPECIFIED", errors)
    check(all("not specified" in r.protocol.lower() for r in res.reports), "protocol does not say not specified",
          errors)


# ---------------------------------------------------------------- comparison cases

def side(mod, region, text, lat="Not applicable"):
    return cmp.ExamSide(modality=mod, region=region, laterality=lat, text=text)


def categories_for(result, *words):
    return [c.category for c in result.changes if all(w in c.finding.lower() for w in words)]


def case_cmp_resolved(errors):
    res, _, _ = cmp.generate_comparison(
        side("XR", "Chest", "## CHEST RADIOGRAPH\nObservations: Right lower zone opacity. Heart size normal.\n"
                            "### IMPRESSION\nRight lower zone opacity."),
        side("XR", "Chest", "## CHEST RADIOGRAPH\nObservations: Lung fields clear. Heart size normal.\n"
                            "### IMPRESSION\nNo active lung lesion."), 14)
    cats = categories_for(res, "lower zone") or categories_for(res, "opacity")
    check(cats == ["RESOLVED"], f"RLZ opacity categories {cats} (expected RESOLVED)", errors)


def case_cmp_cyst_increased(errors):
    res, _, _ = cmp.generate_comparison(
        side("US", "Pelvis", "## USG PELVIS\nLeft ovarian cyst 3 x 2 cm. Uterus normal.", "Left"),
        side("US", "Pelvis", "## USG PELVIS\nLeft ovarian cyst 4 x 3 cm. Uterus normal.", "Left"), 90)
    cyst = [c for c in res.changes if "cyst" in c.finding.lower()]
    check(len(cyst) == 1 and cyst[0].category == "INCREASED", f"cyst rows {[c.category for c in cyst]}", errors)
    if cyst:
        both = (cyst[0].baseline + cyst[0].follow_up).replace("×", "x")
        check("3 x 2" in both and "4 x 3" in both, "measurements not quoted", errors)
    check("%" not in res.model_dump_json(), "percentage present", errors)


def case_cmp_not_mentioned(errors):
    res, _, _ = cmp.generate_comparison(
        side("US", "Abdomen", "## USG ABDOMEN\nLiver normal. 8 mm calculus in the right kidney."),
        side("US", "Abdomen", "## USG ABDOMEN\nLiver normal. Gallbladder normal."), 30)
    cats = categories_for(res, "calcul") or categories_for(res, "kidney") or categories_for(res, "renal")
    check(cats and all(c == "NOT COMPARABLE" for c in cats), f"renal calculus categories {cats}", errors)


def case_cmp_ct_vs_us(errors):
    res, _, _ = cmp.generate_comparison(
        side("CT", "Abdomen", "## CT ABDOMEN\n2 cm hypodense lesion in segment VI of the liver."),
        side("US", "Abdomen", "## USG ABDOMEN\n2.2 cm hypoechoic lesion in the right lobe of the liver."), 21)
    check(not res.examinations_comparable or len(res.limitations) > 0, "no limitations for CT vs US", errors)


CASES = {name[5:]: fn for name, fn in globals().items() if name.startswith("case_")}


def main(argv):
    selected = {k: v for k, v in CASES.items() if not argv or any(a in k for a in argv)}
    failures = 0
    for name, fn in selected.items():
        errors: list[str] = []
        try:
            fn(errors)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"error: {type(exc).__name__}: {exc}")
        status = "PASS" if not errors else "FAIL"
        failures += bool(errors)
        print(f"{status}  {name}" + "".join(f"\n      - {e}" for e in errors), flush=True)
    print(f"\n{len(selected) - failures}/{len(selected)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
