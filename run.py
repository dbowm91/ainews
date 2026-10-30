import os

from app import create_app
import services.mcp_public as public_mcp
from services.mcp_public import PublicASGI, build_mcp_asgi_app

flask_app = create_app()
public_mcp.flask_app = flask_app
try:
    # The persisted admin policy may enable MCP after deployment. Construct
    # the optional transport when its extra is installed, even if disabled.
    mcp_app = build_mcp_asgi_app()
except RuntimeError:
    mcp_app = None
app = PublicASGI(flask_app, flask_app, mcp_app)

if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    port = int(os.environ.get("PORT", "5000"))
    flask_app.run(debug=debug, port=port)
