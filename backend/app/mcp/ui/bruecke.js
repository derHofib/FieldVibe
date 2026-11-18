// Minimale MCP-Apps-Bruecke (JSON-RPC ueber postMessage an den Host). Keine externen Skripte, nichts wird nachgeladen:
// die Daten kommen ausschliesslich aus dem Tool-Ergebnis (structuredContent).
(function () {
  var naechsteId = 1;
  var offen = {};
  function senden(nachricht) { window.parent.postMessage(nachricht, "*"); }
  function anfrage(methode, params) {
    return new Promise(function (ok, fehler) {
      var id = naechsteId++;
      offen[id] = { ok: ok, fehler: fehler };
      senden({ jsonrpc: "2.0", id: id, method: methode, params: params || {} });
    });
  }
  function meldung(methode, params) { senden({ jsonrpc: "2.0", method: methode, params: params || {} }); }

  window.fvLinkOeffnen = function (url) {
    if (typeof url !== "string" || !/^https?:\/\//i.test(url)) return;
    anfrage("ui/open-link", { url: url }).catch(function () { window.open(url, "_blank", "noopener"); });
  };

  window.addEventListener("message", function (ev) {
    if (ev.source !== window.parent) return;
    var m = ev.data;
    if (!m || m.jsonrpc !== "2.0") return;
    if (m.id !== undefined && m.method === undefined) {
      var p = offen[m.id];
      if (p) { delete offen[m.id]; if (m.error) p.fehler(m.error); else p.ok(m.result); }
      return;
    }
    if (m.method === "ui/notifications/tool-result") {
      var daten = m.params && m.params.structuredContent;
      if (daten) window.fvRendern(daten);
    } else if (m.method === "ui/resource-teardown" && m.id !== undefined) {
      senden({ jsonrpc: "2.0", id: m.id, result: {} });
    }
  });

  function groesseMelden() {
    meldung("ui/notifications/size-changed", { width: document.documentElement.scrollWidth, height: document.documentElement.scrollHeight });
  }
  if (window.ResizeObserver) new ResizeObserver(groesseMelden).observe(document.body);

  anfrage("ui/initialize", {
    appInfo: { name: "fieldvibe", version: "1.0.0" },
    appCapabilities: {},
    protocolVersion: "2026-01-26"
  }).then(function () { meldung("ui/notifications/initialized"); groesseMelden(); }).catch(function () {});
})();
