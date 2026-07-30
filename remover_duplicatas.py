"""
Remove perfumes duplicados: mantém o que tem foto (ou o mais recente),
exclui o duplicado sem foto.
Execute no PythonAnywhere:
  cd ~/poder-olfativo && python remover_duplicatas.py
"""
import sqlite3, os

DB = os.path.join(os.path.dirname(__file__), 'estoque.db')

def run():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    # Busca pares com mesma marca e nome similar (ignora maiúsculas)
    cur.execute("""
        SELECT p.id, b.name as brand, p.name, p.photo_filename
        FROM perfumes p
        JOIN brands b ON p.brand_id = b.id
        WHERE p.active = 1
        ORDER BY b.name, p.name
    """)
    perfumes = cur.fetchall()

    # Agrupa por (brand_id, name normalizado)
    import unicodedata, re

    def norm(s):
        s = unicodedata.normalize('NFD', s)
        s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
        return re.sub(r'\s+', ' ', s.lower().strip())

    grupos = {}
    for p in perfumes:
        chave = (p['brand'], norm(p['name']))
        grupos.setdefault(chave, []).append(p)

    removidos = 0
    for chave, grupo in grupos.items():
        if len(grupo) < 2:
            continue

        # Ordena: primeiro os que têm foto
        com_foto    = [p for p in grupo if p['photo_filename']]
        sem_foto    = [p for p in grupo if not p['photo_filename']]

        manter = (com_foto or sem_foto)[0]
        remover = [p for p in grupo if p['id'] != manter['id']]

        print(f"\n  Duplicata: {chave[0]} — {chave[1]}")
        print(f"    ✔ mantém  id={manter['id']}  foto={manter['photo_filename'] or '(nenhuma)'}")
        for p in remover:
            print(f"    ✖ remove  id={p['id']}  foto={p['photo_filename'] or '(nenhuma)'}")
            # Inativa em vez de deletar para preservar histórico
            cur.execute("UPDATE perfumes SET active=0 WHERE id=?", (p['id'],))
            removidos += 1

    con.commit()
    con.close()
    print(f"\nConcluído: {removidos} duplicata(s) removida(s).")

if __name__ == '__main__':
    run()
