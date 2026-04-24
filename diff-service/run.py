"""Entry point — run the Flask diff microservice."""

from app import create_app
from config import FLASK_PORT, FLASK_DEBUG

app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=FLASK_PORT, debug=FLASK_DEBUG)
