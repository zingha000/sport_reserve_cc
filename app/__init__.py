
from flask import Flask, render_template
from app.config import Config


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Register Blueprint
    from app.routes.auth import auth_bp
    from app.routes.fields import fields_bp
    from app.routes.reservations import reservations_bp
    from app.routes.admin import admin_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(fields_bp)
    app.register_blueprint(reservations_bp)
    app.register_blueprint(admin_bp)

    # Landing Page
    @app.route("/")
    def home():
        return render_template("index.html")

    return app
