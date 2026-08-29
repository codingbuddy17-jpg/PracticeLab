"""
Chart pages are served by the API, not fetched from the bucket by the browser.

Written before moving the storage call behind services/storage.py, so the
refactor has something to be judged against. Nothing here asserts HOW the bytes
are fetched — only what the endpoint returns — which is the point: an
implementation change should leave every one of these untouched.

It also pins the property the migration documentation leans on. The browser is
never handed a bucket URL and never holds a credential, so the storage backend
needs to be reachable from the API and from nowhere else. Swapping S3 for
Azure Blob or a file share must not change that.
"""
import io

import pytest

from models import Chart, ChartFile, ChartStatus, Difficulty, Specialty


@pytest.fixture()
def chart_with_page(db):
    chart = Chart(chart_number="PX001", specialty=Specialty.SDS, category="Test",
                  difficulty=Difficulty.INTERMEDIATE, status=ChartStatus.ACTIVE,
                  uploaded_by="t")
    db.add(chart)
    db.flush()
    db.add(ChartFile(chart_id=chart.id, storage_key=f"charts/{chart.id}/0000_page.png",
                     original_filename="page.png", page_order=0, total_pages=1,
                     uploaded_by="t"))
    db.commit()
    return chart


@pytest.fixture()
def fake_storage(monkeypatch):
    """
    Stand in for the bucket. Records what was asked for so the test can check
    the endpoint looked up the right key.
    """
    asked = {}

    class _Body(io.BytesIO):
        pass

    def _fake_get_object(Bucket=None, Key=None):          # noqa: N803 — boto3 kwargs
        asked["bucket"], asked["key"] = Bucket, Key
        return {"Body": _Body(b"PNGBYTES"), "ContentType": "image/png"}

    class _Client:
        get_object = staticmethod(_fake_get_object)

    import services.storage as storage
    monkeypatch.setattr(storage, "get_s3_client", lambda: _Client())
    # routers.charts imported the helper by name, so patch it there too until
    # the call moves behind the service wrapper.
    import routers.charts as charts_router
    if hasattr(charts_router, "get_s3_client"):
        monkeypatch.setattr(charts_router, "get_s3_client", lambda: _Client())
    return asked


def test_a_page_is_served_by_the_api(client, db, chart_with_page, fake_storage):
    r = client.get(f"/charts/{chart_with_page.id}/page/0")
    assert r.status_code == 200
    assert r.content == b"PNGBYTES"


def test_the_content_type_comes_from_the_stored_object(client, db, chart_with_page, fake_storage):
    r = client.get(f"/charts/{chart_with_page.id}/page/0")
    assert r.headers["content-type"].startswith("image/png")


def test_the_response_is_privately_cacheable(client, db, chart_with_page, fake_storage):
    """
    A chart page is the same bytes every time, so an hour of browser cache
    saves a round trip per page turn. Private, because the URL is per-chart and
    the content is not for a shared cache.
    """
    r = client.get(f"/charts/{chart_with_page.id}/page/0")
    assert r.headers["cache-control"] == "private, max-age=3600"


def test_it_asks_the_bucket_for_the_key_the_database_holds(client, db, chart_with_page, fake_storage):
    """
    storage_key is the only link between a database row and its image. If the
    endpoint ever derived the key instead of reading it, a bucket copy that
    preserved keys would still break.
    """
    client.get(f"/charts/{chart_with_page.id}/page/0")
    assert fake_storage["key"] == f"charts/{chart_with_page.id}/0000_page.png"


def test_a_missing_page_is_a_404_not_a_storage_error(client, db, chart_with_page, fake_storage):
    r = client.get(f"/charts/{chart_with_page.id}/page/99")
    assert r.status_code == 404
    assert "key" not in fake_storage, "the bucket was called for a page that does not exist"


def test_a_missing_chart_is_a_404(client, db, fake_storage):
    assert client.get("/charts/999999/page/0").status_code == 404


def test_no_bucket_url_or_credential_reaches_the_client(client, db, chart_with_page, fake_storage):
    """
    The property the migration documentation depends on: the browser talks to
    the API and never to storage. If this ever fails, the deployment needs
    browser-reachable storage and CORS, and the handover document is wrong.
    """
    r = client.get(f"/charts/{chart_with_page.id}/page/0")
    blob = str(r.headers) + r.text[:200]
    for leak in ("r2.cloudflarestorage.com", "amazonaws.com",
                 "X-Amz-Signature", "STORAGE_ACCESS_KEY"):
        assert leak not in blob, f"{leak} reached the client"


def test_chart_text_returns_stored_page_text(client, db, chart_with_page):
    chart_with_page.files[0].page_text = "Discharge Summary\nSepsis due to pneumonia."
    db.commit()

    r = client.get(f"/charts/{chart_with_page.id}/text")

    assert r.status_code == 200
    body = r.json()
    assert body["chart_number"] == "PX001"
    assert body["has_text"] is True
    assert body["pages"] == [{
        "page": 0,
        "text": "Discharge Summary\nSepsis due to pneumonia.",
        "has_text": True,
    }]


def test_chart_text_does_not_call_storage(client, db, chart_with_page, fake_storage):
    chart_with_page.files[0].page_text = "Operative Report\nExcision performed."
    db.commit()

    r = client.get(f"/charts/{chart_with_page.id}/text")

    assert r.status_code == 200
    assert "key" not in fake_storage


def test_chart_text_reports_absent_extracted_text(client, db, chart_with_page):
    r = client.get(f"/charts/{chart_with_page.id}/text")

    assert r.status_code == 200
    assert r.json()["has_text"] is False
    assert r.json()["pages"][0]["has_text"] is False


def test_text_search_returns_page_snippets(client, db, chart_with_page):
    chart_with_page.files[0].page_text = (
        "History and Physical\n"
        "The patient was admitted with sepsis due to pneumonia and acute kidney injury."
    )
    db.commit()

    r = client.get(f"/charts/{chart_with_page.id}/text-search", params={"q": "sepsis"})

    assert r.status_code == 200
    body = r.json()
    assert body["matching_pages"] == [0]
    assert body["snippets"][0]["page"] == 0
    assert "sepsis due to pneumonia" in body["snippets"][0]["snippet"]
