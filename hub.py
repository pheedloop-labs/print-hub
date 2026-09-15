"""Entry point. The service runs `waitress-serve hub:app` from this directory.

    python hub.py                                   dev
    waitress-serve --listen=0.0.0.0:8080 hub:app    as the service does

Everything real is in printhub/. The findings are in CLAUDE.MD.
"""

from printhub.app import app

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=False)
