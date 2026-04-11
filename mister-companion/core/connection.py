import paramiko


class MiSTerConnection:
    def __init__(self):
        self.connected = False
        self.host = ""
        self.username = ""
        self.password = ""
        self.client = None

    def connect(self, host, username, password, use_ssh_agent=False, look_for_ssh_keys=False):
        self.host = host
        self.username = username
        self.password = password

        if not host:
            raise ValueError("IP address is required")

        try:
            if self.client:
                try:
                    self.client.close()
                except Exception:
                    pass

            self.client = paramiko.SSHClient()
            self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            self.client.connect(
                hostname=host,
                username=username,
                password=password,
                timeout=5,
                allow_agent=use_ssh_agent,
                look_for_keys=look_for_ssh_keys,
            )

            transport = self.client.get_transport()
            self.connected = bool(transport and transport.is_active())
            return self.connected

        except Exception:
            self.connected = False
            self.client = None
            return False

    def disconnect(self):
        try:
            if self.client:
                self.client.close()
        except Exception:
            pass

        self.client = None
        self.connected = False
        return True

    def is_connected(self):
        if not self.connected or self.client is None:
            return False

        try:
            transport = self.client.get_transport()
            if transport is None or not transport.is_active():
                self.mark_disconnected()
                return False
        except Exception:
            self.mark_disconnected()
            return False

        return True

    def mark_disconnected(self):
        try:
            if self.client:
                self.client.close()
        except Exception:
            pass

        self.connected = False
        self.client = None

    # =============================
    # COMMAND EXECUTION
    # =============================

    def run_command(self, command):
        if not self.is_connected():
            raise RuntimeError("Not connected")

        try:
            stdin, stdout, stderr = self.client.exec_command(command)

            output = stdout.read().decode("utf-8", errors="ignore").strip()
            error = stderr.read().decode("utf-8", errors="ignore").strip()

            if error and not output:
                return error

            return output

        except Exception:
            self.mark_disconnected()
            raise

    def run_command_stream(self, command, callback):
        if not self.is_connected():
            raise RuntimeError("Not connected")

        try:
            stdin, stdout, stderr = self.client.exec_command(command)

            while True:
                if not self.is_connected():
                    callback("\nConnection closed.\n")
                    return

                line = stdout.readline()
                if not line:
                    break
                callback(line)

            err_output = stderr.read().decode("utf-8", errors="ignore")
            if err_output.strip():
                callback("\n[stderr]\n")
                callback(err_output)

        except Exception:
            self.mark_disconnected()
            callback("\nConnection closed.\n")
            return

    # =============================
    # REBOOT
    # =============================

    def reboot(self):
        if not self.is_connected():
            raise RuntimeError("Not connected")

        self.run_command("nohup /sbin/reboot >/dev/null 2>&1 &")
        self.mark_disconnected()