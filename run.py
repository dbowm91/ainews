import os

from asgiref.wsgi import WsgiToAsgi

from app import create_app

flask_app = create_app()
app = WsgiToAsgi(flask_app)

if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    port = int(os.environ.get("PORT", "5000"))
    flask_app.run(debug=debug, port=port)
