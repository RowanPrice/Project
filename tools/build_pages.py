#!/usr/bin/env python3
"""Build the static, browser-only edition of the game into ``docs/``.

GitHub Pages serves static files and nothing else -- it cannot run Flask, or
any server-side code at all.  That is a hard constraint and there is no way
around it.

What *can* be done is run the simulation in the browser instead of on a
server, and because ``reactorsim`` is pure Python with no dependencies outside
the standard library, it runs unmodified under Pyodide (CPython compiled to
WebAssembly).  So the Pages build is not a reimplementation and not a
simplification: it is the same ``.py`` files, the same
:class:`reactorsim.web.Session`, and the same ``static/app.js``, with a small
shim that answers ``fetch('/api/...')`` from the in-page Python interpreter
instead of from Flask.

    app.py         -> Flask serves Session over HTTP        (local, and any host that runs Python)
    docs/          -> Pyodide runs Session in the tab       (GitHub Pages)
                      ^ same reactorsim, same app.js, same physics

Run this after changing anything in ``reactorsim/``, ``static/`` or
``templates/``::

    python3 tools/build_pages.py

The CI workflow runs it with ``--check`` and fails if ``docs/`` is stale.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"

PYODIDE_VERSION = "0.26.4"
PYODIDE_URL = f"https://cdn.jsdelivr.net/pyodide/v{PYODIDE_VERSION}/full/"


def jinja_to_static(html: str) -> str:
    """Replace Flask's ``url_for`` calls with plain relative paths."""
    html = re.sub(
        r"\{\{\s*url_for\('static',\s*filename='([^']+)'\)\s*\}\}",
        r"\1",
        html,
    )
    html = re.sub(r"\{\{\s*url_for\('[^']+'\)\s*\}\}", "#", html)
    return html


LOADER_MARKUP = """
<div class="overlay open" id="boot">
  <div class="modal" style="max-width:560px">
    <h2>Starting the reactor simulation</h2>
    <p id="boot-status">Loading the Python runtime&hellip;</p>
    <div class="meter"><i id="boot-bar" style="width:5%"></i></div>
    <p class="help">
      This page runs the simulation in your browser. It is the same
      <code>reactorsim</code> package the Flask server runs, executing under
      Pyodide &mdash; CPython compiled to WebAssembly &mdash; because GitHub
      Pages can serve files but cannot run a server. First load fetches about
      10&nbsp;MB of runtime and then everything is local: no requests, no
      backend, and it keeps running with the network unplugged.
    </p>
  </div>
</div>
"""

BOOT_SCRIPT = """/* Browser edition bootstrap.
 *
 * Loads Pyodide, copies the reactorsim package into its virtual filesystem,
 * builds the same Session object app.py builds, and then replaces window.fetch
 * so that the unmodified static/app.js talks to it.  app.js is injected only
 * once all of that is ready, so it never sees a half-built world.
 */

'use strict';

const PYODIDE_URL = 'PYODIDE_URL_PLACEHOLDER';
const MODULES = MODULES_PLACEHOLDER;

function status(text, fraction) {
    const line = document.getElementById('boot-status');
    const bar = document.getElementById('boot-bar');
    if (line) line.textContent = text;
    if (bar && fraction !== undefined) bar.style.width = `${Math.round(fraction * 100)}%`;
}

function loadScript(src) {
    return new Promise((resolve, reject) => {
        const tag = document.createElement('script');
        tag.src = src;
        tag.onload = resolve;
        tag.onerror = () => reject(new Error(`failed to load ${src}`));
        document.head.appendChild(tag);
    });
}

function json(text) {
    return new Response(text, {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
    });
}

async function boot() {
    try {
        status('Loading the Python runtime\\u2026', 0.1);
        await loadScript(`${PYODIDE_URL}pyodide.js`);
        const pyodide = await loadPyodide({ indexURL: PYODIDE_URL });

        status('Loading the simulation\\u2026', 0.55);
        pyodide.FS.mkdir('/reactorsim');
        let done = 0;
        for (const name of MODULES) {
            const response = await fetch(`reactorsim/${name}`);
            if (!response.ok) throw new Error(`missing reactorsim/${name}`);
            pyodide.FS.writeFile(`/reactorsim/${name}`, await response.text());
            done += 1;
            status('Loading the simulation\\u2026', 0.55 + 0.3 * (done / MODULES.length));
        }

        status('Bringing the plant online\\u2026', 0.9);
        pyodide.runPython([
            'import sys',
            "sys.path.insert(0, '/')",
            'from reactorsim.web import Session',
            "session = Session(scenario='full_power')",
        ].join('\\n'));
        const session = pyodide.globals.get('session');

        // The API shim. Everything else falls through to the real fetch, which
        // is how style.css, app.js and the module sources are loaded.
        const original = window.fetch.bind(window);
        window.fetch = async (input, options = {}) => {
            const url = typeof input === 'string' ? input : input.url;
            const path = String(url).replace(/^.*?(\\/api\\/)/, '$1');
            const body = options.body || '';
            try {
                if (path === '/api/state') return json(session.state_json());
                if (path === '/api/history') return json(session.history_json());
                if (path === '/api/scenarios') return json(session.scenarios_json());
                if (path === '/api/save') return json(session.save_json());
                if (path === '/api/action') return json(session.act_json(body));
                if (path === '/api/new') return json(session.new_json(body));
            } catch (error) {
                return json(JSON.stringify({ ok: false, message: String(error) }));
            }
            return original(input, options);
        };

        // The simulation clock. Flask runs this on a background thread at
        // 20 Hz; here it is a timer, and the elapsed time is measured rather
        // than assumed so that a throttled background tab does not silently
        // slow the plant down.
        let previous = performance.now();
        setInterval(() => {
            const now = performance.now();
            const elapsed = Math.min((now - previous) / 1000, 0.5);
            previous = now;
            try { session.tick(elapsed); } catch (error) { console.error(error); }
        }, 50);

        document.getElementById('boot').classList.remove('open');
        await loadScript('app.js');
    } catch (error) {
        status(`Could not start: ${error.message}`, 1);
        console.error(error);
    }
}

boot();
"""


def build() -> dict[str, str]:
    """Return the full contents of ``docs/`` as a path -> text mapping."""
    files: dict[str, str] = {}

    modules = sorted(path.name for path in (ROOT / "reactorsim").glob("*.py"))
    for name in modules:
        files[f"reactorsim/{name}"] = (ROOT / "reactorsim" / name).read_text()

    files["style.css"] = (ROOT / "static" / "style.css").read_text()
    files["app.js"] = (ROOT / "static" / "app.js").read_text()

    html = jinja_to_static((ROOT / "templates" / "index.html").read_text())
    html = html.replace(
        '<script src="app.js"></script>',
        '<script src="boot.js"></script>',
    )
    html = html.replace("</body>", LOADER_MARKUP + "</body>")
    files["index.html"] = html

    files["boot.js"] = (
        BOOT_SCRIPT
        .replace("PYODIDE_URL_PLACEHOLDER", PYODIDE_URL)
        .replace("MODULES_PLACEHOLDER", json.dumps(modules))
    )
    files[".nojekyll"] = ""
    return files


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="fail if docs/ does not match the sources")
    arguments = parser.parse_args()

    files = build()

    if arguments.check:
        stale = []
        for path, content in files.items():
            target = DOCS / path
            if not target.exists() or target.read_text() != content:
                stale.append(path)
        if stale:
            print("docs/ is out of date; run tools/build_pages.py:", file=sys.stderr)
            for path in stale:
                print(f"  {path}", file=sys.stderr)
            return 1
        print(f"docs/ is up to date ({len(files)} files)")
        return 0

    if DOCS.exists():
        shutil.rmtree(DOCS)
    for path, content in files.items():
        target = DOCS / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    print(f"wrote {len(files)} files to docs/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
