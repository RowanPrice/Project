/* Browser edition bootstrap.
 *
 * Loads Pyodide, copies the reactorsim package into its virtual filesystem,
 * builds the same Session object app.py builds, and then replaces window.fetch
 * so that the unmodified static/app.js talks to it.  app.js is injected only
 * once all of that is ready, so it never sees a half-built world.
 */

'use strict';

const PYODIDE_URL = 'https://cdn.jsdelivr.net/pyodide/v0.26.4/full/';
const MODULES = ["__init__.py", "constants.py", "economy.py", "events.py", "game.py", "grid.py", "neutronics.py", "plant.py", "research.py", "rods.py", "scenarios.py", "storage.py", "thermal.py", "web.py"];

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
        status('Loading the Python runtime\u2026', 0.1);
        await loadScript(`${PYODIDE_URL}pyodide.js`);
        const pyodide = await loadPyodide({ indexURL: PYODIDE_URL });

        status('Loading the simulation\u2026', 0.55);
        pyodide.FS.mkdir('/reactorsim');
        let done = 0;
        for (const name of MODULES) {
            const response = await fetch(`reactorsim/${name}`);
            if (!response.ok) throw new Error(`missing reactorsim/${name}`);
            pyodide.FS.writeFile(`/reactorsim/${name}`, await response.text());
            done += 1;
            status('Loading the simulation\u2026', 0.55 + 0.3 * (done / MODULES.length));
        }

        status('Bringing the plant online\u2026', 0.9);
        pyodide.runPython([
            'import sys',
            "sys.path.insert(0, '/')",
            'from reactorsim.web import Session',
            "session = Session(scenario='full_power')",
        ].join('\n'));
        const session = pyodide.globals.get('session');

        // The API shim. Everything else falls through to the real fetch, which
        // is how style.css, app.js and the module sources are loaded.
        const original = window.fetch.bind(window);
        window.fetch = async (input, options = {}) => {
            const url = typeof input === 'string' ? input : input.url;
            const path = String(url).replace(/^.*?(\/api\/)/, '$1');
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
