"""Run the operator CLI as ``python -m ainews_cli``.

This is the relocation-proof entry point used by the ``ainews`` wrapper
script shipped in release artifacts: the installed ``.venv`` is moved from
its build location to the install root, which invalidates the absolute
shebangs of ``.venv/bin/*`` console scripts. Invoking the venv's own
``python`` with ``-m`` always resolves against the shipped source tree
(the wrapper runs from the install root), so it keeps working.
"""

from ainews_cli.main import app

if __name__ == "__main__":
    app()
