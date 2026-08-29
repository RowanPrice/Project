const shop = document.getElementById('fuel-shop');
const openShop = document.getElementById('open-fuel-shop');
const closeShop = document.getElementById('close-fuel-shop');
const buyAmount = document.getElementById('buy-amount');
const fuelCost = document.getElementById('fuel-cost');
const contractInfoDialog = document.getElementById('contract-info-dialog');
const closeContractInfo = document.getElementById('close-contract-info');
const contractStartForm = document.getElementById('contract-start-form');

if (openShop) openShop.addEventListener('click', () => shop.showModal());
if (closeShop) closeShop.addEventListener('click', () => shop.close());
if (buyAmount) buyAmount.addEventListener('input', () => {
    fuelCost.textContent = (Number(buyAmount.value || 0) * 10).toLocaleString();
});
if (closeContractInfo) closeContractInfo.addEventListener('click', () => contractInfoDialog.close());
document.querySelectorAll('.contract-info-button').forEach((button) => {
    button.addEventListener('click', () => {
        document.getElementById('contract-info-title').textContent = button.dataset.title;
        document.getElementById('contract-info-pay').textContent = button.dataset.pay;
        document.getElementById('contract-info-power').textContent = button.dataset.power;
        document.getElementById('contract-info-time').textContent = button.dataset.time;
        document.getElementById('contract-info-description').textContent = button.dataset.description;
        document.getElementById('contract-info-index').value = button.dataset.contract;
        const startButton = document.getElementById('contract-start-button');
        startButton.disabled = button.dataset.active === 'true';
        startButton.textContent = button.dataset.active === 'true' ? 'Active Contract' : 'Start Contract';
        contractInfoDialog.showModal();
    });
});

if (contractStartForm) contractStartForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    const response = await fetch(contractStartForm.action, {
        method: 'POST',
        body: new FormData(contractStartForm),
        headers: { 'X-Requested-With': 'XMLHttpRequest' }
    });
    if (!response.ok) return;
    const data = await response.json();
    updateMoney(data);
    const startButton = document.getElementById('contract-start-button');
    startButton.disabled = true;
    startButton.textContent = 'Active Contract';
});

document.querySelectorAll('.science-tab').forEach((button) => {
    button.addEventListener('click', () => {
        document.querySelectorAll('.science-tab').forEach((tab) => tab.classList.remove('active'));
        document.querySelectorAll('.science-panel').forEach((panel) => panel.classList.add('hidden'));
        button.classList.add('active');
        document.getElementById(button.dataset.tab).classList.remove('hidden');
    });
});

function updateMoney(data) {
    const money = document.querySelector('.money');
    if (money) money.textContent = `£${Number(data.money).toLocaleString()}`;
}

function updateReactorDisplay(data) {
    if (!data.reactor) return;
    data.reactor.rods.forEach((rod, index) => {
        const bar = document.getElementById(`rod-bar-${index}`);
        if (bar) bar.style.height = `${rod}%`;
    });
    const temperature = document.getElementById('temperature');
    const rodDepth = document.getElementById('rod-depth');
    if (temperature) temperature.textContent = `${data.reactor.temperature}°C`;
    if (rodDepth) rodDepth.textContent = data.reactor.average_rod_depth;
}

async function postWithoutRefresh(form) {
    const response = await fetch(form.action, {
        method: 'POST',
        body: new FormData(form),
        headers: { 'X-Requested-With': 'XMLHttpRequest' }
    });
    if (!response.ok) return;
    const data = await response.json();
    updateMoney(data);
    updateReactorDisplay(data);
    if (data.purchase_succeeded) {
        const row = form.closest('.upgrade-row');
        const button = form.querySelector('button');
        if (button) {
            button.disabled = true;
            button.textContent = 'Purchased';
        }
        if (row) row.classList.add('purchased');
    }
}

document.querySelectorAll('.upgrade-form').forEach((form) => {
    form.addEventListener('submit', (event) => {
        event.preventDefault();
        postWithoutRefresh(form);
    });
});

document.querySelectorAll('.no-refresh-form').forEach((form) => {
    form.addEventListener('submit', async (event) => {
        event.preventDefault();
        const response = await fetch(form.action, {
            method: 'POST',
            body: new FormData(form),
            headers: { 'X-Requested-With': 'XMLHttpRequest' }
        });
        if (response.ok) await refreshState();
    });
});

const skipEnrichment = document.getElementById('skip-enrichment');
if (skipEnrichment) skipEnrichment.addEventListener('click', async () => {
    const response = await fetch('/science/skip-enrichment', {
        method: 'POST',
        headers: { 'X-Requested-With': 'XMLHttpRequest' }
    });
    if (response.ok) await refreshState();
});

const reactorToggleForm = document.getElementById('reactor-toggle-form');
if (reactorToggleForm) reactorToggleForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    const response = await fetch(reactorToggleForm.action, {
        method: 'POST',
        headers: { 'X-Requested-With': 'XMLHttpRequest' }
    });
    if (!response.ok) return;
    const data = await response.json();
    const button = document.getElementById('reactor-toggle');
    const status = document.getElementById('plant-status');
    if (button) button.classList.toggle('on', data.power_plant_on);
    document.querySelectorAll('.rod-select-button, .hold-control').forEach((control) => {
        control.disabled = !data.power_plant_on;
    });
    if (!data.power_plant_on) {
        selectedRods.clear();
        document.querySelectorAll('.rod-select-button').forEach((rodButton) => rodButton.classList.remove('selected'));
        updateRodSelection();
    }
    if (status) {
        status.textContent = data.power_plant_on ? 'ONLINE' : 'OFFLINE';
        status.classList.toggle('offline', !data.power_plant_on);
    }
});

const rodControls = document.getElementById('rod-controls');
const rodSelectionCount = document.getElementById('selected-rod-count');
const selectedRods = new Set();
const rodButtons = document.querySelectorAll('.rod-select-button');

function updateRodSelection() {
    const selected = selectedRods.size;
    if (rodSelectionCount) rodSelectionCount.textContent = selected ? `${selected} rod${selected === 1 ? '' : 's'} selected` : 'Select rods below';
}

rodButtons.forEach((button) => button.addEventListener('click', () => {
    const rod = button.dataset.rod;
    if (selectedRods.has(rod)) {
        selectedRods.delete(rod);
        button.classList.remove('selected');
    } else {
        selectedRods.add(rod);
        button.classList.add('selected');
    }
    updateRodSelection();
}));

async function moveSelectedRods(action) {
    if (!rodControls || selectedRods.size === 0) return;
    const formData = new FormData();
    selectedRods.forEach((rod) => formData.append('rods', rod));
    const response = await fetch(`/reactor/${action}`, {
        method: 'POST',
        body: formData,
        headers: { 'X-Requested-With': 'XMLHttpRequest' }
    });
    if (response.ok) updateReactorDisplay(await response.json());
}

document.querySelectorAll('.hold-control').forEach((button) => {
    let holdTimer;
    const start = (event) => {
        event.preventDefault();
        moveSelectedRods(button.dataset.action);
        holdTimer = setInterval(() => moveSelectedRods(button.dataset.action), 50);
    };
    const stop = () => {
        clearInterval(holdTimer);
        holdTimer = undefined;
    };
    button.addEventListener('pointerdown', start);
    button.addEventListener('pointerup', stop);
    button.addEventListener('pointerleave', stop);
    button.addEventListener('pointercancel', stop);
});

async function refreshState() {
    const response = await fetch('/state');
    if (!response.ok) return;
    const data = await response.json();
    const enrichment = data.science.enrichment;
    const progressValue = document.getElementById('progress-value');
    const progressBar = document.getElementById('progress-bar');
    const timeLeft = document.getElementById('time-left');
    const enrichedFuel = document.getElementById('enriched-fuel');
    const unenrichedFuel = document.getElementById('unenriched-fuel');
    updateMoney(data);
    if (progressValue) progressValue.textContent = `${(enrichment.progress * 100).toFixed(1)}%`;
    if (progressBar) progressBar.style.width = `${enrichment.progress * 100}%`;
    if (timeLeft) timeLeft.textContent = enrichment.in_progress ? `${Math.ceil(enrichment.time_left)} seconds remaining` : 'Ready for a new batch';
    if (enrichedFuel) enrichedFuel.textContent = data.science.enriched_fuel;
    if (unenrichedFuel) unenrichedFuel.textContent = data.science.unenriched_fuel;
    updateReactorDisplay(data);
    const batteryCharge = document.getElementById('battery-charge');
    const batteryFill = document.getElementById('battery-meter-fill');
    const batteryMode = document.getElementById('battery-mode');
    const batteryScreen = document.getElementById('battery-screen');
    if (batteryCharge) batteryCharge.textContent = `${Number(data.battery.charge).toLocaleString(undefined, { maximumFractionDigits: 0 })} W`;
    if (batteryFill) batteryFill.style.width = `${data.battery.capacity ? data.battery.charge / data.battery.capacity * 100 : 0}%`;
    if (batteryMode) batteryMode.textContent = data.battery.mode ? data.battery.mode : 'Idle';
    if (batteryScreen) {
        const image = data.battery.mode ? batteryScreen.dataset.zap : batteryScreen.dataset.noZap;
        batteryScreen.style.setProperty('--battery-image', `url('${image}')`);
    }
}

setInterval(refreshState, 1000);
