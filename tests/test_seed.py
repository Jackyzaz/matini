import pathlib

import pytest
from beanie import PydanticObjectId

from matini.api.services.assessment import MAX_EVIDENCE_CHARS
from matini.api.services.nist_rmf import get_criteria
from matini.cmd import seed


def documents(level):
    return [i for d in level["criteria"].values() for i in d["items"] if i["kind"] == "document"]


def stored_text_path(level, name):
    """The file whose text the judge sees: the PDF's Markdown source, or the file itself."""
    if name.endswith(".pdf"):
        return seed.PDF_SOURCE_DIR / level["key"] / (pathlib.Path(name).stem + ".md")
    return seed.DATA_DIR / level["key"] / name


@pytest.mark.parametrize("level", seed.LEVELS, ids=lambda level: level["key"])
def test_seed_files_and_profile_are_consistent(level):
    files = {i["file"] for i in documents(level)}
    on_disk = {p.name for p in (seed.DATA_DIR / level["key"]).iterdir()}
    assert files == on_disk  # nothing referenced is missing, nothing on disk is unused
    for name in files:
        assert (seed.DATA_DIR / level["key"] / name).stat().st_size > 0
        assert stored_text_path(level, name).exists()

    profile = seed.build_profile(level, {name: PydanticObjectId() for name in files})
    measure = {c.id for c in get_criteria() if c.nist_function.value == "MEASURE"}
    assert set(profile.criteria) == {c.id for c in get_criteria()} - measure  # MEASURE comes from probes
    assert profile.updated_date is not None


@pytest.mark.parametrize("level", seed.LEVELS, ids=lambda level: level["key"])
def test_evidence_text_fits_the_judge_budget(level):
    """The judge only sees MAX_EVIDENCE_CHARS of evidence text per criterion, so the decisive text must fit."""
    for criterion_id, declared in level["criteria"].items():
        total = sum(len(i.get("excerpt", "")) for i in declared["items"])
        for item in declared["items"]:
            if item["kind"] == "document":
                total += len(stored_text_path(level, item["file"]).read_text(encoding="utf-8").strip())
        assert total <= MAX_EVIDENCE_CHARS, f"{level['key']}/{criterion_id}: {total} chars"


def test_declared_status_matches_level():
    expected = {1: "not_implemented", 3: "partial", 5: "implemented"}
    for level in seed.LEVELS:
        assert {d["status"] for d in level["criteria"].values()} == {expected[level["score"]]}


def test_seed_creates_valid_llms_and_is_rerunnable(api_client):
    def names():
        return sorted(l["name"] for l in api_client.get("/api/llms?status=all").json()["llms"])

    created = api_client.portal.call(seed.seed_all, "http://ollama.test:11434", "llama3.2:3b", False)
    assert len(created) == 4 and names() == sorted(created)
    llms = {l["name"]: l for l in api_client.get("/api/llms?status=all").json()["llms"]}
    level5 = llms[seed.level_name(seed.LEVEL_5)]
    assert level5["base_url"] == "http://ollama.test:11434" and level5["model_name"] == "llama3.2:3b"

    # the stored profile is accepted by the same endpoint the Admin modal uses, and its files download
    res = api_client.put(f"/api/llms/update/{level5['id']}/profile", json=level5["assessment_profile"])
    assert res.status_code == 200
    file_ids = [i["file_id"] for c in level5["assessment_profile"]["criteria"].values() for i in c["items"] if i["file_id"]]
    assert len(file_ids) == 8
    for file_id in file_ids:
        assert api_client.get(f"/api/evidence-files/{file_id}/download").status_code == 200
        assert api_client.get(f"/api/evidence-files/{file_id}").json()["has_text"] is True

    assert api_client.portal.call(seed.seed_all, "http://x", "m", False) == []  # second run skips everything
    assert len(api_client.portal.call(seed.seed_all, "http://x", "m", True)) == 4
    assert len(names()) == 4  # the old ones are soft-deleted, not duplicated
