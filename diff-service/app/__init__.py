"""Flask application factory."""

from flask import Flask
from flask_cors import CORS
from config import FLASK_DEBUG, FLASK_PORT, CORS_ORIGINS


def create_app():
    """Create and configure Flask app."""
    app = Flask(__name__)
    app.config['DEBUG'] = FLASK_DEBUG
    
    # Enable CORS
    CORS(app, origins=CORS_ORIGINS)
    
    # Register routes
    from .routes import diff_bp
    app.register_blueprint(diff_bp)
    
    @app.route("/health", methods=["GET"])
    def health():
        return {"status": "ok"}, 200
    
    return app
