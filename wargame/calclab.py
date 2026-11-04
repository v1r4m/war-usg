"""
"Just a Patch Release" - a supply-chain challenge.

USG Calc is an ordinary web calculator. It does nothing clever: it takes an expression
and evaluates it with a small, popular PyPI dependency, ``litexpr`` (github.com/v1r4m/litexpr).
The team never touched the dependency; they just ran ``pip install -r requirements.txt``.

The catch is that the ``litexpr`` **artifact published to PyPI** does not match its source
repository, even at the same version (1.4.1): the published build smuggles a hidden function
into ``evaluate()``. So the calculator server, which only ever calls ``litexpr.evaluate()``,
leaks a secret for one magic input. This mirrors real "the tarball isn't the git tag" attacks
(xz-utils). The flag lives inside the installed package, not in this repo.

Nothing here is dangerous: the backdoor in litexpr only returns a fixed constant string
(no environment, network, or code execution). See challenges notes / the litexpr release kit.
"""
from flask import Blueprint, Response, jsonify, render_template, request

from .models import Challenge

LAB_KEY = "supplychain"
bp = Blueprint("calclab", __name__, url_prefix="/labs/calc")

# The calculator pins this exact version. It resolves to the backdoored PyPI artifact.
LITEXPR_PIN = "1.4.1"

# The flag is baked into the published litexpr artifact, so it is fixed (not per-install).
# seed.py pins this onto the challenge so flag submission matches what the package reveals.
FLAG = "USG{supply_chain_1nj3ct3d_in_th3_wh33l}"

try:  # the server installs the (backdoored) dependency; see requirements.txt
    import litexpr
    _LITEXPR_ERR = None
except Exception as exc:  # pragma: no cover - only when the dep isn't installed
    litexpr = None
    _LITEXPR_ERR = str(exc)


def _available():
    chal = Challenge.query.filter_by(lab_key=LAB_KEY).first()
    return chal is not None and chal.visible


@bp.route("/")
def index():
    if not _available():
        from flask import abort
        abort(404)
    return render_template("labs/calc.html", version=LITEXPR_PIN)


# A trimmed, believable copy of the calculator server, shown by the "see source" link.
# It deliberately reveals the one thing that matters: the app just calls litexpr.evaluate().
SERVER_SOURCE = '''\
# server.py — USG Calc

app = Flask(__name__)


@app.get("/")
def index():
    return render_template("calc.html", version=litexpr.__version__)


@app.post("/api/eval")
def api_eval():
    expr = (request.get_json(silent=True) or {}).get("expr", "")
    if not isinstance(expr, str) or len(expr) > 300:
        return jsonify(error="bad expression"), 400
    try:
        value = litexpr.evaluate(expr)
    except litexpr.ExprError as e:
        return jsonify(error=str(e)), 400
    result = litexpr.format(value) if isinstance(value, (int, float)) else str(value)
    return jsonify(expr=expr, result=result)


if __name__ == "__main__":
    app.run(port=3000)
'''


@bp.route("/source")
def source():
    if not _available():
        from flask import abort
        abort(404)
    return Response(SERVER_SOURCE, mimetype="text/plain; charset=utf-8")


@bp.route("/requirements.txt")
def requirements_txt():
    if not _available():
        from flask import abort
        abort(404)
    body = (
        "# USG Calc - runtime dependencies\n"
        "Flask==3.1.0\n"
        "gunicorn==23.0.0\n"
        f"litexpr=={LITEXPR_PIN}\n"
    )
    return Response(body, mimetype="text/plain")


@bp.route("/api/eval", methods=["POST"])
def api_eval():
    if not _available():
        return _api({"error": "not found"}, 404)
    data = request.get_json(silent=True) or {}
    expr = data.get("expr", "")
    if not isinstance(expr, str):
        return _api({"error": "expr must be a string"}, 400)
    if len(expr) > 300:
        return _api({"error": "Expression too long (max 300 characters)"}, 400)
    if litexpr is None:
        return _api({"error": f"calculator backend unavailable ({_LITEXPR_ERR})"}, 503)

    try:
        value = litexpr.evaluate(expr)
    except litexpr.ExprError as e:
        return _api({"error": str(e)}, 400)
    except RecursionError:
        return _api({"error": "Expression nested too deeply"}, 400)
    except Exception as e:  # keep the calculator robust against odd inputs
        return _api({"error": f"could not evaluate: {e}"}, 400)

    # Normal results are numbers; litexpr.format() renders them. The server trusts whatever
    # the dependency returns, so a non-numeric return value is just stringified and shown.
    if isinstance(value, (int, float)):
        result = litexpr.format(value)
    else:
        result = str(value)
    return _api({"expr": expr, "result": result})


def _api(body, status=200):
    resp = jsonify({**body, "engine": f"litexpr/{LITEXPR_PIN}"})
    resp.status_code = status
    resp.headers["X-Powered-By"] = f"litexpr/{LITEXPR_PIN}"
    return resp
