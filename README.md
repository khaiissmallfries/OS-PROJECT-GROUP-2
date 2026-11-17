# Aid Station Resource Management - OS Concurrency & Deadlock Avoidance Simulator

**Course:** Operating Systems  
**Project Group:** Group 2  
**Role:** Managing high-traffic zones (Water/Snack Stations & Medic Tents during a Marathon/Running Event)  
**Core OS Concepts:** Concurrency, Mutexes, Counting Semaphores, Condition Variables, & Deadlock Avoidance  

---

## 🎯 Project Overview & Real-World Analogy

In a marathon event, thousands of runners pass through aid stations (Station A, B, and C) demanding shared supplies: **Drinks**, **Snacks**, and **Medications/Gels**.

If multiple runners grab supplies simultaneously or if an operator restocks a station while runners are taking items without synchronization, **race conditions** and **data corruption** occur. If stations attempt to share or borrow supplies from each other haphazardly, **deadlocks** can freeze the entire logistics network.

This simulator models the entire event using native Operating System synchronization primitives:

| Real-World Entity | OS Primitive / Concept | Role in System |
| :--- | :--- | :--- |
| **Runners** | **Consumer Threads** | Request and decrement station supplies concurrently. |
| **Central Vault (The Bank)** | **Counting Semaphores** | Finite global stock; tracks available resources atomically. |
| **Station Inventories (A, B, C)** | **Mutex Locks (`mutex_station_X`)** | Guarantees mutual exclusion so concurrent takes/restocks never collide. |
| **Threshold Alerts** | **Condition Variables (`wait` & `notify`)** | Stations signal Station D when supplies drop below threshold without CPU-wasting busy loops. |
| **Station D (Central Operator)** | **Producer Thread / Central Banker** | Sole authorized entity to allocate vault stock to stations. |
| **Deadlock Prevention** | **Resource Ordering & No Circular Wait** | Strict lock hierarchy ($Vault \rightarrow Station$). Circular wait is mathematically impossible. |

---

## ⚡ How the OS Concepts Are Implemented in Code

### 1. Counting Semaphores (The Central Vault)
- The Central Vault contains the event's master inventory (e.g. 200 drinks, 200 snacks, 100 meds).
- Each resource type is tracked using an OS **Counting Semaphore** (`threading.Semaphore`).
- When Station D withdraws supplies, it decrements the semaphore. If the count reaches 0, the semaphore prevents further allocation, cleanly handling the "Out of Stock" state across the entire event.

### 2. Mutexes (Mutual Exclusion)
- Each Aid Station has its own Mutex: `mutex_station_A`, `mutex_station_B`, `mutex_station_C`.
- When a runner takes an item, the runner thread must acquire that station's Mutex before reading and updating the count.
- When Station D restocks, it also acquires that station's Mutex.
- **Race Condition Proof Mode:** The simulator includes a toggle to disable Mutex protection during a 100-thread runner rush. Without mutexes, concurrent threads read stale values and produce **Lost Updates**, directly proving why Mutexes are essential!

### 3. Condition Variables (Eliminating Busy Waiting)
- In naive systems, Station D would constantly loop (`while True: check_stations()`), burning 100% CPU cycles with **busy waiting**.
- Here, Station D invokes `condition.wait()`. The operating system puts Station D to sleep (0% CPU).
- When any station's stock reaches its low threshold (e.g., drinks $\le 8$), the station invokes `condition.notify()`.
- The OS scheduler immediately wakes Station D, which processes the alert and restocks the station.

### 4. Deadlock Avoidance (The 4 Coffman Conditions)
A deadlock requires all 4 Coffman conditions to hold:
1. **Mutual Exclusion:** Yes (Mutex locks are used).
2. **Hold and Wait:** Prevented (Stations do not hold resources while demanding other stations' resources).
3. **No Preemption:** Yes (Locks are held until transactions finish).
4. **Circular Wait:** **MATHEMATICALLY ELIMINATED.** 
   - Stations A, B, and C never communicate or request resources from each other.
   - Station D acts as a centralized **Banker**.
   - Lock acquisition strictly enforces hierarchy: **1. Vault Mutex $\rightarrow$ 2. Target Station Mutex**.
   - Because $Lock_{Vault} < Lock_{Station}$, circular dependencies ($L_1 \rightarrow L_2 \rightarrow L_1$) are impossible.

---

## 🚀 How to Run the Simulator

### Method 1: 1-Click Launch (Windows)
Double-click the `run.bat` file in this directory. It will automatically detect Python, start the server, and open `http://localhost:5000` in your browser.

### Method 2: Command Line (PowerShell / Terminal)
```powershell
# From this directory:
python app.py 5000
```
Then navigate to: **`http://localhost:5000`** in your web browser.

---

## 📋 Evaluation & Live Demo Walkthrough

When presenting this project to your lecturer or examiner, follow this 4-step demonstration:

### Step 1: Initial Vault & Pre-Event Allocation
1. Open the UI. Show the **Central Vault** with initial supplies (e.g. 200 drinks, 200 snacks, 100 meds).
2. Show that Stations A, B, and C have received their initial allocations before the race starts.
3. Highlight that the Vault's **Counting Semaphores** decreased atomically to reflect the withdrawn stock.

### Step 2: Concurrency & Runner Takes
1. Click **"Take 1 Drink"** at Station A.
2. Observe the **Live OS Execution Trace Console**:
   - `[MUTEX] Acquired mutex_A`
   - `[RUNNER] Took 1x drinks. Remaining: 39`
   - `[MUTEX] Released mutex_A`

### Step 3: Threshold Alert & Condition Variable Wakeup
1. Continue taking items at Station A until drinks drop $\le 8$ (the threshold).
2. Observe the Condition Variable in action:
   - Station A emits `signal(low_stock)`.
   - Station D switches from `SLEEPING (cond.wait)` $\rightarrow$ `WOKEN (Signal Received)`.
   - In **Autonomous Mode**, Station D automatically acquires `mutex_vault`, decrements the Counting Semaphore by 20, acquires `mutex_A`, increments Station A drinks by +20, and releases both locks!
   - In **Manual Mode**, an alert pill appears under Station D allowing the operator to click **"⚡ Restock +20"**.

### Step 4: Peak Traffic Stress Test (Proving Mutex vs Race Condition)
1. Scroll down to the **Concurrency & Race Condition Laboratory**.
2. Set **Concurrent Runners** to **50**.
3. With **"Enable Mutex Locks" CHECKED**:
   - Click **"Launch Peak Runner Rush"**.
   - 50 concurrent threads hit the stations simultaneously.
   - Result: Expected stock reduction matches actual reduction 100% mathematically.
4. Now **UNCHECK "Enable Mutex Locks"**:
   - Click **"Launch Peak Runner Rush"**.
   - Notice that due to lack of synchronization, threads overwrite each other.
   - The banner flags: **"⚠️ RACE CONDITION DEMONSTRATED! Lost updates occurred!"**

---

## 📁 Project Structure

```
OS Project/
├── app.py                # Multi-threaded Python server, REST API & OS engine
├── run.bat               # 1-click launcher for Windows
├── README.md             # Project documentation & grading guide
└── static/
    ├── index.html        # Interactive simulation dashboard layout
    ├── style.css         # Modern dark-theme dashboard UI styling
    └── app.js            # Real-time state polling, animations, stress test logic
```

---

## 👥 Contributors
- **Group 2**: Aid Station Resource Management
- **Core Focus**: Concurrency, Mutexes, Semaphores, & Deadlock Avoidance
