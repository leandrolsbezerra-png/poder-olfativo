import sqlite3, os, json, webbrowser, threading
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, g

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

# Run on module load so gunicorn workers also initialize the DB
init_db()

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
    total_decants_stk = query_db("SELECT COALESCE(SUM(stock_quantity),0) c FROM decants WHERE active=1", one=True)['c']
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
        SELECT b.name brand, p.name perfume, d.size_ml, SUM(si.quantity) qty, SUM(si.total) revenue
        FROM sale_items si
        JOIN decants d ON d.id=si.decant_id
        JOIN perfumes p ON p.id=d.perfume_id
        JOIN brands b ON b.id=p.brand_id
        JOIN sales s ON s.id=si.sale_id
        WHERE s.status!='cancelada' AND s.sale_date>=date('now','localtime','-30 days')
        GROUP BY d.id ORDER BY qty DESC LIMIT 8
    """)

    stock_value = query_db("""
        SELECT COALESCE(SUM(b.remaining_ml * b.cost_price / b.volume_ml),0) v
        FROM bottles b WHERE b.active=1 AND b.remaining_ml>0
    """, one=True)['v']

    out_of_stock = query_db("""
        SELECT b.name brand, p.name perfume, d.size_ml
        FROM decants d
        JOIN perfumes p ON p.id=d.perfume_id
        JOIN brands b ON b.id=p.brand_id
        WHERE d.active=1 AND d.stock_quantity=0
        ORDER BY brand, perfume LIMIT 10
    """)

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
        total_decants_stk=total_decants_stk, total_suppliers=total_suppliers,
        sales_month=sales_month, monthly_sales=[dict(r) for r in monthly_sales],
        top_decants=top_decants, stock_value=stock_value,
        out_of_stock=out_of_stock, recent_sales=recent_sales)


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
    decants_list=query_db("SELECT * FROM decants WHERE perfume_id=? AND active=1 ORDER BY size_ml",(id,))
    bottles=query_db("""SELECT bt.*,s.name supplier_name FROM bottles bt
        LEFT JOIN suppliers s ON s.id=bt.supplier_id
        WHERE bt.perfume_id=? AND bt.active=1 ORDER BY bt.id DESC""",(id,))
    vials=query_db("SELECT * FROM vial_costs ORDER BY size_ml")
    return render_template('perfumes/detail.html', perfume=perfume,
                           decants=decants_list, bottles=bottles, vials=vials)

@app.route('/perfumes/<int:id>/preco-decants', methods=['POST'])
def perfume_update_prices(id):
    for key,val in request.form.items():
        if key.startswith('price_'):
            decant_id=int(key.split('_')[1])
            try: execute_db("UPDATE decants SET sale_price=? WHERE id=? AND perfume_id=?",(float(val),decant_id,id))
            except: pass
    flash('Preços atualizados!','success')
    return redirect(url_for('perfume_detail', id=id))


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
        # auto-recalculate decant prices
        _recalculate_prices(perfume_id, vol, cost)
        return redirect(url_for('perfume_detail', id=perfume_id))
    perfumes_list=query_db("SELECT p.id,p.name,b.name brand_name FROM perfumes p LEFT JOIN brands b ON b.id=p.brand_id WHERE p.active=1 ORDER BY b.name,p.name")
    suppliers_list=query_db("SELECT * FROM suppliers WHERE active=1 ORDER BY name")
    return render_template('bottles/form.html', perfumes=perfumes_list, suppliers=suppliers_list)

def _recalculate_prices(perfume_id, volume_ml, cost_price):
    cost_per_ml = cost_price / volume_ml
    vials = {r['size_ml']: r for r in query_db("SELECT * FROM vial_costs")}
    for d in query_db("SELECT * FROM decants WHERE perfume_id=? AND active=1", (perfume_id,)):
        v = vials.get(d['size_ml'])
        if not v: continue
        sale_price = round((cost_per_ml * d['size_ml'] + v['cost']) * v['multiplier'], 2)
        execute_db("UPDATE decants SET sale_price=? WHERE id=?", (sale_price, d['id']))


@app.route('/frascos/<int:id>/inativar', methods=['POST'])
def bottle_inactivate(id):
    execute_db("UPDATE bottles SET active=0 WHERE id=?",(id,))
    flash('Frasco removido.','success'); return redirect(url_for('bottles'))


# ──────────────────────────── Fracionamento ────────────────────────────

@app.route('/fracionamento', methods=['GET','POST'])
def fractionation():
    if request.method=='POST':
        bottle_id=int(request.form['bottle_id'])
        decant_id=int(request.form['decant_id'])
        quantity=int(request.form['quantity'])
        vial_cost_unit=float(request.form.get('vial_cost') or 0)

        bottle=query_db("SELECT * FROM bottles WHERE id=?",(bottle_id,),one=True)
        decant=query_db("SELECT * FROM decants WHERE id=?",(decant_id,),one=True)
        if not bottle or not decant:
            flash('Dados inválidos.','danger'); return redirect(request.url)

        ml_used=decant['size_ml']*quantity
        if ml_used>bottle['remaining_ml']:
            flash(f'Sem ml suficiente! Disponível: {bottle["remaining_ml"]:.1f}ml, Necessário: {ml_used:.1f}ml','danger')
            return redirect(request.url)

        cost_per_ml=bottle['cost_price']/bottle['volume_ml']
        cost_per_unit=round(cost_per_ml*decant['size_ml']+vial_cost_unit, 4)

        execute_db("UPDATE bottles SET remaining_ml=remaining_ml-? WHERE id=?",(ml_used,bottle_id))
        execute_db("UPDATE decants SET stock_quantity=stock_quantity+? WHERE id=?",(quantity,decant_id))
        execute_db("""INSERT INTO decant_ops(bottle_id,decant_id,quantity,ml_used,cost_per_unit,vial_cost,notes)
            VALUES(?,?,?,?,?,?,?)""",(bottle_id,decant_id,quantity,ml_used,cost_per_unit,vial_cost_unit,
            request.form.get('notes','')))

        flash(f'{quantity} decants de {decant["size_ml"]:.0f}ml fracionados! Custo/un: R$ {cost_per_unit:.2f}','success')
        return redirect(url_for('fractionation'))

    bottles_list=query_db("""SELECT bt.id,bt.perfume_id,bt.volume_ml,bt.remaining_ml,bt.cost_price,
        p.name perfume_name, b.name brand_name,
        ROUND(bt.cost_price/bt.volume_ml,4) cost_per_ml
        FROM bottles bt JOIN perfumes p ON p.id=bt.perfume_id LEFT JOIN brands b ON b.id=p.brand_id
        WHERE bt.active=1 AND bt.remaining_ml>0 ORDER BY b.name,p.name""")
    decants_by_perfume=query_db("""SELECT d.id,d.size_ml,d.perfume_id,d.stock_quantity,d.sale_price,
        p.name perfume_name,b.name brand_name
        FROM decants d JOIN perfumes p ON p.id=d.perfume_id LEFT JOIN brands b ON b.id=p.brand_id
        WHERE d.active=1 ORDER BY b.name,p.name,d.size_ml""")
    vials=query_db("SELECT * FROM vial_costs ORDER BY size_ml")
    history=query_db("""SELECT op.*,bt.volume_ml,p.name perfume_name,b.name brand_name,d.size_ml
        FROM decant_ops op JOIN bottles bt ON bt.id=op.bottle_id
        JOIN perfumes p ON p.id=bt.perfume_id LEFT JOIN brands b ON b.id=p.brand_id
        JOIN decants d ON d.id=op.decant_id
        ORDER BY op.id DESC LIMIT 30""")
    return render_template('fractionation.html',
        bottles=bottles_list, decants=decants_by_perfume,
        vials=vials, history=history)


# ──────────────────────────── Decants stock ────────────────────────────

@app.route('/decants')
def decants_stock():
    q=request.args.get('q',''); size=request.args.get('size',''); oos=request.args.get('oos','')
    sql="""SELECT d.*,p.name perfume_name,b.name brand_name,p.concentration,p.gender
        FROM decants d JOIN perfumes p ON p.id=d.perfume_id LEFT JOIN brands b ON b.id=p.brand_id
        WHERE d.active=1"""
    params=[]
    if q: sql+=" AND (p.name LIKE ? OR b.name LIKE ?)"; params+=[f'%{q}%',f'%{q}%']
    if size: sql+=" AND d.size_ml=?"; params.append(float(size))
    if oos: sql+=" AND d.stock_quantity=0"
    sql+=" ORDER BY b.name,p.name,d.size_ml"
    rows=query_db(sql,params)
    return render_template('decants/index.html', decants=rows, q=q, size=size, oos=oos)


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
            if key.startswith('vial_'):
                size=float(key.split('_')[1])
                execute_db("UPDATE vial_costs SET cost=? WHERE size_ml=?",(float(val or 0),size))
            elif key.startswith('mult_'):
                size=float(key.split('_')[1])
                execute_db("UPDATE vial_costs SET multiplier=? WHERE size_ml=?",(float(val or 1),size))
            elif key.startswith('fee_'):
                method=key[4:].replace('_',' ')
                execute_db("INSERT OR REPLACE INTO payment_fee_defaults(method,fee_pct,label) VALUES(?,?,?)",
                           (method, float(val or 0), method))
        flash('Configurações salvas!','success'); return redirect(url_for('settings'))
    vials=query_db("SELECT * FROM vial_costs ORDER BY size_ml")
    fee_defaults=query_db("SELECT * FROM payment_fee_defaults ORDER BY method")
    return render_template('settings.html', vials=vials, fee_defaults=fee_defaults)


@app.route('/perfumes/<int:id>/recalcular', methods=['POST'])
def perfume_recalculate(id):
    """Recalculate all decant prices for a perfume based on its latest bottle cost and multipliers."""
    bottles=query_db("SELECT * FROM bottles WHERE perfume_id=? AND active=1 AND remaining_ml>0 ORDER BY id DESC",(id,))
    if not bottles:
        flash('Cadastre um frasco original para calcular os preços.','warning')
        return redirect(url_for('perfume_detail', id=id))
    bottle=bottles[0]
    cost_per_ml=bottle['cost_price']/bottle['volume_ml']
    vials={r['size_ml']:r for r in query_db("SELECT * FROM vial_costs ORDER BY size_ml")}
    decants_list=query_db("SELECT * FROM decants WHERE perfume_id=? AND active=1",(id,))
    updated=0
    for d in decants_list:
        v=vials.get(d['size_ml'])
        if not v: continue
        vial_cost=v['cost']
        multiplier=v['multiplier']
        cost_unit=(cost_per_ml*d['size_ml'])+vial_cost
        sale_price=round(cost_unit*multiplier,2)
        execute_db("UPDATE decants SET sale_price=? WHERE id=?",(sale_price,d['id']))
        updated+=1
    flash(f'Preços recalculados para {updated} tamanho(s) com base no custo atual do frasco.','success')
    return redirect(url_for('perfume_detail', id=id))


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
        subtotal=sum(i['qty']*i['price'] for i in items)
        total=max(0,subtotal-discount)
        fee_amount=round(total*fee_pct/100, 2)
        sale_id=execute_db("INSERT INTO sales(customer_id,customer_name,subtotal,discount,total,payment_method,payment_fee_pct,payment_fee_amount,notes) VALUES(?,?,?,?,?,?,?,?,?)",
                           (customer_id,customer,subtotal,discount,total,payment,fee_pct,fee_amount,notes))
        for i in items:
            decant=query_db("SELECT d.*,p.name pname,b.name bname FROM decants d JOIN perfumes p ON p.id=d.perfume_id LEFT JOIN brands b ON b.id=p.brand_id WHERE d.id=?",(i['id'],),one=True)
            if not decant: continue
            label=f"{decant['bname']} {decant['pname']} {decant['size_ml']:.0f}ml"
            # Calculate real unit cost
            bottle=query_db("""SELECT bt.cost_price,bt.volume_ml FROM bottles bt
                WHERE bt.perfume_id=? AND bt.active=1 ORDER BY bt.id DESC LIMIT 1""",
                (decant['perfume_id'],),one=True)
            vial=query_db("SELECT cost FROM vial_costs WHERE size_ml=?",(decant['size_ml'],),one=True)
            if bottle:
                cost_unit=round(bottle['cost_price']/bottle['volume_ml']*decant['size_ml']+(vial['cost'] if vial else 0),4)
            else:
                cost_unit=0
            execute_db("INSERT INTO sale_items(sale_id,decant_id,product_label,size_ml,quantity,unit_price,cost_price,total) VALUES(?,?,?,?,?,?,?,?)",
                       (sale_id,i['id'],label,decant['size_ml'],i['qty'],i['price'],cost_unit,i['qty']*i['price']))
            execute_db("UPDATE decants SET stock_quantity=MAX(0,stock_quantity-?) WHERE id=?",(i['qty'],i['id']))
        flash(f'Venda #{sale_id} registrada! Total: R$ {total:.2f}','success')
        return redirect(url_for('sale_detail', id=sale_id))
    decants_list=query_db("""SELECT d.id,d.size_ml,d.sale_price,d.stock_quantity,
        p.name perfume_name,b.name brand_name,p.concentration
        FROM decants d JOIN perfumes p ON p.id=d.perfume_id LEFT JOIN brands b ON b.id=p.brand_id
        WHERE d.active=1 AND d.sale_price>0 ORDER BY b.name,p.name,d.size_ml""")
    customers_list = query_db("SELECT id, name, phone FROM customers WHERE active=1 ORDER BY name")
    fee_defaults = {r['method']: r['fee_pct'] for r in query_db("SELECT method, fee_pct FROM payment_fee_defaults")}
    return render_template('sales/new.html', decants=decants_list, customers=customers_list, fee_defaults=fee_defaults)

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
            execute_db("UPDATE decants SET stock_quantity=stock_quantity+? WHERE id=?",(i['quantity'],i['decant_id']))
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
        subtotal = sum(i['qty']*i['price'] for i in items)
        total = max(0, subtotal - discount)
        oid = execute_db("""INSERT INTO orders(customer_id,customer_name,subtotal,discount,total,notes,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?)""",(customer_id,customer_name,subtotal,discount,total,notes,now,now))
        for i in items:
            d = query_db("SELECT d.*,p.name pname,b.name bname FROM decants d JOIN perfumes p ON p.id=d.perfume_id LEFT JOIN brands b ON b.id=p.brand_id WHERE d.id=?", (i['id'],), one=True)
            if not d: continue
            label = f"{d['bname']} {d['pname']} {d['size_ml']:.0f}ml"
            execute_db("INSERT INTO order_items(order_id,decant_id,product_label,size_ml,quantity,unit_price,total) VALUES(?,?,?,?,?,?,?)",
                       (oid,i['id'],label,d['size_ml'],i['qty'],i['price'],i['qty']*i['price']))
        flash(f'Pedido #{oid} criado!','success')
        return redirect(url_for('order_detail', id=oid))
    decants_list = query_db("""SELECT d.id,d.size_ml,d.sale_price,p.name perfume_name,b.name brand_name,p.concentration
        FROM decants d JOIN perfumes p ON p.id=d.perfume_id LEFT JOIN brands b ON b.id=p.brand_id
        WHERE d.active=1 AND d.sale_price>0 ORDER BY b.name,p.name,d.size_ml""")
    customers_list = query_db("SELECT id,name,phone FROM customers WHERE active=1 ORDER BY name")
    return render_template('orders/form.html', decants=decants_list, customers=customers_list)

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
    for i in items:
        d = query_db("SELECT * FROM decants WHERE id=?", (i['decant_id'],), one=True)
        bottle = query_db("""SELECT bt.cost_price,bt.volume_ml FROM bottles bt
            JOIN decants d ON d.perfume_id=bt.perfume_id WHERE d.id=? AND bt.active=1 ORDER BY bt.id DESC LIMIT 1""",
            (i['decant_id'],), one=True)
        vial = query_db("SELECT cost FROM vial_costs WHERE size_ml=?", (i['size_ml'],), one=True)
        cost_unit = round(bottle['cost_price']/bottle['volume_ml']*i['size_ml']+(vial['cost'] if vial else 0),4) if bottle else 0
        execute_db("""INSERT INTO sale_items(sale_id,decant_id,product_label,size_ml,quantity,unit_price,cost_price,total)
            VALUES(?,?,?,?,?,?,?,?)""",
            (sale_id,i['decant_id'],i['product_label'],i['size_ml'],i['quantity'],i['unit_price'],cost_unit,i['total']))
        execute_db("UPDATE decants SET stock_quantity=MAX(0,stock_quantity-?) WHERE id=?", (i['quantity'],i['decant_id']))
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
        SELECT p.*,b.name brand_name,
            GROUP_CONCAT(CAST(CAST(d.size_ml AS INTEGER) AS TEXT) || 'ml', ',') sizes
        FROM perfumes p
        LEFT JOIN brands b ON b.id=p.brand_id
        LEFT JOIN decants d ON d.perfume_id=p.id AND d.active=1 AND d.sale_price>0
        WHERE p.active=1
        GROUP BY p.id ORDER BY b.name,p.name
    """)
    return render_template('labels/index.html', perfumes=perfumes_list)

@app.route('/etiquetas/imprimir')
def labels_print():
    ids = request.args.getlist('ids')
    qty = int(request.args.get('qty', 1))
    label_size = request.args.get('label_size', '80x45')
    show_price = request.args.get('show_price', '1')
    show_notes = request.args.get('show_notes', '1')
    bottle_type = request.args.get('bottle_type', '8ml')
    sizes_map = {'8ml': ['2ml','5ml'], '15ml': ['10ml','15ml']}
    if not ids:
        flash('Selecione ao menos um perfume.','warning')
        return redirect(url_for('labels'))
    perfumes_list = query_db(f"""
        SELECT p.*,b.name brand_name,
            GROUP_CONCAT(CAST(CAST(d.size_ml AS INTEGER) AS TEXT) || 'ml', ',') sizes,
            GROUP_CONCAT(d.sale_price, ',') prices
        FROM perfumes p
        LEFT JOIN brands b ON b.id=p.brand_id
        LEFT JOIN decants d ON d.perfume_id=p.id AND d.active=1 AND d.sale_price>0
        WHERE p.id IN ({','.join('?'*len(ids))})
        GROUP BY p.id ORDER BY b.name,p.name
    """, ids)
    w, h = label_size.split('x')
    checkbox_sizes = sizes_map.get(bottle_type, ['2ml','5ml'])
    return render_template('labels/print.html', perfumes=perfumes_list, qty=qty,
                           label_w=w, label_h=h, show_price=show_price, show_notes=show_notes,
                           bottle_type=bottle_type, checkbox_sizes=checkbox_sizes)


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


# ──────────────────────────── API ────────────────────────────

@app.route('/api/decants-by-bottle/<int:bottle_id>')
def api_decants_by_bottle(bottle_id):
    bottle=query_db("SELECT * FROM bottles WHERE id=?",(bottle_id,),one=True)
    if not bottle: return jsonify([])
    decants=query_db("SELECT * FROM decants WHERE perfume_id=? AND active=1 ORDER BY size_ml",(bottle['perfume_id'],))
    cost_per_ml=bottle['cost_price']/bottle['volume_ml']
    vials={r['size_ml']:r['cost'] for r in query_db("SELECT * FROM vial_costs")}
    result=[{
        'id':d['id'],'size_ml':d['size_ml'],'stock':d['stock_quantity'],'sale_price':d['sale_price'],
        'cost_per_unit':round(cost_per_ml*d['size_ml']+vials.get(d['size_ml'],0),4),
        'max_qty':int(bottle['remaining_ml']/d['size_ml']),
    } for d in decants]
    return jsonify(result)

@app.route('/api/decants')
def api_all_decants():
    rows=query_db("""SELECT d.id,d.size_ml,d.sale_price,d.stock_quantity,
        p.name perfume_name,b.name brand_name,p.concentration
        FROM decants d JOIN perfumes p ON p.id=d.perfume_id LEFT JOIN brands b ON b.id=p.brand_id
        WHERE d.active=1 AND d.sale_price>0 ORDER BY b.name,p.name,d.size_ml""")
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
