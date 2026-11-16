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


@blueprint.get("/app")
@blueprint.get("/app/")
def personal_app():
    """Render the synthetic, read-only personal improvement prototype."""
    return render_template("dash/app.html")
