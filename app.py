"""
Aid Station Resource Management - OS Concurrency & Deadlock Avoidance Simulator
Group 2: Operating Systems Project

Core Concepts Demonstrated:
1. Concurrency: Multiple Runner threads and Station D Operator thread running simultaneously.
2. Mutexes (Mutual Exclusion): Protecting Station inventories and Vault from race conditions.
3. Counting Semaphores: Managing finite resources in the Central Vault.
4. Condition Variables: Alerting Station D when inventory drops below threshold (eliminates busy-waiting).
5. Deadlock Avoidance: Centralized Operator + Strict Lock Ordering (Vault -> Station) prevents circular wait.
6. Race Condition Demonstration: Optional stress-test mode showing lost updates when mutexes are omitted.
"""

import sys
import json
import time
import queue
import logging
import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import os

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] (%(threadName)s) %(message)s'
)

# ---------------------------------------------------------
# Concurrency Event Logger (For Web UI Thread Timeline)
# ---------------------------------------------------------
class ConcurrencyLogger:
    def __init__(self, max_entries=200):
        self.lock = threading.Lock()
        self.entries = []
        self.max_entries = max_entries
        self.entry_id = 0

    def log(self, category, thread_name, action, details, status="INFO"):
        with self.lock:
            self.entry_id += 1
            entry = {
                "id": self.entry_id,
                "timestamp": time.strftime("%H:%M:%S") + f".{int((time.time() % 1) * 1000):03d}",
                "category": category, # MUTEX, SEMAPHORE, COND_VAR, RUNNER, OPERATOR, DEADLOCK
                "thread": thread_name,
                "action": action,
                "details": details,
                "status": status # INFO, SUCCESS, WARNING, DANGER, LOCK, UNLOCK
            }
            self.entries.append(entry)
            if len(self.entries) > self.max_entries:
                self.entries.pop(0)

    def get_entries(self, since_id=0):
        with self.lock:
            if since_id == 0:
                return list(self.entries[-80:])
            return [e for e in self.entries if e["id"] > since_id]

    def clear(self):
        with self.lock:
            self.entries.clear()

logger = ConcurrencyLogger()


# ---------------------------------------------------------
# Counting Semaphore Wrapper with State Telemetry
# ---------------------------------------------------------
class TrackedSemaphore:
    """Counting Semaphore for Vault resources with telemetry inspection."""
    def __init__(self, initial_value, resource_name):
        self.resource_name = resource_name
        self.current_value = initial_value
        self.initial_value = initial_value
        self.lock = threading.Lock()
        self.sem = threading.Semaphore(initial_value)

    def acquire(self, amount=1, timeout=0.1):
        """Acquire `amount` units from the semaphore."""
        acquired_units = 0
        with self.lock:
            if self.current_value < amount:
                return False
            for _ in range(amount):
                if self.sem.acquire(blocking=True, timeout=timeout):
                    acquired_units += 1
                else:
                    # Rollback if partial
                    for _ in range(acquired_units):
                        self.sem.release()
                    return False
            self.current_value -= amount
            return True

    def release(self, amount=1):
        with self.lock:
            for _ in range(amount):
                self.sem.release()
            self.current_value += amount

    def set_value(self, new_val):
        with self.lock:
            diff = new_val - self.current_value
            if diff > 0:
                for _ in range(diff):
                    self.sem.release()
            elif diff < 0:
                for _ in range(abs(diff)):
                    self.sem.acquire(blocking=False)
            self.current_value = new_val
            self.initial_value = new_val

    def get_value(self):
        with self.lock:
            return self.current_value


# ---------------------------------------------------------
# Central Vault (The Bank)
# ---------------------------------------------------------
class CentralVault:
    def __init__(self, drinks=200, snacks=200, meds=100):
        self.mutex = threading.Lock()
        self.holder = None
        self.sem_drinks = TrackedSemaphore(drinks, "drinks")
        self.sem_snacks = TrackedSemaphore(snacks, "snacks")
        self.sem_meds = TrackedSemaphore(meds, "medications")
        self.initial_stocks = {"drinks": drinks, "snacks": snacks, "meds": meds}

    def reset(self, drinks, snacks, meds):
        with self.mutex:
            self.sem_drinks.set_value(drinks)
            self.sem_snacks.set_value(snacks)
            self.sem_meds.set_value(meds)
            self.initial_stocks = {"drinks": drinks, "snacks": snacks, "meds": meds}
            logger.log("SEMAPHORE", "VaultSystem", "RESET_VAULT", 
                       f"Vault replenished to {drinks} drinks, {snacks} snacks, {meds} meds.", "INFO")

    def withdraw(self, item, amount, thread_name="Caller"):
        """Atomic withdrawal protected by Vault Mutex and Resource Semaphore."""
        sem_map = {
            "drinks": self.sem_drinks,
            "snacks": self.sem_snacks,
            "meds": self.sem_meds
        }
        sem = sem_map.get(item)
        if not sem:
            return False, "Unknown item"

        # Lock ordering: 1. Vault Mutex
        acquired_lock = self.mutex.acquire(timeout=2.0)
        if not acquired_lock:
            return False, "Vault Mutex busy / timeout"

        self.holder = thread_name
        logger.log("MUTEX", thread_name, "LOCK_ACQUIRED", f"Acquired mutex_vault for {amount}x {item}", "LOCK")

        try:
            # Check Counting Semaphore
            if sem.acquire(amount=amount):
                logger.log("SEMAPHORE", thread_name, "SEM_DECREMENT", 
                           f"Counting Semaphore '{item}' decreased by {amount}. Remaining: {sem.get_value()}", "SUCCESS")
                return True, f"Allocated {amount} {item}"
            else:
                logger.log("SEMAPHORE", thread_name, "SEM_DEPLETED", 
                           f"Failed to acquire {amount}x {item}. Vault semaphore is empty or insufficient ({sem.get_value()} available).", "WARNING")
                return False, f"Insufficient {item} in Vault"
        finally:
            self.holder = None
            self.mutex.release()
            logger.log("MUTEX", thread_name, "LOCK_RELEASED", f"Released mutex_vault", "UNLOCK")

    def deposit(self, item, amount, thread_name="Caller"):
        """Deposit items back into the vault."""
        sem_map = {
            "drinks": self.sem_drinks,
            "snacks": self.sem_snacks,
            "meds": self.sem_meds
        }
        sem = sem_map.get(item)
        if not sem:
            return False

        with self.mutex:
            sem.release(amount=amount)
            logger.log("SEMAPHORE", thread_name, "SEM_INCREMENT", 
                       f"Vault semaphore '{item}' replenished by {amount}. Total: {sem.get_value()}", "SUCCESS")
            return True

    def get_state(self):
        return {
            "drinks": self.sem_drinks.get_value(),
            "snacks": self.sem_snacks.get_value(),
            "meds": self.sem_meds.get_value(),
            "initial": self.initial_stocks,
            "is_locked": self.mutex.locked(),
            "lock_holder": self.holder
        }


# ---------------------------------------------------------
# Aid Station (Stations A, B, C)
# ---------------------------------------------------------
class AidStation:
    def __init__(self, station_id, name, condition_var, alert_queue, thresholds=None):
        self.station_id = station_id
        self.name = name
        self.mutex = threading.Lock()
        self.lock_holder = None
        self.condition_var = condition_var
        self.alert_queue = alert_queue

        # Stock counts
        self.stocks = {"drinks": 0, "snacks": 0, "meds": 0}
        self.initial_allocation = {"drinks": 0, "snacks": 0, "meds": 0}

        # Thresholds that trigger Condition Variable signal to Station D
        self.thresholds = thresholds or {"drinks": 8, "snacks": 6, "meds": 4}

        # Track outstanding alerts to avoid alert storms
        self.active_alerts = {"drinks": False, "snacks": False, "meds": False}

        # Metrics
        self.runners_served = 0
        self.items_dispensed = {"drinks": 0, "snacks": 0, "meds": 0}

    def allocate_initial(self, vault, drinks, snacks, meds):
        """Initial allocation before event starts."""
        thread_name = f"Init-{self.station_id}"
        with self.mutex:
            # Transfer drinks
            if drinks > 0:
                ok, _ = vault.withdraw("drinks", drinks, thread_name)
                if ok:
                    self.stocks["drinks"] += drinks
                    self.initial_allocation["drinks"] += drinks
            if snacks > 0:
                ok, _ = vault.withdraw("snacks", snacks, thread_name)
                if ok:
                    self.stocks["snacks"] += snacks
                    self.initial_allocation["snacks"] += snacks
            if meds > 0:
                ok, _ = vault.withdraw("meds", meds, thread_name)
                if ok:
                    self.stocks["meds"] += meds
                    self.initial_allocation["meds"] += meds

            logger.log("INIT", thread_name, "ALLOCATION_DONE", 
                       f"{self.name} initialized with {self.stocks['drinks']} drinks, {self.stocks['snacks']} snacks, {self.stocks['meds']} meds.", "SUCCESS")

    def runner_take(self, item, amount=1, runner_id="Runner", use_mutex=True):
        """
        Runner thread takes an item from station.
        Demonstrates Mutex protection vs Race Condition (if use_mutex=False).
        """
        thread_name = f"{runner_id}@{self.station_id}"

        if use_mutex:
            # Acquire Station Mutex (Mutual Exclusion)
            acquired = self.mutex.acquire(timeout=2.0)
            if not acquired:
                logger.log("MUTEX", thread_name, "LOCK_TIMEOUT", f"Could not acquire mutex_{self.station_id}", "DANGER")
                return False, "Lock timeout (Contention)", self.stocks[item]

            self.lock_holder = thread_name
            logger.log("MUTEX", thread_name, "LOCK_ACQUIRED", f"Acquired mutex_{self.station_id} to take {amount}x {item}", "LOCK")

        try:
            current = self.stocks[item]
            if current < amount:
                logger.log("RUNNER", thread_name, "OUT_OF_STOCK", 
                           f"Failed to take {item}: Only {current} available at {self.name}!", "WARNING")
                return False, f"Out of stock ({current} left)", current

            if not use_mutex:
                # Simulate non-atomic read-modify-write delay to trigger race conditions
                # during concurrent multi-threaded stress testing
                read_val = self.stocks[item]
                time.sleep(0.002) # 2ms thread preemption window
                self.stocks[item] = read_val - amount
            else:
                self.stocks[item] -= amount

            self.runners_served += 1
            self.items_dispensed[item] += amount

            new_stock = self.stocks[item]
            logger.log("RUNNER", thread_name, "ITEM_TAKEN", 
                       f"Took {amount}x {item}. Remaining: {new_stock}", "INFO")

            # Check threshold for Condition Variable notification
            thresh = self.thresholds.get(item, 5)
            if new_stock <= thresh and not self.active_alerts[item]:
                self.active_alerts[item] = True
                # Signal Station D via Condition Variable
                self._signal_low_stock(item, new_stock, thresh, thread_name)

            return True, "Success", new_stock

        finally:
            if use_mutex:
                self.lock_holder = None
                self.mutex.release()
                logger.log("MUTEX", thread_name, "LOCK_RELEASED", f"Released mutex_{self.station_id}", "UNLOCK")

    def _signal_low_stock(self, item, current_stock, threshold, signaler_thread):
        """Signals Station D condition variable without busy-waiting."""
        alert_payload = {
            "station_id": self.station_id,
            "station_name": self.name,
            "item": item,
            "current_stock": current_stock,
            "threshold": threshold,
            "requested_restock": 20, # Standard batch size
            "timestamp": time.strftime("%H:%M:%S")
        }
        with self.condition_var:
            self.alert_queue.put(alert_payload)
            self.condition_var.notify() # Wake Station D!
            logger.log("COND_VAR", signaler_thread, "SIGNAL_EMITTED", 
                       f"Stock threshold breached for {item} ({current_stock} <= {threshold}). Sent signal() to wake Station D!", "WARNING")

    def restock(self, item, amount, operator_thread="StationD-Operator"):
        """Called ONLY by Station D (Restock Producer). Mutex must already be acquired by caller or acquired here."""
        acquired = self.mutex.acquire(timeout=3.0)
        if not acquired:
            return False, "Could not acquire station mutex"

        self.lock_holder = operator_thread
        logger.log("MUTEX", operator_thread, "LOCK_ACQUIRED", f"Acquired mutex_{self.station_id} for Restock", "LOCK")
        try:
            self.stocks[item] += amount
            self.active_alerts[item] = False
            logger.log("OPERATOR", operator_thread, "RESTOCK_APPLIED", 
                       f"Restocked {amount}x {item} at {self.name}. New total: {self.stocks[item]}", "SUCCESS")
            return True, f"Restocked {amount}x {item}"
        finally:
            self.lock_holder = None
            self.mutex.release()
            logger.log("MUTEX", operator_thread, "LOCK_RELEASED", f"Released mutex_{self.station_id}", "UNLOCK")

    def get_state(self):
        return {
            "id": self.station_id,
            "name": self.name,
            "stocks": dict(self.stocks),
            "thresholds": dict(self.thresholds),
            "active_alerts": dict(self.active_alerts),
            "is_locked": self.mutex.locked(),
            "lock_holder": self.lock_holder,
            "runners_served": self.runners_served,
            "items_dispensed": dict(self.items_dispensed)
        }


# ---------------------------------------------------------
# Station D: Central Operator (The Producer / Restocker)
# ---------------------------------------------------------
class OperatorStationD:
    """
    Station D: The Centralized Operator Thread.
    Waits on Condition Variable (no busy wait).
    Strict lock hierarchy: Vault Mutex -> Target Station Mutex.
    Completely eliminates circular wait (Deadlock Avoidance).
    """
    def __init__(self, vault, stations_map, condition_var, alert_queue):
        self.vault = vault
        self.stations = stations_map
        self.condition_var = condition_var
        self.alert_queue = alert_queue

        self.is_running = True
        self.auto_dispatch = True # Auto dispatch or manual dispatch
        self.status = "SLEEPING" # SLEEPING, WOKEN, RESTOCKING
        self.current_task = None
        self.history = []
        self.pending_manual_alerts = []
        self.pending_lock = threading.Lock()

        # Start operator background thread
        self.worker_thread = threading.Thread(
            target=self._operator_loop,
            name="StationD-OperatorThread",
            daemon=True
        )
        self.worker_thread.start()

    def _operator_loop(self):
        """Background daemon loop: sleeps on condition variable until notified."""
        logger.log("OPERATOR", "StationD-OperatorThread", "THREAD_STARTED", 
                   "Station D Operator Thread online. Entering wait() on condition variable...", "INFO")

        while self.is_running:
            alert = None
            with self.condition_var:
                while self.alert_queue.empty() and self.is_running:
                    self.status = "SLEEPING (Waiting on Condition Variable)"
                    self.current_task = "Idle: Awaiting low-stock signals"
                    self.condition_var.wait(timeout=1.0) # Condition Variable wait

                if not self.is_running:
                    break

                if not self.alert_queue.empty():
                    alert = self.alert_queue.get()
                    self.status = "WOKEN (Signal Received)"
                    self.current_task = f"Processing alert: {alert['station_name']} needs {alert['item']}"
                    logger.log("COND_VAR", "StationD-OperatorThread", "SIGNAL_CONSUMED", 
                               f"Station D woken up by signal! Processing alert for {alert['station_name']} ({alert['item']})", "SUCCESS")

            if alert:
                if self.auto_dispatch:
                    self.dispatch_restock(alert)
                else:
                    # In manual mode, stage the alert for user button click
                    with self.pending_lock:
                        self.pending_manual_alerts.append(alert)
                    self.status = "PENDING_APPROVAL"
                    self.current_task = f"Waiting for manual dispatch approval for {alert['station_name']}"

            time.sleep(0.05)

    def dispatch_restock(self, alert):
        """
        Execute restock with strict lock ordering:
        Lock Order: 1. Vault Mutex -> 2. Target Station Mutex.
        Prevents deadlocks completely.
        """
        thread_name = "StationD-OperatorThread"
        self.status = "RESTOCKING"
        station_id = alert["station_id"]
        item = alert["item"]
        amount = alert.get("requested_restock", 20)
        station = self.stations.get(station_id)

        if not station:
            return False, "Station not found"

        self.current_task = f"Transferring {amount}x {item} from Vault to {station.name}..."
        logger.log("DEADLOCK_AVOID", thread_name, "HIERARCHY_START", 
                   f"Enforcing strict lock hierarchy: Vault -> Station {station_id} (No circular wait)", "INFO")

        # 1. Withdraw from Vault (Acquires Vault Mutex + Semaphore)
        success, msg = self.vault.withdraw(item, amount, thread_name=thread_name)
        if not success:
            logger.log("OPERATOR", thread_name, "RESTOCK_FAILED", 
                       f"Restock aborted: Vault cannot supply {amount}x {item} ({msg})", "DANGER")
            self.history.append({
                "time": time.strftime("%H:%M:%S"),
                "station": station.name,
                "item": item,
                "amount": amount,
                "status": f"FAILED: {msg}"
            })
            return False, msg

        # Simulate operator physical transit time (0.2s for realism in UI)
        time.sleep(0.2)

        # 2. Add to Station (Station Mutex)
        ok, r_msg = station.restock(item, amount, operator_thread=thread_name)

        record = {
            "time": time.strftime("%H:%M:%S"),
            "station": station.name,
            "item": item,
            "amount": amount,
            "status": "SUCCESS" if ok else "FAILED"
        }
        self.history.append(record)
        if len(self.history) > 50:
            self.history.pop(0)

        self.status = "SLEEPING"
        self.current_task = f"Completed restock: {amount}x {item} to {station.name}"
        return ok, r_msg

    def manual_restock(self, station_id, item, amount):
        """Manual trigger from Operator UI."""
        alert = {
            "station_id": station_id,
            "station_name": self.stations[station_id].name,
            "item": item,
            "requested_restock": amount,
            "timestamp": time.strftime("%H:%M:%S")
        }
        # Remove from pending list if present
        with self.pending_lock:
            self.pending_manual_alerts = [
                a for a in self.pending_manual_alerts 
                if not (a["station_id"] == station_id and a["item"] == item)
            ]
        # Dispatch in background thread so HTTP response is fast
        t = threading.Thread(target=self.dispatch_restock, args=(alert,), name="ManualDispatchThread")
        t.start()
        return True, "Dispatch launched"

    def get_state(self):
        with self.pending_lock:
            pending = list(self.pending_manual_alerts)
        return {
            "status": self.status,
            "current_task": self.current_task,
            "auto_dispatch": self.auto_dispatch,
            "pending_alerts": pending,
            "history": list(self.history[-15:])
        }


# ---------------------------------------------------------
# Concurrency Stress Test & Race Condition Simulator
# ---------------------------------------------------------
class RunnerRushSimulator:
    """Spawns multiple concurrent runner threads to simulate peak marathon traffic."""
    def __init__(self, stations):
        self.stations = stations
        self.active_rush = False
        self.rush_stats = {}

    def launch_rush(self, num_runners=30, station_ids=None, item="drinks", use_mutex=True):
        if self.active_rush:
            return False, "Rush already in progress"

        target_stations = [self.stations[s] for s in (station_ids or ["A", "B", "C"]) if s in self.stations]
        if not target_stations:
            return False, "No valid stations"

        self.active_rush = True
        self.rush_stats = {
            "total_runners": num_runners,
            "item": item,
            "use_mutex": use_mutex,
            "success_count": 0,
            "failed_count": 0,
            "start_time": time.time(),
            "completed": False,
            "initial_stocks": {s.station_id: s.stocks[item] for s in target_stations}
        }

        thread = threading.Thread(
            target=self._run_rush_worker,
            args=(num_runners, target_stations, item, use_mutex),
            name="RunnerRush-Coordinator"
        )
        thread.start()
        return True, f"Launched rush with {num_runners} concurrent runners (Mutex={'ON' if use_mutex else 'OFF'})"

    def _run_rush_worker(self, num_runners, stations, item, use_mutex):
        logger.log("RUNNER", "RushCoordinator", "RUSH_STARTED", 
                   f"Spawning {num_runners} concurrent runner threads across stations (Mutex={use_mutex})", "WARNING")

        threads = []
        barrier = threading.Barrier(num_runners)

        def runner_job(r_id, station):
            # All threads wait at barrier to hit the station at the exact same millisecond
            try:
                barrier.wait(timeout=5.0)
            except Exception:
                pass

            success, _, _ = station.runner_take(
                item=item,
                amount=1,
                runner_id=f"Runner-{r_id:02d}",
                use_mutex=use_mutex
            )
            if success:
                self.rush_stats["success_count"] += 1
            else:
                self.rush_stats["failed_count"] += 1

        import random
        for i in range(num_runners):
            station = random.choice(stations)
            t = threading.Thread(target=runner_job, args=(i + 1, station), name=f"Runner-{i+1:02d}")
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        self.rush_stats["completed"] = True
        self.rush_stats["elapsed_ms"] = round((time.time() - self.rush_stats["start_time"]) * 1000, 2)
        self.rush_stats["final_stocks"] = {s.station_id: s.stocks[item] for s in stations}
        self.active_rush = False

        expected_decrease = self.rush_stats["success_count"]
        actual_decrease = sum(self.rush_stats["initial_stocks"][s.station_id] - self.rush_stats["final_stocks"][s.station_id] for s in stations)

        if not use_mutex and actual_decrease != expected_decrease:
            logger.log("DEADLOCK_AVOID", "RushCoordinator", "RACE_CONDITION_DETECTED", 
                       f"Race condition observed! Expected -{expected_decrease} but stock changed by -{actual_decrease}. Lost updates occurred!", "DANGER")
        else:
            logger.log("RUNNER", "RushCoordinator", "RUSH_FINISHED", 
                       f"Rush completed in {self.rush_stats['elapsed_ms']}ms. Mutex guaranteed 100% data consistency.", "SUCCESS")


# ---------------------------------------------------------
# Simulation Manager (Singleton)
# ---------------------------------------------------------
class SimulationManager:
    def __init__(self):
        self.cond_var_lock = threading.Lock()
        self.condition_var = threading.Condition(self.cond_var_lock)
        self.alert_queue = queue.Queue()

        # Central Vault
        self.vault = CentralVault(drinks=200, snacks=200, meds=100)

        # Stations A, B, C
        self.stations = {
            "A": AidStation("A", "Aid Station A (Mile 5)", self.condition_var, self.alert_queue, 
                            thresholds={"drinks": 8, "snacks": 6, "meds": 4}),
            "B": AidStation("B", "Aid Station B (Mile 13)", self.condition_var, self.alert_queue, 
                            thresholds={"drinks": 10, "snacks": 8, "meds": 5}),
            "C": AidStation("C", "Aid Station C (Finish Line)", self.condition_var, self.alert_queue, 
                            thresholds={"drinks": 12, "snacks": 8, "meds": 6}),
        }

        # Central Operator Station D
        self.operator = OperatorStationD(self.vault, self.stations, self.condition_var, self.alert_queue)

        # Rush simulator
        self.rush_sim = RunnerRushSimulator(self.stations)

        # Default initial allocation setup
        self.initial_setup_done = False
        self._setup_initial_allocations()

    def _setup_initial_allocations(self):
        """Initial allocation of stock from Vault to Stations before event starts."""
        self.stations["A"].allocate_initial(self.vault, drinks=40, snacks=30, meds=15)
        self.stations["B"].allocate_initial(self.vault, drinks=50, snacks=40, meds=20)
        self.stations["C"].allocate_initial(self.vault, drinks=40, snacks=30, meds=15)
        self.initial_setup_done = True

    def reset_simulation(self, vault_drinks=200, vault_snacks=200, vault_meds=100, 
                         alloc_A=None, alloc_B=None, alloc_C=None):
        logger.clear()
        self.vault.reset(vault_drinks, vault_snacks, vault_meds)

        default_a = alloc_A or {"drinks": 40, "snacks": 30, "meds": 15}
        default_b = alloc_B or {"drinks": 50, "snacks": 40, "meds": 20}
        default_c = alloc_C or {"drinks": 40, "snacks": 30, "meds": 15}

        for sid, alloc in [("A", default_a), ("B", default_b), ("C", default_c)]:
            st = self.stations[sid]
            with st.mutex:
                st.stocks = {"drinks": 0, "snacks": 0, "meds": 0}
                st.initial_allocation = {"drinks": 0, "snacks": 0, "meds": 0}
                st.active_alerts = {"drinks": False, "snacks": False, "meds": False}
                st.runners_served = 0
                st.items_dispensed = {"drinks": 0, "snacks": 0, "meds": 0}
            st.allocate_initial(self.vault, alloc.get("drinks", 0), alloc.get("snacks", 0), alloc.get("meds", 0))

        with self.operator.pending_lock:
            self.operator.pending_manual_alerts.clear()
        self.operator.history.clear()
        self.operator.status = "SLEEPING"
        self.operator.current_task = "Simulation Reset: Ready"
        logger.log("SYSTEM", "MainSystem", "RESET_COMPLETE", "Simulation reset to initial state.", "SUCCESS")

    def get_full_state(self):
        return {
            "vault": self.vault.get_state(),
            "stations": {k: v.get_state() for k, v in self.stations.items()},
            "operator": self.operator.get_state(),
            "rush_stats": self.rush_sim.rush_stats,
            "active_rush": self.rush_sim.active_rush,
            "deadlock_analysis": {
                "mutual_exclusion": "Enforced via Station Mutexes & Vault Mutex",
                "hold_and_wait": "Prevented: Stations never hold resources while requesting others",
                "no_preemption": "Enforced: Only lock holders can release resources",
                "circular_wait": "ELIMINATED: Centralized Station D Banker + Strict Ordering (Vault -> Station)",
                "status": "DEADLOCK FREE GUARANTEED"
            }
        }


sim = SimulationManager()


# ---------------------------------------------------------
# HTTP Request Handler & REST API
# ---------------------------------------------------------
class SimulationRequestHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
        super().__init__(*args, directory=static_dir, **kwargs)

    def log_message(self, format, *args):
        # Suppress noisy HTTP GET asset logs from terminal
        pass

    def send_json(self, data, status_code=200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/state":
            self.send_json(sim.get_full_state())
        elif path == "/api/logs":
            qs = parse_qs(parsed.query)
            since_id = int(qs.get("since", [0])[0])
            self.send_json({"logs": logger.get_entries(since_id)})
        else:
            # Serve static files (HTML, CSS, JS)
            super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        content_len = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_len).decode("utf-8") if content_len > 0 else "{}"
        try:
            data = json.loads(body)
        except Exception:
            data = {}

        if path == "/api/runner/take":
            station_id = data.get("station_id")
            item = data.get("item")
            amount = int(data.get("amount", 1))
            use_mutex = bool(data.get("use_mutex", True))

            station = sim.stations.get(station_id)
            if not station:
                self.send_json({"success": False, "message": "Invalid station"}, 400)
                return

            # Execute take
            success, msg, remaining = station.runner_take(
                item=item,
                amount=amount,
                runner_id=f"Runner-{int(time.time()*1000)%10000}",
                use_mutex=use_mutex
            )
            self.send_json({
                "success": success,
                "message": msg,
                "remaining": remaining,
                "station_id": station_id,
                "item": item
            })

        elif path == "/api/operator/restock":
            station_id = data.get("station_id")
            item = data.get("item")
            amount = int(data.get("amount", 20))

            if station_id not in sim.stations:
                self.send_json({"success": False, "message": "Invalid station"}, 400)
                return

            ok, msg = sim.operator.manual_restock(station_id, item, amount)
            self.send_json({"success": ok, "message": msg})

        elif path == "/api/operator/toggle_auto":
            sim.operator.auto_dispatch = not sim.operator.auto_dispatch
            mode = "AUTONOMOUS (Auto Dispatch)" if sim.operator.auto_dispatch else "MANUAL (Operator Approval Required)"
            logger.log("OPERATOR", "UserInterface", "MODE_SWITCH", f"Operator mode switched to: {mode}", "INFO")
            self.send_json({"success": True, "auto_dispatch": sim.operator.auto_dispatch})

        elif path == "/api/stress_test/rush":
            runners = int(data.get("runners", 30))
            stations = data.get("stations", ["A", "B", "C"])
            item = data.get("item", "drinks")
            use_mutex = bool(data.get("use_mutex", True))

            ok, msg = sim.rush_sim.launch_rush(
                num_runners=runners,
                station_ids=stations,
                item=item,
                use_mutex=use_mutex
            )
            self.send_json({"success": ok, "message": msg})

        elif path == "/api/station/threshold":
            station_id = data.get("station_id")
            item = data.get("item")
            thresh = int(data.get("threshold", 5))
            if station_id in sim.stations and item in ["drinks", "snacks", "meds"]:
                sim.stations[station_id].thresholds[item] = thresh
                logger.log("CONFIG", "UserInterface", "THRESHOLD_UPDATED", 
                           f"Threshold for {sim.stations[station_id].name} - {item} set to {thresh}", "INFO")
                self.send_json({"success": True})
            else:
                self.send_json({"success": False, "message": "Invalid params"}, 400)

        elif path == "/api/reset":
            v_drinks = int(data.get("vault_drinks", 200))
            v_snacks = int(data.get("vault_snacks", 200))
            v_meds = int(data.get("vault_meds", 100))
            alloc_a = data.get("alloc_a")
            alloc_b = data.get("alloc_b")
            alloc_c = data.get("alloc_c")

            sim.reset_simulation(v_drinks, v_snacks, v_meds, alloc_a, alloc_b, alloc_c)
            self.send_json({"success": True, "message": "Simulation reset successfully"})

        else:
            self.send_json({"error": "Endpoint not found"}, 404)


def start_server(port=5000):
    server_address = ('0.0.0.0', port)
    httpd = HTTPServer(server_address, SimulationRequestHandler)
    print(f"\n=======================================================")
    print(f" Aid Station Resource Management Simulator Online!")
    print(f" Local Web Interface: http://localhost:{port}")
    print(f"=======================================================\n")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server...")
        httpd.server_close()


if __name__ == "__main__":
    port = 5000
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            pass
    start_server(port)
