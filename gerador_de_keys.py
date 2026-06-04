"""
gerador_de_keys.py
-------------------
Ferramenta do DONO do software para criar keys.
NÃO distribua este arquivo para os usuários finais.

Uso:
    python gerador_de_keys.py            -> gera 1 key de 30 dias
    python gerador_de_keys.py 7 90       -> gera 7 keys de 90 dias cada
"""

import sys
from licenca import gerar_key, validar_key


def main():
    # Argumentos opcionais: quantidade e dias de validade
    quantidade = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    dias = int(sys.argv[2]) if len(sys.argv) > 2 else 30

    print(f"\nGerando {quantidade} key(s) com {dias} dias de validade:\n")
    print("-" * 50)

    keys_geradas = []
    for _ in range(quantidade):
        k = gerar_key(dias)
        keys_geradas.append(k)
        ok, msg = validar_key(k)  # confirma que está válida
        status = "OK" if ok else "FALHOU"
        print(f"{k}   [{status}]")

    print("-" * 50)

    # Salva num arquivo de texto para você ter o controle
    with open("keys_geradas.txt", "a", encoding="utf-8") as f:
        for k in keys_geradas:
            f.write(k + "\n")

    print(f"\n{quantidade} key(s) salva(s) em 'keys_geradas.txt'.")
    print("Entregue uma key para cada usuário.\n")


if __name__ == "__main__":
    main()
