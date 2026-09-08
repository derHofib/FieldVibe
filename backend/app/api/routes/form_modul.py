"""Routen fuer das Formular-Modul v2 (Schema-Verwaltung + Ausfuellungen).

Zwei Router:
- `router` (/api/form-schemas): Verwaltung von Schema/Gruppen/Feldern/
  Views/Layouts/Praesentationselementen/Regeln/Auftragstyp-Zuordnungen.
  Rechte-Bereich "formulare" (dasselbe Bereichs-Vokabular wie das alte
  Modul, siehe app/api/routes/formulare.py).
- `submissions_router` (/api/form-submissions): Ausfuellungen an einem
  Vorgang -- Rechte-Bereich "vorgaenge", Zugriff zusaetzlich auf den
  eigenen Vorgang beschraenkt (siehe _require_own_vorgang, identisch zum
  Muster in app/api/routes/vorgang_formulare.py).
"""
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_current_user, get_db, require_recht, require_roles
from app.models.anlage import Anlage
from app.models.mandant import Mandant
from app.models.form_modul import (
    FormAuftragstypZuordnung,
    FormField,
    FormGroup,
    FormLogicRule,
    FormPresentationElement,
    FormSchema,
    FormSubmission,
    FormSubmissionAudit,
    FormView,
    FormViewFieldLayout,
)
from app.models.kunde import Kunde
from app.models.standort import Standort
from app.models.user import User
from app.models.vorgang import Vorgang
from app.models.vorgang_event import VorgangEvent
from app.schemas.form_modul import (
    FormAuftragstypZuordnungCreate,
    FormAuftragstypZuordnungRead,
    FormAuftragstypZuordnungUpdate,
    FormFieldCreate,
    FormFieldRead,
    FormFieldStateRead,
    FormFieldUpdate,
    FormGroupCreate,
    FormGroupRead,
    FormGroupUpdate,
    FormLogicRuleCreate,
    FormLogicRuleRead,
    FormLogicRuleUpdate,
    FormPresentationElementCreate,
    FormPresentationElementRead,
    FormPresentationElementUpdate,
    FormSchemaCreate,
    FormSchemaDetailRead,
    FormSchemaRead,
    FormSchemaUpdate,
    FormSchemaVerfuegbar,
    FormSubmissionRead,
    FormSubmissionStart,
    FormSubmissionValuesUpdate,
    FormViewCreate,
    FormViewFieldLayoutIn,
    FormViewFieldLayoutRead,
    FormViewRead,
    FormViewResolvedRead,
    FormViewUpdate,
)
from app.services import form_modul_service, storage_service
from app.services.event_bus import event_bus
from app.services.form_logic_engine import FormLogicCycleError, detect_cycles
from app.services.pdf_service import generate_form_submission_pdf
from app.services.rechte_service import ist_auf_zugewiesene_kunden_beschraenkt
from app.services.vorgang_completion_service import VORGANG_STATUS_GESCHLOSSEN
from app.services.zuweisung_service import assigned_kunde_ids

MAX_UPLOAD_BYTES = 15 * 1024 * 1024
FELDTYPEN_MIT_DATEI = ("foto", "unterschrift")

router = APIRouter(
    prefix="/api/form-schemas",
    tags=["form-modul"],
    dependencies=[
        Depends(require_roles("mandant_admin", "custom")),
        Depends(require_recht("formulare", "sehen")),
    ],
)

submissions_router = APIRouter(
    prefix="/api/form-submissions",
    tags=["form-modul"],
    dependencies=[
        Depends(require_roles("mandant_admin", "custom")),
        Depends(require_recht("vorgaenge", "sehen")),
    ],
)


# --- form_schemas ------------------------------------------------------


async def _get_schema_or_404(session: AsyncSession, schema_id: UUID) -> FormSchema:
    schema = await session.get(FormSchema, schema_id)
    if schema is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Formular-Schema nicht gefunden")
    return schema


async def _schema_detail(session: AsyncSession, schema: FormSchema) -> FormSchemaDetailRead:
    groups = await form_modul_service.groups_fuer(session, schema.id)
    fields = await form_modul_service.fields_fuer(session, schema.id)
    zuordnungen = await form_modul_service.zuordnungen_fuer(session, schema.id)
    return FormSchemaDetailRead(
        **{k: getattr(schema, k) for k in FormSchemaRead.model_fields},
        groups=[FormGroupRead.model_validate(g) for g in groups],
        fields=[FormFieldRead.model_validate(f) for f in fields],
        zuordnungen=[FormAuftragstypZuordnungRead.model_validate(z) for z in zuordnungen],
    )


async def _existing_keys(session: AsyncSession, schema_id: UUID) -> set[str]:
    fields = await form_modul_service.fields_fuer(session, schema_id)
    groups = await form_modul_service.groups_fuer(session, schema_id)
    return {f.key for f in fields} | {g.key for g in groups}


@router.get("", response_model=list[FormSchemaRead])
async def list_schemas(
    status_filter: str | None = Query(default=None, alias="status"),
    session: AsyncSession = Depends(get_db),
) -> list[FormSchema]:
    stmt = select(FormSchema).order_by(FormSchema.name)
    if status_filter is not None:
        stmt = stmt.where(FormSchema.status == status_filter)
    return list((await session.execute(stmt)).scalars().all())


@router.post(
    "",
    response_model=FormSchemaRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_recht("formulare", "erstellen"))],
)
async def create_schema(
    body: FormSchemaCreate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> FormSchema:
    schema = FormSchema(
        mandant_id=auth.mandant_id,
        name=body.name,
        beschreibung=body.beschreibung,
        erstellt_von=auth.user_id,
    )
    session.add(schema)
    await session.flush()
    await session.refresh(schema)
    return schema


@router.get("/{schema_id}", response_model=FormSchemaDetailRead)
async def get_schema(schema_id: UUID, session: AsyncSession = Depends(get_db)) -> FormSchemaDetailRead:
    schema = await _get_schema_or_404(session, schema_id)
    return await _schema_detail(session, schema)


@router.patch(
    "/{schema_id}",
    response_model=FormSchemaDetailRead,
    dependencies=[Depends(require_recht("formulare", "bearbeiten"))],
)
async def update_schema(
    schema_id: UUID, body: FormSchemaUpdate, session: AsyncSession = Depends(get_db)
) -> FormSchemaDetailRead:
    schema = await _get_schema_or_404(session, schema_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(schema, field, value)
    await session.flush()
    await session.refresh(schema)
    return await _schema_detail(session, schema)


# --- form_groups ---------------------------------------------------------


@router.post(
    "/{schema_id}/groups",
    response_model=FormGroupRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_recht("formulare", "bearbeiten"))],
)
async def create_group(
    schema_id: UUID,
    body: FormGroupCreate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> FormGroup:
    await _get_schema_or_404(session, schema_id)
    if body.key in await _existing_keys(session, schema_id):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Key '{body.key}' ist bereits vergeben")
    group = FormGroup(mandant_id=auth.mandant_id, schema_id=schema_id, **body.model_dump())
    session.add(group)
    await session.flush()
    await session.refresh(group)
    return group


@router.patch(
    "/{schema_id}/groups/{group_id}",
    response_model=FormGroupRead,
    dependencies=[Depends(require_recht("formulare", "bearbeiten"))],
)
async def update_group(
    schema_id: UUID, group_id: UUID, body: FormGroupUpdate, session: AsyncSession = Depends(get_db)
) -> FormGroup:
    group = await session.get(FormGroup, group_id)
    if group is None or group.schema_id != schema_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gruppe nicht gefunden")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(group, field, value)
    await session.flush()
    await session.refresh(group)
    return group


@router.delete(
    "/{schema_id}/groups/{group_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_recht("formulare", "loeschen"))],
)
async def delete_group(schema_id: UUID, group_id: UUID, session: AsyncSession = Depends(get_db)) -> None:
    group = await session.get(FormGroup, group_id)
    if group is None or group.schema_id != schema_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gruppe nicht gefunden")
    await session.delete(group)
    await session.flush()


# --- form_fields -----------------------------------------------------------


@router.post(
    "/{schema_id}/fields",
    response_model=FormFieldRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_recht("formulare", "bearbeiten"))],
)
async def create_field(
    schema_id: UUID,
    body: FormFieldCreate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> FormField:
    await _get_schema_or_404(session, schema_id)
    if body.key in await _existing_keys(session, schema_id):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Key '{body.key}' ist bereits vergeben")
    if body.group_key is not None:
        groups = await form_modul_service.groups_fuer(session, schema_id)
        if body.group_key not in {g.key for g in groups}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=f"Gruppe '{body.group_key}' existiert nicht"
            )
    field = FormField(mandant_id=auth.mandant_id, schema_id=schema_id, **body.model_dump())
    session.add(field)
    await session.flush()
    await session.refresh(field)
    return field


@router.patch(
    "/{schema_id}/fields/{field_id}",
    response_model=FormFieldRead,
    dependencies=[Depends(require_recht("formulare", "bearbeiten"))],
)
async def update_field(
    schema_id: UUID, field_id: UUID, body: FormFieldUpdate, session: AsyncSession = Depends(get_db)
) -> FormField:
    field = await session.get(FormField, field_id)
    if field is None or field.schema_id != schema_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Feld nicht gefunden")
    daten = body.model_dump(exclude_unset=True)
    if "group_key" in daten and daten["group_key"] is not None:
        groups = await form_modul_service.groups_fuer(session, schema_id)
        if daten["group_key"] not in {g.key for g in groups}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=f"Gruppe '{daten['group_key']}' existiert nicht"
            )
    for f, value in daten.items():
        setattr(field, f, value)
    await session.flush()
    await session.refresh(field)
    return field


@router.delete(
    "/{schema_id}/fields/{field_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_recht("formulare", "loeschen"))],
)
async def delete_field(schema_id: UUID, field_id: UUID, session: AsyncSession = Depends(get_db)) -> None:
    field = await session.get(FormField, field_id)
    if field is None or field.schema_id != schema_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Feld nicht gefunden")
    await session.delete(field)
    await session.flush()


# --- form_views + layouts + presentation elements ---------------------------


async def _get_view_or_404(session: AsyncSession, schema_id: UUID, view_id: UUID) -> FormView:
    view = await session.get(FormView, view_id)
    if view is None or view.schema_id != schema_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="View nicht gefunden")
    return view


@router.get("/{schema_id}/views", response_model=list[FormViewRead])
async def list_views(schema_id: UUID, session: AsyncSession = Depends(get_db)) -> list[FormView]:
    await _get_schema_or_404(session, schema_id)
    result = await session.execute(select(FormView).where(FormView.schema_id == schema_id).order_by(FormView.type))
    return list(result.scalars().all())


@router.post(
    "/{schema_id}/views",
    response_model=FormViewRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_recht("formulare", "bearbeiten"))],
)
async def create_view(
    schema_id: UUID,
    body: FormViewCreate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> FormView:
    await _get_schema_or_404(session, schema_id)
    view = FormView(mandant_id=auth.mandant_id, schema_id=schema_id, erstellt_von=auth.user_id, **body.model_dump())
    session.add(view)
    await session.flush()
    await session.refresh(view)
    return view


@router.get("/{schema_id}/views/{view_id}", response_model=FormViewResolvedRead)
async def get_view(
    schema_id: UUID,
    view_id: UUID,
    submission_id: UUID | None = Query(default=None),
    session: AsyncSession = Depends(get_db),
) -> FormViewResolvedRead:
    view = await _get_view_or_404(session, schema_id, view_id)
    layouts = await form_modul_service.layouts_fuer(session, view_id)
    elements = await form_modul_service.elements_fuer(session, view_id)
    states: dict[str, FormFieldStateRead] = {}
    if submission_id is not None:
        submission = await session.get(FormSubmission, submission_id)
        if submission is not None and submission.schema_id == schema_id:
            result = await form_modul_service.compute_states(
                session, schema_id=schema_id, values=submission.values, view_id=view_id
            )
            states = {path: FormFieldStateRead(**st.as_dict()) for path, st in result.states.items()}
    return FormViewResolvedRead(
        view=FormViewRead.model_validate(view),
        layouts=[FormViewFieldLayoutRead.model_validate(layout) for layout in layouts],
        elements=[FormPresentationElementRead.model_validate(e) for e in elements],
        states=states,
    )


@router.patch(
    "/{schema_id}/views/{view_id}",
    response_model=FormViewRead,
    dependencies=[Depends(require_recht("formulare", "bearbeiten"))],
)
async def update_view(
    schema_id: UUID, view_id: UUID, body: FormViewUpdate, session: AsyncSession = Depends(get_db)
) -> FormView:
    view = await _get_view_or_404(session, schema_id, view_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(view, field, value)
    await session.flush()
    await session.refresh(view)
    return view


@router.delete(
    "/{schema_id}/views/{view_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_recht("formulare", "loeschen"))],
)
async def delete_view(schema_id: UUID, view_id: UUID, session: AsyncSession = Depends(get_db)) -> None:
    view = await _get_view_or_404(session, schema_id, view_id)
    await session.delete(view)
    await session.flush()


@router.put(
    "/{schema_id}/views/{view_id}/layouts",
    response_model=list[FormViewFieldLayoutRead],
    dependencies=[Depends(require_recht("formulare", "bearbeiten"))],
)
async def replace_layouts(
    schema_id: UUID,
    view_id: UUID,
    body: list[FormViewFieldLayoutIn],
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[FormViewFieldLayout]:
    """Ersetzt alle Layout-Eintraege einer View in einem Rutsch (Bulk-Save
    aus dem Editor) -- analog zu PUT /api/formulare/{id}/felder/positionen
    im alten Modell."""
    await _get_view_or_404(session, schema_id, view_id)
    valid_keys = {f.key for f in await form_modul_service.fields_fuer(session, schema_id)}
    unknown = {layout.field_key for layout in body} - valid_keys
    if unknown:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unbekannte Feld-Keys: {', '.join(sorted(unknown))}"
        )
    existing = await form_modul_service.layouts_fuer(session, view_id)
    for layout in existing:
        await session.delete(layout)
    await session.flush()
    neue = [
        FormViewFieldLayout(mandant_id=auth.mandant_id, view_id=view_id, **layout.model_dump())
        for layout in body
    ]
    session.add_all(neue)
    await session.flush()
    for layout in neue:
        await session.refresh(layout)
    return neue


@router.post(
    "/{schema_id}/views/{view_id}/elements",
    response_model=FormPresentationElementRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_recht("formulare", "bearbeiten"))],
)
async def create_element(
    schema_id: UUID,
    view_id: UUID,
    body: FormPresentationElementCreate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> FormPresentationElement:
    await _get_view_or_404(session, schema_id, view_id)
    element = FormPresentationElement(mandant_id=auth.mandant_id, view_id=view_id, **body.model_dump())
    session.add(element)
    await session.flush()
    await session.refresh(element)
    return element


@router.patch(
    "/{schema_id}/views/{view_id}/elements/{element_id}",
    response_model=FormPresentationElementRead,
    dependencies=[Depends(require_recht("formulare", "bearbeiten"))],
)
async def update_element(
    schema_id: UUID,
    view_id: UUID,
    element_id: UUID,
    body: FormPresentationElementUpdate,
    session: AsyncSession = Depends(get_db),
) -> FormPresentationElement:
    element = await session.get(FormPresentationElement, element_id)
    if element is None or element.view_id != view_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Element nicht gefunden")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(element, field, value)
    await session.flush()
    await session.refresh(element)
    return element


@router.delete(
    "/{schema_id}/views/{view_id}/elements/{element_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_recht("formulare", "loeschen"))],
)
async def delete_element(
    schema_id: UUID, view_id: UUID, element_id: UUID, session: AsyncSession = Depends(get_db)
) -> None:
    element = await session.get(FormPresentationElement, element_id)
    if element is None or element.view_id != view_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Element nicht gefunden")
    await session.delete(element)
    await session.flush()


# --- form_logic_rules --------------------------------------------------------


@router.get("/{schema_id}/rules", response_model=list[FormLogicRuleRead])
async def list_rules(schema_id: UUID, session: AsyncSession = Depends(get_db)) -> list[FormLogicRule]:
    await _get_schema_or_404(session, schema_id)
    return await form_modul_service.rules_fuer(session, schema_id)


async def _validate_rule_target(session: AsyncSession, schema_id: UUID, target_key: str) -> None:
    if target_key not in await _existing_keys(session, schema_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"target_key '{target_key}' existiert nicht in diesem Schema"
        )


@router.post(
    "/{schema_id}/rules",
    response_model=FormLogicRuleRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_recht("formulare", "bearbeiten"))],
)
async def create_rule(
    schema_id: UUID,
    body: FormLogicRuleCreate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> FormLogicRule:
    await _get_schema_or_404(session, schema_id)
    await _validate_rule_target(session, schema_id, body.target_key)
    if body.effect == "set_value" and body.value is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="set_value braucht 'value'")

    bestehende = form_modul_service._rule_dicts(await form_modul_service.rules_fuer(session, schema_id))
    try:
        detect_cycles(bestehende + [body.model_dump(mode="json")])
    except FormLogicCycleError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    rule = FormLogicRule(mandant_id=auth.mandant_id, schema_id=schema_id, **body.model_dump())
    session.add(rule)
    await session.flush()
    await session.refresh(rule)
    return rule


@router.patch(
    "/{schema_id}/rules/{rule_id}",
    response_model=FormLogicRuleRead,
    dependencies=[Depends(require_recht("formulare", "bearbeiten"))],
)
async def update_rule(
    schema_id: UUID, rule_id: UUID, body: FormLogicRuleUpdate, session: AsyncSession = Depends(get_db)
) -> FormLogicRule:
    rule = await session.get(FormLogicRule, rule_id)
    if rule is None or rule.schema_id != schema_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Regel nicht gefunden")
    daten = body.model_dump(exclude_unset=True)
    if "target_key" in daten:
        await _validate_rule_target(session, schema_id, daten["target_key"])

    alle_regeln = await form_modul_service.rules_fuer(session, schema_id)
    andere_regeln = form_modul_service._rule_dicts([r for r in alle_regeln if r.id != rule_id])
    vorschau = {
        "target_key": daten.get("target_key", rule.target_key),
        "effect": daten.get("effect", rule.effect),
        "condition": daten.get("condition", rule.condition),
        "value": daten.get("value", rule.value),
        "view_id": str(daten.get("view_id", rule.view_id)) if daten.get("view_id", rule.view_id) else None,
        "reihenfolge": daten.get("reihenfolge", rule.reihenfolge),
    }
    try:
        detect_cycles(andere_regeln + [vorschau])
    except FormLogicCycleError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    for field, value in daten.items():
        setattr(rule, field, value)
    await session.flush()
    await session.refresh(rule)
    return rule


@router.delete(
    "/{schema_id}/rules/{rule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_recht("formulare", "loeschen"))],
)
async def delete_rule(schema_id: UUID, rule_id: UUID, session: AsyncSession = Depends(get_db)) -> None:
    rule = await session.get(FormLogicRule, rule_id)
    if rule is None or rule.schema_id != schema_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Regel nicht gefunden")
    await session.delete(rule)
    await session.flush()


# --- form_auftragstyp_zuordnungen -------------------------------------------


@router.post(
    "/{schema_id}/zuordnungen",
    response_model=FormAuftragstypZuordnungRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_recht("formulare", "bearbeiten"))],
)
async def create_zuordnung(
    schema_id: UUID,
    body: FormAuftragstypZuordnungCreate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> FormAuftragstypZuordnung:
    await _get_schema_or_404(session, schema_id)
    zuordnung = FormAuftragstypZuordnung(mandant_id=auth.mandant_id, schema_id=schema_id, **body.model_dump())
    session.add(zuordnung)
    await session.flush()
    await session.refresh(zuordnung)
    return zuordnung


@router.patch(
    "/{schema_id}/zuordnungen/{zuordnung_id}",
    response_model=FormAuftragstypZuordnungRead,
    dependencies=[Depends(require_recht("formulare", "bearbeiten"))],
)
async def update_zuordnung(
    schema_id: UUID,
    zuordnung_id: UUID,
    body: FormAuftragstypZuordnungUpdate,
    session: AsyncSession = Depends(get_db),
) -> FormAuftragstypZuordnung:
    zuordnung = await session.get(FormAuftragstypZuordnung, zuordnung_id)
    if zuordnung is None or zuordnung.schema_id != schema_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Zuordnung nicht gefunden")
    zuordnung.pflicht_vor_abschluss = body.pflicht_vor_abschluss
    await session.flush()
    await session.refresh(zuordnung)
    return zuordnung


@router.delete(
    "/{schema_id}/zuordnungen/{zuordnung_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_recht("formulare", "bearbeiten"))],
)
async def delete_zuordnung(
    schema_id: UUID, zuordnung_id: UUID, session: AsyncSession = Depends(get_db)
) -> None:
    zuordnung = await session.get(FormAuftragstypZuordnung, zuordnung_id)
    if zuordnung is None or zuordnung.schema_id != schema_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Zuordnung nicht gefunden")
    await session.delete(zuordnung)
    await session.flush()


# --- form_submissions --------------------------------------------------------


async def _require_own_vorgang(session: AsyncSession, auth: AuthContext, vorgang_id: UUID) -> Vorgang:
    vorgang = await session.get(Vorgang, vorgang_id)
    if vorgang is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vorgang nicht gefunden")
    beschraenkt = await ist_auf_zugewiesene_kunden_beschraenkt(
        session, role=auth.role, account_typ_id=auth.account_typ_id
    )
    if beschraenkt and vorgang.kunde_id not in await assigned_kunde_ids(session, auth.user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vorgang nicht gefunden")
    return vorgang


async def _get_own_submission(session: AsyncSession, auth: AuthContext, submission_id: UUID) -> FormSubmission:
    submission = await session.get(FormSubmission, submission_id)
    if submission is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ausfüllung nicht gefunden")
    await _require_own_vorgang(session, auth, submission.vorgang_id)
    return submission


@submissions_router.get("/verfuegbar", response_model=list[FormSchemaVerfuegbar])
async def list_verfuegbare_schemas(
    vorgang_id: UUID = Query(...),
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[FormSchemaVerfuegbar]:
    vorgang = await _require_own_vorgang(session, auth, vorgang_id)
    schemas = await form_modul_service.verfuegbare_schemas_fuer(session, vorgang)
    return [
        FormSchemaVerfuegbar(id=s.id, name=s.name, beschreibung=s.beschreibung, pflicht_vor_abschluss=pflicht)
        for s, pflicht in schemas
    ]


@submissions_router.get("", response_model=list[FormSubmissionRead])
async def list_submissions(
    vorgang_id: UUID = Query(...),
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[FormSubmissionRead]:
    await _require_own_vorgang(session, auth, vorgang_id)
    result = await session.execute(
        select(FormSubmission).where(FormSubmission.vorgang_id == vorgang_id).order_by(FormSubmission.created_at.desc())
    )
    return [await form_modul_service.to_submission_read(session, s) for s in result.scalars().all()]


@submissions_router.post("", response_model=FormSubmissionRead, status_code=status.HTTP_201_CREATED)
async def start_submission(
    body: FormSubmissionStart,
    vorgang_id: UUID = Query(...),
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> FormSubmissionRead:
    vorgang = await _require_own_vorgang(session, auth, vorgang_id)
    if vorgang.status in VORGANG_STATUS_GESCHLOSSEN:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Vorgang ist abgeschlossen und kann nicht mehr geändert werden",
        )
    schema = await session.get(FormSchema, body.schema_id)
    if schema is None or schema.status != "published":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Formular-Schema nicht gefunden")

    fields = await form_modul_service.fields_fuer(session, schema.id)
    kunde = await session.get(Kunde, vorgang.kunde_id) if vorgang.kunde_id else None
    anlage = await session.get(Anlage, vorgang.anlage_id) if vorgang.anlage_id else None
    standort = await session.get(Standort, vorgang.standort_id) if vorgang.standort_id else None
    zugewiesener = (
        await session.get(User, vorgang.zugewiesener_user_id) if vorgang.zugewiesener_user_id else None
    )
    submission = FormSubmission(
        mandant_id=auth.mandant_id,
        vorgang_id=vorgang_id,
        schema_id=schema.id,
        schema_version=schema.version,
        values=form_modul_service.auto_fill_values(
            fields, vorgang, kunde, anlage, standort, zugewiesener.name if zugewiesener else None
        ),
        ausgefuellt_von=auth.user_id,
    )
    session.add(submission)
    await session.flush()
    await session.refresh(submission)
    return await form_modul_service.to_submission_read(session, submission)


@submissions_router.get("/{submission_id}", response_model=FormSubmissionRead)
async def get_submission(
    submission_id: UUID, auth: AuthContext = Depends(get_current_user), session: AsyncSession = Depends(get_db)
) -> FormSubmissionRead:
    submission = await _get_own_submission(session, auth, submission_id)
    return await form_modul_service.to_submission_read(session, submission)


@submissions_router.get("/{submission_id}/pdf")
async def submission_pdf(
    submission_id: UUID,
    view_id: UUID | None = Query(default=None),
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Response:
    """Rendert die Ausfuellung live ueber eine print-View -- ohne view_id
    wird die erste print-View des Schemas verwendet. Wie beim alten Modul
    (vorgang_formular_pdf) ist eine noch offene Ausfuellung nur eine
    Vorschau mit Hinweisbanner."""
    submission = await _get_own_submission(session, auth, submission_id)
    schema = await session.get(FormSchema, submission.schema_id)
    if schema is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Formular-Schema nicht gefunden")

    if view_id is not None:
        view = await _get_view_or_404(session, submission.schema_id, view_id)
    else:
        result = await session.execute(
            select(FormView).where(FormView.schema_id == submission.schema_id, FormView.type == "print").limit(1)
        )
        view = result.scalars().first()
        if view is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Keine Druckansicht fuer dieses Schema angelegt")

    vorgang = await session.get(Vorgang, submission.vorgang_id)
    mandant = await session.get(Mandant, auth.mandant_id)
    fields = await form_modul_service.fields_fuer(session, submission.schema_id)
    groups = await form_modul_service.groups_fuer(session, submission.schema_id)
    layouts = await form_modul_service.layouts_fuer(session, view.id)
    elements = await form_modul_service.elements_fuer(session, view.id)

    bilder: dict[str, bytes] = {}
    for field in fields:
        if field.feld_typ not in ("foto", "unterschrift"):
            continue
        wert = submission.values.get(field.key)
        if isinstance(wert, dict) and wert.get("key"):
            bilder[field.key] = await storage_service.download_bytes(wert["key"])

    ist_vorschau = submission.status != "abgeschlossen"
    pdf_bytes = generate_form_submission_pdf(
        mandant, vorgang, submission, schema.name, fields, groups, layouts, elements, bilder, ist_vorschau=ist_vorschau
    )
    praefix = "Vorschau-" if ist_vorschau else ""
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{praefix}{schema.name}-{vorgang.vorgangsnummer}.pdf"'},
    )


@submissions_router.patch("/{submission_id}", response_model=FormSubmissionRead)
async def update_submission_values(
    submission_id: UUID,
    body: FormSubmissionValuesUpdate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> FormSubmissionRead:
    """Autosave: ersetzt die uebergebenen Top-Level-Keys in `values`
    (Root-Feld-Key oder Gruppen-Key mit der kompletten neuen Zeilen-Liste),
    unveraenderte Keys bleiben erhalten. Schreibt fuer jeden tatsaechlich
    geaenderten Key einen form_submission_audit-Eintrag."""
    submission = await _get_own_submission(session, auth, submission_id)
    if submission.status != "offen":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Ausfüllung ist bereits abgeschlossen")

    alte_werte = dict(submission.values)
    neue_werte = dict(alte_werte)
    for key, wert in body.values.items():
        if alte_werte.get(key) == wert:
            continue
        session.add(
            FormSubmissionAudit(
                mandant_id=auth.mandant_id,
                submission_id=submission.id,
                field_key=key,
                alter_wert=alte_werte.get(key),
                neuer_wert=wert,
                geaendert_von=auth.user_id,
            )
        )
        neue_werte[key] = wert
    submission.values = neue_werte
    await session.flush()
    await session.refresh(submission)
    return await form_modul_service.to_submission_read(session, submission)


@submissions_router.post("/{submission_id}/dateien")
async def datei_hochladen(
    submission_id: UUID,
    field_key: str,
    file: UploadFile,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    """Laedt eine Datei fuer ein Foto-/Unterschrift-Feld hoch, Pendant zu
    POST /api/vorgang-formulare/{id}/dateien im alten Modell. Gibt den
    Storage-Key zurueck, den das Frontend per PATCH als Wert fuer
    field_key ablegt (siehe update_submission_values)."""
    submission = await _get_own_submission(session, auth, submission_id)
    if submission.status != "offen":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Ausfüllung ist bereits abgeschlossen")
    fields = await form_modul_service.fields_fuer(session, submission.schema_id)
    field = next((f for f in fields if f.key == field_key), None)
    if field is None or field.feld_typ not in FELDTYPEN_MIT_DATEI:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ungültiges Feld")
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Nur Bilddateien werden unterstützt")

    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Datei zu groß (max. 15 MB)")

    key = storage_service.new_object_key(submission.vorgang_id, file.filename or "datei.jpg")
    await storage_service.upload_bytes(key, data, file.content_type)
    return {
        "field_key": field_key,
        "key": key,
        "content_type": file.content_type,
        "size": len(data),
        "url": storage_service.presigned_get_url(key),
    }


def _feld_label(field: FormField) -> str:
    return (field.label or {}).get("de") or field.key


def _missing_pflichtfelder(fields: list[FormField], states: dict, values: dict) -> list[str]:
    missing: list[str] = []
    for f in fields:
        if f.group_key is None:
            state = states.get(f.key)
            visible = state.visible if state else True
            required = f.pflichtfeld or bool(state and state.required)
            if visible and required and not values.get(f.key):
                missing.append(_feld_label(f))
            continue

        group_state = states.get(f.group_key)
        if group_state is not None and not group_state.visible:
            continue
        rows = values.get(f.group_key) or []
        for idx, row in enumerate(rows):
            path = f"{f.group_key}[{idx}].{f.key}"
            state = states.get(path)
            visible = state.visible if state else True
            required = f.pflichtfeld or bool(state and state.required)
            if visible and required and not (isinstance(row, dict) and row.get(f.key)):
                missing.append(f"{_feld_label(f)} (Zeile {idx + 1})")
    return missing


@submissions_router.post("/{submission_id}/abschliessen", response_model=FormSubmissionRead)
async def abschliessen_submission(
    submission_id: UUID, auth: AuthContext = Depends(get_current_user), session: AsyncSession = Depends(get_db)
) -> FormSubmissionRead:
    submission = await _get_own_submission(session, auth, submission_id)
    if submission.status != "offen":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Ausfüllung ist bereits abgeschlossen")

    fields = await form_modul_service.fields_fuer(session, submission.schema_id)
    capture_view = await form_modul_service.capture_view_fuer(session, submission.schema_id)
    result = await form_modul_service.compute_states(
        session,
        schema_id=submission.schema_id,
        values=submission.values,
        view_id=capture_view.id if capture_view else None,
    )
    fehlend = _missing_pflichtfelder(fields, result.states, submission.values)
    if fehlend:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"Pflichtfelder fehlen: {', '.join(fehlend)}"
        )

    schema = await session.get(FormSchema, submission.schema_id)
    submission.status = "abgeschlossen"
    submission.abgeschlossen_am = datetime.now(timezone.utc)

    # Feed-Eintrag (Pendant zu abschliessen_vorgang_formular im alten
    # Modul) -- derselbe event_type "formular" (Check-Constraint erlaubt
    # ihn weiterhin), ref_entity_type "form_submission" statt
    # "vorgang_formular" markiert die Herkunft aus dem neuen Modul.
    session.add(
        VorgangEvent(
            mandant_id=auth.mandant_id,
            vorgang_id=submission.vorgang_id,
            event_type="formular",
            author_user_id=auth.user_id,
            body=schema.name if schema else None,
            payload={"form_submission_id": str(submission.id)},
            ref_entity_type="form_submission",
            ref_entity_id=submission.id,
            kundensichtbar=submission.kundensichtbar,
        )
    )
    await session.flush()
    await session.refresh(submission)

    await event_bus.publish(
        auth.mandant_id, "vorgang_event", {"vorgang_id": str(submission.vorgang_id), "event_type": "formular"}
    )
    return await form_modul_service.to_submission_read(session, submission)


@submissions_router.delete("/{submission_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_submission(
    submission_id: UUID, auth: AuthContext = Depends(get_current_user), session: AsyncSession = Depends(get_db)
) -> None:
    submission = await _get_own_submission(session, auth, submission_id)
    if submission.status != "offen":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Nur eine noch nicht abgeschlossene Ausfüllung kann verworfen werden"
        )
    await session.delete(submission)
    await session.flush()
