"""API HTTP de la Central de mantenimiento (:8200).

Solo biblioteca estándar: el panel y la API no agregan dependencias al
contenedor del agente. Los endpoints son los que usa el CLI y la página.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import servicio

HTML = """<!doctype html>
<html lang="es"><head><meta charset="utf-8"><title>Central de mantenimiento</title>
<style>
body{font-family:system-ui,sans-serif;margin:2rem;background:#0f1720;color:#e6edf3}
h1,h2{font-weight:600}table{border-collapse:collapse;width:100%;margin-bottom:1.5rem}
th,td{border-bottom:1px solid #2b3a48;padding:.45rem;text-align:left;font-size:.9rem}
button{margin:.15rem;padding:.25rem .6rem;border:0;border-radius:4px;cursor:pointer}
.ok{background:#1f6f43;color:#fff}.no{background:#8a2c2c;color:#fff}
pre{background:#16212c;padding:.5rem;border-radius:4px;white-space:pre-wrap}
</style></head><body>
<h1>Central de mantenimiento · PIA-3</h1>
<p>Planificador aprueba o rechaza · Supervisor cierra · Inspector certifica u observa.</p>
<h2>Órdenes</h2><table id="tabla"><thead><tr>
<th>Orden</th><th>Equipo</th><th>Estado</th><th>Tareas</th><th>Motivo</th><th>Decisión</th>
</tr></thead><tbody></tbody></table>
<h2>Detalle</h2><pre id="detalle">Elegí una orden.</pre>
<script>
const rol = {planificador:['aprobar','rechazar'],supervisor:['cerrar'],
             inspector:['certificar','observar']};
async function cargar(){
  const o = await (await fetch('/api/ordenes')).json();
  const tb = document.querySelector('#tabla tbody'); tb.innerHTML='';
  for (const f of o){
    const p = f.payload; const tr = document.createElement('tr');
    tr.innerHTML = `<td>${p.id}</td><td>${p.equipo}</td><td>${p.estado}</td>`+
                   `<td>${(p.tareas||[]).join(', ')}</td><td>${p.motivo||''}</td><td></td>`;
    const celda = tr.lastElementChild;
    for (const [r,acciones] of Object.entries(rol)) for (const a of acciones){
      if ((p.estado==='PendienteAprobacion' && r==='planificador') ||
          (p.estado==='Ejecutada' && (r==='supervisor'||r==='inspector'))){
        const b=document.createElement('button'); b.textContent=a;
        b.className=(a==='aprobar'||a==='certificar'||a==='cerrar')?'ok':'no';
        b.onclick=async()=>{
          const cuerpo={quien:prompt('Quién decide (opcional):')||''};
          if (a==='rechazar'||a==='observar') cuerpo.motivo=prompt('Motivo (obligatorio):')||'';
          const r=await fetch(`/api/ordenes/${p.id}/${a}`,{method:'POST',
            headers:{'Content-Type':'application/json','X-Rol':r},
            body:JSON.stringify(cuerpo)});
          const t=await r.json();
          document.querySelector('#detalle').textContent=JSON.stringify(t,null,2);
          cargar();
        };
        celda.appendChild(b);
      }
    }
    tr.onclick=async e=>{ if(e.target.tagName!=='BUTTON'){
      const d=await (await fetch(`/api/ordenes/${p.id}`)).json();
      document.querySelector('#detalle').textContent=JSON.stringify(d,null,2);}};
    tb.appendChild(tr);
  }
}
cargar(); setInterval(cargar, 20000);
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    publicador = None

    def log_message(self, *args):  # silencio: el log del agente ya cuenta todo
        return

    def _enviar(self, codigo: int, cuerpo, tipo: str = "application/json") -> None:
        if isinstance(cuerpo, str):
            datos = cuerpo.encode("utf-8")
        else:
            datos = json.dumps(cuerpo, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(codigo)
        self.send_header("Content-Type", f"{tipo}; charset=utf-8")
        self.send_header("Content-Length", str(len(datos)))
        self.end_headers()
        self.wfile.write(datos)

    def do_GET(self):  # noqa: N802
        ruta = urlparse(self.path)
        if ruta.path in ("/", "/index.html"):
            return self._enviar(200, HTML, "text/html")
        if ruta.path == "/api/ordenes":
            filtro = parse_qs(ruta.query).get("estado", [None])[0]
            try:
                return self._enviar(200, servicio.listar(filtro))
            except Exception as exc:  # base caída
                return self._enviar(503, {"error": str(exc)})
        partes = ruta.path.strip("/").split("/")
        if len(partes) == 3 and partes[:2] == ["api", "ordenes"]:
            try:
                return self._enviar(200, servicio.obtener(partes[2]))
            except servicio.OrdenNoEncontrada:
                return self._enviar(404, {"error": "orden no encontrada"})
        return self._enviar(404, {"error": "ruta desconocida"})

    def do_POST(self):  # noqa: N802
        partes = urlparse(self.path).path.strip("/").split("/")
        if len(partes) != 4 or partes[:2] != ["api", "ordenes"]:
            return self._enviar(404, {"error": "ruta desconocida"})
        orden_id, accion = partes[2], partes[3]
        largo = int(self.headers.get("Content-Length") or 0)
        try:
            cuerpo = json.loads(self.rfile.read(largo) or b"{}")
        except ValueError:
            cuerpo = {}
        rol = self.headers.get("X-Rol") or cuerpo.get("rol") or ""
        try:
            orden = servicio.decidir(
                self.publicador,
                orden_id,
                accion,
                rol=rol,
                quien=cuerpo.get("quien"),
                motivo=cuerpo.get("motivo"),
            )
            return self._enviar(200, orden)
        except servicio.PermisoDenegado as exc:
            return self._enviar(403, {"error": str(exc)})
        except servicio.OrdenNoEncontrada as exc:
            return self._enviar(404, {"error": str(exc)})
        except servicio.DecisionInvalida as exc:
            return self._enviar(409, {"error": str(exc)})
        except ValueError as exc:
            return self._enviar(409, {"error": str(exc)})


def crear_servidor(publicador, host: str = "0.0.0.0", puerto: int = 8200) -> ThreadingHTTPServer:
    handler = type("HandlerCentral", (Handler,), {"publicador": publicador})
    return ThreadingHTTPServer((host, puerto), handler)


def servir(publicador, puerto: int = 8200) -> None:
    servidor = crear_servidor(publicador, puerto=puerto)
    servidor.serve_forever()
