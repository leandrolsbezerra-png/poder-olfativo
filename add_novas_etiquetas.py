"""
Cadastra os 186 perfumes do lote "Novas Etiquetas" (links do Fragrantica),
com foto, frasco padrao de 100ml/R$100 e preco por ml calculado.

Marca todos com batch='Novas Etiquetas' para aparecerem separados na pagina
de Etiquetas (filtro "Novas Etiquetas").

Rodar no PythonAnywhere:
    cd ~/poder-olfativo && python add_novas_etiquetas.py
"""
import os
import sqlite3
import sys
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(HERE, 'estoque.db')
FOTOS = os.path.join(HERE, 'static', 'perfume_photos')

sys.path.insert(0, HERE)
from dados_novas_etiquetas import PERFUMES, LOTE, nome_foto


def migrar(cur):
    """Cria a coluna batch, usada para agrupar lotes de etiquetas."""
    cols = {r[1] for r in cur.execute("PRAGMA table_info(perfumes)")}
    if 'batch' not in cols:
        cur.execute("ALTER TABLE perfumes ADD COLUMN batch TEXT DEFAULT ''")
        print("coluna 'batch' criada em perfumes")


# Marcas que ja existem no sistema com outra grafia. Sem isso o script criaria
# uma marca nova e o perfume ficaria separado do resto da mesma marca.
ALIASES = {
    'ysl': 'Yves Saint Laurent',
    'yvessaintlaurent': 'Yves Saint Laurent',
    'dg': 'Dolce & Gabbana',
    'dolcegabbana': 'Dolce & Gabbana',
    'armani': 'Giorgio Armani',
    'giorgioarmani': 'Giorgio Armani',
    'emporioarmani': 'Giorgio Armani',
    'pacorabanne': 'Rabanne',
    'rabanne': 'Rabanne',
    'lattafaperfumes': 'Lattafa',
    'orienticapremium': 'Orientica',
    'sospiro': 'Sospiro Perfumes',
    'rojadove': 'Roja Parfums',
    'mfk': 'Maison Francis Kurkdjian',
    'initio': 'Initio Parfums Privés',
}


def chave(s):
    """Normaliza um nome de marca para comparacao: sem acento, sem pontuacao, minusculo."""
    s = unicodedata.normalize('NFKD', s or '')
    s = ''.join(c for c in s if not unicodedata.combining(c))
    return ''.join(c for c in s.lower() if c.isalnum())


def canon(nome):
    """Chave canonica da marca: aplica o apelido nos DOIS lados da comparacao,
    senao 'Yves Saint Laurent' nao reconheceria o 'YSL' ja cadastrado."""
    k = chave(nome)
    return chave(ALIASES.get(k, nome))


def resolver_marca(cur, marca, criadas, avisos, dry):
    """Acha a marca existente (ignorando acento/pontuacao/grafia) ou cria."""
    cur.execute("SELECT id, name FROM brands")
    existentes = cur.fetchall()
    alvo = canon(marca)

    # varias grafias podem apontar para a mesma marca ('Armani' e 'Giorgio
    # Armani'). Prefere o nome exato que queremos e, depois, o mais completo —
    # na etiqueta 'GIORGIO ARMANI' fica melhor que 'ARMANI'.
    candidatas = [r for r in existentes if canon(r['name']) == alvo]
    candidatas.sort(key=lambda r: (r['name'] != marca, -len(r['name'])))
    achou = candidatas[0] if candidatas else None
    if achou:
        if achou['name'] != marca:
            avisos.append(f"'{marca}' usou a marca ja existente '{achou['name']}'")
        return achou['id']

    # nada igual: avisa se existe algo parecido antes de criar uma marca nova
    # compara a grafia crua (sem expandir apelido), senao 'MFK' viraria
    # 'maisonfrancis...' e casaria com qualquer marca que comece com 'Maison'
    crua = chave(marca)
    parecidas = [r['name'] for r in existentes
                 if chave(r['name'])[:6] == crua[:6]]
    if parecidas:
        avisos.append(f"ATENCAO: criando marca '{marca}' — parecidas no sistema: {', '.join(parecidas)}")
    criadas.append(marca)
    if dry:
        return -1
    cur.execute("INSERT INTO brands (name) VALUES (?)", (marca,))
    return cur.lastrowid


def preco_por_ml(cur, custo=100.0, volume=100.0):
    cur.execute("SELECT key, value FROM group_settings")
    settings = {r[0]: float(r[1] or 0) for r in cur.fetchall()}
    cur.execute("SELECT pct FROM group_indirect_costs WHERE active=1")
    indiretos = sum(r[0] for r in cur.fetchall())
    total = indiretos + settings.get('net_margin_pct', 40)
    if total >= 100:
        return 0.0
    return round((custo / volume) / ((100 - total) / 100), 4)


def run(dry=False):
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    if dry:
        print(">>> MODO TESTE: nada vai ser gravado no banco.\n")

    migrar(cur)
    ppm = preco_por_ml(cur)
    print(f"preco por ml do frasco padrao: R$ {ppm:.4f}\n")

    add = skip = sem_foto = 0
    marcas_novas, avisos, pulados, faltou_foto = [], [], [], []

    for frag_id, marca, nome, conc, genero, estilo, _revisar in PERFUMES:
        brand_id = resolver_marca(cur, marca, marcas_novas, avisos, dry)

        # duplicidade: mesma marca + nome + concentracao, ignorando acento e caixa.
        # (Luna Rossa Carbon existe em EDT e EDP, por isso a concentracao entra)
        if brand_id != -1:
            cur.execute("SELECT name, concentration FROM perfumes WHERE brand_id=?", (brand_id,))
            ja_tem = {(chave(r['name']), chave(r['concentration'])) for r in cur.fetchall()}
            if (chave(nome), chave(conc)) in ja_tem:
                skip += 1
                pulados.append(f"{marca} - {nome} ({conc})")
                continue

        foto = nome_foto(marca, nome, conc)
        if not os.path.exists(os.path.join(FOTOS, foto)):
            faltou_foto.append(f"{marca} - {nome}")
            foto = None
            sem_foto += 1

        add += 1
        if dry:
            continue

        cur.execute(
            "INSERT INTO perfumes (brand_id, name, concentration, gender, style, "
            "photo_filename, batch) VALUES (?,?,?,?,?,?,?)",
            (brand_id, nome, conc, genero, estilo, foto, LOTE))
        pid = cur.lastrowid

        cur.execute(
            "INSERT INTO bottles (perfume_id, volume_ml, cost_price, remaining_ml, notes) "
            "VALUES (?,100,100,100,'Frasco padrao')", (pid,))
        cur.execute("UPDATE perfumes SET price_per_ml=? WHERE id=?", (ppm, pid))

    if dry:
        con.rollback()
    else:
        con.commit()
    con.close()

    print('=' * 56)
    print(f"{'seriam adicionados' if dry else 'adicionados'} : {add}")
    print(f"ja existiam : {skip}")
    print(f"sem foto    : {sem_foto}")

    if marcas_novas:
        unicas = sorted(set(marcas_novas))
        print(f"\nmarcas {'que seriam criadas' if dry else 'criadas'} ({len(unicas)}):")
        print('  ' + ', '.join(unicas))
    if avisos:
        print(f"\nconferir ({len(avisos)}):")
        for a in dict.fromkeys(avisos):
            print(f"  - {a}")
    if pulados:
        print(f"\nja existiam, nao duplicados ({len(pulados)}):")
        for p in pulados:
            print(f"  - {p}")
    if faltou_foto:
        print(f"\nsem foto ({len(faltou_foto)}):")
        for f in faltou_foto:
            print(f"  - {f}")

    if dry:
        print("\nNada gravado. Rode sem --teste para aplicar.")
    else:
        print(f"\nTodos marcados como lote '{LOTE}'.")
        print("Na pagina Etiquetas: filtro 'Novas Etiquetas' + botao 'Todos'.")


if __name__ == '__main__':
    run(dry='--teste' in sys.argv)
