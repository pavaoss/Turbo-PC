"""
servidor.py  —  Servidor de licença + loja do Turbo PC Booster
--------------------------------------------------------------
Faz tudo do lado do "dono":
- Valida/ativa keys travando 1 key por PC (HWID).
- Painel de ADMIN no navegador (criar, revogar, liberar, listar keys).
- LOJA pública com pagamento PIX (Mercado Pago) que gera a key automaticamente.

Coloque este arquivo na MESMA pasta de licenca.py.

Instalar e rodar:
    pip install fastapi uvicorn
    set ADMIN_TOKEN=meu_token_secreto
    set MP_ACCESS_TOKEN=APP_USR-xxxxx       (token do Mercado Pago p/ a loja)
    python servidor.py

Acesse:
    Loja .......... http://localhost:8000/loja
    Admin ......... http://localhost:8000/admin
"""

import os
import ssl
import json
import uuid
import sqlite3
import smtplib
import urllib.parse
import urllib.request
from datetime import datetime
from email.message import EmailMessage

try:
    from fastapi import FastAPI, Header, HTTPException
    from fastapi.responses import HTMLResponse
    from pydantic import BaseModel
    import uvicorn
except ImportError:
    print("Faltam dependências. Rode:  pip install fastapi uvicorn")
    raise SystemExit(1)

from licenca import gerar_key, validar_key

ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "Theo20p11")
MP_TOKEN = os.environ.get("MP_ACCESS_TOKEN", "APP_USR-4807753332506280-060416-c6e66e0e1bae55314f87e35ab4e82af4-98365695")
DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "licencas.db")

# E-mail (SMTP) para enviar a key ao comprador.
# Gmail: SMTP_HOST=smtp.gmail.com / SMTP_PORT=587 / SMTP_USER=seu@gmail.com /
#        SMTP_PASS = "senha de app" (não a senha normal; gere em myaccount.google.com).
SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "turbopcltda@gmail.com")
SMTP_PASS = os.environ.get("SMTP_PASS", "vnok oubc tdhh ivpz")
SMTP_FROM = os.environ.get("SMTP_FROM", SMTP_USER or "no-reply@turbopcbooster")

# Pushover: notificação no seu celular quando vender.
# Crie conta em pushover.net, pegue seu "User Key" e crie um "Application" p/ o Token.
PUSHOVER_TOKEN = os.environ.get("PUSHOVER_TOKEN", "a6vj4iibggeop6hst3dtez4rup47n6")
PUSHOVER_USER = os.environ.get("PUSHOVER_USER", "uexxkyn2vmdktv4b2pubvzonoyvwmc")

# Planos vendidos na loja (preço em R$). Trial é gratuito e sai na hora.
PLANOS = {
    "TESTE":      {"nome": "TESTE",  "dias": 3,    "preco": 1.00},
    "mensal":     {"nome": "Mensal",        "dias": 30,   "preco": 19.90},
    "trimestral": {"nome": "Trimestral",    "dias": 90,   "preco": 39.90},
    "vitalicio":  {"nome": "Vitalício",     "dias": 3650, "preco": 99.90},
}

app = FastAPI(title="Turbo PC Booster")


def conectar():
    con = sqlite3.connect(DB)
    con.execute("""CREATE TABLE IF NOT EXISTS licencas (
        key TEXT PRIMARY KEY, hwid TEXT, revogada INTEGER DEFAULT 0,
        plano TEXT, ativada_em TEXT)""")
    con.execute("""CREATE TABLE IF NOT EXISTS pagamentos (
        pagamento_id TEXT PRIMARY KEY, plano TEXT, key TEXT,
        status TEXT, email TEXT, criado_em TEXT)""")
    try:
        con.execute("ALTER TABLE pagamentos ADD COLUMN email TEXT")  # bancos antigos
    except Exception:
        pass
    return con


# ====================================================================
# MERCADO PAGO (PIX)
# ====================================================================
def mp_criar_pix(valor, email, descricao):
    if not MP_TOKEN:
        return None, "Loja não configurada (defina MP_ACCESS_TOKEN)."
    body = json.dumps({
        "transaction_amount": round(float(valor), 2),
        "description": descricao,
        "payment_method_id": "pix",
        "payer": {"email": email or "comprador@email.com"},
    }).encode()
    req = urllib.request.Request(
        "https://api.mercadopago.com/v1/payments", data=body,
        headers={"Authorization": f"Bearer {MP_TOKEN}",
                 "Content-Type": "application/json",
                 "X-Idempotency-Key": str(uuid.uuid4())})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.load(r), None
    except Exception as e:
        return None, f"Erro ao falar com o Mercado Pago: {e}"


def mp_status(pagamento_id):
    if not MP_TOKEN:
        return "desconhecido"
    req = urllib.request.Request(
        f"https://api.mercadopago.com/v1/payments/{pagamento_id}",
        headers={"Authorization": f"Bearer {MP_TOKEN}"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.load(r).get("status", "desconhecido")
    except Exception:
        return "desconhecido"


def emitir_key(plano):
    return gerar_key(PLANOS[plano]["dias"])


from email.message import EmailMessage
import smtplib
import ssl
import os

def enviar_email(destino, key, plano):
    """Envia a key para o e-mail do comprador. Se o SMTP não estiver configurado
    (ou faltar e-mail), apenas avisa no console — a key ainda aparece na tela."""
    if not destino or not SMTP_HOST or not SMTP_USER:
        print("[email] SMTP não configurado ou sem destino; envio pulado.")
        return False

    try:
        msg = EmailMessage()
        msg["Subject"] = "Sua key do Turbo PC Booster ⚡"
        msg["From"] = SMTP_FROM
        msg["To"] = destino

        msg.set_content(
            f"Obrigado pela compra do plano {plano}!\n\n"
            f"Sua key de ativacao:\n\n    {key}\n\n"
            f"Abra o Turbo PC Booster e cole a key na tela de ativacao.\n"
            f"Bons jogos!"
        )

        msg.add_alternative(
            f"<div style='font-family:Arial;color:#222'>"
            f"<h2 style='color:#00a152'>⚡ Turbo PC Booster</h2>"
            f"<p>Obrigado pela compra do plano <b>{plano}</b>!</p>"
            f"<p>Sua key de ativação:👇 Link de Download: https://www.mediafire.com/file/3zwqxm3uqpy33y0/TurboPCBooster.exe/file </p>"
            f"<p style='font-size:20px;background:#f0f0f0;padding:12px;"
            f"border-radius:8px'><b>{key}</b></p>"
            f"<p>Abra o app e cole a key na tela de ativação. Bons jogos! 🚀</p>"
            f"</div>",
            subtype="html"
        )

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as s:
            s.starttls(context=ssl.create_default_context())
            s.login(SMTP_USER, SMTP_PASS)
            s.send_message(msg)

        print(f"[email] key enviada para {destino}")
        return True

    except Exception as e:
        print(f"[email] falha ao enviar para {destino}: {e}")
        return False
 
def notificar_pushover(titulo, mensagem):
    try:
        import urllib.parse
        import urllib.request

        data = urllib.parse.urlencode({
            "token": PUSHOVER_TOKEN,
            "user": PUSHOVER_USER,
            "title": titulo,
            "message": mensagem,
        }).encode("utf-8")

        req = urllib.request.Request(
            "https://api.pushover.net/1/messages.json",
            data=data
        )

        with urllib.request.urlopen(req) as resp:
            print(resp.read().decode())

        return True

    except Exception as e:
        print("Erro Pushover:", e)
        return False
 
# ====================================================================
# MODELOS
# ====================================================================
class Ativacao(BaseModel):
    key: str
    hwid: str


class Compra(BaseModel):
    plano: str
    email: str = ""


class CriarLote(BaseModel):
    quantidade: int = 1
    dias: int = 30


class KeyRef(BaseModel):
    key: str


# ====================================================================
# APP (otimizador) -> ativar / validar
# ====================================================================
@app.post("/ativar")
def ativar(d: Ativacao):
    key = d.key.strip().upper()
    ok, msg = validar_key(key)
    if not ok:
        return {"ok": False, "msg": msg}
    con = conectar()
    row = con.execute("SELECT hwid, revogada FROM licencas WHERE key=?", (key,)).fetchone()
    if row and row[1] == 1:
        con.close(); return {"ok": False, "msg": "Key revogada."}
    if row is None:
        con.execute("INSERT INTO licencas (key, hwid, ativada_em) VALUES (?,?,?)",
                    (key, d.hwid, datetime.now().isoformat()))
        con.commit(); con.close()
        return {"ok": True, "msg": "Key ativada neste PC. " + msg}
    if row[0] == d.hwid:
        con.close(); return {"ok": True, "msg": "Key já ativa neste PC. " + msg}
    con.close()
    return {"ok": False, "msg": "Esta key já está em uso em outro PC."}


@app.post("/validar")
def validar(d: Ativacao):
    key = d.key.strip().upper()
    ok, msg = validar_key(key)
    if not ok:
        return {"ok": False, "msg": msg}
    con = conectar()
    row = con.execute("SELECT hwid, revogada FROM licencas WHERE key=?", (key,)).fetchone()
    con.close()
    if row is None:
        return {"ok": False, "msg": "Key ainda não ativada."}
    if row[1] == 1:
        return {"ok": False, "msg": "Key revogada."}
    if row[0] != d.hwid:
        return {"ok": False, "msg": "Key registrada em outro PC."}
    return {"ok": True, "msg": msg}


# ====================================================================
# LOJA (pública)
# ====================================================================
@app.post("/comprar")
def comprar(d: Compra):
    if d.plano not in PLANOS:
        return {"ok": False, "msg": "Plano inválido."}
    plano = PLANOS[d.plano]

    # Trial é grátis: gera a key na hora
    if plano["preco"] <= 0:
        key = emitir_key(d.plano)
        enviar_email(d.email, key, plano["nome"])
        notificar_pushover("🎁 Novo trial ativado",
                           f"Plano {plano['nome']} (grátis)\nCliente: {d.email or 'sem e-mail'}")
        return {"ok": True, "gratis": True, "key": key}

    pago, erro = mp_criar_pix(plano["preco"], d.email,
                              f"Turbo PC Booster - {plano['nome']}")
    if erro:
        return {"ok": False, "msg": erro}

    pid = str(pago["id"])
    tdata = pago.get("point_of_interaction", {}).get("transaction_data", {})
    con = conectar()
    con.execute("INSERT OR REPLACE INTO pagamentos "
                "(pagamento_id, plano, key, status, email, criado_em) "
                "VALUES (?,?,?,?,?,?)", (pid, d.plano, "", pago.get("status", "pending"),
                                         d.email, datetime.now().isoformat()))
    con.commit(); con.close()
    return {"ok": True, "gratis": False, "pagamento_id": pid,
            "valor": plano["preco"],
            "qr_code": tdata.get("qr_code", ""),
            "qr_base64": tdata.get("qr_code_base64", "")}


@app.get("/status/{pagamento_id}")
def status_pagamento(pagamento_id: str):
    con = conectar()
    row = con.execute("SELECT plano, key, email FROM pagamentos WHERE pagamento_id=?",
                      (pagamento_id,)).fetchone()
    if not row:
        con.close(); return {"ok": False, "msg": "Pagamento não encontrado."}
    plano, key, email = row
    st = mp_status(pagamento_id)
    if st == "approved":
        if not key:
            key = emitir_key(plano)
            con.execute("UPDATE pagamentos SET key=?, status=? WHERE pagamento_id=?",
                        (key, "approved", pagamento_id))
            con.commit()
            info = PLANOS.get(plano, {})
            nome_plano = info.get("nome", plano)
            preco = info.get("preco", 0)
            enviar_email(email, key, nome_plano)
            notificar_pushover(
                "💰 Compra aprovada!",
                f"Plano {nome_plano} — R$ {preco:.2f}".replace(".", ",")
                + f"\nCliente: {email or 'sem e-mail'}")
        con.close()
        return {"ok": True, "status": "approved", "key": key}
    con.execute("UPDATE pagamentos SET status=? WHERE pagamento_id=?", (st, pagamento_id))
    con.commit(); con.close()
    return {"ok": True, "status": st}


@app.post("/webhook")
def webhook(payload: dict):
    # Mercado Pago notifica aqui quando o pagamento muda de status.
    try:
        pid = str(payload.get("data", {}).get("id", ""))
        if pid:
            status_pagamento(pid)
    except Exception:
        pass
    return {"ok": True}


# ====================================================================
# ADMIN (token)
# ====================================================================
def _admin(token):
    if token != ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="Token inválido.")


@app.post("/admin/criar")
def admin_criar(d: CriarLote, x_admin_token: str = Header(default="")):
    _admin(x_admin_token)
    return {"ok": True, "keys": [gerar_key(d.dias) for _ in range(d.quantidade)]}


@app.post("/admin/revogar")
def admin_revogar(d: KeyRef, x_admin_token: str = Header(default="")):
    _admin(x_admin_token)
    con = conectar()
    con.execute("INSERT INTO licencas (key, hwid, revogada) VALUES (?,?,1) "
                "ON CONFLICT(key) DO UPDATE SET revogada=1", (d.key.strip().upper(), ""))
    con.commit(); con.close()
    return {"ok": True}


@app.post("/admin/liberar")
def admin_liberar(d: KeyRef, x_admin_token: str = Header(default="")):
    _admin(x_admin_token)
    con = conectar()
    con.execute("DELETE FROM licencas WHERE key=?", (d.key.strip().upper(),))
    con.commit(); con.close()
    return {"ok": True}


@app.get("/admin/listar")
def admin_listar(x_admin_token: str = Header(default="")):
    _admin(x_admin_token)
    con = conectar()
    rows = con.execute("SELECT key, hwid, revogada, ativada_em FROM licencas "
                       "ORDER BY ativada_em DESC").fetchall()
    con.close()
    return {"ok": True, "licencas": [
        {"key": r[0], "hwid": r[1], "revogada": bool(r[2]), "ativada_em": r[3]} for r in rows]}


# ====================================================================
# PÁGINAS HTML
# ====================================================================
ESTILO = """
<style>
 body{font-family:Arial,Helvetica,sans-serif;background:#0e0f13;color:#e8eaed;margin:0;padding:30px}
 .card{background:#1b1e27;border:1px solid #2a2f3c;border-radius:16px;padding:24px;max-width:760px;margin:14px auto}
 h1{color:#00e676} h2{margin-top:0}
 button{background:#00e676;color:#06210f;border:0;border-radius:10px;padding:10px 16px;font-weight:bold;cursor:pointer}
 button.alt{background:#22262f;color:#1de9ff} button.danger{background:#ff5252;color:#fff}
 input,select{background:#0e0f13;color:#e8eaed;border:1px solid #2a2f3c;border-radius:8px;padding:10px;width:100%;box-sizing:border-box;margin:6px 0}
 table{width:100%;border-collapse:collapse;font-size:13px} td,th{border-bottom:1px solid #2a2f3c;padding:8px;text-align:left}
 .plano{display:inline-block;background:#0e0f13;border:1px solid #2a2f3c;border-radius:12px;padding:16px;margin:6px;width:150px;vertical-align:top}
 code{background:#0e0f13;padding:4px 8px;border-radius:6px;color:#00e676;word-break:break-all}
 .muted{color:#8b909a;font-size:12px}
</style>"""


@app.get("/", response_class=HTMLResponse)
def raiz():
    return f"{ESTILO}<div class='card'><h1>⚡ Turbo PC Booster</h1>" \
           "<p><a style='color:#1de9ff' href='/loja'>Ir para a Loja</a> &nbsp;|&nbsp; " \
           "<a style='color:#1de9ff' href='/admin'>Painel Admin</a></p></div>"


@app.get("/loja", response_class=HTMLResponse)
def loja():
    cards = ""
    for pid, p in PLANOS.items():
        preco = "Grátis" if p["preco"] <= 0 else f"R$ {p['preco']:.2f}".replace(".", ",")
        cards += (f"<div class='plano'><h3>{p['nome']}</h3>"
                  f"<p class='muted'>{p['dias']} dias</p><p><b>{preco}</b></p>"
                  f"<button onclick=\"comprar('{pid}')\">Comprar</button></div>")
    return f"""{ESTILO}
<div class='card'><h1>⚡ Loja</h1>
  <p>Seu e-mail (a key será enviada para ele):</p>
  <input id='email' placeholder='voce@email.com'>
  <div>{cards}</div>
</div>
<div class='card' id='area' style='display:none'></div>
<script>
async function comprar(plano){{
  const email=document.getElementById('email').value;
  const area=document.getElementById('area'); area.style.display='block';
  area.innerHTML='Gerando...';
  const r=await fetch('/comprar',{{method:'POST',headers:{{'Content-Type':'application/json'}},
    body:JSON.stringify({{plano,email}})}});
  const d=await r.json();
  if(!d.ok){{area.innerHTML='<b>'+(d.msg||'Erro')+'</b>';return;}}
  if(d.gratis){{mostrarKey(d.key);return;}}
  area.innerHTML="<h2>Pague com PIX</h2>"+
    "<img style='width:220px' src='data:image/png;base64,"+d.qr_base64+"'>"+
    "<p>Ou copie e cole:</p><code>"+d.qr_code+"</code>"+
    "<p class='muted'>Assim que o pagamento cair, sua key aparece aqui.</p>"+
    "<p id='st'>Aguardando pagamento...</p>";
  const t=setInterval(async()=>{{
    const s=await (await fetch('/status/'+d.pagamento_id)).json();
    if(s.status==='approved'){{clearInterval(t);mostrarKey(s.key);}}
  }},4000);
}}
function mostrarKey(k){{
  document.getElementById('area').innerHTML=
   "<h2>✅ Pronto!</h2><p>Sua key:</p><code>"+k+"</code>"+
   "<p class='muted'>Enviamos também para o seu e-mail. Cole no app na tela de ativação. VERIFIQUE SUA CAIXA DE DE SPAM.</p>";
}}
</script>"""


@app.get("/admin", response_class=HTMLResponse)
def admin_page():
    return f"""{ESTILO}
<div class='card'><h1>🔐 Painel Admin</h1>
  <input id='tok' type='password' placeholder='ADMIN_TOKEN'>
  <button onclick='entrar()'>Entrar</button>
</div>
<div class='card' id='painel' style='display:none'>
  <h2>Criar keys</h2>
  <input id='qtd' type='number' value='1' placeholder='Quantidade'>
  <input id='dias' type='number' value='30' placeholder='Dias de validade'>
  <button onclick='criar()'>Gerar</button>
  <div id='novas'></div>
  <h2 style='margin-top:24px'>Licenças</h2>
  <button class='alt' onclick='listar()'>Atualizar lista</button>
  <div id='lista'></div>
</div>
<script>
let TOK='';
const H=()=>({{'Content-Type':'application/json','X-Admin-Token':TOK}});
function entrar(){{TOK=document.getElementById('tok').value;
  document.getElementById('painel').style.display='block';listar();}}
async function criar(){{
  const quantidade=+document.getElementById('qtd').value;
  const dias=+document.getElementById('dias').value;
  const r=await fetch('/admin/criar',{{method:'POST',headers:H(),
    body:JSON.stringify({{quantidade,dias}})}});
  const d=await r.json();
  document.getElementById('novas').innerHTML=(d.keys||[]).map(k=>'<code>'+k+'</code>').join('<br>');
}}
async function listar(){{
  const r=await fetch('/admin/listar',{{headers:H()}});
  if(r.status===401){{alert('Token inválido');return;}}
  const d=await r.json();
  let h='<table><tr><th>Key</th><th>PC</th><th>Status</th><th></th></tr>';
  for(const l of d.licencas){{
    h+='<tr><td><code>'+l.key+'</code></td><td class=muted>'+(l.hwid||'-').slice(0,12)+'</td>'+
       '<td>'+(l.revogada?'❌ revogada':'✅ ativa')+'</td>'+
       '<td><button class=danger onclick="rev(\\''+l.key+'\\')">Revogar</button> '+
       '<button class=alt onclick="lib(\\''+l.key+'\\')">Liberar PC</button></td></tr>';
  }}
  document.getElementById('lista').innerHTML=h+'</table>';
}}
async function rev(k){{await fetch('/admin/revogar',{{method:'POST',headers:H(),body:JSON.stringify({{key:k}})}});listar();}}
async function lib(k){{await fetch('/admin/liberar',{{method:'POST',headers:H(),body:JSON.stringify({{key:k}})}});listar();}}
</script>"""


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
