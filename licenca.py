"""
licenca.py
-----------
Lógica compartilhada de geração e validação de keys.
Tanto o gerador (gerador_de_keys.py) quanto o app (otimizador.py) usam este módulo,
para que a validação seja sempre consistente.

COMO FUNCIONA:
- Cada key tem um "payload" (parte aleatória + data de expiração).
- Sobre esse payload geramos uma assinatura HMAC-SHA256 usando uma CHAVE SECRETA.
- O app recalcula a assinatura e compara. Se bater, a key é legítima e não foi forjada.

IMPORTANTE (segurança):
- Como a validação é OFFLINE, a CHAVE_SECRETA precisa estar no app. Alguém muito
  avançado poderia extraí-la e gerar keys. Isso impede falsificação casual, mas não
  é proteção militar. Para anti-pirataria de verdade (impedir compartilhamento de key,
  travar por máquina, revogar keys) o certo é validar num SERVIDOR. Veja o README.
- TROQUE a CHAVE_SECRETA abaixo por uma sua, longa e aleatória, e NÃO compartilhe.
"""

import hmac
import hashlib
import secrets
from datetime import datetime, timedelta

# >>> TROQUE ISTO por uma sequência sua, longa e aleatória <<<
CHAVE_SECRETA = b"TROQUE_ESTA_CHAVE_SECRETA_POR_UMA_SUA_LONGA_E_ALEATORIA_2025"


def _assinar(payload: str) -> str:
    """Gera a assinatura (8 caracteres) de um payload."""
    return hmac.new(CHAVE_SECRETA, payload.encode(), hashlib.sha256).hexdigest()[:8].upper()


def gerar_key(dias_validade: int = 30) -> str:
    """
    Gera uma key no formato:  AAAA-BBBB-CCCC-AAAAMMDD-SSSSSSSS
    onde os 3 primeiros blocos são aleatórios, o 4º é a data de expiração
    e o último é a assinatura.
    """
    bloco = secrets.token_hex(6).upper()  # 12 caracteres aleatórios
    p1, p2, p3 = bloco[0:4], bloco[4:8], bloco[8:12]
    expira = (datetime.now() + timedelta(days=dias_validade)).strftime("%Y%m%d")
    payload = f"{p1}{p2}{p3}{expira}"
    sig = _assinar(payload)
    return f"{p1}-{p2}-{p3}-{expira}-{sig}"


def validar_key(key: str):
    """
    Valida uma key. Retorna uma tupla (bool, mensagem).
    """
    try:
        partes = key.strip().upper().split("-")
        if len(partes) != 5:
            return False, "Formato de key inválido."

        p1, p2, p3, expira, sig = partes
        payload = f"{p1}{p2}{p3}{expira}"

        # Confere a assinatura (impede keys inventadas)
        if not hmac.compare_digest(_assinar(payload), sig):
            return False, "Key inválida (assinatura não confere)."

        # Confere a validade
        validade = datetime.strptime(expira, "%Y%m%d")
        if datetime.now().date() > validade.date():
            return False, f"Key expirada em {validade.strftime('%d/%m/%Y')}."

        return True, f"Key válida até {validade.strftime('%d/%m/%Y')}."
    except Exception:
        return False, "Erro ao ler a key."
