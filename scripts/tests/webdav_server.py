"""Minimaler WebDAV-Server nur fuer den Test von befehl-beispiel.sh.example.

Unterstuetzt PUT, GET, DELETE, MKCOL und PROPFIND (Tiefe 0/1) mit Basic-Auth auf
einem Verzeichnis. Aufruf: webdav_server.py <wurzel> <portdatei> <user> <passwort>
Schreibt den gewaehlten Port in <portdatei>, sobald der Server bereit ist.
"""
import base64
import http.server
import os
import sys

WURZEL, PORTDATEI, USER, PASSWORT = sys.argv[1:5]
ERWARTET = "Basic " + base64.b64encode(f"{USER}:{PASSWORT}".encode()).decode()
PRAEFIX = "/dav"


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):  # still
        pass

    def _auth(self):
        if self.headers.get("Authorization") != ERWARTET:
            self.send_response(401)
            self.send_header("WWW-Authenticate", 'Basic realm="test"')
            self.send_header("Content-Length", "0")
            self.end_headers()
            return False
        return True

    def _pfad(self):
        if not self.path.startswith(PRAEFIX):
            return None
        rel = self.path[len(PRAEFIX):].lstrip("/")
        if ".." in rel.split("/"):
            return None
        return os.path.join(WURZEL, rel)

    def _leer(self, code):
        self.send_response(code)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_PUT(self):
        if not self._auth():
            return
        p = self._pfad()
        laenge = int(self.headers.get("Content-Length", "0"))
        daten = self.rfile.read(laenge)
        if p is None:
            return self._leer(404)
        with open(p, "wb") as f:
            f.write(daten)
        self._leer(201)

    def do_GET(self):
        if not self._auth():
            return
        p = self._pfad()
        if p is None or not os.path.isfile(p):
            return self._leer(404)
        with open(p, "rb") as f:
            daten = f.read()
        self.send_response(200)
        self.send_header("Content-Length", str(len(daten)))
        self.end_headers()
        self.wfile.write(daten)

    def do_DELETE(self):
        if not self._auth():
            return
        p = self._pfad()
        if p is None or not os.path.isfile(p):
            return self._leer(404)
        os.remove(p)
        self._leer(204)

    def do_MKCOL(self):
        if not self._auth():
            return
        p = self._pfad()
        if p is None or os.path.exists(p):
            return self._leer(405)
        os.makedirs(p)
        self._leer(201)

    def do_PROPFIND(self):
        if not self._auth():
            return
        laenge = int(self.headers.get("Content-Length", "0"))
        if laenge:
            self.rfile.read(laenge)
        p = self._pfad()
        if p is None or not os.path.exists(p):
            return self._leer(404)
        eintraege = [self.path]
        if self.headers.get("Depth", "1") != "0" and os.path.isdir(p):
            basis = self.path.rstrip("/")
            eintraege += [f"{basis}/{n}" for n in sorted(os.listdir(p))]
        teile = "".join(f"<d:response><d:href>{e}</d:href></d:response>" for e in eintraege)
        body = f'<?xml version="1.0"?><d:multistatus xmlns:d="DAV:">{teile}</d:multistatus>'.encode()
        self.send_response(207)
        self.send_header("Content-Type", "application/xml")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
with open(PORTDATEI, "w") as f:
    f.write(str(server.server_address[1]))
server.serve_forever()
