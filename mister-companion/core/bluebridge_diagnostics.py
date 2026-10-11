import collections
import datetime
import json
import platform
import threading

class BlueBridgeDiagnostics:
    def __init__(self, adapter_id, app):
        self.lock = threading.RLock()
        self.adapter_id = adapter_id
        self.app = app
        self.active = False
        self.started = None
        self.sequence = 0
        self.events = collections.deque(maxlen=1500)
        self.connections = {}
        self.failures = {}
        self.current = None
        self.last_failure = None
        self.error = ""
        self.thread = None
        self.stop = threading.Event()

    def record(self, kind, value):
        with self.lock:
            if not self.active:
                return
            self.sequence += 1
            self.events.append({"sequence": self.sequence, "time": datetime.datetime.now().astimezone().isoformat(timespec="milliseconds"), "adapter": self.adapter_id, "kind": kind, "value": value})

    def snapshot(self, value, selected=False):
        with self.lock:
            key = str(value.get("slot", 0))
            if self.connections.get(key) != value:
                self.record("bluetooth", value)
            self.connections[key] = dict(value)
            if selected:
                self.current = dict(value)
            if value.get("failed_stage") not in (None, "", "none") or value.get("status", -1) > 0:
                if self.failures.get(key) != value:
                    self.failures[key] = dict(value)
                    self.last_failure = dict(value)

    def summary(self):
        with self.lock:
            return {"capturing": self.active, "started": self.started, "event_count": len(self.events), "connections": list(self.connections.values()), "last_failure": self.last_failure, "error": self.error}

    def report(self):
        with self.lock:
            return json.loads(json.dumps({"app": self.app, "host": platform.platform(), "adapter_id": self.adapter_id, "capturing": self.active, "started": self.started, "connections": list(self.connections.values()), "connection_failures": list(self.failures.values()), "current": self.current, "last_failure": self.last_failure, "events": list(self.events), "diagnostic_error": self.error}))

    def start(self, manager):
        with self.lock:
            if self.active:
                return
            if self.thread is not None and self.thread.is_alive():
                raise RuntimeError("Previous capture is stopping; try again shortly")
            self.events.clear()
            self.connections.clear()
            self.failures.clear()
            self.sequence = 0
            self.current = self.last_failure = None
            self.error = ""
            self.started = datetime.datetime.now().astimezone().isoformat(timespec="milliseconds")
            self.stop.clear()
            self.active = True
            self.thread = threading.Thread(target=self._worker, args=(manager,), daemon=True)
            self.thread.start()

    def finish(self):
        with self.lock:
            self.active = False
            self.stop.set()

    def _worker(self, manager):
        while not self.stop.is_set():
            if manager.lock.acquire(blocking=False):
                try:
                    manager.sample_diagnostics()
                    with self.lock:
                        self.error = ""
                except Exception as error:
                    with self.lock:
                        self.error = str(error)
                    self.record("diagnostic_error", str(error))
                finally:
                    manager.lock.release()
            self.stop.wait(2.0)
