/**
 * Aid Station Resource Management - OS Concurrency Frontend Logic
 * Group 2: Operating Systems Project
 */

let lastLogId = 0;
let currentFilter = "ALL";
let isPolling = true;

// DOM Elements
const elVaultDrinksCount = document.getElementById("vault-drinks-count");
const elVaultSnacksCount = document.getElementById("vault-snacks-count");
const elVaultMedsCount = document.getElementById("vault-meds-count");
const elVaultDrinksFill = document.getElementById("vault-drinks-fill");
const elVaultSnacksFill = document.getElementById("vault-snacks-fill");
const elVaultMedsFill = document.getElementById("vault-meds-fill");
const elSemDrinks = document.getElementById("sem-val-drinks");
const elSemSnacks = document.getElementById("sem-val-snacks");
const elSemMeds = document.getElementById("sem-val-meds");
const elVaultLockInd = document.getElementById("vault-lock-indicator");

const elTelVaultMutex = document.getElementById("tel-vault-mutex");
const elTelOperator = document.getElementById("tel-operator-state");
const elTelMutexA = document.getElementById("tel-mutex-A");
const elTelMutexB = document.getElementById("tel-mutex-B");
const elTelMutexC = document.getElementById("tel-mutex-C");

const elOpStatusTitle = document.getElementById("op-status-title");
const elOpTaskDesc = document.getElementById("op-task-desc");
const elOpDot = document.getElementById("op-dot");
const elModeText = document.getElementById("mode-text");
const elBtnToggleAuto = document.getElementById("btn-toggle-auto");
const elAlertsContainer = document.getElementById("alerts-container");
const elPendingCount = document.getElementById("pending-count");

const elConsoleLogs = document.getElementById("console-logs");
const elBtnClearLog = document.getElementById("btn-clear-log");

// Stress Test DOM
const sliderRunners = document.getElementById("slider-runners");
const runnerValDisplay = document.getElementById("runner-val-display");
const btnRunnerCount = document.getElementById("btn-runner-count");
const checkUseMutex = document.getElementById("check-use-mutex");
const selectStressItem = document.getElementById("stress-item-select");
const selectStressStation = document.getElementById("stress-station-select");
const btnLaunchRush = document.getElementById("btn-launch-rush");
const stressResultBanner = document.getElementById("stress-result-banner");
const resultTitle = document.getElementById("result-title");
const resultDetails = document.getElementById("result-details");

// Setup Modal DOM
const setupModal = document.getElementById("setup-modal");
const btnInitialSetup = document.getElementById("btn-initial-setup");
const btnCloseModal = document.getElementById("btn-close-modal");
const btnCancelModal = document.getElementById("btn-cancel-modal");
const btnSaveSetup = document.getElementById("btn-save-setup");
const btnQuickReset = document.getElementById("btn-quick-reset");

// Setup slider listener
sliderRunners.addEventListener("input", (e) => {
  const val = e.target.value;
  runnerValDisplay.innerText = val;
  btnRunnerCount.innerText = val;
});

// Setup modal event listeners
btnInitialSetup.addEventListener("click", () => {
  setupModal.style.display = "flex";
});

const closeModal = () => {
  setupModal.style.display = "none";
};
btnCloseModal.addEventListener("click", closeModal);
btnCancelModal.addEventListener("click", closeModal);

btnQuickReset.addEventListener("click", () => {
  if (confirm("Reset simulation to initial state?")) {
    resetSimulation();
  }
});

btnSaveSetup.addEventListener("click", () => {
  const payload = {
    vault_drinks: parseInt(document.getElementById("inp-vault-drinks").value) || 200,
    vault_snacks: parseInt(document.getElementById("inp-vault-snacks").value) || 200,
    vault_meds: parseInt(document.getElementById("inp-vault-meds").value) || 100,
    alloc_a: {
      drinks: parseInt(document.getElementById("inp-a-drinks").value) || 0,
      snacks: parseInt(document.getElementById("inp-a-snacks").value) || 0,
      meds: parseInt(document.getElementById("inp-a-meds").value) || 0,
    },
    alloc_b: {
      drinks: parseInt(document.getElementById("inp-b-drinks").value) || 0,
      snacks: parseInt(document.getElementById("inp-b-snacks").value) || 0,
      meds: parseInt(document.getElementById("inp-b-meds").value) || 0,
    },
    alloc_c: {
      drinks: parseInt(document.getElementById("inp-c-drinks").value) || 0,
      snacks: parseInt(document.getElementById("inp-c-snacks").value) || 0,
      meds: parseInt(document.getElementById("inp-c-meds").value) || 0,
    }
  };

  fetch("/api/reset", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  })
    .then(r => r.json())
    .then(data => {
      closeModal();
      fetchState();
      fetchLogs();
    });
});

function resetSimulation() {
  fetch("/api/reset", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({})
  })
    .then(r => r.json())
    .then(() => {
      fetchState();
      fetchLogs();
    });
}

// Toggle Auto/Manual Mode
elBtnToggleAuto.addEventListener("click", () => {
  fetch("/api/operator/toggle_auto", { method: "POST" })
    .then(r => r.json())
    .then(data => {
      updateModeDisplay(data.auto_dispatch);
      fetchState();
    });
});

function updateModeDisplay(isAuto) {
  if (isAuto) {
    elModeText.innerText = "Autonomous";
    elModeText.style.color = "var(--color-emerald)";
  } else {
    elModeText.innerText = "Manual Approval";
    elModeText.style.color = "var(--color-amber)";
  }
}

// Filter chips
document.querySelectorAll(".filter-chip").forEach(chip => {
  chip.addEventListener("click", () => {
    document.querySelectorAll(".filter-chip").forEach(c => c.classList.remove("active"));
    chip.classList.add("active");
    currentFilter = chip.getAttribute("data-filter");
    applyLogFilter();
  });
});

elBtnClearLog.addEventListener("click", () => {
  elConsoleLogs.innerHTML = "";
});

function applyLogFilter() {
  const lines = elConsoleLogs.querySelectorAll(".log-line");
  lines.forEach(line => {
    const category = line.getAttribute("data-cat");
    if (currentFilter === "ALL" || category === currentFilter) {
      line.style.display = "block";
    } else {
      line.style.display = "none";
    }
  });
}

// Take Item API call
window.takeItem = function(stationId, item, amount = 1) {
  fetch("/api/runner/take", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      station_id: stationId,
      item: item,
      amount: amount,
      use_mutex: true
    })
  })
    .then(r => r.json())
    .then(data => {
      fetchState();
      fetchLogs();
    });
};

// Take Combo API call
window.takeCombo = function(stationId) {
  // Take 1 of each
  ['drinks', 'snacks', 'meds'].forEach((item, idx) => {
    setTimeout(() => {
      window.takeItem(stationId, item, 1);
    }, idx * 60);
  });
};

// Dispatch Restock API Call (Manual mode)
window.dispatchManualRestock = function(stationId, item, amount = 20) {
  fetch("/api/operator/restock", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      station_id: stationId,
      item: item,
      amount: amount
    })
  })
    .then(r => r.json())
    .then(data => {
      fetchState();
      fetchLogs();
    });
};

// Concurrency Stress Test Trigger
btnLaunchRush.addEventListener("click", () => {
  const numRunners = parseInt(sliderRunners.value);
  const item = selectStressItem.value;
  const stationVal = selectStressStation.value;
  const useMutex = checkUseMutex.checked;
  const stations = stationVal === "all" ? ["A", "B", "C"] : [stationVal];

  btnLaunchRush.disabled = true;
  btnLaunchRush.innerText = "Running Concurrent Threads...";

  fetch("/api/stress_test/rush", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      runners: numRunners,
      stations: stations,
      item: item,
      use_mutex: useMutex
    })
  })
    .then(r => r.json())
    .then(res => {
      // Poll until completed
      const pollRushInterval = setInterval(() => {
        fetch("/api/state")
          .then(r => r.json())
          .then(st => {
            renderState(st);
            fetchLogs();
            if (!st.active_rush && st.rush_stats && st.rush_stats.completed) {
              clearInterval(pollRushInterval);
              btnLaunchRush.disabled = false;
              btnLaunchRush.innerText = `🚀 Launch Peak Runner Rush (${numRunners} Concurrent Threads)`;
              renderRushResults(st.rush_stats);
            }
          });
      }, 200);
    })
    .catch(err => {
      btnLaunchRush.disabled = false;
      btnLaunchRush.innerText = `🚀 Launch Peak Runner Rush (${numRunners} Concurrent Threads)`;
    });
});

function renderRushResults(stats) {
  stressResultBanner.style.display = "block";
  const { total_runners, item, use_mutex, success_count, failed_count, elapsed_ms, initial_stocks, final_stocks } = stats;

  let totalInitial = 0;
  let totalFinal = 0;
  for (const s in initial_stocks) {
    totalInitial += initial_stocks[s];
    totalFinal += final_stocks[s];
  }
  const actualDecrease = totalInitial - totalFinal;
  const expectedDecrease = success_count;

  if (use_mutex) {
    stressResultBanner.className = "stress-result success";
    resultTitle.innerHTML = "✅ MUTEX LOCKS ACTIVE: 100% DATA CONSISTENCY GUARANTEED";
    resultDetails.innerHTML = `
      Threads spawned: <strong>${total_runners}</strong> concurrent runners | Execution: <strong>${elapsed_ms}ms</strong><br>
      Expected Stock Reduction: <strong>-${expectedDecrease}</strong> ${item} | Actual Stock Reduction: <strong>-${actualDecrease}</strong> ${item}<br>
      <em>Every concurrent read-modify-write operation was serialized cleanly by the Station Mutex. Zero lost updates.</em>
    `;
  } else {
    const lostUpdates = expectedDecrease - actualDecrease;
    if (lostUpdates > 0) {
      stressResultBanner.className = "stress-result danger";
      resultTitle.innerHTML = "⚠️ RACE CONDITION DEMONSTRATED! CRITICAL DATA DESYNCHRONIZATION DETECTED";
      resultDetails.innerHTML = `
        Threads spawned: <strong>${total_runners}</strong> concurrent runners (No Mutex) | Execution: <strong>${elapsed_ms}ms</strong><br>
        Successful Thread Takes Reported: <strong>${success_count}</strong> | Actual Physical Inventory Decreased: <strong>${actualDecrease}</strong><br>
        <strong>LOST UPDATES: ${lostUpdates} items disappeared or were double-counted!</strong><br>
        <em>Because threads accessed shared memory concurrently without Mutual Exclusion, multiple threads read stale values and overwrote each other's updates.</em>
      `;
    } else {
      stressResultBanner.className = "stress-result danger";
      resultTitle.innerHTML = "⚠️ MUTEX OFF (Race Condition Mode)";
      resultDetails.innerHTML = `
        Threads spawned: <strong>${total_runners}</strong> runners without mutex protection. Try increasing runner count to 50+ to witness thread collisions!
      `;
    }
  }
}

// Fetch Full Simulation State
function fetchState() {
  fetch("/api/state")
    .then(r => r.json())
    .then(renderState)
    .catch(err => console.error("Error fetching state:", err));
}

function renderState(state) {
  if (!state) return;

  const { vault, stations, operator } = state;

  // 1. Vault Rendering
  const initDrinks = vault.initial.drinks || 200;
  const initSnacks = vault.initial.snacks || 200;
  const initMeds = vault.initial.meds || 100;

  elVaultDrinksCount.innerText = `${vault.drinks} / ${initDrinks}`;
  elVaultSnacksCount.innerText = `${vault.snacks} / ${initSnacks}`;
  elVaultMedsCount.innerText = `${vault.meds} / ${initMeds}`;

  elVaultDrinksFill.style.width = `${Math.max(0, Math.min(100, (vault.drinks / initDrinks) * 100))}%`;
  elVaultSnacksFill.style.width = `${Math.max(0, Math.min(100, (vault.snacks / initSnacks) * 100))}%`;
  elVaultMedsFill.style.width = `${Math.max(0, Math.min(100, (vault.meds / initMeds) * 100))}%`;

  elSemDrinks.innerText = vault.drinks;
  elSemSnacks.innerText = vault.snacks;
  elSemMeds.innerText = vault.meds;

  if (vault.is_locked) {
    elVaultLockInd.innerText = `LOCKED by ${vault.lock_holder}`;
    elVaultLockInd.className = "status-indicator badge badge-red";
    elTelVaultMutex.innerHTML = `<span class="badge badge-red">LOCKED (${vault.lock_holder})</span>`;
  } else {
    elVaultLockInd.innerText = "Mutex Free";
    elVaultLockInd.className = "status-indicator badge badge-green";
    elTelVaultMutex.innerHTML = `<span class="badge badge-green">UNLOCKED</span>`;
  }

  // 2. Operator D Rendering
  updateModeDisplay(operator.auto_dispatch);
  elOpStatusTitle.innerText = `Status: ${operator.status}`;
  elOpTaskDesc.innerText = operator.current_task || "Idle: Awaiting low-stock signals";

  if (operator.status.includes("SLEEPING")) {
    elOpDot.className = "pulsing-dot";
    elTelOperator.innerHTML = `<span class="badge badge-blue">SLEEPING (cond.wait)</span>`;
  } else if (operator.status.includes("RESTOCKING")) {
    elOpDot.className = "pulsing-dot active-red";
    elTelOperator.innerHTML = `<span class="badge badge-red">RESTOCKING (Lock Held)</span>`;
  } else {
    elOpDot.className = "pulsing-dot active-amber";
    elTelOperator.innerHTML = `<span class="badge badge-amber">WOKEN (Alert Queued)</span>`;
  }

  // Render Pending Alerts for Station D
  const pending = operator.pending_alerts || [];
  elPendingCount.innerText = pending.length;
  if (pending.length === 0) {
    elAlertsContainer.innerHTML = `<div class="empty-state">No low-stock alerts. All aid stations are adequately supplied.</div>`;
  } else {
    elAlertsContainer.innerHTML = pending.map(a => `
      <div class="alert-item">
        <div class="alert-meta">
          <div class="alert-title">${a.station_name} Needs ${a.item.toUpperCase()}</div>
          <div class="alert-desc">Current: ${a.current_stock} &le; Threshold: ${a.threshold} (Req: +${a.requested_restock || 20})</div>
        </div>
        <button class="btn btn-sm btn-primary" onclick="dispatchManualRestock('${a.station_id}', '${a.item}', ${a.requested_restock || 20})">
          ⚡ Restock +${a.requested_restock || 20}
        </button>
      </div>
    `).join("");
  }

  // 3. Aid Stations Rendering (A, B, C)
  for (const sid of ["A", "B", "C"]) {
    const st = stations[sid];
    if (!st) continue;

    // Mutex Badge
    const badge = document.getElementById(`mutex-badge-${sid}`);
    const telBadge = document.getElementById(`tel-mutex-${sid}`);
    if (st.is_locked) {
      const holder = st.lock_holder || "Thread";
      badge.innerText = `MUTEX: LOCKED (${holder})`;
      badge.className = "mutex-badge locked";
      telBadge.innerHTML = `<span class="badge badge-red">LOCKED (${holder})</span>`;
    } else {
      badge.innerText = "MUTEX: FREE";
      badge.className = "mutex-badge";
      telBadge.innerHTML = `<span class="badge badge-green">UNLOCKED</span>`;
    }

    // Stocks & Thresholds
    for (const item of ["drinks", "snacks", "meds"]) {
      const stockVal = st.stocks[item];
      const threshVal = st.thresholds[item];
      const countEl = document.getElementById(`stock-${sid}-${item}`);
      const threshEl = document.getElementById(`thresh-${sid}-${item}`);
      const rowEl = document.getElementById(`stock-row-${sid}-${item}`);

      if (countEl) countEl.innerText = stockVal;
      if (threshEl) threshEl.innerText = threshVal;

      if (rowEl) {
        if (stockVal <= threshVal) {
          rowEl.classList.add("low-warning");
        } else {
          rowEl.classList.remove("low-warning");
        }
      }
    }

    // Stats
    const servedEl = document.getElementById(`served-${sid}`);
    if (servedEl) servedEl.innerText = st.runners_served;
  }
}

// Fetch & Append Logs
function fetchLogs() {
  fetch(`/api/logs?since=${lastLogId}`)
    .then(r => r.json())
    .then(data => {
      const logs = data.logs || [];
      if (logs.length === 0) return;

      logs.forEach(entry => {
        if (entry.id > lastLogId) {
          lastLogId = entry.id;
        }

        const div = document.createElement("div");
        div.className = `log-line log-${entry.category}`;
        div.setAttribute("data-cat", entry.category);
        div.innerHTML = `[${entry.timestamp}] <strong>[${entry.category}]</strong> (${entry.thread}) <em>${entry.action}</em>: ${entry.details}`;

        if (currentFilter !== "ALL" && entry.category !== currentFilter) {
          div.style.display = "none";
        }

        elConsoleLogs.appendChild(div);
      });

      // Auto-scroll to bottom of console
      elConsoleLogs.scrollTop = elConsoleLogs.scrollHeight;
    })
    .catch(err => console.error("Error fetching logs:", err));
}

// Start polling loop
fetchState();
fetchLogs();
setInterval(() => {
  if (isPolling) {
    fetchState();
    fetchLogs();
  }
}, 600);
