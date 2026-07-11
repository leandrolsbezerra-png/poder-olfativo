import sqlite3, os, json, webbrowser, threading
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, g, session
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'decants-pro-2024')
DATABASE = os.environ.get('DATABASE_PATH', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'estoque.db'))


# ──────────────────────────── DB helpers ────────────────────────────

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
    return db

@app.teardown_appcontext
def close_db(e):
    db = getattr(g, '_database', None)
    if db: db.close()

def query_db(sql, args=(), one=False):
    cur = get_db().execute(sql, args)
    rv = cur.fetchall()
    return (rv[0] if rv else None) if one else rv

def execute_db(sql, args=()):
    db = get_db(); cur = db.execute(sql, args); db.commit(); return cur.lastrowid


init_db_done = False

def init_db():
    global init_db_done
    if init_db_done or os.path.exists(DATABASE): return
    db = sqlite3.connect(DATABASE)
    db.executescript("""
        CREATE TABLE brands (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            country TEXT,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE suppliers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL, contact_name TEXT, phone TEXT,
            email TEXT, address TEXT, cnpj TEXT, notes TEXT, active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE perfumes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            brand_id INTEGER REFERENCES brands(id),
            name TEXT NOT NULL,
            concentration TEXT DEFAULT 'EDP',
            gender TEXT DEFAULT 'Unissex',
            family TEXT DEFAULT '',
            notes_top TEXT DEFAULT '',
            notes_heart TEXT DEFAULT '',
            notes_base TEXT DEFAULT '',
            description TEXT DEFAULT '',
            year INTEGER,
            photo_filename TEXT,
            active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );

        /* frasco original comprado */
        CREATE TABLE bottles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            perfume_id INTEGER REFERENCES perfumes(id),
            supplier_id INTEGER REFERENCES suppliers(id),
            volume_ml REAL NOT NULL,
            cost_price REAL NOT NULL,
            remaining_ml REAL NOT NULL,
            purchase_date TEXT DEFAULT (date('now','localtime')),
            notes TEXT,
            active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );

        /* produto vendável = perfume + tamanho de decant */
        CREATE TABLE decants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            perfume_id INTEGER REFERENCES perfumes(id),
            size_ml REAL NOT NULL,
            sale_price REAL DEFAULT 0,
            stock_quantity INTEGER DEFAULT 0,
            active INTEGER DEFAULT 1,
            UNIQUE(perfume_id, size_ml)
        );

        /* operação de fracionamento */
        CREATE TABLE decant_ops (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bottle_id INTEGER REFERENCES bottles(id),
            decant_id INTEGER REFERENCES decants(id),
            quantity INTEGER NOT NULL,
            ml_used REAL NOT NULL,
            cost_per_unit REAL DEFAULT 0,
            vial_cost REAL DEFAULT 0,
            notes TEXT,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE sales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER REFERENCES customers(id),
            customer_name TEXT DEFAULT 'Consumidor',
            sale_date TEXT DEFAULT (datetime('now','localtime')),
            subtotal REAL DEFAULT 0, discount REAL DEFAULT 0, total REAL DEFAULT 0,
            payment_method TEXT DEFAULT 'Pix',
            payment_fee_pct REAL DEFAULT 0, payment_fee_amount REAL DEFAULT 0,
            notes TEXT, status TEXT DEFAULT 'concluida'
        );

        CREATE TABLE IF NOT EXISTS payment_fee_defaults (
            method TEXT PRIMARY KEY, fee_pct REAL DEFAULT 0, label TEXT
        );
        INSERT INTO payment_fee_defaults VALUES('Pix', 0.0, 'Pix');
        INSERT INTO payment_fee_defaults VALUES('Dinheiro', 0.0, 'Dinheiro');
        INSERT INTO payment_fee_defaults VALUES('Cartão de Débito', 1.5, 'Cartão de Débito');
        INSERT INTO payment_fee_defaults VALUES('Cartão de Crédito', 3.0, 'Cartão de Crédito');

        CREATE TABLE sale_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sale_id INTEGER REFERENCES sales(id) ON DELETE CASCADE,
            decant_id INTEGER REFERENCES decants(id),
            product_label TEXT,
            size_ml REAL, quantity INTEGER NOT NULL,
            unit_price REAL NOT NULL, cost_price REAL DEFAULT 0,
            total REAL NOT NULL
        );

        /* custo dos frasquinhos de decant por tamanho */
        CREATE TABLE vial_costs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            size_ml REAL NOT NULL UNIQUE,
            cost REAL DEFAULT 0,
            label TEXT,
            multiplier REAL DEFAULT 3.0
        );

        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER REFERENCES customers(id), customer_name TEXT DEFAULT 'Cliente',
            status TEXT DEFAULT 'pendente', subtotal REAL DEFAULT 0,
            discount REAL DEFAULT 0, total REAL DEFAULT 0,
            payment_method TEXT, payment_fee_pct REAL DEFAULT 0, payment_fee_amount REAL DEFAULT 0,
            shipping_method TEXT, tracking_code TEXT, shipped_at TEXT, delivered_at TEXT,
            notes TEXT, created_at TEXT, updated_at TEXT
        );
        CREATE TABLE IF NOT EXISTS order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER REFERENCES orders(id) ON DELETE CASCADE,
            decant_id INTEGER REFERENCES decants(id), product_label TEXT, size_ml REAL,
            quantity INTEGER NOT NULL, unit_price REAL NOT NULL, total REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS goals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            month TEXT NOT NULL UNIQUE, revenue_goal REAL DEFAULT 0, orders_goal INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL, phone TEXT, email TEXT,
            cep TEXT, street TEXT, number TEXT, complement TEXT,
            neighborhood TEXT, city TEXT, state TEXT,
            notes TEXT, active INTEGER DEFAULT 1, created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS materials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL, unit TEXT DEFAULT 'un',
            cost_per_unit REAL DEFAULT 0, stock_quantity REAL DEFAULT 0,
            min_stock REAL DEFAULT 0, active INTEGER DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS material_size_map (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            material_id INTEGER REFERENCES materials(id),
            size_ml REAL NOT NULL, qty_per_decant REAL DEFAULT 1,
            UNIQUE(material_id, size_ml)
        );
        INSERT INTO materials(id,name,unit) VALUES
            (1,'Frasco de recrave 8ml','un'),(2,'Frasco de recrave 15ml','un'),
            (3,'Embalagem','un'),(4,'Tampa dos frascos','un'),(5,'Borrifador dos frascos','un');
        INSERT INTO material_size_map(material_id,size_ml) VALUES
            (1,2.0),(1,5.0),(2,10.0),(2,15.0),
            (4,2.0),(4,5.0),(4,10.0),(4,15.0),(5,2.0),(5,5.0),(5,10.0),(5,15.0);

        INSERT INTO vial_costs (size_ml, cost, label, multiplier) VALUES
            (2, 0.50, '2ml', 4.0), (5, 0.80, '5ml', 3.5),
            (10, 1.20, '10ml', 3.2), (15, 1.50, '15ml', 3.0),
            (20, 1.80, '20ml', 3.0), (30, 2.20, '30ml', 2.8);

        INSERT INTO brands (name, country) VALUES
            ('Chanel','França'),('Dior','França'),('Tom Ford','EUA'),
            ('YSL','França'),('Givenchy','França'),('Armani','Itália'),
            ('Versace','Itália'),('Prada','Itália'),('Burberry','Reino Unido'),
            ('Creed','França'),('MFK','França'),('Amouage','Omã'),
            ('Xerjoff','Itália'),('Initio','França');
    """)
    db.commit(); db.close()
    init_db_done = True


def migrate_db():
    """Roda sempre (mesmo em banco já existente). Idempotente: só cria o que faltar.
    É aqui que entram tabelas/colunas novas adicionadas depois do lançamento inicial."""
    db = sqlite3.connect(DATABASE)
    db.executescript("""
        CREATE TABLE IF NOT EXISTS accounts_payable (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            description TEXT NOT NULL,
            category TEXT DEFAULT '',
            supplier_id INTEGER REFERENCES suppliers(id),
            amount REAL NOT NULL,
            due_date TEXT NOT NULL,
            paid_date TEXT,
            paid_amount REAL,
            status TEXT DEFAULT 'pendente',
            payment_method TEXT DEFAULT '',
            notes TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE TABLE IF NOT EXISTS accounts_receivable (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            description TEXT NOT NULL,
            category TEXT DEFAULT '',
            customer_id INTEGER REFERENCES customers(id),
            sale_id INTEGER REFERENCES sales(id),
            amount REAL NOT NULL,
            due_date TEXT NOT NULL,
            received_date TEXT,
            received_amount REAL,
            status TEXT DEFAULT 'pendente',
            payment_method TEXT DEFAULT '',
            notes TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE TABLE IF NOT EXISTS group_settings (
            key TEXT PRIMARY KEY,
            value TEXT
        );
        CREATE TABLE IF NOT EXISTS group_indirect_costs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            label TEXT NOT NULL,
            pct REAL NOT NULL DEFAULT 0,
            active INTEGER DEFAULT 1,
            sort_order INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS apc_products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            perfume_id INTEGER REFERENCES perfumes(id),
            size_ml REAL NOT NULL,
            group_price REAL DEFAULT 0,
            active INTEGER DEFAULT 1,
            UNIQUE(perfume_id, size_ml)
        );
    """)
    # valores padrão só na primeira vez (tabela vazia)
    if not db.execute("SELECT 1 FROM group_settings WHERE key='net_margin_pct'").fetchone():
        db.execute("INSERT INTO group_settings(key,value) VALUES('net_margin_pct','40')")
    if not db.execute("SELECT 1 FROM group_settings WHERE key='vial_cost_group'").fetchone():
        db.execute("INSERT INTO group_settings(key,value) VALUES('vial_cost_group','6')")
    if not db.execute("SELECT 1 FROM group_settings WHERE key='min_ml'").fetchone():
        db.execute("INSERT INTO group_settings(key,value) VALUES('min_ml','2')")
    if not db.execute("SELECT 1 FROM group_settings WHERE key='max_ml'").fetchone():
        db.execute("INSERT INTO group_settings(key,value) VALUES('max_ml','15')")
    if not db.execute("SELECT 1 FROM group_indirect_costs").fetchone():
        db.executemany("INSERT INTO group_indirect_costs(label,pct,sort_order) VALUES(?,?,?)", [
            ('Maquininha de cartão', 5.0, 1),
            ('Influenciador', 0.0, 2),
            ('Gestor do grupo', 0.0, 3),
            ('Outros custos', 0.0, 4),
        ])
    # colunas novas em tabelas já existentes (ALTER falha se a coluna já existe — ignoramos)
    for stmt in [
        "ALTER TABLE decants ADD COLUMN group_price REAL DEFAULT 0",
        "ALTER TABLE decants ADD COLUMN group_active INTEGER DEFAULT 1",
        "ALTER TABLE sale_items ADD COLUMN apc_id INTEGER REFERENCES apc_products(id)",
        "ALTER TABLE order_items ADD COLUMN apc_id INTEGER REFERENCES apc_products(id)",
        "ALTER TABLE perfumes ADD COLUMN price_per_ml REAL DEFAULT 0",
        "ALTER TABLE sale_items ADD COLUMN perfume_id INTEGER REFERENCES perfumes(id)",
        "ALTER TABLE order_items ADD COLUMN perfume_id INTEGER REFERENCES perfumes(id)",
        "ALTER TABLE sale_items ADD COLUMN vial_fee REAL DEFAULT 0",
        "ALTER TABLE order_items ADD COLUMN vial_fee REAL DEFAULT 0",
    ]:
        try:
            db.execute(stmt)
        except sqlite3.OperationalError:
            pass
    # preço final sempre redondo, sem centavos (arredonda o que já estava salvo com decimais)
    db.execute("UPDATE apc_products SET group_price = ROUND(group_price) WHERE group_price > 0")
    db.commit(); db.close()

# Run on module load so gunicorn workers also initialize the DB
init_db()
migrate_db()

# ──────────────────────────── Auth ────────────────────────────

APP_USER     = os.environ.get('APP_USER', 'admin')
APP_PASSWORD = os.environ.get('APP_PASSWORD', 'poderolfativo123')

@app.before_request
def require_login():
    public = {'login', 'logout', 'static'}
    if request.endpoint and request.endpoint not in public:
        if not session.get('logged_in'):
            return redirect(url_for('login', next=request.url))

@app.route('/login', methods=['GET','POST'])
def login():
    if session.get('logged_in'):
        return redirect(url_for('dashboard'))
    error = None
    if request.method == 'POST':
        user = request.form.get('username','').strip()
        pwd  = request.form.get('password','')
        if user == APP_USER and pwd == APP_PASSWORD:
            session.permanent = True
            session['logged_in'] = True
            session['username'] = user
            return redirect(request.form.get('next') or url_for('dashboard'))
        error = 'Usuário ou senha incorretos.'
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


# ──────────────────────────── Context ────────────────────────────

@app.context_processor
def inject_globals():
    low = 0
    try:
        r = query_db("SELECT COUNT(*) c FROM decants WHERE active=1 AND stock_quantity=0", one=True)
        low = r['c'] if r else 0
    except: pass
    return dict(low_stock_count=low)


# ──────────────────────────── Dashboard ────────────────────────────

@app.route('/')
def dashboard():
    total_perfumes = query_db("SELECT COUNT(*) c FROM perfumes WHERE active=1", one=True)['c']
    total_bottles = query_db("SELECT COUNT(*) c FROM bottles WHERE active=1 AND remaining_ml>0", one=True)['c']
    total_suppliers = query_db("SELECT COUNT(*) c FROM suppliers WHERE active=1", one=True)['c']

    sales_month = query_db(
        "SELECT COALESCE(SUM(total),0) s, COUNT(*) c FROM sales WHERE strftime('%Y-%m',sale_date)=strftime('%Y-%m','now','localtime') AND status!='cancelada'",
        one=True)
    # Net revenue = revenue - cogs - payment fees
    net_month = query_db("""
        SELECT
            COALESCE(SUM(s.total),0) revenue,
            COALESCE(SUM(s.payment_fee_amount),0) fees,
            COALESCE((SELECT SUM(si.cost_price * si.quantity) FROM sale_items si
                      JOIN sales ss ON ss.id=si.sale_id
                      WHERE strftime('%Y-%m',ss.sale_date)=strftime('%Y-%m','now','localtime')
                        AND ss.status!='cancelada'),0) cogs
        FROM sales s
        WHERE strftime('%Y-%m',s.sale_date)=strftime('%Y-%m','now','localtime') AND s.status!='cancelada'
    """, one=True)
    net_month_value = net_month['revenue'] - net_month['fees'] - net_month['cogs']

    monthly_sales = query_db("""
        SELECT strftime('%Y-%m',sale_date) month, COALESCE(SUM(total),0) total, COUNT(*) count
        FROM sales WHERE sale_date>=date('now','localtime','-6 months') AND status!='cancelada'
        GROUP BY month ORDER BY month
    """)

    top_decants = query_db("""
        SELECT b.name brand, p.name perfume, SUM(si.quantity) qty,
            SUM(si.size_ml*si.quantity) ml_total, SUM(si.total) revenue
        FROM sale_items si
        JOIN perfumes p ON p.id=si.perfume_id
        JOIN brands b ON b.id=p.brand_id
        JOIN sales s ON s.id=si.sale_id
        WHERE s.status!='cancelada' AND si.perfume_id IS NOT NULL
            AND s.sale_date>=date('now','localtime','-30 days')
        GROUP BY si.perfume_id ORDER BY revenue DESC LIMIT 8
    """)

    stock_value = query_db("""
        SELECT COALESCE(SUM(b.remaining_ml * b.cost_price / b.volume_ml),0) v
        FROM bottles b WHERE b.active=1 AND b.remaining_ml>0
    """, one=True)['v']

    recent_sales = query_db(
        "SELECT id,customer_name,total,payment_method,sale_date FROM sales ORDER BY id DESC LIMIT 8")

    import datetime
    current_month = datetime.date.today().strftime('%Y-%m')
    current_goal = query_db("SELECT * FROM goals WHERE month=?", (current_month,), one=True)
    pending_orders = query_db("SELECT COUNT(*) c FROM orders WHERE status NOT IN ('entregue','cancelado')", one=True)['c']
    return render_template('dashboard.html',
        total_perfumes=total_perfumes, total_bottles=total_bottles,
        net_month_value=net_month_value, net_month=net_month,
        current_goal=current_goal, pending_orders=pending_orders,
        total_suppliers=total_suppliers,
        sales_month=sales_month, monthly_sales=[dict(r) for r in monthly_sales],
        top_decants=top_decants, stock_value=stock_value,
        recent_sales=recent_sales)


# ──────────────────────────── Brands ────────────────────────────

@app.route('/marcas')
def brands():
    rows = query_db("""
        SELECT b.*, COUNT(p.id) total
        FROM brands b LEFT JOIN perfumes p ON p.brand_id=b.id AND p.active=1
        GROUP BY b.id ORDER BY b.name
    """)
    return render_template('brands/index.html', brands=rows)

@app.route('/marcas/novo', methods=['GET','POST'])
def brand_new():
    if request.method=='POST':
        name=request.form['name'].strip(); country=request.form.get('country','').strip()
        if not name: flash('Nome obrigatório.','danger')
        else:
            try: execute_db("INSERT INTO brands(name,country) VALUES(?,?)",(name,country)); flash('Marca criada!','success')
            except: flash('Marca já cadastrada.','warning')
            return redirect(url_for('brands'))
    return render_template('brands/form.html', brand=None)

@app.route('/marcas/<int:id>/editar', methods=['GET','POST'])
def brand_edit(id):
    brand=query_db("SELECT * FROM brands WHERE id=?",(id,),one=True)
    if request.method=='POST':
        execute_db("UPDATE brands SET name=?,country=? WHERE id=?",
                   (request.form['name'].strip(), request.form.get('country','').strip(), id))
        flash('Marca atualizada!','success'); return redirect(url_for('brands'))
    return render_template('brands/form.html', brand=brand)

@app.route('/marcas/<int:id>/excluir', methods=['POST'])
def brand_delete(id):
    execute_db("DELETE FROM brands WHERE id=?",(id,)); flash('Marca removida.','success')
    return redirect(url_for('brands'))


# ──────────────────────────── Perfumes ────────────────────────────

@app.route('/perfumes')
def perfumes():
    q=request.args.get('q',''); brand_id=request.args.get('brand',''); gender=request.args.get('gender','')
    sql="""SELECT p.*,b.name brand_name FROM perfumes p LEFT JOIN brands b ON b.id=p.brand_id WHERE p.active=1"""
    params=[]
    if q: sql+=" AND (p.name LIKE ? OR b.name LIKE ?)"; params+=[f'%{q}%',f'%{q}%']
    if brand_id: sql+=" AND p.brand_id=?"; params.append(brand_id)
    if gender: sql+=" AND p.gender=?"; params.append(gender)
    sql+=" ORDER BY b.name, p.name"
    rows=query_db(sql,params)
    brands_list=query_db("SELECT * FROM brands ORDER BY name")
    return render_template('perfumes/index.html', perfumes=rows, brands=brands_list,
                           q=q, brand_id=brand_id, gender=gender)

@app.route('/perfumes/novo', methods=['GET','POST'])
def perfume_new():
    if request.method=='POST': return _save_perfume(None)
    brands_list=query_db("SELECT * FROM brands ORDER BY name")
    return render_template('perfumes/form.html', perfume=None, brands=brands_list)

@app.route('/perfumes/<int:id>/editar', methods=['GET','POST'])
def perfume_edit(id):
    perfume=query_db("SELECT * FROM perfumes WHERE id=?",(id,),one=True)
    if not perfume: flash('Perfume não encontrado.','danger'); return redirect(url_for('perfumes'))
    if request.method=='POST': return _save_perfume(id)
    brands_list=query_db("SELECT * FROM brands ORDER BY name")
    return render_template('perfumes/form.html', perfume=perfume, brands=brands_list)

def _save_perfume(id):
    f=request.form
    data={k:f.get(k,'').strip() for k in ['name','concentration','gender','family','notes_top','notes_heart','notes_base','description']}
    data['brand_id']=f.get('brand_id') or None
    data['year']=f.get('year') or None
    if not data['name']: flash('Nome obrigatório.','danger'); return redirect(request.url)
    if id is None:
        new_id=execute_db("""INSERT INTO perfumes(brand_id,name,concentration,gender,family,
            notes_top,notes_heart,notes_base,description,year)
            VALUES(:brand_id,:name,:concentration,:gender,:family,
            :notes_top,:notes_heart,:notes_base,:description,:year)""",data)
        # create default decant sizes
        for size in [2.0,5.0,10.0,15.0]:
            try: execute_db("INSERT INTO decants(perfume_id,size_ml) VALUES(?,?)",(new_id,size))
            except: pass
        flash('Perfume cadastrado! Configure os preços dos decants.','success')
        return redirect(url_for('perfume_detail', id=new_id))
    else:
        data['id']=id
        execute_db("""UPDATE perfumes SET brand_id=:brand_id,name=:name,concentration=:concentration,
            gender=:gender,family=:family,notes_top=:notes_top,notes_heart=:notes_heart,
            notes_base=:notes_base,description=:description,year=:year WHERE id=:id""",data)
        flash('Perfume atualizado!','success')
        return redirect(url_for('perfume_detail', id=id))

@app.route('/perfumes/<int:id>/excluir', methods=['POST'])
def perfume_delete(id):
    execute_db("UPDATE perfumes SET active=0 WHERE id=?",(id,))
    flash('Perfume removido.','success'); return redirect(url_for('perfumes'))

@app.route('/perfumes/<int:id>')
def perfume_detail(id):
    perfume=query_db("""SELECT p.*,b.name brand_name FROM perfumes p
        LEFT JOIN brands b ON b.id=p.brand_id WHERE p.id=?""",(id,),one=True)
    if not perfume: flash('Não encontrado.','danger'); return redirect(url_for('perfumes'))
    bottles=query_db("""SELECT bt.*,s.name supplier_name FROM bottles bt
        LEFT JOIN suppliers s ON s.id=bt.supplier_id
        WHERE bt.perfume_id=? AND bt.active=1 ORDER BY bt.id DESC""",(id,))
    apc_list=query_db("SELECT * FROM apc_products WHERE perfume_id=? AND active=1 ORDER BY size_ml",(id,))
    denom, vial_cost_group, net_margin_pct, indirect_pct_total, min_ml, max_ml = _group_pricing_params()
    return render_template('perfumes/detail.html', perfume=perfume, bottles=bottles,
                           apc_list=apc_list, denom=denom, vial_cost_group=vial_cost_group,
                           net_margin_pct=net_margin_pct, indirect_pct_total=indirect_pct_total,
                           min_ml=min_ml, max_ml=max_ml)


# ──────────────────────────── Bottles (frascos originais) ────────────────────────────

@app.route('/frascos')
def bottles():
    rows=query_db("""SELECT bt.*,p.name perfume_name,b.name brand_name,s.name supplier_name,
        ROUND(bt.remaining_ml/bt.volume_ml*100,1) pct_remaining,
        ROUND(bt.cost_price/bt.volume_ml,4) cost_per_ml
        FROM bottles bt
        JOIN perfumes p ON p.id=bt.perfume_id
        LEFT JOIN brands b ON b.id=p.brand_id
        LEFT JOIN suppliers s ON s.id=bt.supplier_id
        WHERE bt.active=1 ORDER BY b.name, p.name, bt.id DESC""")
    return render_template('bottles/index.html', bottles=rows)

@app.route('/frascos/novo', methods=['GET','POST'])
def bottle_new():
    if request.method=='POST':
        perfume_id=int(request.form['perfume_id'])
        vol=float(request.form['volume_ml'])
        cost=float(request.form['cost_price'])
        execute_db("""INSERT INTO bottles(perfume_id,supplier_id,volume_ml,cost_price,remaining_ml,purchase_date,notes)
            VALUES(?,?,?,?,?,?,?)""",(
            perfume_id, request.form.get('supplier_id') or None, vol, cost, vol,
            request.form.get('purchase_date') or None, request.form.get('notes','').strip()))
        flash('Frasco registrado!','success')
        # auto-recalculate group prices (decant + APC)
        _recalculate_group_prices(perfume_id, vol, cost)
        return redirect(url_for('perfume_detail', id=perfume_id))
    perfumes_list=query_db("SELECT p.id,p.name,b.name brand_name FROM perfumes p LEFT JOIN brands b ON b.id=p.brand_id WHERE p.active=1 ORDER BY b.name,p.name")
    suppliers_list=query_db("SELECT * FROM suppliers WHERE active=1 ORDER BY name")
    return render_template('bottles/form.html', perfumes=perfumes_list, suppliers=suppliers_list)


# ──────────────────────────── Precificação Grupo WhatsApp ────────────────────────────

def _group_pricing_params():
    """Retorna (denom, vial_cost_group, net_margin_pct, indirect_pct_total, min_ml, max_ml) já validados.
    denom é None se a soma de custos indiretos + margem passar de 100% (config inválida)."""
    settings_rows = {r['key']: r['value'] for r in query_db("SELECT * FROM group_settings")}
    net_margin_pct = float(settings_rows.get('net_margin_pct', 40) or 0)
    vial_cost_group = float(settings_rows.get('vial_cost_group', 0) or 0)
    min_ml = float(settings_rows.get('min_ml', 2) or 2)
    max_ml = float(settings_rows.get('max_ml', 15) or 15)
    indirect_pct_total = sum(r['pct'] for r in query_db(
        "SELECT * FROM group_indirect_costs WHERE active=1"))
    total_pct = indirect_pct_total + net_margin_pct
    denom = (1 - total_pct / 100) if total_pct < 100 else None
    return denom, vial_cost_group, net_margin_pct, indirect_pct_total, min_ml, max_ml

def _recalculate_group_prices(perfume_id, volume_ml, cost_price):
    """Preço/ml de grupo = custo/ml / (1 - custos_indiretos% - margem_liquida%).
    O custo do frasquinho NÃO entra aqui — é cobrado à parte, na hora da venda.
    APC (frasco original) usa o mesmo denom, mas seu próprio preço por tamanho fixo, sem frasquinho."""
    denom, vial_cost_group, *_ = _group_pricing_params()
    if not denom:
        return False  # configuração de custos/margem inválida (soma >= 100%) — não recalcula
    cost_per_ml = cost_price / volume_ml
    # price_per_ml mantém precisão decimal internamente (é uma taxa, não um preço final) —
    # o arredondamento pra número redondo acontece no preço FINAL cobrado (na venda / no APC).
    price_per_ml = round(cost_per_ml / denom, 4)
    execute_db("UPDATE perfumes SET price_per_ml=? WHERE id=?", (price_per_ml, perfume_id))
    for a in query_db("SELECT * FROM apc_products WHERE perfume_id=? AND active=1", (perfume_id,)):
        direct_cost = cost_per_ml * a['size_ml']
        group_price = round(direct_cost / denom)  # preço final do APC — sempre redondo, sem centavos
        execute_db("UPDATE apc_products SET group_price=? WHERE id=?", (group_price, a['id']))
    return True


@app.route('/frascos/<int:id>/inativar', methods=['POST'])
def bottle_inactivate(id):
    execute_db("UPDATE bottles SET active=0 WHERE id=?",(id,))
    flash('Frasco removido.','success'); return redirect(url_for('bottles'))


# ──────────────────────────── Suppliers ────────────────────────────

@app.route('/fornecedores')
def suppliers():
    q=request.args.get('q','')
    rows=query_db("SELECT * FROM suppliers WHERE active=1" +
                  (" AND (name LIKE ? OR contact_name LIKE ?)" if q else "") +
                  " ORDER BY name", ([f'%{q}%',f'%{q}%'] if q else []))
    return render_template('suppliers/index.html', suppliers=rows, search=q)

@app.route('/fornecedores/novo', methods=['GET','POST'])
def supplier_new():
    if request.method=='POST':
        d={k:request.form.get(k,'').strip() for k in ['name','contact_name','phone','email','address','cnpj','notes']}
        if not d['name']: flash('Nome obrigatório.','danger')
        else:
            execute_db("INSERT INTO suppliers(name,contact_name,phone,email,address,cnpj,notes) VALUES(:name,:contact_name,:phone,:email,:address,:cnpj,:notes)",d)
            flash('Fornecedor cadastrado!','success'); return redirect(url_for('suppliers'))
    return render_template('suppliers/form.html', supplier=None)

@app.route('/fornecedores/<int:id>/editar', methods=['GET','POST'])
def supplier_edit(id):
    supplier=query_db("SELECT * FROM suppliers WHERE id=?",(id,),one=True)
    if request.method=='POST':
        d={k:request.form.get(k,'').strip() for k in ['name','contact_name','phone','email','address','cnpj','notes']}
        d['id']=id
        execute_db("UPDATE suppliers SET name=:name,contact_name=:contact_name,phone=:phone,email=:email,address=:address,cnpj=:cnpj,notes=:notes WHERE id=:id",d)
        flash('Fornecedor atualizado!','success'); return redirect(url_for('suppliers'))
    return render_template('suppliers/form.html', supplier=supplier)

@app.route('/fornecedores/<int:id>/excluir', methods=['POST'])
def supplier_delete(id):
    execute_db("UPDATE suppliers SET active=0 WHERE id=?",(id,))
    flash('Fornecedor removido.','success'); return redirect(url_for('suppliers'))


# ──────────────────────────── Vial costs settings ────────────────────────────

@app.route('/configuracoes', methods=['GET','POST'])
def settings():
    if request.method=='POST':
        for key,val in request.form.items():
            if key.startswith('fee_'):
                method=key[4:].replace('_',' ')
                execute_db("INSERT OR REPLACE INTO payment_fee_defaults(method,fee_pct,label) VALUES(?,?,?)",
                           (method, float(val or 0), method))
        flash('Configurações salvas!','success'); return redirect(url_for('settings'))
    fee_defaults=query_db("SELECT * FROM payment_fee_defaults ORDER BY method")
    return render_template('settings.html', fee_defaults=fee_defaults)


@app.route('/perfumes/<int:id>/recalcular', methods=['POST'])
def perfume_recalculate(id):
    """Recalculate group prices (decant + APC) for a perfume based on its latest bottle cost."""
    bottles=query_db("SELECT * FROM bottles WHERE perfume_id=? AND active=1 AND remaining_ml>0 ORDER BY id DESC",(id,))
    if not bottles:
        flash('Cadastre um frasco original para calcular os preços.','warning')
        return redirect(url_for('perfume_detail', id=id))
    bottle=bottles[0]
    group_ok = _recalculate_group_prices(id, bottle['volume_ml'], bottle['cost_price'])
    if group_ok:
        flash('Preços do grupo WhatsApp recalculados com base no custo atual do frasco.', 'success')
    else:
        flash('Preços NÃO recalculados: custos indiretos + margem somam 100% ou mais — ajuste em Configurações do Grupo.', 'warning')
    return redirect(url_for('perfume_detail', id=id))


@app.route('/grupo/configuracoes', methods=['GET','POST'])
def group_settings():
    if request.method == 'POST':
        net_margin_pct = float(request.form.get('net_margin_pct') or 0)
        vial_cost_group = float(request.form.get('vial_cost_group') or 0)
        min_ml = float(request.form.get('min_ml') or 2)
        max_ml = float(request.form.get('max_ml') or 15)
        execute_db("UPDATE group_settings SET value=? WHERE key='net_margin_pct'", (net_margin_pct,))
        execute_db("UPDATE group_settings SET value=? WHERE key='vial_cost_group'", (vial_cost_group,))
        execute_db("UPDATE group_settings SET value=? WHERE key='min_ml'", (min_ml,))
        execute_db("UPDATE group_settings SET value=? WHERE key='max_ml'", (max_ml,))
        for key, val in request.form.items():
            if key.startswith('indirect_pct_'):
                cost_id = int(key.split('_')[-1])
                try: execute_db("UPDATE group_indirect_costs SET pct=? WHERE id=?", (float(val or 0), cost_id))
                except: pass
        # checkboxes só vêm no form quando marcados — desmarca todos, remarca os presentes
        execute_db("UPDATE group_indirect_costs SET active=0")
        for key in request.form:
            if key.startswith('indirect_active_'):
                cost_id = int(key.split('_')[-1])
                execute_db("UPDATE group_indirect_costs SET active=1 WHERE id=?", (cost_id,))
        flash('Configurações do grupo salvas! Vá no perfume e clique em "Recalcular tudo" para atualizar os preços.', 'success')
        return redirect(url_for('group_settings'))

    denom, vial_cost_group, net_margin_pct, indirect_pct_total, min_ml, max_ml = _group_pricing_params()
    indirect_costs = query_db("SELECT * FROM group_indirect_costs ORDER BY sort_order, id")
    total_pct = indirect_pct_total + net_margin_pct
    return render_template('group/settings.html', indirect_costs=indirect_costs,
                           net_margin_pct=net_margin_pct, vial_cost_group=vial_cost_group,
                           indirect_pct_total=indirect_pct_total, total_pct=total_pct,
                           denom=denom, min_ml=min_ml, max_ml=max_ml)

@app.route('/grupo/custo-indireto/novo', methods=['POST'])
def group_indirect_cost_new():
    label = request.form.get('label','').strip()
    pct = float(request.form.get('pct') or 0)
    if label:
        max_order = query_db("SELECT COALESCE(MAX(sort_order),0) m FROM group_indirect_costs", one=True)['m']
        execute_db("INSERT INTO group_indirect_costs(label,pct,sort_order) VALUES(?,?,?)", (label, pct, max_order+1))
        flash('Custo indireto adicionado!','success')
    return redirect(url_for('group_settings'))

@app.route('/grupo/custo-indireto/<int:id>/excluir', methods=['POST'])
def group_indirect_cost_delete(id):
    execute_db("DELETE FROM group_indirect_costs WHERE id=?", (id,))
    flash('Custo indireto removido.','success')
    return redirect(url_for('group_settings'))


# ──────────────────────────── APC (Apresentação Completa) ────────────────────────────

@app.route('/perfumes/<int:id>/apc/novo', methods=['POST'])
def apc_new(id):
    size_ml = float(request.form.get('size_ml') or 0)
    if size_ml <= 0:
        flash('Informe um tamanho válido.','danger')
        return redirect(url_for('perfume_detail', id=id))
    try:
        execute_db("INSERT INTO apc_products(perfume_id,size_ml) VALUES(?,?)", (id, size_ml))
    except sqlite3.IntegrityError:
        flash('Esse tamanho de APC já existe para este perfume.','warning')
        return redirect(url_for('perfume_detail', id=id))
    bottle = query_db("SELECT * FROM bottles WHERE perfume_id=? AND active=1 ORDER BY id DESC", (id,), one=True)
    if bottle:
        _recalculate_group_prices(id, bottle['volume_ml'], bottle['cost_price'])
    flash('APC adicionado!','success')
    return redirect(url_for('perfume_detail', id=id))

@app.route('/perfumes/<int:pid>/apc/<int:id>/excluir', methods=['POST'])
def apc_delete(pid, id):
    execute_db("DELETE FROM apc_products WHERE id=?", (id,))
    flash('APC removido.','success')
    return redirect(url_for('perfume_detail', id=pid))


# ──────────────────────────── Sales ────────────────────────────

@app.route('/vendas')
def sales():
    q=request.args.get('q',''); df=request.args.get('from',''); dt=request.args.get('to','')
    sql="SELECT * FROM sales WHERE 1=1"; params=[]
    if q: sql+=" AND customer_name LIKE ?"; params.append(f'%{q}%')
    if df: sql+=" AND date(sale_date)>=?"; params.append(df)
    if dt: sql+=" AND date(sale_date)<=?"; params.append(dt)
    sql+=" ORDER BY id DESC LIMIT 300"
    rows=query_db(sql,params)
    total=sum(r['total'] for r in rows if r['status']!='cancelada')
    return render_template('sales/index.html', sales=rows, search=q, date_from=df, date_to=dt, total=total)

@app.route('/vendas/nova', methods=['GET','POST'])
def sale_new():
    if request.method=='POST':
        customer_id = request.form.get('customer_id') or None
        if customer_id:
            c = query_db("SELECT name FROM customers WHERE id=?", (customer_id,), one=True)
            customer = c['name'] if c else 'Consumidor'
        else:
            customer=request.form.get('customer_name','').strip() or 'Consumidor'
        payment=request.form.get('payment_method','Pix')
        fee_pct=float(request.form.get('payment_fee_pct') or 0)
        discount=float(request.form.get('discount') or 0)
        notes=request.form.get('notes','').strip()
        items=json.loads(request.form.get('items_json','[]'))
        if not items: flash('Adicione ao menos um item.','danger'); return redirect(request.url)
        _, vial_cost_group, _, _, min_ml, max_ml = _group_pricing_params()
        # valida ANTES de criar a venda, pra não gerar venda "fantasma" sem itens
        valid_items = [i for i in items if i.get('type')=='apc' or (min_ml <= float(i.get('ml') or 0) <= max_ml)]
        if not valid_items:
            flash('Nenhum item válido (verifique a quantidade em ml).','danger')
            return redirect(request.url)
        for i in valid_items: i['price'] = round(i['price'])  # preço sempre redondo, sem centavos
        subtotal=sum(i['qty']*i['price'] for i in valid_items)
        total=max(0,subtotal-discount)
        fee_amount=round(total*fee_pct/100, 2)
        sale_id=execute_db("INSERT INTO sales(customer_id,customer_name,subtotal,discount,total,payment_method,payment_fee_pct,payment_fee_amount,notes) VALUES(?,?,?,?,?,?,?,?,?)",
                           (customer_id,customer,subtotal,discount,total,payment,fee_pct,fee_amount,notes))
        for i in valid_items:
            if i.get('type') == 'apc':
                apc=query_db("SELECT a.*,p.name pname,b.name bname FROM apc_products a JOIN perfumes p ON p.id=a.perfume_id LEFT JOIN brands b ON b.id=p.brand_id WHERE a.id=?",(i['id'],),one=True)
                if not apc: continue
                label=f"{apc['bname']} {apc['pname']} {apc['size_ml']:.0f}ml (APC)"
                bottle=query_db("""SELECT bt.id,bt.cost_price,bt.volume_ml,bt.remaining_ml FROM bottles bt
                    WHERE bt.perfume_id=? AND bt.active=1 ORDER BY bt.id DESC LIMIT 1""",
                    (apc['perfume_id'],),one=True)
                ml_needed=apc['size_ml']*i['qty']
                if bottle and bottle['remaining_ml']>=ml_needed:
                    cost_unit=round(bottle['cost_price']/bottle['volume_ml']*apc['size_ml'],4)
                    execute_db("UPDATE bottles SET remaining_ml=remaining_ml-? WHERE id=?",(ml_needed,bottle['id']))
                else:
                    cost_unit=0
                    flash(f"Aviso: frasco sem ml suficiente para o APC {apc['pname']} {apc['size_ml']:.0f}ml — venda registrada, confira o estoque do frasco.",'warning')
                execute_db("INSERT INTO sale_items(sale_id,apc_id,product_label,size_ml,quantity,unit_price,cost_price,total) VALUES(?,?,?,?,?,?,?,?)",
                           (sale_id,i['id'],label,apc['size_ml'],i['qty'],i['price'],cost_unit,i['qty']*i['price']))
            else:
                # decant sob demanda: i['id'] = perfume_id, i['ml'] = quantidade em ml escolhida (livre)
                perfume=query_db("SELECT p.*,b.name bname FROM perfumes p LEFT JOIN brands b ON b.id=p.brand_id WHERE p.id=?",(i['id'],),one=True)
                if not perfume: continue
                ml=float(i.get('ml') or 0)
                if ml < min_ml or ml > max_ml: continue
                label=f"{perfume['bname']} {perfume['name']} {ml:g}ml"
                bottle=query_db("""SELECT bt.id,bt.cost_price,bt.volume_ml,bt.remaining_ml FROM bottles bt
                    WHERE bt.perfume_id=? AND bt.active=1 ORDER BY bt.id DESC LIMIT 1""",
                    (perfume['id'],),one=True)
                ml_needed=ml*i['qty']
                if bottle and bottle['remaining_ml']>=ml_needed:
                    cost_unit=round(bottle['cost_price']/bottle['volume_ml']*ml+vial_cost_group,4)
                    execute_db("UPDATE bottles SET remaining_ml=remaining_ml-? WHERE id=?",(ml_needed,bottle['id']))
                else:
                    cost_unit=vial_cost_group
                    flash(f"Aviso: frasco sem ml suficiente para {perfume['name']} {ml:g}ml — venda registrada, confira o estoque do frasco.",'warning')
                execute_db("""INSERT INTO sale_items(sale_id,perfume_id,product_label,size_ml,quantity,unit_price,cost_price,total,vial_fee)
                    VALUES(?,?,?,?,?,?,?,?,?)""",
                    (sale_id,perfume['id'],label,ml,i['qty'],i['price'],cost_unit,i['qty']*i['price'],vial_cost_group))
        flash(f'Venda #{sale_id} registrada! Total: R$ {total:.2f}','success')
        return redirect(url_for('sale_detail', id=sale_id))

    _, vial_cost_group, _, _, min_ml, max_ml = _group_pricing_params()
    perfumes_list=query_db("""SELECT p.id,p.price_per_ml,p.name,b.name brand_name,p.concentration
        FROM perfumes p LEFT JOIN brands b ON b.id=p.brand_id
        WHERE p.active=1 AND p.price_per_ml>0 ORDER BY b.name,p.name""")
    apc_list=query_db("""SELECT a.id,a.size_ml,a.group_price,
        p.name perfume_name,b.name brand_name,p.concentration
        FROM apc_products a JOIN perfumes p ON p.id=a.perfume_id LEFT JOIN brands b ON b.id=p.brand_id
        WHERE a.active=1 AND a.group_price>0 ORDER BY b.name,p.name,a.size_ml""")
    customers_list = query_db("SELECT id, name, phone FROM customers WHERE active=1 ORDER BY name")
    fee_defaults = {r['method']: r['fee_pct'] for r in query_db("SELECT method, fee_pct FROM payment_fee_defaults")}
    return render_template('sales/new.html', perfumes=perfumes_list, apc_products=apc_list,
                           customers=customers_list, fee_defaults=fee_defaults,
                           vial_cost_group=vial_cost_group, min_ml=min_ml, max_ml=max_ml)

@app.route('/vendas/<int:id>')
def sale_detail(id):
    sale=query_db("SELECT * FROM sales WHERE id=?",(id,),one=True)
    if not sale: flash('Venda não encontrada.','danger'); return redirect(url_for('sales'))
    items=query_db("SELECT * FROM sale_items WHERE sale_id=?",(id,))
    return render_template('sales/detail.html', sale=sale, items=items)

@app.route('/vendas/<int:id>/cancelar', methods=['POST'])
def sale_cancel(id):
    sale=query_db("SELECT * FROM sales WHERE id=?",(id,),one=True)
    if sale and sale['status']!='cancelada':
        items=query_db("SELECT * FROM sale_items WHERE sale_id=?",(id,))
        for i in items:
            perfume_id = None
            if i['apc_id']:
                apc=query_db("SELECT perfume_id FROM apc_products WHERE id=?",(i['apc_id'],),one=True)
                if apc: perfume_id = apc['perfume_id']
            elif i['perfume_id']:
                perfume_id = i['perfume_id']
            elif i['decant_id']:
                # vendas antigas (pré-decant-sob-demanda), ainda usam stock_quantity de decants
                execute_db("UPDATE decants SET stock_quantity=stock_quantity+? WHERE id=?",(i['quantity'],i['decant_id']))
                continue
            if perfume_id:
                bottle=query_db("""SELECT id FROM bottles WHERE perfume_id=? AND active=1
                    ORDER BY id DESC LIMIT 1""",(perfume_id,),one=True)
                if bottle:
                    execute_db("UPDATE bottles SET remaining_ml=remaining_ml+? WHERE id=?",
                               (i['size_ml']*i['quantity'],bottle['id']))
        execute_db("UPDATE sales SET status='cancelada' WHERE id=?",(id,))
        flash('Venda cancelada e estoque restaurado.','warning')
    return redirect(url_for('sale_detail', id=id))


# ──────────────────────────── Reports ────────────────────────────

@app.route('/relatorios')
def reports():
    period=request.args.get('period','30'); days=int(period)
    sales_data=query_db(f"""
        SELECT strftime('%Y-%m-%d',sale_date) day, SUM(total) total, COUNT(*) count
        FROM sales WHERE date(sale_date)>=date('now','localtime','-{days} days') AND status!='cancelada'
        GROUP BY day ORDER BY day""")
    total_revenue=sum(r['total'] for r in sales_data)
    total_count=sum(r['count'] for r in sales_data)
    avg_ticket=total_revenue/total_count if total_count else 0

    top_decants=query_db(f"""
        SELECT b.name brand,p.name perfume,d.size_ml,SUM(si.quantity) qty,SUM(si.total) revenue
        FROM sale_items si JOIN decants d ON d.id=si.decant_id
        JOIN perfumes p ON p.id=d.perfume_id JOIN brands b ON b.id=p.brand_id
        JOIN sales s ON s.id=si.sale_id
        WHERE date(s.sale_date)>=date('now','localtime','-{days} days') AND s.status!='cancelada'
        GROUP BY d.id ORDER BY revenue DESC LIMIT 10""")

    top_brands=query_db(f"""
        SELECT b.name brand,SUM(si.quantity) qty,SUM(si.total) revenue
        FROM sale_items si JOIN decants d ON d.id=si.decant_id
        JOIN perfumes p ON p.id=d.perfume_id JOIN brands b ON b.id=p.brand_id
        JOIN sales s ON s.id=si.sale_id
        WHERE date(s.sale_date)>=date('now','localtime','-{days} days') AND s.status!='cancelada'
        GROUP BY b.id ORDER BY revenue DESC LIMIT 8""")

    by_size=query_db(f"""
        SELECT d.size_ml,SUM(si.quantity) qty,SUM(si.total) revenue
        FROM sale_items si JOIN decants d ON d.id=si.decant_id
        JOIN sales s ON s.id=si.sale_id
        WHERE date(s.sale_date)>=date('now','localtime','-{days} days') AND s.status!='cancelada'
        GROUP BY d.size_ml ORDER BY qty DESC""")

    payment_methods=query_db(f"""
        SELECT payment_method,COUNT(*) count,SUM(total) total FROM sales
        WHERE date(sale_date)>=date('now','localtime','-{days} days') AND status!='cancelada'
        GROUP BY payment_method ORDER BY total DESC""")

    stock_value=query_db("SELECT COALESCE(SUM(remaining_ml*cost_price/volume_ml),0) v FROM bottles WHERE active=1 AND remaining_ml>0",one=True)['v']

    return render_template('reports/index.html',
        period=period,total_revenue=total_revenue,total_count=total_count,avg_ticket=avg_ticket,
        sales_data=[dict(r) for r in sales_data],
        top_decants=top_decants,top_brands=top_brands,by_size=by_size,
        payment_methods=payment_methods,stock_value=stock_value)


# ──────────────────────────── Orders ────────────────────────────

ORDER_STATUSES = [
    ('pendente',  'Pendente',   'secondary'),
    ('producao',  'Em Produção','warning'),
    ('pronto',    'Pronto',     'info'),
    ('enviado',   'Enviado',    'primary'),
    ('entregue',  'Entregue',   'success'),
    ('cancelado', 'Cancelado',  'danger'),
]
STATUS_LABEL = {s[0]: s[1] for s in ORDER_STATUSES}
STATUS_COLOR = {s[0]: s[2] for s in ORDER_STATUSES}

@app.route('/pedidos')
def orders():
    status_filter = request.args.get('status','')
    q = request.args.get('q','')
    sql = "SELECT * FROM orders WHERE 1=1"
    params = []
    if status_filter: sql += " AND status=?"; params.append(status_filter)
    if q: sql += " AND customer_name LIKE ?"; params.append(f'%{q}%')
    sql += " ORDER BY id DESC LIMIT 300"
    rows = query_db(sql, params)
    counts = {r['status']: r['c'] for r in query_db(
        "SELECT status, COUNT(*) c FROM orders GROUP BY status")}
    return render_template('orders/index.html', orders=rows, counts=counts,
                           status_filter=status_filter, q=q,
                           STATUS_LABEL=STATUS_LABEL, STATUS_COLOR=STATUS_COLOR,
                           ORDER_STATUSES=ORDER_STATUSES)

@app.route('/pedidos/novo', methods=['GET','POST'])
def order_new():
    if request.method == 'POST':
        import datetime
        now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        customer_id = request.form.get('customer_id') or None
        if customer_id:
            c = query_db("SELECT name FROM customers WHERE id=?", (customer_id,), one=True)
            customer_name = c['name'] if c else 'Cliente'
        else:
            customer_name = request.form.get('customer_name','').strip() or 'Cliente'
        discount = float(request.form.get('discount') or 0)
        notes = request.form.get('notes','').strip()
        items = json.loads(request.form.get('items_json','[]'))
        if not items: flash('Adicione ao menos um item.','danger'); return redirect(request.url)
        _, _, _, _, min_ml, max_ml = _group_pricing_params()
        valid_items = [i for i in items if i.get('type')=='apc' or (min_ml <= float(i.get('ml') or 0) <= max_ml)]
        if not valid_items:
            flash('Nenhum item válido (verifique a quantidade em ml).','danger')
            return redirect(request.url)
        for i in valid_items: i['price'] = round(i['price'])  # preço sempre redondo, sem centavos
        subtotal = sum(i['qty']*i['price'] for i in valid_items)
        total = max(0, subtotal - discount)
        oid = execute_db("""INSERT INTO orders(customer_id,customer_name,subtotal,discount,total,notes,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?)""",(customer_id,customer_name,subtotal,discount,total,notes,now,now))
        for i in valid_items:
            if i.get('type') == 'apc':
                a = query_db("SELECT a.*,p.name pname,b.name bname FROM apc_products a JOIN perfumes p ON p.id=a.perfume_id LEFT JOIN brands b ON b.id=p.brand_id WHERE a.id=?", (i['id'],), one=True)
                if not a: continue
                label = f"{a['bname']} {a['pname']} {a['size_ml']:.0f}ml (APC)"
                execute_db("INSERT INTO order_items(order_id,apc_id,product_label,size_ml,quantity,unit_price,total) VALUES(?,?,?,?,?,?,?)",
                           (oid,i['id'],label,a['size_ml'],i['qty'],i['price'],i['qty']*i['price']))
            else:
                p = query_db("SELECT p.*,b.name bname FROM perfumes p LEFT JOIN brands b ON b.id=p.brand_id WHERE p.id=?", (i['id'],), one=True)
                if not p: continue
                ml = float(i.get('ml') or 0)
                if ml < min_ml or ml > max_ml: continue
                label = f"{p['bname']} {p['name']} {ml:g}ml"
                execute_db("INSERT INTO order_items(order_id,perfume_id,product_label,size_ml,quantity,unit_price,total) VALUES(?,?,?,?,?,?,?)",
                           (oid,i['id'],label,ml,i['qty'],i['price'],i['qty']*i['price']))
        flash(f'Pedido #{oid} criado!','success')
        return redirect(url_for('order_detail', id=oid))
    _, vial_cost_group, _, _, min_ml, max_ml = _group_pricing_params()
    perfumes_list = query_db("""SELECT p.id,p.price_per_ml,p.name,b.name brand_name,p.concentration
        FROM perfumes p LEFT JOIN brands b ON b.id=p.brand_id
        WHERE p.active=1 AND p.price_per_ml>0 ORDER BY b.name,p.name""")
    apc_list = query_db("""SELECT a.id,a.size_ml,a.group_price,p.name perfume_name,b.name brand_name,p.concentration
        FROM apc_products a JOIN perfumes p ON p.id=a.perfume_id LEFT JOIN brands b ON b.id=p.brand_id
        WHERE a.active=1 AND a.group_price>0 ORDER BY b.name,p.name,a.size_ml""")
    customers_list = query_db("SELECT id,name,phone FROM customers WHERE active=1 ORDER BY name")
    return render_template('orders/form.html', perfumes=perfumes_list, apc_products=apc_list,
                           customers=customers_list, vial_cost_group=vial_cost_group,
                           min_ml=min_ml, max_ml=max_ml)

@app.route('/pedidos/<int:id>')
def order_detail(id):
    order = query_db("SELECT o.*,c.phone,c.cep,c.street,c.number,c.complement,c.neighborhood,c.city,c.state FROM orders o LEFT JOIN customers c ON c.id=o.customer_id WHERE o.id=?", (id,), one=True)
    if not order: flash('Pedido não encontrado.','danger'); return redirect(url_for('orders'))
    items = query_db("SELECT * FROM order_items WHERE order_id=?", (id,))
    return render_template('orders/detail.html', order=order, items=items,
                           STATUS_LABEL=STATUS_LABEL, STATUS_COLOR=STATUS_COLOR, ORDER_STATUSES=ORDER_STATUSES)

@app.route('/pedidos/<int:id>/status', methods=['POST'])
def order_status(id):
    import datetime
    new_status = request.form['status']
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    execute_db("UPDATE orders SET status=?,updated_at=? WHERE id=?", (new_status,now,id))
    if new_status == 'enviado':
        tracking = request.form.get('tracking_code','').strip()
        shipping = request.form.get('shipping_method','').strip()
        execute_db("UPDATE orders SET tracking_code=?,shipping_method=?,shipped_at=? WHERE id=?",
                   (tracking,shipping,now,id))
    if new_status == 'entregue':
        execute_db("UPDATE orders SET delivered_at=? WHERE id=?", (now,id))
    flash(f'Status atualizado para {STATUS_LABEL.get(new_status, new_status)}.','success')
    return redirect(url_for('order_detail', id=id))

@app.route('/pedidos/<int:id>/converter', methods=['POST'])
def order_to_sale(id):
    import datetime
    order = query_db("SELECT * FROM orders WHERE id=?", (id,), one=True)
    if not order: flash('Pedido não encontrado.','danger'); return redirect(url_for('orders'))
    items = query_db("SELECT * FROM order_items WHERE order_id=?", (id,))
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    payment = request.form.get('payment_method','Pix')
    fee_pct = float(request.form.get('payment_fee_pct') or 0)
    fee_amount = round(order['total']*fee_pct/100, 2)
    sale_id = execute_db("""INSERT INTO sales(customer_id,customer_name,subtotal,discount,total,
        payment_method,payment_fee_pct,payment_fee_amount,notes)
        VALUES(?,?,?,?,?,?,?,?,?)""",
        (order['customer_id'],order['customer_name'],order['subtotal'],order['discount'],
         order['total'],payment,fee_pct,fee_amount,f'Convertido do Pedido #{id}'))
    _, vial_cost_group, *_ = _group_pricing_params()
    for i in items:
        if i['apc_id']:
            a = query_db("SELECT * FROM apc_products WHERE id=?", (i['apc_id'],), one=True)
            bottle = query_db("""SELECT bt.id,bt.cost_price,bt.volume_ml,bt.remaining_ml FROM bottles bt
                WHERE bt.perfume_id=? AND bt.active=1 ORDER BY bt.id DESC LIMIT 1""",
                (a['perfume_id'] if a else None,), one=True)
            ml_needed = i['size_ml']*i['quantity']
            if bottle and bottle['remaining_ml']>=ml_needed:
                cost_unit = round(bottle['cost_price']/bottle['volume_ml']*i['size_ml'],4)
                execute_db("UPDATE bottles SET remaining_ml=remaining_ml-? WHERE id=?",(ml_needed,bottle['id']))
            else:
                cost_unit = 0
                flash(f"Aviso: frasco sem ml suficiente para o APC {i['product_label']} — convertido mesmo assim, confira o estoque.",'warning')
            execute_db("""INSERT INTO sale_items(sale_id,apc_id,product_label,size_ml,quantity,unit_price,cost_price,total)
                VALUES(?,?,?,?,?,?,?,?)""",
                (sale_id,i['apc_id'],i['product_label'],i['size_ml'],i['quantity'],i['unit_price'],cost_unit,i['total']))
        else:
            bottle = query_db("""SELECT bt.id,bt.cost_price,bt.volume_ml,bt.remaining_ml FROM bottles bt
                WHERE bt.perfume_id=? AND bt.active=1 ORDER BY bt.id DESC LIMIT 1""",
                (i['perfume_id'],), one=True)
            ml_needed = i['size_ml']*i['quantity']
            if bottle and bottle['remaining_ml']>=ml_needed:
                cost_unit = round(bottle['cost_price']/bottle['volume_ml']*i['size_ml']+vial_cost_group,4)
                execute_db("UPDATE bottles SET remaining_ml=remaining_ml-? WHERE id=?",(ml_needed,bottle['id']))
            else:
                cost_unit = vial_cost_group
                flash(f"Aviso: frasco sem ml suficiente para {i['product_label']} — convertido mesmo assim, confira o estoque.",'warning')
            execute_db("""INSERT INTO sale_items(sale_id,perfume_id,product_label,size_ml,quantity,unit_price,cost_price,total,vial_fee)
                VALUES(?,?,?,?,?,?,?,?,?)""",
                (sale_id,i['perfume_id'],i['product_label'],i['size_ml'],i['quantity'],i['unit_price'],cost_unit,i['total'],vial_cost_group))
    execute_db("UPDATE orders SET status='entregue',updated_at=? WHERE id=?", (now,id))
    flash(f'Pedido convertido em Venda #{sale_id}!','success')
    return redirect(url_for('sale_detail', id=sale_id))


# ──────────────────────────── Perfume photo upload ────────────────────────────

@app.route('/perfumes/<int:id>/upload-foto', methods=['POST'])
def perfume_upload_photo(id):
    if 'photo' not in request.files:
        flash('Nenhum arquivo.', 'warning')
        return redirect(url_for('perfume_detail', id=id))
    file = request.files['photo']
    if not file or file.filename == '':
        flash('Nenhum arquivo selecionado.', 'warning')
        return redirect(url_for('perfume_detail', id=id))
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ['.jpg','.jpeg','.png','.webp']:
        flash('Use JPG ou PNG.', 'danger')
        return redirect(url_for('perfume_detail', id=id))
    filename = f'perfume_{id}{ext}'
    photos_dir = os.path.join(app.root_path, 'static', 'perfume_photos')
    os.makedirs(photos_dir, exist_ok=True)
    file.save(os.path.join(photos_dir, filename))
    execute_db("UPDATE perfumes SET photo_filename=? WHERE id=?", (filename, id))
    flash('Foto do frasco salva!', 'success')
    return redirect(url_for('perfume_detail', id=id))


# ──────────────────────────── Labels ────────────────────────────

@app.route('/etiquetas')
def labels():
    perfumes_list = query_db("""
        SELECT p.*,b.name brand_name
        FROM perfumes p
        LEFT JOIN brands b ON b.id=p.brand_id
        WHERE p.active=1 AND p.price_per_ml>0
        ORDER BY b.name,p.name
    """)
    return render_template('labels/index.html', perfumes=perfumes_list)

@app.route('/etiquetas/imprimir')
def labels_print():
    ids = request.args.getlist('ids')
    qty = int(request.args.get('qty', 1))
    label_size = request.args.get('label_size', '80x45')
    show_price = request.args.get('show_price', '1')
    show_notes = request.args.get('show_notes', '1')
    if not ids:
        flash('Selecione ao menos um perfume.','warning')
        return redirect(url_for('labels'))
    _, vial_cost_group, _, _, min_ml, max_ml = _group_pricing_params()
    perfumes_list = query_db(f"""
        SELECT p.*,b.name brand_name
        FROM perfumes p
        LEFT JOIN brands b ON b.id=p.brand_id
        WHERE p.id IN ({','.join('?'*len(ids))})
        ORDER BY b.name,p.name
    """, ids)
    w, h = label_size.split('x')
    import base64

    def to_b64(path):
        if path and os.path.exists(path):
            with open(path, 'rb') as f:
                ext = os.path.splitext(path)[1].lstrip('.') or 'png'
                return f'data:image/{ext};base64,' + base64.b64encode(f.read()).decode()
        return ''

    logo_b64 = to_b64(os.path.join(app.root_path, 'static', 'logo.png'))

    # Base64 das fotos dos perfumes para evitar CORS no html2canvas
    photo_b64 = {}
    for p in perfumes_list:
        if p['photo_filename']:
            photo_b64[p['id']] = to_b64(os.path.join(app.root_path, 'static', 'perfume_photos', p['photo_filename']))

    return render_template('labels/print.html', perfumes=perfumes_list, qty=qty,
                           label_w=w, label_h=h, show_price=show_price, show_notes=show_notes,
                           vial_cost_group=vial_cost_group, min_ml=min_ml, max_ml=max_ml,
                           logo_b64=logo_b64, photo_b64=photo_b64)


# ──────────────────────────── DRE ────────────────────────────

@app.route('/relatorios/dre')
def dre():
    year = int(request.args.get('year', __import__('datetime').date.today().year))
    months = []
    for m in range(1, 13):
        period = f'{year}-{m:02d}'
        row = query_db(f"""
            SELECT
                COALESCE(SUM(s.total),0) receita_bruta,
                COALESCE(SUM(s.discount),0) descontos,
                COALESCE(SUM(s.payment_fee_amount),0) taxas,
                COALESCE((SELECT SUM(si.cost_price*si.quantity) FROM sale_items si
                    JOIN sales ss ON ss.id=si.sale_id
                    WHERE strftime('%Y-%m',ss.sale_date)=? AND ss.status!='cancelada'),0) cmv,
                COUNT(*) qtd_vendas
            FROM sales s WHERE strftime('%Y-%m',s.sale_date)=? AND s.status!='cancelada'
        """, (period, period), one=True)
        receita_liq = row['receita_bruta'] - row['descontos']
        lucro_bruto = receita_liq - row['cmv']
        lucro_liq = lucro_bruto - row['taxas']
        margem = (lucro_liq / receita_liq * 100) if receita_liq else 0
        months.append({'period': period, 'month': m, **dict(row),
                       'receita_liq': receita_liq, 'lucro_bruto': lucro_bruto,
                       'lucro_liq': lucro_liq, 'margem': margem})
    totals = {k: sum(m[k] for m in months) for k in
              ['receita_bruta','descontos','taxas','cmv','receita_liq','lucro_bruto','lucro_liq','qtd_vendas']}
    totals['margem'] = (totals['lucro_liq']/totals['receita_liq']*100) if totals['receita_liq'] else 0
    return render_template('reports/dre.html', months=months, totals=totals, year=year)


# ──────────────────────────── Export CSV ────────────────────────────

@app.route('/relatorios/exportar/vendas')
def export_sales_csv():
    import csv, io
    df = request.args.get('from','')
    dt = request.args.get('to','')
    sql = "SELECT s.*,GROUP_CONCAT(si.product_label||' x'||si.quantity,' | ') items FROM sales s LEFT JOIN sale_items si ON si.sale_id=s.id WHERE s.status!='cancelada'"
    params = []
    if df: sql += " AND date(s.sale_date)>=?"; params.append(df)
    if dt: sql += " AND date(s.sale_date)<=?"; params.append(dt)
    sql += " GROUP BY s.id ORDER BY s.id DESC"
    rows = query_db(sql, params)
    output = io.StringIO()
    w = csv.writer(output)
    w.writerow(['#','Data','Cliente','Itens','Pagamento','Taxa %','Taxa R$','Subtotal','Desconto','Total'])
    for r in rows:
        w.writerow([r['id'],r['sale_date'][:16],r['customer_name'],r['items'] or '',
                    r['payment_method'],r['payment_fee_pct'],f"{r['payment_fee_amount']:.2f}",
                    f"{r['subtotal']:.2f}",f"{r['discount']:.2f}",f"{r['total']:.2f}"])
    from flask import Response
    return Response(output.getvalue(), mimetype='text/csv; charset=utf-8',
        headers={'Content-Disposition': 'attachment; filename=vendas_poder_olfativo.csv'})

@app.route('/relatorios/exportar/pedidos')
def export_orders_csv():
    import csv, io
    rows = query_db("SELECT o.*,GROUP_CONCAT(oi.product_label||' x'||oi.quantity,' | ') items FROM orders o LEFT JOIN order_items oi ON oi.order_id=o.id GROUP BY o.id ORDER BY o.id DESC")
    output = io.StringIO()
    w = csv.writer(output)
    w.writerow(['#','Data','Cliente','Status','Itens','Total','Envio','Rastreio'])
    for r in rows:
        w.writerow([r['id'],r['created_at'][:16] if r['created_at'] else '',r['customer_name'],
                    STATUS_LABEL.get(r['status'],r['status']),r['items'] or '',
                    f"{r['total']:.2f}",r['shipping_method'] or '',r['tracking_code'] or ''])
    from flask import Response
    return Response(output.getvalue(), mimetype='text/csv; charset=utf-8',
        headers={'Content-Disposition': 'attachment; filename=pedidos_poder_olfativo.csv'})


# ──────────────────────────── Goals ────────────────────────────

@app.route('/metas', methods=['GET','POST'])
def goals():
    import datetime
    if request.method == 'POST':
        month = request.form['month']
        revenue_goal = float(request.form.get('revenue_goal') or 0)
        orders_goal = int(request.form.get('orders_goal') or 0)
        execute_db("INSERT OR REPLACE INTO goals(month,revenue_goal,orders_goal) VALUES(?,?,?)",
                   (month, revenue_goal, orders_goal))
        flash('Meta salva!','success')
        return redirect(url_for('goals'))
    current_month = datetime.date.today().strftime('%Y-%m')
    goals_list = query_db("SELECT * FROM goals ORDER BY month DESC LIMIT 12")
    current_goal = query_db("SELECT * FROM goals WHERE month=?", (current_month,), one=True)
    current_sales = query_db("""SELECT COALESCE(SUM(total),0) s, COUNT(*) c FROM sales
        WHERE strftime('%Y-%m',sale_date)=? AND status!='cancelada'""", (current_month,), one=True)
    return render_template('goals/index.html', goals=goals_list, current_goal=current_goal,
                           current_sales=current_sales, current_month=current_month)


# ──────────────────────────── Customers ────────────────────────────

@app.route('/clientes')
def customers():
    q = request.args.get('q','')
    rows = query_db("SELECT * FROM customers WHERE active=1" +
        (" AND (name LIKE ? OR phone LIKE ?)" if q else "") + " ORDER BY name",
        ([f'%{q}%',f'%{q}%'] if q else []))
    return render_template('customers/index.html', customers=rows, search=q)

@app.route('/clientes/novo', methods=['GET','POST'])
def customer_new():
    if request.method == 'POST':
        return _save_customer(None)
    return render_template('customers/form.html', customer=None)

@app.route('/clientes/<int:id>/editar', methods=['GET','POST'])
def customer_edit(id):
    customer = query_db("SELECT * FROM customers WHERE id=?", (id,), one=True)
    if not customer:
        flash('Cliente não encontrado.','danger')
        return redirect(url_for('customers'))
    if request.method == 'POST':
        return _save_customer(id)
    return render_template('customers/form.html', customer=customer)

def _save_customer(id):
    f = request.form
    data = {k: f.get(k,'').strip() for k in
            ['name','phone','email','cep','street','number','complement','neighborhood','city','state','notes']}
    if not data['name']:
        flash('Nome é obrigatório.','danger')
        return redirect(request.url)
    import datetime
    if id is None:
        data['created_at'] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        execute_db("""INSERT INTO customers(name,phone,email,cep,street,number,complement,
            neighborhood,city,state,notes,created_at)
            VALUES(:name,:phone,:email,:cep,:street,:number,:complement,
            :neighborhood,:city,:state,:notes,:created_at)""", data)
        flash('Cliente cadastrado!','success')
    else:
        data['id'] = id
        execute_db("""UPDATE customers SET name=:name,phone=:phone,email=:email,cep=:cep,
            street=:street,number=:number,complement=:complement,neighborhood=:neighborhood,
            city=:city,state=:state,notes=:notes WHERE id=:id""", data)
        flash('Cliente atualizado!','success')
    return redirect(url_for('customers'))

@app.route('/clientes/<int:id>')
def customer_detail(id):
    customer = query_db("SELECT * FROM customers WHERE id=?", (id,), one=True)
    if not customer: flash('Cliente não encontrado.','danger'); return redirect(url_for('customers'))
    sales = query_db("""SELECT s.*,COUNT(si.id) item_count,
        GROUP_CONCAT(si.product_label || ' x' || si.quantity, ' | ') items_detail
        FROM sales s LEFT JOIN sale_items si ON si.sale_id=s.id
        WHERE s.customer_id=? AND s.status!='cancelada' GROUP BY s.id ORDER BY s.id DESC""", (id,))
    orders = query_db("SELECT * FROM orders WHERE customer_id=? ORDER BY id DESC", (id,))
    total_spent = sum(s['total'] for s in sales)
    top_perfumes = query_db("""SELECT si.product_label, SUM(si.quantity) qty, SUM(si.total) total
        FROM sale_items si JOIN sales s ON s.id=si.sale_id
        WHERE s.customer_id=? AND s.status!='cancelada'
        GROUP BY si.product_label ORDER BY qty DESC LIMIT 5""", (id,))
    return render_template('customers/detail.html', customer=customer, sales=sales,
                           orders=orders, total_spent=total_spent, top_perfumes=top_perfumes,
                           STATUS_LABEL=STATUS_LABEL, STATUS_COLOR=STATUS_COLOR)

@app.route('/clientes/<int:id>/excluir', methods=['POST'])
def customer_delete(id):
    execute_db("UPDATE customers SET active=0 WHERE id=?", (id,))
    flash('Cliente removido.','success')
    return redirect(url_for('customers'))


# ──────────────────────────── Materials ────────────────────────────

@app.route('/materiais')
def materials():
    rows = query_db("""
        SELECT m.*,
            GROUP_CONCAT(DISTINCT msm.size_ml) as sizes
        FROM materials m
        LEFT JOIN material_size_map msm ON msm.material_id=m.id
        WHERE m.active=1 GROUP BY m.id ORDER BY m.id
    """)
    # compute container cost per decant size from materials
    size_costs = _compute_size_costs()
    return render_template('materials/index.html', materials=rows, size_costs=size_costs)

@app.route('/materiais/salvar', methods=['POST'])
def materials_save():
    for key, val in request.form.items():
        if key.startswith('cost_'):
            mid = int(key.split('_')[1])
            execute_db("UPDATE materials SET cost_per_unit=? WHERE id=?", (float(val or 0), mid))
        elif key.startswith('stock_'):
            mid = int(key.split('_')[1])
            execute_db("UPDATE materials SET stock_quantity=? WHERE id=?", (float(val or 0), mid))
        elif key.startswith('min_'):
            mid = int(key.split('_')[1])
            execute_db("UPDATE materials SET min_stock=? WHERE id=?", (float(val or 0), mid))
    # sync vial_costs from material costs
    _sync_vial_costs()
    flash('Materiais salvos! Custos dos frasquinhos atualizados automaticamente.','success')
    return redirect(url_for('materials'))

@app.route('/materiais/entrada', methods=['POST'])
def material_entry():
    mid = int(request.form['material_id'])
    qty = float(request.form['quantity'] or 0)
    cost = request.form.get('cost_per_unit','').strip()
    if qty > 0:
        execute_db("UPDATE materials SET stock_quantity=stock_quantity+? WHERE id=?", (qty, mid))
        if cost:
            execute_db("UPDATE materials SET cost_per_unit=? WHERE id=?", (float(cost), mid))
            _sync_vial_costs()
    flash('Estoque de material atualizado!','success')
    return redirect(url_for('materials'))

def _compute_size_costs():
    """Returns dict: size_ml -> total container cost from materials."""
    materials_list = query_db("SELECT id, cost_per_unit FROM materials WHERE active=1")
    cost_map = {m['id']: m['cost_per_unit'] for m in materials_list}
    maps = query_db("SELECT material_id, size_ml, qty_per_decant FROM material_size_map")
    size_costs = {}
    for row in maps:
        s = row['size_ml']
        cost = cost_map.get(row['material_id'], 0) * row['qty_per_decant']
        size_costs[s] = size_costs.get(s, 0) + cost
    return size_costs

def _sync_vial_costs():
    """Update vial_costs.cost based on current material costs."""
    size_costs = _compute_size_costs()
    for size_ml, total_cost in size_costs.items():
        execute_db("UPDATE vial_costs SET cost=? WHERE size_ml=?", (round(total_cost, 4), size_ml))


# ──────────────────────────── Contas a Pagar ────────────────────────────

import datetime as _dt

def _payable_status(row):
    if row['status'] == 'pago':
        return 'pago'
    if row['due_date'] < _dt.date.today().isoformat():
        return 'atrasado'
    return 'pendente'

@app.route('/contas-pagar')
def payables():
    status_filter = request.args.get('status', '')
    rows = query_db("""SELECT ap.*, s.name supplier_name FROM accounts_payable ap
        LEFT JOIN suppliers s ON s.id=ap.supplier_id ORDER BY ap.due_date""")
    rows = [dict(r, computed_status=_payable_status(r)) for r in rows]
    if status_filter:
        rows = [r for r in rows if r['computed_status'] == status_filter]
    open_rows = [r for r in rows if r['computed_status'] != 'pago']
    summary = {
        'total_aberto': sum(r['amount'] for r in open_rows),
        'total_atrasado': sum(r['amount'] for r in open_rows if r['computed_status'] == 'atrasado'),
        'qtd_aberto': len(open_rows),
    }
    suppliers_list = query_db("SELECT * FROM suppliers ORDER BY name")
    return render_template('payable/index.html', rows=rows, summary=summary,
                           status_filter=status_filter, suppliers=suppliers_list,
                           today=_dt.date.today().isoformat())

@app.route('/contas-pagar/novo', methods=['GET','POST'])
def payable_new():
    if request.method == 'POST':
        return _save_payable(None)
    suppliers_list = query_db("SELECT * FROM suppliers ORDER BY name")
    return render_template('payable/form.html', row=None, suppliers=suppliers_list)

@app.route('/contas-pagar/<int:id>/editar', methods=['GET','POST'])
def payable_edit(id):
    row = query_db("SELECT * FROM accounts_payable WHERE id=?", (id,), one=True)
    if not row:
        flash('Conta não encontrada.','danger'); return redirect(url_for('payables'))
    if request.method == 'POST':
        return _save_payable(id)
    suppliers_list = query_db("SELECT * FROM suppliers ORDER BY name")
    return render_template('payable/form.html', row=row, suppliers=suppliers_list)

def _save_payable(id):
    f = request.form
    description = f.get('description','').strip()
    due_date = f.get('due_date','').strip()
    if not description or not due_date:
        flash('Descrição e vencimento são obrigatórios.','danger')
        return redirect(request.url)
    try:
        amount = float(f.get('amount') or 0)
    except ValueError:
        amount = 0
    data = {
        'description': description,
        'category': f.get('category','').strip(),
        'supplier_id': int(f['supplier_id']) if f.get('supplier_id') else None,
        'amount': amount,
        'due_date': due_date,
        'notes': f.get('notes','').strip(),
    }
    if id is None:
        execute_db("""INSERT INTO accounts_payable(description,category,supplier_id,amount,due_date,notes)
            VALUES(:description,:category,:supplier_id,:amount,:due_date,:notes)""", data)
        flash('Conta a pagar cadastrada!','success')
    else:
        data['id'] = id
        execute_db("""UPDATE accounts_payable SET description=:description,category=:category,
            supplier_id=:supplier_id,amount=:amount,due_date=:due_date,notes=:notes WHERE id=:id""", data)
        flash('Conta a pagar atualizada!','success')
    return redirect(url_for('payables'))

@app.route('/contas-pagar/<int:id>/pagar', methods=['POST'])
def payable_pay(id):
    row = query_db("SELECT * FROM accounts_payable WHERE id=?", (id,), one=True)
    if not row:
        flash('Conta não encontrada.','danger'); return redirect(url_for('payables'))
    paid_amount = float(request.form.get('paid_amount') or row['amount'])
    paid_date = request.form.get('paid_date') or _dt.date.today().isoformat()
    payment_method = request.form.get('payment_method','')
    execute_db("""UPDATE accounts_payable SET status='pago', paid_date=?, paid_amount=?,
        payment_method=? WHERE id=?""", (paid_date, paid_amount, payment_method, id))
    flash('Conta marcada como paga!','success')
    return redirect(url_for('payables'))

@app.route('/contas-pagar/<int:id>/reabrir', methods=['POST'])
def payable_reopen(id):
    execute_db("UPDATE accounts_payable SET status='pendente', paid_date=NULL, paid_amount=NULL WHERE id=?", (id,))
    flash('Conta reaberta.','success')
    return redirect(url_for('payables'))

@app.route('/contas-pagar/<int:id>/excluir', methods=['POST'])
def payable_delete(id):
    execute_db("DELETE FROM accounts_payable WHERE id=?", (id,))
    flash('Conta a pagar removida.','success')
    return redirect(url_for('payables'))


# ──────────────────────────── Contas a Receber ────────────────────────────

def _receivable_status(row):
    if row['status'] == 'recebido':
        return 'recebido'
    if row['due_date'] < _dt.date.today().isoformat():
        return 'atrasado'
    return 'pendente'

@app.route('/contas-receber')
def receivables():
    status_filter = request.args.get('status', '')
    rows = query_db("""SELECT ar.*, c.name customer_name_ref FROM accounts_receivable ar
        LEFT JOIN customers c ON c.id=ar.customer_id ORDER BY ar.due_date""")
    rows = [dict(r, computed_status=_receivable_status(r)) for r in rows]
    if status_filter:
        rows = [r for r in rows if r['computed_status'] == status_filter]
    open_rows = [r for r in rows if r['computed_status'] != 'recebido']
    summary = {
        'total_aberto': sum(r['amount'] for r in open_rows),
        'total_atrasado': sum(r['amount'] for r in open_rows if r['computed_status'] == 'atrasado'),
        'qtd_aberto': len(open_rows),
    }
    customers_list = query_db("SELECT * FROM customers WHERE active=1 ORDER BY name")
    return render_template('receivable/index.html', rows=rows, summary=summary,
                           status_filter=status_filter, customers=customers_list,
                           today=_dt.date.today().isoformat())

@app.route('/contas-receber/novo', methods=['GET','POST'])
def receivable_new():
    if request.method == 'POST':
        return _save_receivable(None)
    customers_list = query_db("SELECT * FROM customers WHERE active=1 ORDER BY name")
    return render_template('receivable/form.html', row=None, customers=customers_list)

@app.route('/contas-receber/<int:id>/editar', methods=['GET','POST'])
def receivable_edit(id):
    row = query_db("SELECT * FROM accounts_receivable WHERE id=?", (id,), one=True)
    if not row:
        flash('Conta não encontrada.','danger'); return redirect(url_for('receivables'))
    if request.method == 'POST':
        return _save_receivable(id)
    customers_list = query_db("SELECT * FROM customers WHERE active=1 ORDER BY name")
    return render_template('receivable/form.html', row=row, customers=customers_list)

def _save_receivable(id):
    f = request.form
    description = f.get('description','').strip()
    due_date = f.get('due_date','').strip()
    if not description or not due_date:
        flash('Descrição e vencimento são obrigatórios.','danger')
        return redirect(request.url)
    try:
        amount = float(f.get('amount') or 0)
    except ValueError:
        amount = 0
    data = {
        'description': description,
        'category': f.get('category','').strip(),
        'customer_id': int(f['customer_id']) if f.get('customer_id') else None,
        'amount': amount,
        'due_date': due_date,
        'notes': f.get('notes','').strip(),
    }
    if id is None:
        execute_db("""INSERT INTO accounts_receivable(description,category,customer_id,amount,due_date,notes)
            VALUES(:description,:category,:customer_id,:amount,:due_date,:notes)""", data)
        flash('Conta a receber cadastrada!','success')
    else:
        data['id'] = id
        execute_db("""UPDATE accounts_receivable SET description=:description,category=:category,
            customer_id=:customer_id,amount=:amount,due_date=:due_date,notes=:notes WHERE id=:id""", data)
        flash('Conta a receber atualizada!','success')
    return redirect(url_for('receivables'))

@app.route('/contas-receber/<int:id>/receber', methods=['POST'])
def receivable_receive(id):
    row = query_db("SELECT * FROM accounts_receivable WHERE id=?", (id,), one=True)
    if not row:
        flash('Conta não encontrada.','danger'); return redirect(url_for('receivables'))
    received_amount = float(request.form.get('received_amount') or row['amount'])
    received_date = request.form.get('received_date') or _dt.date.today().isoformat()
    payment_method = request.form.get('payment_method','')
    execute_db("""UPDATE accounts_receivable SET status='recebido', received_date=?, received_amount=?,
        payment_method=? WHERE id=?""", (received_date, received_amount, payment_method, id))
    flash('Conta marcada como recebida!','success')
    return redirect(url_for('receivables'))

@app.route('/contas-receber/<int:id>/reabrir', methods=['POST'])
def receivable_reopen(id):
    execute_db("UPDATE accounts_receivable SET status='pendente', received_date=NULL, received_amount=NULL WHERE id=?", (id,))
    flash('Conta reaberta.','success')
    return redirect(url_for('receivables'))

@app.route('/contas-receber/<int:id>/excluir', methods=['POST'])
def receivable_delete(id):
    execute_db("DELETE FROM accounts_receivable WHERE id=?", (id,))
    flash('Conta a receber removida.','success')
    return redirect(url_for('receivables'))


# ──────────────────────────── API ────────────────────────────

@app.route('/api/decants-by-bottle/<int:bottle_id>')
def api_decants_by_bottle(bottle_id):
    bottle=query_db("SELECT * FROM bottles WHERE id=?",(bottle_id,),one=True)
    if not bottle: return jsonify([])
    decants=query_db("SELECT * FROM decants WHERE perfume_id=? AND active=1 ORDER BY size_ml",(bottle['perfume_id'],))
    cost_per_ml=bottle['cost_price']/bottle['volume_ml']
    _, vial_cost_group, *_ = _group_pricing_params()
    result=[{
        'id':d['id'],'size_ml':d['size_ml'],'stock':d['stock_quantity'],'group_price':d['group_price'],
        'cost_per_unit':round(cost_per_ml*d['size_ml']+vial_cost_group,4),
        'max_qty':int(bottle['remaining_ml']/d['size_ml']),
    } for d in decants]
    return jsonify(result)

@app.route('/api/decants')
def api_all_decants():
    rows=query_db("""SELECT d.id,d.size_ml,d.group_price,d.stock_quantity,
        p.name perfume_name,b.name brand_name,p.concentration
        FROM decants d JOIN perfumes p ON p.id=d.perfume_id LEFT JOIN brands b ON b.id=p.brand_id
        WHERE d.active=1 AND d.group_price>0 ORDER BY b.name,p.name,d.size_ml""")
    return jsonify([dict(r) for r in rows])


# ──────────────────────────── Main ────────────────────────────

if __name__=='__main__':
    init_db()
    port = int(os.environ.get('PORT', 8080))
    is_local = os.environ.get('RAILWAY_ENVIRONMENT') is None
    if is_local:
        def open_browser():
            import time; time.sleep(1)
            webbrowser.open(f'http://localhost:{port}')
        threading.Thread(target=open_browser, daemon=True).start()
    app.run(debug=False, host='0.0.0.0', port=port)
