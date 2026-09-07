/* Reactor control room front end.
 *
 * The simulation lives on the server and runs whether or not this page is
 * open. All this does is poll a state snapshot four times a second, render it,
 * and post operator actions back. Nothing here decides anything; every number
 * on screen came out of the physics.
 */

'use strict';

const REFRESH_MS = 250;
let state = null;
let history = [];
let selectedTab = 'reactor';
let scenarios = [];

/* ------------------------------------------------------------- utilities */

const $ = (id) => document.getElementById(id);
const el = (tag, cls, text) => {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = text;
    return node;
};

const fmt = (value, digits = 1) => {
    if (value === null || value === undefined || Number.isNaN(value)) return '--';
    let number = Number(value);
    // Suppress "-0.0", which reads as a fault indication rather than a zero.
    if (Math.abs(number) < 0.5 * Math.pow(10, -digits)) number = 0;
    return number.toLocaleString('en-GB', {
        minimumFractionDigits: digits, maximumFractionDigits: digits });
};

const money = (value) => {
    const sign = value < 0 ? '-' : '';
    const magnitude = Math.abs(value);
    if (magnitude >= 1e9) return `${sign}£${(magnitude / 1e9).toFixed(2)}bn`;
    if (magnitude >= 1e6) return `${sign}£${(magnitude / 1e6).toFixed(2)}m`;
    if (magnitude >= 1e3) return `${sign}£${(magnitude / 1e3).toFixed(0)}k`;
    return `${sign}£${magnitude.toFixed(0)}`;
};

const clockString = (seconds) => {
    const day = Math.floor(seconds / 86400) + 1;
    const rest = seconds % 86400;
    const hh = String(Math.floor(rest / 3600)).padStart(2, '0');
    const mm = String(Math.floor((rest % 3600) / 60)).padStart(2, '0');
    const ss = String(Math.floor(rest % 60)).padStart(2, '0');
    return `Day ${day}  ${hh}:${mm}:${ss}`;
};

let toastTimer = null;
function toast(message, bad) {
    const node = $('toast');
    node.textContent = message;
    node.className = `toast show${bad ? ' bad' : ''}`;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { node.className = 'toast'; }, 3200);
}

async function action(name, payload) {
    const response = await fetch('/api/action', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: name, payload: payload || {} }),
    });
    const result = await response.json();
    if (result.state) apply(result.state);
    if (result.message) toast(result.message, !result.ok);
    return result;
}

/* Build a readings block: [label, value, className] triples. */
function readings(container, rows) {
    container.innerHTML = '';
    rows.forEach(([label, value, cls]) => {
        const row = el('div', `reading${cls ? ' ' + cls : ''}`);
        row.appendChild(el('label', null, label));
        row.appendChild(el('b', null, value));
        container.appendChild(row);
    });
}

/* --------------------------------------------------------------- charting */

function prepare(canvas) {
    const ratio = window.devicePixelRatio || 1;
    const width = canvas.clientWidth || 300;
    // Remember the design height on first use: setting canvas.height rewrites
    // the attribute, so reading it back on a high-DPI screen would multiply
    // the chart by the pixel ratio every single frame.
    if (!canvas.dataset.height) {
        canvas.dataset.height = canvas.getAttribute('height') || '120';
    }
    const height = Number(canvas.dataset.height);
    if (canvas.width !== Math.round(width * ratio)) {
        canvas.width = Math.round(width * ratio);
        canvas.height = Math.round(height * ratio);
    }
    // Pin the CSS height, or the element takes its size from the backing
    // store and grows by the device pixel ratio on a high-DPI screen.
    canvas.style.height = `${height}px`;
    const context = canvas.getContext('2d');
    context.setTransform(ratio, 0, 0, ratio, 0, 0);
    context.clearRect(0, 0, width, height);
    return { context, width, height };
}

/* Draw one or more series. Each series is {key, colour, log, dash}. */
function chart(canvas, series, options = {}) {
    const { context, width, height } = prepare(canvas);
    const pad = { left: 38, right: 6, top: 8, bottom: 6 };
    const plotWidth = width - pad.left - pad.right;
    const plotHeight = height - pad.top - pad.bottom;
    if (!history.length) return;

    const values = [];
    series.forEach((s) => history.forEach((point) => {
        const value = point[s.key];
        if (Number.isFinite(value)) values.push(s.log ? Math.log10(Math.max(value, 1e-7)) : value);
    }));
    if (!values.length) return;

    const fixed = options.min !== undefined && options.max !== undefined;
    let low = options.min !== undefined ? options.min : Math.min(...values);
    let high = options.max !== undefined ? options.max : Math.max(...values);
    if (high - low < 1e-9) { high += 1; low -= 1; }
    if (!fixed) {
        // Breathing room, but only when the scale was chosen from the data.
        const margin = (high - low) * 0.08;
        low -= margin;
        high += margin;
    }

    const x = (index) => pad.left + (index / Math.max(history.length - 1, 1)) * plotWidth;
    const y = (value) => pad.top + plotHeight - ((value - low) / (high - low)) * plotHeight;

    // Gridlines and axis labels.
    context.strokeStyle = '#1b232a';
    context.fillStyle = '#5d6c78';
    context.font = '9px ui-monospace, monospace';
    context.lineWidth = 1;
    for (let i = 0; i <= 4; i += 1) {
        const value = low + (high - low) * (i / 4);
        const py = Math.round(y(value)) + 0.5;
        context.beginPath();
        context.moveTo(pad.left, py);
        context.lineTo(width - pad.right, py);
        context.stroke();
        const shown = series[0].log ? Math.pow(10, value) : value;
        context.fillText(
            Math.abs(shown) >= 1000 ? shown.toFixed(0) : shown.toFixed(shown < 10 ? 2 : 1),
            2, py + 3,
        );
    }

    if (options.marker !== undefined) {
        const py = Math.round(y(options.marker)) + 0.5;
        context.strokeStyle = '#3d4a55';
        context.setLineDash([3, 3]);
        context.beginPath();
        context.moveTo(pad.left, py);
        context.lineTo(width - pad.right, py);
        context.stroke();
        context.setLineDash([]);
    }

    series.forEach((s) => {
        context.strokeStyle = s.colour;
        context.lineWidth = 1.6;
        context.setLineDash(s.dash || []);
        context.beginPath();
        let started = false;
        history.forEach((point, index) => {
            let value = point[s.key];
            if (!Number.isFinite(value)) return;
            if (s.log) value = Math.log10(Math.max(value, 1e-7));
            const px = x(index);
            const py = y(value);
            if (!started) { context.moveTo(px, py); started = true; }
            else context.lineTo(px, py);
        });
        context.stroke();
        context.setLineDash([]);
    });
}

/* The heat balance schematic: core, loop, steam generator, turbine, grid. */
function schematic() {
    const canvas = $('schematic');
    const { context, width, height } = prepare(canvas);
    if (!state) return;
    const t = state.thermal;
    const r = state.reactor;
    const e = state.electrical;

    const box = (x, y, w, h, label, lines, accent) => {
        context.fillStyle = '#141a1f';
        context.strokeStyle = accent || '#35434f';
        context.lineWidth = 1.4;
        context.beginPath();
        context.roundRect(x, y, w, h, 5);
        context.fill();
        context.stroke();
        context.fillStyle = '#8697a3';
        context.font = '10px ui-monospace, monospace';
        context.fillText(label, x + 9, y + 15);
        context.fillStyle = '#dfe7ec';
        context.font = '11px ui-monospace, monospace';
        lines.forEach((line, index) => context.fillText(line, x + 9, y + 32 + index * 14));
    };

    const arrow = (x1, y1, x2, y2, label, intensity) => {
        const strength = Math.max(0, Math.min(1, intensity));
        context.strokeStyle = `rgba(${Math.round(70 + 185 * strength)}, ${Math.round(200 - 90 * strength)}, ${Math.round(140 - 60 * strength)}, ${0.35 + 0.6 * strength})`;
        context.lineWidth = 1.5 + 3.5 * strength;
        context.beginPath();
        context.moveTo(x1, y1);
        context.lineTo(x2, y2);
        context.stroke();
        const angle = Math.atan2(y2 - y1, x2 - x1);
        context.beginPath();
        context.moveTo(x2, y2);
        context.lineTo(x2 - 8 * Math.cos(angle - 0.4), y2 - 8 * Math.sin(angle - 0.4));
        context.lineTo(x2 - 8 * Math.cos(angle + 0.4), y2 - 8 * Math.sin(angle + 0.4));
        context.closePath();
        context.fill();
        if (label) {
            context.fillStyle = '#8697a3';
            context.font = '10px ui-monospace, monospace';
            context.fillText(label, (x1 + x2) / 2 - 26, (y1 + y2) / 2 - 8);
        }
    };

    const w = Math.max(width, 640);
    const unit = w / 4.4;
    const y0 = 34;
    const boxHeight = 96;

    box(8, y0, unit, boxHeight, 'CORE', [
        `${fmt(r.thermal_mw, 0)} MW th`,
        `fuel ${fmt(t.fuel_temperature, 0)} °C`,
        `decay ${fmt(r.decay_mw, 1)} MW`,
    ], r.tripped ? '#ff5a52' : '#46d17f');

    box(8 + unit * 1.15, y0, unit, boxHeight, 'PRIMARY', [
        `Th ${fmt(t.hot_leg, 1)} / Tc ${fmt(t.cold_leg, 1)}`,
        `${fmt(t.pressure, 2)} MPa`,
        `flow ${fmt(t.flow * 100, 0)}%  sub ${fmt(t.subcooling, 0)} K`,
    ], t.subcooling < 10 ? '#ff5a52' : '#35434f');

    box(8 + unit * 2.3, y0, unit, boxHeight, 'STEAM GENERATORS', [
        `${fmt(t.steam_pressure, 2)} MPa`,
        `${fmt(t.steam_temperature, 1)} °C`,
        `level ${fmt(t.sg_inventory * 100, 0)}%`,
    ], t.sg_inventory < 0.4 ? '#ffb648' : '#35434f');

    box(8 + unit * 3.45, y0, unit * 0.9, boxHeight, 'TURBINE / GRID', [
        `${fmt(e.gross_mw, 0)} MW gross`,
        `${fmt(e.net_mw, 0)} MW net`,
        `valve ${fmt(t.turbine_valve * 100, 0)}%`,
    ], t.turbine_tripped ? '#ff5a52' : '#52b8ff');

    const midY = y0 + boxHeight / 2;
    arrow(8 + unit, midY, 8 + unit * 1.15, midY, null, r.power_fraction);
    arrow(8 + unit * 2.15, midY, 8 + unit * 2.3, midY, null, r.power_fraction * t.flow);
    arrow(8 + unit * 3.3, midY, 8 + unit * 3.45, midY, null, t.turbine_valve);

    // Steam dump path, drawn only when it is passing steam.
    if (t.dump_valve > 0.01) {
        context.strokeStyle = 'rgba(255,182,72,0.85)';
        context.lineWidth = 1 + 4 * t.dump_valve;
        context.beginPath();
        context.moveTo(8 + unit * 3.05, y0 + boxHeight);
        context.lineTo(8 + unit * 3.05, y0 + boxHeight + 34);
        context.lineTo(8 + unit * 3.9, y0 + boxHeight + 34);
        context.stroke();
        context.fillStyle = '#ffb648';
        context.font = '10px ui-monospace, monospace';
        context.fillText(
            `steam dumps ${fmt(t.dump_valve * 100, 0)}% to condenser`,
            8 + unit * 2.55, y0 + boxHeight + 50,
        );
    }

    context.fillStyle = '#5d6c78';
    context.font = '10px ui-monospace, monospace';
    context.fillText('heat flows left to right; line thickness is power', 10, height - 8);
}

/* --------------------------------------------------------------- renderer */

function apply(next) {
    // A malformed or error payload must not take the whole panel down; the
    // next poll will bring a good one.
    if (!next || !next.clock) return;
    state = next;
    if (next.history) history = next.history;
    render();
}

function render() {
    if (!state) return;
    renderTop();
    renderAlarms();
    renderRail();
    renderLog();
    if (selectedTab === 'reactor') renderReactor();
    if (selectedTab === 'thermal') renderThermal();
    if (selectedTab === 'electrical') renderElectrical();
    if (selectedTab === 'commercial') renderCommercial();
    if (selectedTab === 'fuel') renderFuel();
    if (selectedTab === 'plant') renderPlant();
    if (state.game_over) showGameOver();
}

function renderTop() {
    const c = state.clock;
    $('clock').innerHTML =
        `<strong>${clockString(c.time)}</strong> &middot; ${state.scenario.replace('_', ' ')}`;
    const r = state.reactor;
    $('hl-power').textContent = `${fmt(r.power_fraction * 100, 1)}%`;
    $('hl-power').style.color = r.tripped ? 'var(--red)'
        : r.power_fraction > 1.02 ? 'var(--amber)' : 'var(--green)';
    $('hl-mwe').textContent = `${fmt(state.electrical.site_output_mw, 0)} MW`;
    $('hl-period').textContent = r.period === null ? '∞'
        : `${fmt(r.period, 0)} s`;
    $('hl-period').style.color =
        r.period !== null && r.period > 0 && r.period < 30 ? 'var(--red)' : 'var(--text)';
    $('hl-freq').textContent = `${fmt(state.grid.frequency, 3)} Hz`;
    $('hl-freq').style.color = state.grid.healthy ? 'var(--text)' : 'var(--amber)';
    $('hl-cash').textContent = money(state.finance.cash);
    $('hl-cash').style.color = state.finance.cash < 0 ? 'var(--red)' : 'var(--text)';

    document.querySelectorAll('#speeds button').forEach((button) => {
        const speed = Number(button.dataset.speed);
        button.classList.toggle('active', speed === c.speed);
        button.classList.toggle('limited', speed === c.speed && c.effective_speed !== c.speed);
    });
}

function renderAlarms() {
    const container = $('alarms');
    container.innerHTML = '';
    if (!state.alarms.length) {
        container.appendChild(el('div', 'none', 'No active alarms'));
        return;
    }
    const order = { critical: 0, alarm: 1, warning: 2, info: 3 };
    [...state.alarms]
        .sort((a, b) => order[a.severity] - order[b.severity])
        .forEach((alarm) => {
            const chip = el('div', `chip ${alarm.severity}${alarm.acknowledged ? ' acked' : ''}`,
                alarm.message);
            chip.onclick = () => action('acknowledge', { key: alarm.key });
            container.appendChild(chip);
        });
}

function renderRail() {
    const r = state.reactor;
    const t = state.thermal;
    const grade = (value, warn, bad, invert) => {
        if (invert) return value <= bad ? 'bad' : value <= warn ? 'warn' : 'good';
        return value >= bad ? 'bad' : value >= warn ? 'warn' : 'good';
    };

    readings($('rail-reactor'), [
        ['Power', `${fmt(r.power_fraction * 100, 2)} %`],
        ['Thermal', `${fmt(r.thermal_mw, 0)} MW`],
        ['Reactivity', `${fmt(r.reactivity.total, 1)} pcm`,
            Math.abs(r.reactivity.total) > 200 ? 'warn' : ''],
        ['Period', r.period === null ? '∞ s' : `${fmt(r.period, 0)} s`,
            r.period !== null && r.period > 0 && r.period < 30 ? 'bad' : ''],
        ['Banks', `${fmt(r.control_position, 1)} %`],
        ['Diff. worth', `${fmt(r.differential_worth, 1)} pcm/%`],
        ['Boron', `${fmt(r.boron_ppm, 0)} ppm`],
        ['MTC', `${fmt(r.mtc, 1)} pcm/K`, r.mtc > 0 ? 'bad' : ''],
        ['Xenon', `${fmt(r.xenon_pcm, 0)} pcm`],
        ['Burnup', `${fmt(r.burnup, 2)} GWd/tU`],
    ]);

    readings($('rail-primary'), [
        ['Fuel temp', `${fmt(t.fuel_temperature, 0)} °C`,
            grade(t.fuel_temperature, 900, 1200)],
        ['T-average', `${fmt(t.coolant_temperature, 1)} °C`],
        ['Hot leg', `${fmt(t.hot_leg, 1)} °C`, grade(t.hot_leg, 335, 342)],
        ['Pressure', `${fmt(t.pressure, 2)} MPa`],
        ['Subcooling', `${fmt(t.subcooling, 1)} K`, grade(t.subcooling, 15, 5, true)],
        ['Flow', `${fmt(t.flow * 100, 0)} %`, grade(t.flow, 0.95, 0.88, true)],
        ['Void', `${fmt(t.void * 100, 2)} %`, t.void > 0.001 ? 'bad' : ''],
        ['Inventory', `${fmt(t.inventory * 100, 1)} %`, grade(t.inventory, 0.99, 0.9, true)],
    ]);

    readings($('rail-secondary'), [
        ['Steam', `${fmt(t.steam_pressure, 2)} MPa`],
        ['SG level', `${fmt(t.sg_inventory * 100, 0)} %`, grade(t.sg_inventory, 0.6, 0.35, true)],
        ['Turbine', `${fmt(t.turbine_valve * 100, 0)} %`],
        ['Dumps', `${fmt(t.dump_valve * 100, 0)} %`],
        ['Gross', `${fmt(state.electrical.gross_mw, 0)} MW`],
        ['Net', `${fmt(state.electrical.net_mw, 0)} MW`],
    ]);

    const committed = state.contracts.active
        .reduce((total, contract) => total + contract.required_now, 0);
    readings($('rail-commercial'), [
        ['Contracted', `${fmt(committed, 0)} MW`,
            committed > state.electrical.site_output_mw + 1 ? 'bad' : 'good'],
        ['Spot price', `£${fmt(state.grid.spot_price, 0)}`],
        ['Demand', `${fmt(state.grid.demand_mw / 1000, 1)} GW`],
        ['Weather', state.grid.weather],
        ['Reputation', fmt(state.finance.reputation, 0)],
        ['Safety', fmt(state.maintenance.safety_score, 0),
            state.maintenance.safety_score < 60 ? 'bad'
                : state.maintenance.safety_score < 80 ? 'warn' : 'good'],
    ]);
}

function renderReactor() {
    const r = state.reactor;

    const banks = $('banks');
    banks.innerHTML = '';
    r.banks.forEach((bank) => {
        const node = el('div', `bank${bank.shutdown ? ' shutdown' : ''}`);
        node.appendChild(el('div', 'value', `${bank.position.toFixed(0)}%`));
        const track = el('div', 'track');
        const fill = el('i', 'fill');
        fill.style.height = `${100 - bank.position}%`;
        const demand = el('i', 'demand');
        demand.style.bottom = `${100 - bank.demand}%`;
        track.appendChild(fill);
        track.appendChild(demand);
        node.appendChild(track);
        node.appendChild(el('div', 'label', bank.name));
        node.title = `${bank.name}: ${bank.worth} pcm total worth, `
            + `${bank.shutdown ? 'shutdown bank' : 'control bank'}`;
        banks.appendChild(node);
    });

    $('btn-auto-rods').classList.toggle('on', r.auto_rods);
    $('btn-auto-boron').classList.toggle('on', r.auto_boron);
    $('btn-reset-trip').disabled = !r.tripped;
    $('rod-help').innerHTML = r.tripped
        ? '<b style="color:var(--red)">Reactor tripped.</b> '
          + `${r.trip_reasons.join('; ')}. The banks are on the bottom. Clear the `
          + 'condition, reset the trip, then withdraw again &mdash; and remember the '
          + 'xenon that is building while you do it.'
        : `Differential worth here is ${fmt(r.differential_worth, 1)} pcm per percent `
          + 'of bank travel. It follows a sin&sup2; profile, so the same step is worth '
          + 'four times as much at mid-travel as it is near the top. Shutdown margin '
          + `on a trip: ${fmt(r.shutdown_margin, 0)} pcm.`;

    // Reactivity balance bars.
    const balance = $('balance');
    balance.innerHTML = '';
    const terms = [
        ['Fuel', r.reactivity.fuel], ['Rods', r.reactivity.rods],
        ['Boron', r.reactivity.boron], ['Doppler', r.reactivity.doppler],
        ['Moderator', r.reactivity.moderator], ['Void', r.reactivity.void],
        ['Xenon', r.reactivity.xenon], ['Samarium', r.reactivity.samarium],
    ];
    const scale = Math.max(...terms.map(([, v]) => Math.abs(v)), 1000);
    terms.forEach(([label, value]) => {
        const row = el('div', 'term');
        row.appendChild(el('label', null, label));
        const bar = el('div', 'bar');
        bar.appendChild(el('div', 'zero'));
        const fill = el('i');
        const width = (Math.abs(value) / scale) * 50;
        fill.style.width = `${width}%`;
        fill.style.background = value >= 0 ? 'var(--green)' : 'var(--red)';
        if (value >= 0) fill.style.left = '50%'; else fill.style.right = '50%';
        bar.appendChild(fill);
        row.appendChild(bar);
        row.appendChild(el('span', null, fmt(value, 0)));
        balance.appendChild(row);
    });
    const total = el('div', 'term total');
    total.appendChild(el('label', null, 'Total'));
    total.appendChild(el('div', null, ''));
    const totalValue = el('span', null, `${fmt(r.reactivity.total, 1)} pcm`);
    totalValue.style.color = Math.abs(r.reactivity.total) < 50 ? 'var(--green)'
        : r.reactivity.total > 500 ? 'var(--red)' : 'var(--amber)';
    total.appendChild(totalValue);
    balance.appendChild(total);

    // Fixed wide-range scale, the way a real flux instrument reads: five
    // decades, so full power sits near the top and a shutdown is still on the
    // chart rather than autoscaling into a meaningless flat line.
    chart($('chart-power'), [
        { key: 'power', colour: '#46d17f', log: true },
    ], { min: -3, max: 2.08 });
    $('chart-power-range').textContent =
        `${history.length} samples · rho ${fmt(r.reactivity.total, 0)} pcm`;

    // Xenon history plus the forecast, if flux mapping has been installed.
    const canvas = $('chart-xenon');
    if (state.xenon_forecast && state.xenon_forecast.length) {
        drawForecast(canvas, state.xenon_forecast);
        $('xenon-note').textContent = 'measured (left) and projected (right)';
    } else {
        chart(canvas, [{ key: 'xenon', colour: '#b088ff' }]);
        $('xenon-note').textContent = 'install incore flux mapping to see the forecast';
    }
    readings($('xenon-readings'), [
        ['Xenon worth', `${fmt(r.xenon_pcm, 0)} pcm`],
        ['Samarium worth', `${fmt(r.samarium_pcm, 0)} pcm`],
        ['Equilibrium at 100%', '-2720 pcm'],
        ['Rod worth inserted', `${fmt(-r.reactivity.rods, 0)} pcm`],
    ]);
    readings($('boron-readings'), [
        ['Concentration', `${fmt(r.boron_ppm, 0)} ppm`],
        ['Worth', `${fmt(r.reactivity.boron, 0)} pcm`],
        ['Demand', r.boron_demand > 0 ? 'Borating'
            : r.boron_demand < 0 ? 'Diluting' : 'Hold'],
        ['MTC', `${fmt(r.mtc, 1)} pcm/K`, r.mtc > 0 ? 'bad' : 'good'],
        ['MTC zero crossing', '1810 ppm'],
    ]);
}

function drawForecast(canvas, forecast) {
    const { context, width, height } = prepare(canvas);
    const values = forecast.map((point) => point.pcm);
    const past = history.slice(-120).map((point) => point.xenon).filter(Number.isFinite);
    const all = past.concat(values);
    if (!all.length) return;
    const low = Math.min(...all) * 1.05;
    const high = Math.max(...all, -100) * 0.95;
    const pad = 34;
    const split = pad + (width - pad - 6) * 0.42;
    const y = (value) => 8 + (height - 16) * (1 - (value - low) / (high - low || 1));

    context.strokeStyle = '#1b232a';
    context.fillStyle = '#5d6c78';
    context.font = '9px ui-monospace, monospace';
    for (let i = 0; i <= 3; i += 1) {
        const value = low + (high - low) * (i / 3);
        const py = Math.round(y(value)) + 0.5;
        context.beginPath();
        context.moveTo(pad, py); context.lineTo(width - 6, py); context.stroke();
        context.fillText(value.toFixed(0), 2, py + 3);
    }

    context.strokeStyle = '#b088ff';
    context.lineWidth = 1.6;
    context.beginPath();
    past.forEach((value, index) => {
        const px = pad + (index / Math.max(past.length - 1, 1)) * (split - pad);
        if (index === 0) context.moveTo(px, y(value)); else context.lineTo(px, y(value));
    });
    context.stroke();

    context.strokeStyle = '#ffb648';
    context.setLineDash([4, 3]);
    context.beginPath();
    forecast.forEach((point, index) => {
        const px = split + (index / Math.max(forecast.length - 1, 1)) * (width - 6 - split);
        if (index === 0) context.moveTo(px, y(point.pcm)); else context.lineTo(px, y(point.pcm));
    });
    context.stroke();
    context.setLineDash([]);

    context.strokeStyle = '#35434f';
    context.beginPath();
    context.moveTo(split, 4); context.lineTo(split, height - 4); context.stroke();
    context.fillStyle = '#8697a3';
    context.fillText('now', split + 4, 12);
}

function renderThermal() {
    const t = state.thermal;
    schematic();

    const pumps = $('pumps');
    pumps.innerHTML = '';
    t.pumps.forEach((running, index) => {
        const component = state.maintenance.components.find((c) => c.key === `rcp${index + 1}`);
        const button = el('button', `act${running ? ' on' : ''}`, `RCP ${index + 1}`);
        button.disabled = component.failed || component.repairing;
        button.title = component.failed ? 'Failed'
            : `Health ${(component.health * 100).toFixed(0)}%`;
        button.onclick = () => action('pump', { index, on: !running });
        pumps.appendChild(button);
    });

    readings($('primary-readings'), [
        ['Flow', `${fmt(t.flow * 100, 1)} %`],
        ['Loop ΔT', `${fmt(t.hot_leg - t.cold_leg, 1)} K`],
        ['Saturation at P', `${fmt(t.saturation, 1)} °C`],
        ['Subcooling margin', `${fmt(t.subcooling, 1)} K`],
        ['Pressuriser relief', t.relief_open ? 'OPEN' : 'shut', t.relief_open ? 'bad' : ''],
        ['Safety injection', t.safety_injection ? 'ARMED' : 'secured'],
        ['Vessel fatigue', `${fmt(t.vessel_stress * 100, 2)} %`,
            t.vessel_stress > 0.4 ? 'bad' : ''],
    ]);

    $('turbine-label').textContent = `${fmt(t.turbine_demand * 100, 0)}% demand, `
        + `${fmt(t.turbine_valve * 100, 0)}% actual`;
    $('dump-label').textContent = `${fmt(t.dump_setpoint, 2)} MPa `
        + `(holds ~${fmt(t.dump_setpoint > 0.2 ? saturationApprox(t.dump_setpoint) : 0, 0)} °C)`;
    if (document.activeElement !== $('turbine-demand')) {
        $('turbine-demand').value = Math.round(t.turbine_demand * 100);
    }
    if (document.activeElement !== $('dump-setpoint')) {
        $('dump-setpoint').value = Math.round(t.dump_setpoint * 100);
    }
    $('btn-auto-feed').classList.toggle('on', t.auto_feedwater);
    $('btn-si').classList.toggle('on', t.safety_injection);
    $('btn-reset-turbine').disabled = !t.turbine_tripped;

    readings($('secondary-readings'), [
        ['Steam pressure', `${fmt(t.steam_pressure, 2)} MPa`],
        ['Steam temp', `${fmt(t.steam_temperature, 1)} °C`],
        ['SG level', `${fmt(t.sg_inventory * 100, 0)} %`],
        ['Feedwater', `${fmt(t.feedwater * 100, 0)} %`],
        ['Dump valve', `${fmt(t.dump_valve * 100, 0)} %`],
        ['Condenser', t.condenser ? 'available' : 'UNAVAILABLE', t.condenser ? '' : 'bad'],
        ['Turbine', t.turbine_tripped ? 'TRIPPED' : 'in service', t.turbine_tripped ? 'bad' : ''],
    ]);

    chart($('chart-temp'), [
        { key: 'fuel', colour: '#ff5a52' },
        { key: 'coolant', colour: '#52b8ff' },
    ]);
    $('chart-temp-range').textContent = 'fuel (red), coolant average (blue)';
    chart($('chart-pressure'), [{ key: 'pressure', colour: '#46d17f' }], { marker: 15.5 });
    $('chart-pressure-range').textContent = 'setpoint 15.5, trips at 13.1 and 16.4';
}

/* A cheap saturation lookup for labels only; the server owns the real one. */
function saturationApprox(mpa) {
    const table = [[0.1, 99.6], [0.5, 151.8], [1, 179.9], [2, 212.4], [3, 233.9],
        [4, 250.4], [5, 263.9], [6, 275.6], [7, 285.8], [8, 295], [9, 303.3]];
    if (mpa <= table[0][0]) return table[0][1];
    for (let i = 1; i < table.length; i += 1) {
        if (mpa <= table[i][0]) {
            const [p0, t0] = table[i - 1];
            const [p1, t1] = table[i];
            return t0 + (t1 - t0) * (Math.log(mpa / p0) / Math.log(p1 / p0));
        }
    }
    return 303;
}

function renderElectrical() {
    const e = state.electrical;
    const b = e.battery;

    readings($('generator-readings'), [
        ['Gross output', `${fmt(e.gross_mw, 0)} MW`],
        ['Coolant pumps', `${fmt(state.thermal.pumps.filter(Boolean).length * 6.5, 1)} MW`],
        ['House load', '22.0 MW'],
        ['Net to grid', `${fmt(e.net_mw, 0)} MW`],
        ['Battery', `${fmt(b.power_mw, 0)} MW`],
        ['Site output', `${fmt(e.site_output_mw, 0)} MW`],
        ['Offsite power', e.offsite_power ? 'available' : 'LOST', e.offsite_power ? '' : 'bad'],
        ['Diesels', e.diesels ? 'RUNNING' : 'standby', e.diesels ? 'warn' : ''],
    ]);

    readings($('grid-readings'), [
        ['Frequency', `${fmt(state.grid.frequency, 3)} Hz`, state.grid.healthy ? 'good' : 'bad'],
        ['System demand', `${fmt(state.grid.demand_mw / 1000, 2)} GW`],
        ['Spot price', `£${fmt(state.grid.spot_price, 2)}/MWh`],
        ['Wind', `${fmt(state.grid.wind_factor * 100, 0)} %`],
        ['Conditions', state.grid.weather],
    ]);

    const meter = $('soc-meter');
    meter.className = `meter${b.soc < 0.15 || b.soc > 0.9 ? ' warn' : ''}`;
    meter.firstElementChild.style.width = `${b.soc * 100}%`;
    $('battery-label').textContent =
        `${b.demand_mw >= 0 ? '+' : ''}${fmt(b.demand_mw, 0)} MW demanded, `
        + `${fmt(b.power_mw, 0)} MW actual`;
    if (document.activeElement !== $('battery-power')) {
        $('battery-power').min = -b.max_power_mw;
        $('battery-power').max = b.max_power_mw;
        $('battery-power').value = Math.round(b.demand_mw);
    }
    $('btn-freq-response').classList.toggle('on', b.frequency_response);
    readings($('battery-readings'), [
        ['State of charge', `${fmt(b.soc * 100, 1)} %`],
        ['Energy', `${fmt(b.charge_mwh, 0)} / ${fmt(b.capacity_mwh, 0)} MWh`],
        ['Power', `${fmt(b.power_mw, 1)} MW`],
        ['Health', `${fmt(b.health * 100, 2)} %`, b.health < 0.8 ? 'warn' : 'good'],
        ['Equivalent cycles', fmt(b.cycles, 1)],
        ['Replacement cost', money(b.replacement_cost)],
    ]);

    chart($('chart-frequency'), [{ key: 'frequency', colour: '#52b8ff' }], { marker: 50 });
    chart($('chart-price'), [{ key: 'price', colour: '#ffb648' }], { marker: 0 });
    $('chart-price-range').textContent = 'negative prices mean you are paying to generate';
}

function contractCard(contract, isOffer) {
    const wrapper = el('div', 'card');
    wrapper.style.background = 'var(--panel-2)';
    const head = el('div', 'row');
    head.style.justifyContent = 'space-between';
    const title = el('div');
    title.appendChild(el('b', null, contract.title));
    const kinds = {
        baseload: 'grey', load_following: 'blue', peaking: 'amber',
        capacity: 'green', frequency_response: 'blue',
    };
    const tag = el('span', `tag ${kinds[contract.kind] || 'grey'}`,
        contract.kind.replace('_', ' '));
    tag.style.marginLeft = '8px';
    title.appendChild(tag);
    head.appendChild(title);
    wrapper.appendChild(head);
    wrapper.appendChild(el('div', 'small muted', contract.description));

    const unit = contract.kind === 'capacity' ? '/MW/day'
        : contract.kind === 'frequency_response' ? '/MW/day' : '/MWh';
    const rows = [
        ['Capacity', `${fmt(contract.capacity_mw, 0)} MW`],
        ['Price', `£${fmt(contract.strike_price, 2)}${unit}`],
        ['Term', `${fmt(contract.duration_days, 0)} days`],
        ['Shortfall penalty', money(contract.shortfall_penalty)],
        ['Completion bonus', money(contract.completion_bonus)],
        ['Collateral', money(contract.collateral)],
    ];
    if (!isOffer) {
        rows.push(['Required now', `${fmt(contract.required_now, 0)} MW`]);
        rows.push(['Delivered', `${fmt(contract.delivered_mwh, 0)} of `
            + `${fmt(contract.required_mwh, 0)} MWh`]);
        rows.push(['Delivery rate', `${fmt(contract.delivery_rate * 100, 1)} %`,
            contract.delivery_rate < 0.97 ? 'bad' : 'good']);
        rows.push(['Days left', fmt(contract.days_left, 2)]);
        rows.push(['Net so far', money(contract.earned - contract.penalties)]);
        if (contract.kind === 'capacity') {
            rows.push(['Availability tests',
                `${contract.tests_passed} passed, ${contract.tests_failed} failed`,
                contract.tests_failed ? 'bad' : 'good']);
            if (contract.test_active) rows.push(['TEST IN PROGRESS', 'deliver now', 'bad']);
        }
    }
    const block = el('div');
    readings(block, rows);
    wrapper.appendChild(block);

    const button = el('button', 'act wide',
        isOffer ? 'Sign contract' : 'Abandon contract');
    if (!isOffer) button.classList.add('danger');
    button.style.marginTop = '8px';
    button.onclick = () => action(isOffer ? 'accept_contract' : 'abandon_contract',
        { key: contract.key });
    wrapper.appendChild(button);
    return wrapper;
}

function renderCommercial() {
    const active = $('active-contracts');
    active.innerHTML = '';
    if (!state.contracts.active.length) {
        active.appendChild(el('p', 'muted small',
            'Nothing contracted. Everything generated is being sold at the spot '
            + 'price, which right now is £' + fmt(state.grid.spot_price, 2) + '/MWh.'));
    } else {
        const grid = el('div', 'grid cards');
        state.contracts.active.forEach((c) => grid.appendChild(contractCard(c, false)));
        active.appendChild(grid);
    }

    const offers = $('contract-offers');
    offers.innerHTML = '';
    if (!state.contracts.offers.length) {
        offers.appendChild(el('p', 'muted small',
            'No offers available. Build reputation by completing what you have signed.'));
    } else {
        const grid = el('div', 'grid cards');
        state.contracts.offers.forEach((c) => grid.appendChild(contractCard(c, true)));
        offers.appendChild(grid);
    }

    const f = state.finance;
    readings($('finance-readings'), [
        ['Cash', money(f.cash), f.cash < 0 ? 'bad' : 'good'],
        ['Revenue today', money(f.revenue_today)],
        ['Costs today', money(f.costs_today)],
        ['Lifetime income', money(f.lifetime_income)],
        ['Lifetime costs', money(f.lifetime_costs)],
        ['Fines', money(f.fines), f.fines > 0 ? 'warn' : ''],
        ['Decommissioning fund', money(f.decommissioning_fund)],
        ['Reputation', fmt(f.reputation, 1)],
        ['Energy delivered', `${fmt(state.score.energy_delivered_mwh, 0)} MWh`],
        ['Capacity factor', `${fmt(state.score.capacity_factor * 100, 1)} %`],
    ]);

    const ledger = $('ledger');
    ledger.innerHTML = '';
    const table = el('table');
    table.innerHTML = '<tr><th>Time</th><th>Item</th><th class="right">Amount</th></tr>';
    [...f.ledger].reverse().forEach((entry) => {
        const row = el('tr');
        row.appendChild(el('td', 'muted', clockString(entry.time).slice(0, 12)));
        row.appendChild(el('td', null, entry.description));
        const amount = el('td', 'right', money(entry.amount));
        amount.style.color = entry.amount >= 0 ? 'var(--green)' : 'var(--red)';
        row.appendChild(amount);
        table.appendChild(row);
    });
    ledger.appendChild(table);
}

function renderFuel() {
    const f = state.fuel;
    const r = state.reactor;
    readings($('fuel-readings'), [
        ['Core enrichment', `${fmt(r.enrichment, 2)} %`],
        ['Burnup', `${fmt(r.burnup, 2)} GWd/tU`],
        ['Cycle used', `${fmt(r.cycle_fraction * 100, 1)} %`,
            r.cycle_fraction > 0.9 ? 'bad' : r.cycle_fraction > 0.75 ? 'warn' : 'good'],
        ['Fuel in store', `${fmt(f.store_kg, 0)} kg at ${fmt(f.store_assay, 2)} %`],
        ['Uranium price', `£${fmt(f.uranium_price, 2)}/kg`],
        ['SWU price', `£${fmt(f.swu_price, 2)}/SWU`],
        ['Minimum tails', `${fmt(f.tails_floor, 2)} %`],
        ['Campaign', f.job ? `${fmt(f.job.progress * 100, 1)}%, `
            + `${fmt(f.job.days_left, 1)} days left` : 'idle'],
        ['Outage', f.outage_days_left !== null
            ? `${fmt(f.outage_days_left, 1)} days remaining` : 'none'],
    ]);
    $('btn-refuel').disabled = f.outage_days_left !== null;
    $('fuel-tails').min = f.tails_floor;
}

function renderPlant() {
    const container = $('components');
    container.innerHTML = '';
    const table = el('table');
    table.innerHTML = '<tr><th>Component</th><th>Condition</th><th>Status</th>'
        + '<th class="right">Repair</th><th></th></tr>';
    state.maintenance.components.forEach((component) => {
        const row = el('tr');
        row.appendChild(el('td', null, component.name));
        const health = el('td');
        const meter = el('div', `meter${component.health < 0.3 ? ' bad'
            : component.health < 0.6 ? ' warn' : ''}`);
        const fill = el('i');
        fill.style.width = `${component.health * 100}%`;
        meter.appendChild(fill);
        health.appendChild(meter);
        health.appendChild(el('div', 'small muted', `${(component.health * 100).toFixed(0)}%`));
        row.appendChild(health);
        const status = el('td');
        status.appendChild(el('span',
            `tag ${component.failed ? 'red' : component.repairing ? 'blue'
                : component.health < 0.35 ? 'amber' : 'green'}`,
            component.failed ? 'failed' : component.repairing
                ? `${component.days_left.toFixed(1)}d` : 'in service'));
        row.appendChild(status);
        row.appendChild(el('td', 'right', money(component.repair_cost)));
        const actions = el('td');
        const button = el('button', 'act', component.failed ? 'Repair' : 'Overhaul');
        button.disabled = component.repairing;
        button.onclick = () => action('repair', { key: component.key });
        actions.appendChild(button);
        row.appendChild(actions);
        table.appendChild(row);
    });
    container.appendChild(table);
    container.appendChild(el('p', 'help',
        'Overhauling something before it fails costs 55% of a repair and does not '
        + 'happen at the worst possible moment. Failure hazard follows a bathtub '
        + 'curve, so condition below about 35% is where the odds turn sharply.'));

    const upgrades = $('upgrades');
    upgrades.innerHTML = '';
    const categories = {};
    state.research.upgrades.forEach((upgrade) => {
        (categories[upgrade.category] = categories[upgrade.category] || []).push(upgrade);
    });
    Object.entries(categories).forEach(([category, items]) => {
        upgrades.appendChild(el('h3', null, category));
        const table2 = el('table');
        items.forEach((upgrade) => {
            const row = el('tr');
            const name = el('td');
            name.appendChild(el('b', null, upgrade.name));
            name.appendChild(el('div', 'small muted', upgrade.description));
            if (upgrade.requires.length) {
                const names = upgrade.requires.map((key) => {
                    const found = state.research.upgrades.find((u) => u.key === key);
                    return found ? found.name : key;
                });
                name.appendChild(el('div', 'small muted', `Requires: ${names.join(', ')}`));
            }
            row.appendChild(name);
            row.appendChild(el('td', 'right', money(upgrade.cost)));
            const actions = el('td', 'right');
            if (upgrade.installed) {
                actions.appendChild(el('span', 'tag green', 'installed'));
            } else if (upgrade.purchased) {
                actions.appendChild(el('span', 'tag blue',
                    `${upgrade.days_left.toFixed(1)} days`));
            } else {
                const button = el('button', 'act', 'Purchase');
                button.disabled = upgrade.locked || state.finance.cash < upgrade.cost;
                button.onclick = () => action('purchase_upgrade', { key: upgrade.key });
                actions.appendChild(button);
            }
            row.appendChild(actions);
            table2.appendChild(row);
        });
        upgrades.appendChild(table2);
    });
}

function renderLog() {
    const container = $('logbar');
    const atBottom = container.scrollHeight - container.scrollTop - container.clientHeight < 30;
    container.innerHTML = '';
    state.log.forEach((entry) => {
        const line = el('div', `logline ${entry.severity}`);
        line.appendChild(el('span', 'ts', clockString(entry.time).slice(0, 12)));
        line.appendChild(el('span', 'msg', entry.message));
        container.appendChild(line);
    });
    if (atBottom) container.scrollTop = container.scrollHeight;
}

/* ---------------------------------------------------------------- modals */

function openModal(build) {
    const modal = $('modal');
    modal.innerHTML = '';
    build(modal);
    $('overlay').classList.add('open');
}

function closeModal() { $('overlay').classList.remove('open'); }

function showScenarios() {
    openModal((modal) => {
        modal.appendChild(el('h2', null, 'Scenarios'));
        modal.appendChild(el('p', null,
            'Each of these is the same simulation with a different starting '
            + 'condition and a different commercial position. Nothing is scripted.'));
        const list = el('div', 'scenario-list');
        scenarios.forEach((scenario) => {
            const button = el('button', 'scenario');
            const heading = el('b');
            heading.textContent = scenario.name;
            const tag = el('span', 'tag grey', scenario.difficulty);
            tag.style.marginLeft = '8px';
            heading.appendChild(tag);
            button.appendChild(heading);
            button.appendChild(el('small', null, scenario.briefing));
            button.onclick = async () => {
                const response = await fetch('/api/new', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ scenario: scenario.key }),
                });
                const result = await response.json();
                if (result.state) { history = []; apply(result.state); }
                closeModal();
                toast(`Started: ${scenario.name}`);
            };
            list.appendChild(button);
        });
        modal.appendChild(list);
        const close = el('button', 'act wide', 'Close');
        close.onclick = closeModal;
        modal.appendChild(close);
    });
}

let gameOverShown = false;
function showGameOver() {
    if (gameOverShown) return;
    gameOverShown = true;
    openModal((modal) => {
        modal.appendChild(el('h2', null, 'Run over'));
        modal.appendChild(el('p', null, state.game_over_reason));
        const score = state.score;
        const block = el('div');
        readings(block, [
            ['Days operated', fmt(score.days, 2)],
            ['Energy delivered', `${fmt(score.energy_delivered_mwh, 0)} MWh`],
            ['Capacity factor', `${fmt(score.capacity_factor * 100, 1)} %`],
            ['Profit', money(score.profit)],
            ['Reactor trips', String(score.trips)],
            ['Burnup achieved', `${fmt(score.burnup, 2)} GWd/tU`],
            ['Core damage', `${fmt(score.core_damage * 100, 1)} %`],
            ['Release', fmt(score.release, 3)],
        ]);
        modal.appendChild(block);
        const button = el('button', 'act wide', 'Choose a scenario');
        button.style.marginTop = '12px';
        button.onclick = () => { gameOverShown = false; showScenarios(); };
        modal.appendChild(button);
    });
}

/* ---------------------------------------------------------------- wiring */

function wire() {
    [0, 1, 5, 30, 120, 240].forEach((speed) => {
        const button = el('button', null, speed === 0 ? '⏸' : `${speed}×`);
        button.dataset.speed = speed;
        button.title = speed === 0 ? 'Pause'
            : `${speed} seconds of plant time per second (limited to 5x while the `
              + 'plant is in an abnormal condition)';
        button.onclick = () => action('set_speed', { speed });
        $('speeds').appendChild(button);
    });

    $('tabs').addEventListener('click', (event) => {
        const button = event.target.closest('button');
        if (!button) return;
        selectedTab = button.dataset.tab;
        document.querySelectorAll('#tabs button').forEach((b) =>
            b.classList.toggle('active', b === button));
        document.querySelectorAll('.panel').forEach((panel) =>
            panel.classList.toggle('active', panel.dataset.panel === selectedTab));
        render();
    });

    document.querySelectorAll('[data-rods]').forEach((button) => {
        button.onclick = () => action('move_rods', { delta: Number(button.dataset.rods) });
    });
    document.querySelectorAll('[data-boron]').forEach((button) => {
        button.onclick = () => action('boron', { demand: Number(button.dataset.boron) });
    });

    $('btn-scram').onclick = () => action('scram');
    $('btn-reset-trip').onclick = () => action('reset_trip');
    $('btn-auto-rods').onclick = () => action('auto_rods');
    $('btn-auto-boron').onclick = () => action('auto_boron');
    $('btn-scenarios').onclick = showScenarios;
    $('overlay').onclick = (event) => { if (event.target === $('overlay')) closeModal(); };

    $('turbine-demand').oninput = (event) =>
        action('turbine', { demand: Number(event.target.value) / 100 });
    $('dump-setpoint').oninput = (event) =>
        action('dump_setpoint', { value: Number(event.target.value) / 100 });
    $('btn-reset-turbine').onclick = () => action('reset_turbine');
    $('btn-auto-feed').onclick = () =>
        action('feedwater', { auto: !state.thermal.auto_feedwater });
    $('btn-si').onclick = () => action('safety_injection');

    $('battery-power').oninput = (event) =>
        action('battery', { power: Number(event.target.value) });
    $('btn-battery-zero').onclick = () => action('battery', { power: 0 });
    $('btn-freq-response').onclick = () =>
        action('battery', { frequency_response: !state.electrical.battery.frequency_response });
    $('btn-replace-battery').onclick = () => action('replace_battery');

    $('btn-quote').onclick = async () => {
        const result = await action('quote_enrichment', {
            kg: Number($('fuel-kg').value),
            assay: Number($('fuel-assay').value),
            tails: Number($('fuel-tails').value),
        });
        if (result.quote) {
            const q = result.quote;
            const block = el('div');
            readings(block, [
                ['Natural uranium feed', `${fmt(q.feed_kg, 0)} kg`],
                ['Separative work', `${fmt(q.swu, 0)} SWU`],
                ['Uranium', money(q.uranium_cost)],
                ['Conversion', money(q.conversion_cost)],
                ['Enrichment', money(q.swu_cost)],
                ['Fabrication', money(q.fabrication_cost)],
                ['Total', money(q.total)],
                ['Cost per kg', `£${fmt(q.cost_per_kg, 0)}`],
            ]);
            $('quote').innerHTML = '';
            $('quote').appendChild(block);
        }
    };
    $('btn-order').onclick = () => action('order_enrichment', {
        kg: Number($('fuel-kg').value),
        assay: Number($('fuel-assay').value),
        tails: Number($('fuel-tails').value),
    });
    $('btn-refuel').onclick = () => action('refuel');

    document.addEventListener('keydown', (event) => {
        if (event.target.tagName === 'INPUT') return;
        const keys = {
            ' ': () => action('set_speed', { speed: state.clock.speed === 0 ? 1 : 0 }),
            'ArrowUp': () => action('move_rods', { delta: event.shiftKey ? 1 : 0.2 }),
            'ArrowDown': () => action('move_rods', { delta: event.shiftKey ? -1 : -0.2 }),
            'b': () => action('boron', { demand: 1 }),
            'd': () => action('boron', { demand: -1 }),
            'h': () => action('boron', { demand: 0 }),
            'a': () => action('acknowledge', {}),
        };
        if (event.key === 'S' && event.shiftKey) { action('scram'); event.preventDefault(); return; }
        const handler = keys[event.key];
        if (handler) { handler(); event.preventDefault(); }
    });
}

async function poll() {
    try {
        const response = await fetch('/api/state');
        apply(await response.json());
    } catch (error) {
        /* The server may be restarting; the next poll will pick it up. */
    }
    setTimeout(poll, REFRESH_MS);
}

(async function start() {
    wire();
    scenarios = await (await fetch('/api/scenarios')).json();
    poll();
}());
