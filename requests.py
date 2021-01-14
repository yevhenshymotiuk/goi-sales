import json
from datetime import datetime

from flask import Blueprint, request
from flask_login import login_required, current_user
from pydantic import ValidationError

from core.models.agency import Agency, Reason
from core.models.employer import Request
from core.models.search import Search
from core.schemas.request import (
    PydanticRequestCreateRequest,
    PydanticRequestCreateResponse,
    PydanticRequestUpdateRequest,
    PydanticRequestUpdateResponse,
)
from core.services.db import db
from core.blueprints.auth import UserRoles, roles_required

bp = Blueprint("requests", __name__)


@bp.route("/", methods=["POST"])
@login_required
@roles_required([UserRoles.EMPLOYER])
def create():
    data = request.get_json()

    # validate request data
    try:
        data = PydanticRequestCreateRequest(**data)
    except ValidationError as e:
        return {"message": json.loads(e.json())}, 400

    search = Search.query.get(data.search_id)
    if not search:
        return {"message": f"Search with id {data.search_id} does not exist"}, 400

    employer_id = current_user.id
    timestamp = datetime.utcnow().timestamp()
    action = {"action": data.status, "timestamp": timestamp}
    if data.message:
        action["message"] = data.message

    req = Request(
        search_id=data.search_id,
        employer_id=employer_id,
        candidate_id=data.candidate_id,
        status=data.status,
        actions=[action],
    )

    search.updated_at = timestamp

    session = db.session

    session.add(req)
    session.commit()

    last_action = req.actions[-1]

    return (
        PydanticRequestCreateResponse(
            id=req.id,
            employer_id=req.employer_id,
            candidate_id=req.candidate_id,
            search_id=req.search_id,
            status=req.status,
            timestamp=last_action.get("timestamp"),
            message=last_action.get("message"),
        ).dict(exclude_none=True),
        200,
    )


@bp.route("/<id>", methods=["PUT"])
@login_required
@roles_required([UserRoles.AGENCY, UserRoles.EMPLOYER])
def update(id):
    data = request.get_json()

    # validate request data
    try:
        data = PydanticRequestUpdateRequest(**data)
    except ValidationError as e:
        return {"message": json.loads(e.json())}, 400

    req = Request.query.get(id)

    if not req:
        return {"message": "Request with id {id} does not exist"}, 400

    if data.reason_id:
        reason = Reason.query.get(data.reason_id)

        if not reason:
            return {"message": "Reason with id {id} does not exist"}, 400

    agency = Agency.query.get(current_user.id)

    if (agency and req.candidate not in agency.candidates) or (not agency and current_user.id != req.employer_id):
        return (
            {"message": "Permission Denied. You do not have sufficient privileges for this resource."},
            403,
        )

    timestamp = datetime.utcnow().timestamp()

    action = {"action": data.status, "timestamp": timestamp}
    if data.message:
        action["message"] = data.message
    if data.reason_id:
        action["reason_id"] = data.reason_id

    search = Search.query.get(req.search_id)
    search.updated_at = timestamp

    req.actions = req.actions + [action]
    req.status = data.status

    db.session.commit()

    return (
        PydanticRequestUpdateResponse(
            timestamp=timestamp, message=data.message, reason=reason if data.reason_id else None
        ).dict(exclude_unset=True, exclude_none=True),
        200,
    )
