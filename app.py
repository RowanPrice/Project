"""Flask front end for the reactor simulation.

The simulation runs in a background thread at a fixed rate, independent of the
browser.  This matters: the physics has time constants of a few seconds and the
plant must keep evolving whether or not anyone is looking at it, so the web
layer only ever reads a snapshot and posts actions.  Everything that touches
the game holds a lock.

The game itself lives in :class:`reactorsim.web.Session`, which is shared with
the browser-only build under ``docs/`` -- the two front ends run identical code.
"""

from __future__ import annotations

import threading
import time

from flask import Flask, jsonify, render_template, request, send_from_directory

from reactorsim.web import Session

app = Flask(__name__)

#: Simulation rate, hertz.  The game sub-steps internally, so this only sets
#: how often the browser can see something new.
TICK_HZ = 20.0


class ThreadedSession:
    """A Session advanced by a daemon thread, guarded by a lock."""

    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.session = Session(scenario="full_power")
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        period = 1.0 / TICK_HZ
        previous = time.monotonic()
        while not self._stop.is_set():
            time.sleep(period)
            now = time.monotonic()
            elapsed = min(now - previous, 0.5)
            previous = now
            with self.lock:
                self.session.tick(elapsed)


runtime = ThreadedSession()


@app.route("/")
def index():
    return render_template("index.html")


@app.get("/api/state")
def api_state():
    with runtime.lock:
        return jsonify(runtime.session.state())


@app.get("/api/history")
def api_history():
    with runtime.lock:
        return jsonify(runtime.session.history)


@app.post("/api/action")
def api_action():
    payload = request.get_json(silent=True) or {}
    with runtime.lock:
        return jsonify(runtime.session.act(
            str(payload.get("action", "")), payload.get("payload") or {}))


@app.get("/api/scenarios")
def api_scenarios():
    return jsonify(Session.scenarios())


@app.post("/api/new")
def api_new():
    payload = request.get_json(silent=True) or {}
    seed = payload.get("seed")
    with runtime.lock:
        result = runtime.session.reset(
            str(payload.get("scenario", "full_power")),
            int(seed) if seed not in (None, "") else None,
        )
    return (jsonify(result), 200) if result["ok"] else (jsonify(result), 400)


@app.get("/api/save")
def api_save():
    with runtime.lock:
        return app.response_class(runtime.session.save_json(),
                                  mimetype="application/json")


@app.get("/api/speeds")
def api_speeds():
    return jsonify(Session.speeds())


@app.route("/assets/<path:filename>")
def assets(filename):
    return send_from_directory(app.root_path, filename)


if __name__ == "__main__":
    app.run(debug=False, threaded=True, port=5000)
