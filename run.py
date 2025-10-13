import os
from app.app import create_app

app = create_app()

if __name__ == '__main__':
    # Listen on all interfaces and on the port provided by the environment.
    # Default to 8080 if PORT is not set (for local testing).
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port, debug=app.config.get('DEBUG', False))
