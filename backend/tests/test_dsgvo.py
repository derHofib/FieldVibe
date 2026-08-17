import io

import pytest

from tests.conftest import auth_headers, login


@pytest.mark.asyncio
async def test_super_admin_can_upload_list_and_replace_dsgvo_dokument(
    client, make_user
):
    super_admin = await make_user(mandant=None, role="super_admin", password="pw-123456")
    token = await login(client, super_admin.email, "pw-123456")

    upload = await client.post(
        "/api/admin/dsgvo-dokumente/avv_vorlage",
        headers=auth_headers(token),
        files={"file": ("avv.pdf", io.BytesIO(b"%PDF-1.4 test"), "application/pdf")},
    )
    assert upload.status_code == 201
    body = upload.json()
    assert body["typ"] == "avv_vorlage"
    assert body["dateiname"] == "avv.pdf"

    list_resp = await client.get("/api/admin/dsgvo-dokumente", headers=auth_headers(token))
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1
    assert list_resp.json()[0]["typ"] == "avv_vorlage"

    url_resp = await client.get(
        "/api/admin/dsgvo-dokumente/avv_vorlage/download-url", headers=auth_headers(token)
    )
    assert url_resp.status_code == 200
    assert url_resp.json()["url"]

    # Erneuter Upload desselben Typs ersetzt das bestehende Dokument statt
    # ein zweites anzulegen.
    replace = await client.post(
        "/api/admin/dsgvo-dokumente/avv_vorlage",
        headers=auth_headers(token),
        files={"file": ("avv-v2.pdf", io.BytesIO(b"%PDF-1.4 v2"), "application/pdf")},
    )
    assert replace.status_code == 201
    assert replace.json()["dateiname"] == "avv-v2.pdf"

    list_resp_2 = await client.get("/api/admin/dsgvo-dokumente", headers=auth_headers(token))
    assert len(list_resp_2.json()) == 1
    assert list_resp_2.json()[0]["dateiname"] == "avv-v2.pdf"

    delete_resp = await client.delete(
        "/api/admin/dsgvo-dokumente/avv_vorlage", headers=auth_headers(token)
    )
    assert delete_resp.status_code == 204

    list_resp_3 = await client.get("/api/admin/dsgvo-dokumente", headers=auth_headers(token))
    assert list_resp_3.json() == []


@pytest.mark.asyncio
async def test_dsgvo_dokument_lehnt_unbekannten_typ_und_falschen_dateityp_ab(client, make_user):
    super_admin = await make_user(mandant=None, role="super_admin", password="pw-123456")
    token = await login(client, super_admin.email, "pw-123456")

    unbekannt = await client.post(
        "/api/admin/dsgvo-dokumente/nicht_existent",
        headers=auth_headers(token),
        files={"file": ("x.pdf", io.BytesIO(b"%PDF-1.4"), "application/pdf")},
    )
    assert unbekannt.status_code == 400

    falscher_typ = await client.post(
        "/api/admin/dsgvo-dokumente/impressum",
        headers=auth_headers(token),
        files={"file": ("x.exe", io.BytesIO(b"MZ"), "application/x-msdownload")},
    )
    assert falscher_typ.status_code == 400


@pytest.mark.asyncio
async def test_mandant_admin_cannot_access_dsgvo_dokumente(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    resp = await client.get("/api/admin/dsgvo-dokumente", headers=auth_headers(token))
    assert resp.status_code == 403

    upload = await client.post(
        "/api/admin/dsgvo-dokumente/impressum",
        headers=auth_headers(token),
        files={"file": ("x.pdf", io.BytesIO(b"%PDF-1.4"), "application/pdf")},
    )
    assert upload.status_code == 403


@pytest.mark.asyncio
async def test_download_url_ohne_dokument_gibt_404(client, make_user):
    super_admin = await make_user(mandant=None, role="super_admin", password="pw-123456")
    token = await login(client, super_admin.email, "pw-123456")

    resp = await client.get(
        "/api/admin/dsgvo-dokumente/tom_dokument/download-url", headers=auth_headers(token)
    )
    assert resp.status_code == 404
