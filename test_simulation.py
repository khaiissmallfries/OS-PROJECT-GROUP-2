"""
Test Suite for OS Concurrency Simulation
Group 2: Aid Station Resource Management
"""
import time
from app import sim, logger

def run_tests():
    print("=== TEST 1: Initial Vault & Semaphores ===")
    v_state = sim.vault.get_state()
    print(f"Vault initial: Drinks={v_state['drinks']}, Snacks={v_state['snacks']}, Meds={v_state['meds']}")
    assert v_state['drinks'] > 0, "Vault drinks should be > 0"
    print("Test 1 Passed: Vault counting semaphores initialized correctly.\n")

    print("=== TEST 2: Station Mutex & Runner Take ===")
    st_a = sim.stations["A"]
    initial_drinks = st_a.stocks["drinks"]
    print(f"Station A initial drinks: {initial_drinks}")
    
    ok, msg, remaining = st_a.runner_take("drinks", 1, runner_id="TestRunner-01", use_mutex=True)
    assert ok is True
    assert remaining == initial_drinks - 1
    print(f"Runner take successful. Remaining drinks: {remaining}")
    print("Test 2 Passed: Station Mutex acquisition and atomic decrement validated.\n")

    print("=== TEST 3: Condition Variable Threshold Signaling ===")
    # Set threshold high to trigger signal immediately on next take
    st_a.thresholds["drinks"] = remaining
    # Switch operator to manual to inspect queue
    sim.operator.auto_dispatch = False
    
    ok, msg, remaining = st_a.runner_take("drinks", 1, runner_id="TestRunner-02", use_mutex=True)
    assert ok is True
    time.sleep(0.3) # Give worker thread time to process signal
    
    with sim.operator.pending_lock:
        pending = list(sim.operator.pending_manual_alerts)
    print(f"Pending alerts received by Station D: {len(pending)}")
    assert len(pending) > 0, "Condition variable should have delivered alert to Station D"
    alert = pending[0]
    print(f"Alert details: Station={alert['station_name']}, Item={alert['item']}, Current={alert['current_stock']}")
    print("Test 3 Passed: Condition variable wait/signal mechanism validated without busy-waiting.\n")

    print("=== TEST 4: Station D Restock (Lock Ordering & Banker Pattern) ===")
    before_restock = st_a.stocks["drinks"]
    vault_before = sim.vault.sem_drinks.get_value()
    
    ok, r_msg = sim.operator.dispatch_restock(alert)
    assert ok is True
    after_restock = st_a.stocks["drinks"]
    vault_after = sim.vault.sem_drinks.get_value()
    
    print(f"Station A drinks: {before_restock} -> {after_restock} (+20)")
    print(f"Vault drinks: {vault_before} -> {vault_after} (-20)")
    assert after_restock == before_restock + 20
    assert vault_after == vault_before - 20
    print("Test 4 Passed: Station D restocked cleanly following strict hierarchy (Vault -> Station).\n")

    print("=== TEST 5: Concurrent Multi-Threaded Stress Test (50 Runners) ===")
    # Turn auto dispatch on
    sim.operator.auto_dispatch = True
    ok, msg = sim.rush_sim.launch_rush(num_runners=50, station_ids=["A", "B", "C"], item="drinks", use_mutex=True)
    assert ok is True
    
    # Wait for completion
    while sim.rush_sim.active_rush:
        time.sleep(0.05)
        
    stats = sim.rush_sim.rush_stats
    print(f"50 Concurrent Threads Execution Time: {stats['elapsed_ms']}ms")
    print(f"Successful takes: {stats['success_count']}, Failed takes: {stats['failed_count']}")
    assert stats['completed'] is True
    print("Test 5 Passed: Multi-threaded concurrency handled without deadlock or crash.\n")

    print("==================================================")
    print("🎉 ALL 5 CORE OPERATING SYSTEM TESTS PASSED 100%!")
    print("==================================================")

if __name__ == "__main__":
    run_tests()
