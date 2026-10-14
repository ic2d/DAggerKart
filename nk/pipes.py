"""Named pipes do Windows (só stdlib) para conversar com lua/agent.lua.

Dois pipes de bytes por emulador:
  \\\\.\\pipe\\<nome>_req   Python -> Lua (comandos)
  \\\\.\\pipe\\<nome>_resp  Lua -> Python (respostas)
"""
import _winapi
import msvcrt
import os
import threading

PIPE_ACCESS_OUTBOUND = 0x00000002
PIPE_TYPE_BYTE = 0x00000000
PIPE_READMODE_BYTE = 0x00000000
BUFFER_SIZE = 64 * 1024


def _create(path, access):
    return _winapi.CreateNamedPipe(path, access, PIPE_TYPE_BYTE | PIPE_READMODE_BYTE | _winapi.PIPE_WAIT,
                                   1, BUFFER_SIZE, BUFFER_SIZE, 0, _winapi.NULL)


def _connect(handle):
    try:
        _winapi.ConnectNamedPipe(handle, False)
    except OSError as e:
        if e.winerror != _winapi.ERROR_PIPE_CONNECTED:  # cliente conectou antes: tudo bem
            raise


class PipeServer:
    """Cria os pipes já no construtor (antes de abrir o emulador) e espera o Lua conectar."""

    def __init__(self, name):
        self.name = name
        self._req = _create(r"\\.\pipe\{}_req".format(name), PIPE_ACCESS_OUTBOUND)
        self._resp = _create(r"\\.\pipe\{}_resp".format(name), _winapi.PIPE_ACCESS_INBOUND)
        self.writer = self.reader = None

    def accept(self, timeout):
        """Espera o Lua abrir os dois pipes. ConnectNamedPipe não tem timeout, então roda numa thread."""
        error = []

        def run():
            try:
                _connect(self._req)   # o Lua abre o _req primeiro
                _connect(self._resp)
            except OSError as e:
                error.append(e)

        t = threading.Thread(target=run, daemon=True)
        t.start()
        t.join(timeout)
        if t.is_alive():
            raise TimeoutError("o agent.lua não conectou em %.0f s" % timeout)
        if error:
            raise error[0]
        self.writer = os.fdopen(msvcrt.open_osfhandle(self._req, os.O_WRONLY), "wb", buffering=0)
        self.reader = os.fdopen(msvcrt.open_osfhandle(self._resp, os.O_RDONLY), "rb")

    def request(self, line):
        self.writer.write((line + "\n").encode("utf-8"))
        reply = self.reader.readline()
        if not reply:
            raise ConnectionError("o emulador fechou a conexão")
        return reply.decode("utf-8").rstrip("\r\n")

    def readline(self):
        reply = self.reader.readline()
        if not reply:
            raise ConnectionError("o emulador fechou a conexão")
        return reply.decode("utf-8").rstrip("\r\n")

    def close(self):
        for f in (self.writer, self.reader):
            if f is not None:
                try:
                    f.close()
                except OSError:
                    pass
        if self.writer is None:  # nunca conectou: fecha os handles crus
            for h in (self._req, self._resp):
                try:
                    _winapi.CloseHandle(h)
                except OSError:
                    pass
