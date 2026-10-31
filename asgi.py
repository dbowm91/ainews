"""ASGI entry point for serving the Flask application through WsgiToAsgi.

Run with an ASGI server such as Uvicorn using ``uvicorn asgi:application``.
The application remains synchronous; WsgiToAsgi runs Flask requests in its
thread-sensitive execution context.
"""

from asgiref.wsgi import WsgiToAsgi

from app import create_app

application = WsgiToAsgi(create_app())
