from flask import Blueprint, render_template

from .content import IMPROVEMENT_LOOP, JOURNEY_STAGES, PURPOSES, WORK_AREAS


blueprint = Blueprint("dash", __name__, url_prefix="/dash")


@blueprint.get("")
@blueprint.get("/")
def home():
    return render_template(
        "dash/home.html",
        improvement_loop=IMPROVEMENT_LOOP,
        journey_stages=JOURNEY_STAGES,
        purposes=PURPOSES,
        work_areas=WORK_AREAS,
    )
