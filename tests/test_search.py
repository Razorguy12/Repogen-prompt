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
