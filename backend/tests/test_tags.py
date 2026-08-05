import pytest

from tests.conftest import auth_headers, login


@pytest.mark.asyncio
async def test_create_and_normalize_tag_label(client, make_mandant, make_user):
    mandant = await make_mandant()
    disponent = await make_user(mandant=mandant, role="disponent", password="pw-123456")
    token = await login(client, disponent.email, "pw-123456")

    resp = await client.post(
        "/api/tags", headers=auth_headers(token), json={"label": "#Nachbestellen"}
    )
    assert resp.status_code == 201
    assert resp.json()["label"] == "nachbestellen"


@pytest.mark.asyncio
async def test_techniker_cannot_create_tag_but_can_assign(
    client, make_mandant, make_user, make_kunde
):
    mandant = await make_mandant()
    disponent = await make_user(mandant=mandant, role="disponent", password="pw-123456")
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    disponent_token = await login(client, disponent.email, "pw-123456")
    techniker_token = await login(client, techniker.email, "pw-123456")

    create_resp = await client.post(
        "/api/tags", headers=auth_headers(techniker_token), json={"label": "verboten"}
    )
    assert create_resp.status_code == 403

    tag_resp = await client.post(
        "/api/tags", headers=auth_headers(disponent_token), json={"label": "ueberfaellig"}
    )
    tag_id = tag_resp.json()["id"]

    assign_resp = await client.post(
        f"/api/tags/{tag_id}/assignments",
        headers=auth_headers(techniker_token),
        json={"entity_type": "kunde", "entity_id": str(kunde.id)},
    )
    assert assign_resp.status_code == 201


@pytest.mark.asyncio
async def test_system_tag_cannot_be_deleted(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    from app.db.session import system_session
    from app.models.tag import Tag

    async with system_session() as session:
        tag = Tag(mandant_id=mandant.id, label="wiederkehrend", system_tag=True)
        session.add(tag)
        await session.flush()
        tag_id = tag.id

    resp = await client.delete(f"/api/tags/{tag_id}", headers=auth_headers(token))
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_assignment_list_and_unassign(client, make_mandant, make_user, make_kunde):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    token = await login(client, admin.email, "pw-123456")

    tag_resp = await client.post(
        "/api/tags", headers=auth_headers(token), json={"label": "gewaehrleistung"}
    )
    tag_id = tag_resp.json()["id"]

    await client.post(
        f"/api/tags/{tag_id}/assignments",
        headers=auth_headers(token),
        json={"entity_type": "kunde", "entity_id": str(kunde.id)},
    )

    list_resp = await client.get(
        "/api/tags/assignments",
        headers=auth_headers(token),
        params={"entity_type": "kunde", "entity_id": str(kunde.id)},
    )
    assert len(list_resp.json()) == 1

    unassign_resp = await client.delete(
        f"/api/tags/{tag_id}/assignments",
        headers=auth_headers(token),
        params={"entity_type": "kunde", "entity_id": str(kunde.id)},
    )
    assert unassign_resp.status_code == 204

    list_after = await client.get(
        "/api/tags/assignments",
        headers=auth_headers(token),
        params={"entity_type": "kunde", "entity_id": str(kunde.id)},
    )
    assert list_after.json() == []


@pytest.mark.asyncio
async def test_duplicate_tag_label_conflicts(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    await client.post("/api/tags", headers=auth_headers(token), json={"label": "eilig"})
    resp = await client.post("/api/tags", headers=auth_headers(token), json={"label": "Eilig"})
    assert resp.status_code == 409
