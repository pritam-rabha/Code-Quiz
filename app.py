"""Entry point.

Local development:  python app.py
Production (Render): gunicorn app:app -c gunicorn.conf.py
"""
from __future__ import annotations

import os

from quiz_app import create_app

app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=os.environ.get("FLASK_DEBUG") == "1")
