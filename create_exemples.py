from app import create_app
from app.extensions import db
from app.models.catalog import Product, Unit, Category, ProductUnit, ProductStatus
from app.services import stock_validation as stock_validation_service
from decimal import Decimal
import uuid

app = create_app()
app.app_context().push()

units = {u.code: u for u in Unit.query.all()}

def gu(code, label, kind='piece'):
    if code in units:
        return units[code]
    u = Unit(code=code, label=label, kind=kind)
    db.session.add(u)
    db.session.commit()
    units[code] = u
    return u

# Unités
ml = gu('ML', 'Millilitre', 'volume')
l = gu('L', 'Litre', 'volume')
g = gu('G', 'Gramme', 'poids')
kg = gu('KG', 'Kilogramme', 'poids')
piece = gu('PIECE', 'Pièce', 'piece')
cm = gu('CM', 'Centimètre', 'longueur')
m = gu('M', 'Mètre', 'longueur')
verre = gu('VERRE', 'Verre', 'contenance')
bidon = gu('BIDON', 'Bidon', 'contenance')
carton = gu('CARTON', 'Carton', 'contenance')
bouteille = gu('BOUTEILLE', 'Bouteille', 'contenance')
dizaine = gu('DIZAINE', 'Dizaine', 'piece')
douzaine = gu('DOUZAINE', 'Douzaine', 'piece')
centaine = gu('CENT', 'Centaine', 'piece')
sac = gu('SAC', 'Sac', 'contenance')
paquet = gu('PAQUET', 'Paquet', 'contenance')

# Catégorie
cat = Category.query.first()
if not cat:
    cat = Category(name='Général')
    db.session.add(cat)
    db.session.commit()

def ep(name, base_unit, kind='autre'):
    p = Product.query.filter_by(name=name).first()
    if p:
        return p
    p = Product(
        code=f'PRD-{uuid.uuid4().hex[:8].upper()}',
        name=name,
        base_unit_id=base_unit.id,
        category_id=cat.id,
        kind=kind,
        currency='CDF',
        validation_status=ProductStatus.VALIDE,
        active=True,
        is_perishable=False,
        track_lot=False
    )
    db.session.add(p)
    db.session.commit()
    return p

def add_pu(p, unit, factor, prix):
    if ProductUnit.query.filter_by(product_id=p.id, unit_id=unit.id, factor=factor).first():
        return
    pu = ProductUnit(product_id=p.id, unit_id=unit.id, factor=factor, prix_vente=prix, currency='CDF')
    db.session.add(pu)
    db.session.commit()

def enter(p, qty_base, cost):
    req = stock_validation_service.create_entry_request(
        product=p,
        quantity=qty_base,
        unit_id=p.base_unit_id,
        cost_unit=cost,
        currency='CDF',
        reason='Exemple',
        commit=False
    )
    db.session.commit()
    stock_validation_service.validate_entry_request(req, 1, notes='Création exemples', commit=True)
    print(f'OK - {p.name}: {p.stock_qty} {p.base_unit.code}')

# 1) Lait UHT - liquide avec plusieurs verres
lait = ep('Lait UHT', ml, 'lait')
add_pu(lait, bidon, Decimal('20000'), Decimal('20000'))
add_pu(lait, l, Decimal('1000'), Decimal('1500'))
add_pu(lait, verre, Decimal('100'), Decimal('1000'))
add_pu(lait, verre, Decimal('150'), Decimal('1300'))
add_pu(lait, verre, Decimal('200'), Decimal('1700'))
enter(lait, Decimal('60000'), Decimal('1'))

# 2) Eau minérale - bidon + litres
eau = ep('Eau minérale', ml, 'eau')
add_pu(eau, bidon, Decimal('20000'), Decimal('3000'))
add_pu(eau, l, Decimal('1000'), Decimal('200'))
add_pu(eau, l, Decimal('5000'), Decimal('800'))
add_pu(eau, l, Decimal('10000'), Decimal('1500'))
enter(eau, Decimal('80000'), Decimal('0.1'))

# 3) Eau en bouteille - carton + bouteille
eaub = ep('Eau en bouteille', piece, 'eau')
add_pu(eaub, carton, Decimal('12'), Decimal('10000'))
add_pu(eaub, bouteille, Decimal('1'), Decimal('1000'))
enter(eaub, Decimal('120'), Decimal('666.67'))

# 4) Savon - carton de 12/24
savon = ep('Savon', piece, 'accessoire')
add_pu(savon, carton, Decimal('12'), Decimal('12000'))
add_pu(savon, carton, Decimal('24'), Decimal('23000'))
add_pu(savon, piece, Decimal('1'), Decimal('1100'))
enter(savon, Decimal('144'), Decimal('900'))

# 5) Boutons - carton/dizaine/douzaine/centaine/pièce
boutons = ep('Boutons', piece, 'accessoire')
add_pu(boutons, carton, Decimal('100'), Decimal('14000'))
add_pu(boutons, centaine, Decimal('100'), Decimal('14000'))
add_pu(boutons, douzaine, Decimal('12'), Decimal('1800'))
add_pu(boutons, dizaine, Decimal('10'), Decimal('1500'))
add_pu(boutons, piece, Decimal('1'), Decimal('150'))
enter(boutons, Decimal('500'), Decimal('100'))

# 6) Aiguilles - carton/pièce
aiguilles = ep('Aiguilles', piece, 'accessoire')
add_pu(aiguilles, paquet, Decimal('100'), Decimal('5000'))
add_pu(aiguilles, piece, Decimal('1'), Decimal('60'))
enter(aiguilles, Decimal('1000'), Decimal('40'))

# 7) Tissu coton - mètre/centimètre
tissu = ep('Tissu coton', m, 'autre')
tissu.base_unit_id = m.id
db.session.commit()
add_pu(tissu, m, Decimal('1'), Decimal('2500'))
add_pu(tissu, cm, Decimal('0.01'), Decimal('30'))
enter(tissu, Decimal('100'), Decimal('2000'))

# 8) Pommes de terre - kg/g
pdt = ep('Pommes de terre', kg, 'autre')
add_pu(pdt, sac, Decimal('50'), Decimal('110000'))
add_pu(pdt, kg, Decimal('1'), Decimal('2500'))
add_pu(pdt, g, Decimal('0.001'), Decimal('3'))
enter(pdt, Decimal('500'), Decimal('2000'))

# 9) Farine - sac/kg/g
farine = ep('Farine', kg, 'autre')
add_pu(farine, sac, Decimal('50'), Decimal('125000'))
add_pu(farine, kg, Decimal('1'), Decimal('2500'))
add_pu(farine, g, Decimal('0.001'), Decimal('3'))
enter(farine, Decimal('1000'), Decimal('2200'))

# 10) Riz - sac/kg/g
riz = ep('Riz', kg, 'autre')
add_pu(riz, sac, Decimal('50'), Decimal('130000'))
add_pu(riz, kg, Decimal('1'), Decimal('2700'))
add_pu(riz, g, Decimal('0.001'), Decimal('3'))
enter(riz, Decimal('500'), Decimal('2400'))

# 11) Beignets - pièce
beignets = ep('Beignets', piece, 'autre')
add_pu(beignets, piece, Decimal('1'), Decimal('200'))
enter(beignets, Decimal('500'), Decimal('100'))

# 12) Huile végétale - bidon/litre/verre
huile = ep('Huile végétale', l, 'boisson')
huile.base_unit_id = l.id
db.session.commit()
add_pu(huile, bidon, Decimal('20'), Decimal('32000'))
add_pu(huile, l, Decimal('1'), Decimal('1800'))
add_pu(huile, verre, Decimal('0.25'), Decimal('500'))
enter(huile, Decimal('100'), Decimal('1500'))

db.session.close()
print('=== TERMINE ===')
