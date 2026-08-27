const shop = document.getElementById('fuel-shop');
const openShop = document.getElementById('open-fuel-shop');
const closeShop = document.getElementById('close-fuel-shop');
const buyAmount = document.getElementById('buy-amount');
const fuelCost = document.getElementById('fuel-cost');

if (openShop) openShop.addEventListener('click', () => shop.showModal());
if (closeShop) closeShop.addEventListener('click', () => shop.close());
if (buyAmount) buyAmount.addEventListener('input', () => {
    fuelCost.textContent = (Number(buyAmount.value || 0) * 10).toLocaleString();
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
}

setInterval(refreshState, 1000);
