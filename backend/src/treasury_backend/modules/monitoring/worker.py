"""Background polling of durable read-only jobs; never signs or broadcasts."""

import threading


def start_monitor(monitor, interval=5):
    if not 1 <= interval <= 60:
        raise ValueError("Monitor interval must be 1..60 seconds")
    stop = threading.Event()

    def run():
        while not stop.is_set():
            try:
                monitor.tick(limit=5)
            except Exception:
                # Jobs and retry state are durable; provider details are never logged.
                pass
            stop.wait(interval)

    thread = threading.Thread(target=run, name="readonly-outcome-monitor", daemon=True)
    thread.start()
    return stop, thread
