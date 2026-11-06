from tests.helpers import client, finalize, make_draft, make_user


def _patient(h, user, name, ident=None, gender="Male"):
    r = finalize(h, make_draft(user).id, create_new_anyway=True,
                 new_patient={"full_name": name, "patient_identifier": ident, "gender": gender})
    assert r.status_code == 200, r.text
    return r.json()["patient"]


def test_partial_name_and_exact_id_search():
    user, h = make_user()
    _patient(h, user, "Ramesh Kumar", "UH1001")
    _patient(h, user, "Mrs. Rama S", "UH1002", "Female")
    _patient(h, user, "Priya Nair", "UH2001", "Female")
    names = {p["full_name"] for p in client.get("/api/patients?q=ram", headers=h).json()}
    assert names == {"Ramesh Kumar", "Mrs. Rama S"}
    exact = client.get("/api/patients?q=uh 1001", headers=h).json()
    assert [p["full_name"] for p in exact] == ["Ramesh Kumar"]
    prefix = {p["full_name"] for p in client.get("/api/patients?q=UH10", headers=h).json()}
    assert prefix == {"Ramesh Kumar", "Mrs. Rama S"}
    assert exact[0]["report_count"] == 1 and exact[0]["latest_study_date"] == "2026-10-23"


def test_like_wildcards_are_escaped():
    user, h = make_user()
    _patient(h, user, "Anil Rao")
    assert client.get("/api/patients?q=%25%25", headers=h).json() == []


def test_dashboard_list_carries_patient_for_finalized_drafts():
    user, h = make_user()
    other, ho = make_user()
    finalized = make_draft(user)
    plain = make_draft(user)
    fr = finalize(h, finalized.id, new_patient={"full_name": "Dash Board", "patient_identifier": "DB1",
                                                 "gender": "Male"}).json()
    items = {r["id"]: r for r in client.get("/api/reports", headers=h).json()}
    assert items[plain.id]["final_report"] is None
    summary = items[finalized.id]["final_report"]
    assert summary["id"] == fr["id"] and summary["patient_name"] == "Dash Board"
    # After an amendment the dashboard points at the newest version.
    amended = client.post(f"/api/final-reports/{fr['id']}/amend", json={"final_text": "## X\\nNew."}, headers=h).json()
    items = {r["id"]: r for r in client.get("/api/reports", headers=h).json()}
    assert items[finalized.id]["final_report"]["id"] == amended["id"]
    # Another doctor sees neither the draft nor the patient.
    assert all(r["id"] != finalized.id for r in client.get("/api/reports", headers=ho).json())


def test_final_reports_search_by_patient():
    user, h = make_user()
    _patient(h, user, "Kavya Menon", "KM9", "Female")
    _patient(h, user, "Arjun Das", "AD3")
    names = [r["patient"]["full_name"] for r in client.get("/api/final-reports?q=kavya&limit=200", headers=h).json()]
    assert names == ["Kavya Menon"]
    assert client.get("/api/final-reports?q=nobody", headers=h).json() == []
    assert len(client.get("/api/final-reports?limit=200", headers=h).json()) == 2
