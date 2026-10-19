"""
Lista os perfumes do lote "Novas Etiquetas" cuja CONCENTRACAO vale conferir
antes de mandar a folha para a grafica.

Por que existe: o Fragrantica nao tem campo de concentracao — ele so informa
nome, marca, genero, familia e ano. Quando a concentracao nao estava escrita
no nome do produto nem legivel na foto do frasco, foi usada a concentracao
padrao da linha (quase sempre EDP). Esses casos estao listados aqui.

Para corrigir: Perfumes -> abrir o perfume -> editar a concentracao.

    python relatorio_revisao.py
"""
import sys
import os

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from dados_novas_etiquetas import PERFUMES


def run():
    rev = [p for p in PERFUMES if p[6]]
    rev.sort(key=lambda p: (p[5], p[1], p[2]))

    print(f"\n{len(rev)} de {len(PERFUMES)} perfumes para conferir a concentracao\n")
    estilo_atual = None
    for _fid, marca, nome, conc, genero, estilo, _r in rev:
        if estilo != estilo_atual:
            estilo_atual = estilo
            print(f"\n--- {estilo} ---")
        print(f"  [{conc:9}] {marca} - {nome}  ({genero})")

    print(f"\n{'-'*60}")
    print(f"Os outros {len(PERFUMES) - len(rev)} estao confirmados: a concentracao")
    print("aparecia no nome oficial ou estava legivel na foto do frasco.")


if __name__ == '__main__':
    run()
