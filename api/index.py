# Vercel entrypoint: exposes the FastAPI app to the Python runtime.
# Serverless filesystems are read-only outside /tmp, so default the SQLite
# path and logs there; production on Vercel should use Turso (TURSO_* vars).
import os

os.environ.setdefault('AUTH_DB', '/tmp/prd.db')
os.environ.setdefault('LOG_DIR', '/tmp')

from server import app  # noqa: E402, F401
