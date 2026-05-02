from .admin_routes import admin_bp
from .auth_routes import auth_bp
from .poll_routes import poll_bp
from .restaurant_routes import restaurant_bp

_MOBILE_UA = frozenset(
    [
        "mobile",
        "android",
        "iphone",
        "ipad",
        "ipod",
        "blackberry",
        "windows phone",
        "opera mini",
        "webos",
    ]
)


def _is_mobile(user_agent: str) -> bool:
    ua = user_agent.lower()
    return any(kw in ua for kw in _MOBILE_UA)


def register_blueprints(app) -> None:
    from database import close_db
    from flask import request

    app.teardown_appcontext(close_db)

    @app.context_processor
    def _inject_globals():
        from auth import current_user

        return {
            "current_user": current_user(),
            "is_mobile": _is_mobile(request.headers.get("User-Agent", "")),
        }

    app.register_blueprint(auth_bp)
    app.register_blueprint(poll_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(restaurant_bp)

    _register_error_handlers(app)
    _register_security_headers(app)


def _register_error_handlers(app) -> None:
    from flask import render_template

    @app.errorhandler(400)
    def bad_request(_e):
        return render_template("error.html", code=400, message="Bad request"), 400

    @app.errorhandler(403)
    def forbidden(_e):
        return render_template("error.html", code=403, message="Forbidden"), 403

    @app.errorhandler(404)
    def not_found(_e):
        return render_template("error.html", code=404, message="Not found"), 404

    @app.errorhandler(413)
    def too_large(_e):
        return render_template("error.html", code=413, message="Request too large"), 413


def _register_security_headers(app) -> None:
    @app.after_request
    def add_security_headers(resp):
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Referrer-Policy"] = "same-origin"
        resp.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "script-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "form-action 'self'; "
            "frame-ancestors 'none'; "
            "base-uri 'self'"
        )
        resp.headers["Vary"] = "User-Agent"
        return resp
