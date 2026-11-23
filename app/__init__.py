from flask import Flask, render_template
from app.config import Config
from app.errors import register_error_handlers


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Register Blueprint
    from app.routes.auth import auth_bp
    from app.routes.fields import fields_bp
    from app.routes.reservations import reservations_bp
    from app.routes.admin import admin_bp
    from app.routes.admin_fields import admin_fields_bp
    from app.routes.payments import payments_bp, admin_payments_bp
    from app.routes.notifications import notifications_bp
    from app.routes.health import health_bp
    from app.routes.field_photos import field_photos_bp, admin_field_photos_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(fields_bp)
    app.register_blueprint(reservations_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(admin_fields_bp)
    app.register_blueprint(payments_bp)
    app.register_blueprint(admin_payments_bp)
    app.register_blueprint(notifications_bp)
    app.register_blueprint(health_bp)
    app.register_blueprint(field_photos_bp)
    app.register_blueprint(admin_field_photos_bp)

    register_error_handlers(app)

    # Landing Page
        # Landing Page
    @app.route("/")
    def home():
        from app.home_data import get_home_data

        fields, schedule = get_home_data()
        return render_template(
            "index.html", fields=fields, schedule=schedule
        )

    @app.route("/tentang")
    def about():
        return render_template("about.html")

    return app
