from app import create_app
from app.extensions import db
from app.models.catalog import Product, Unit, Category, ProductUnit, ProductStatus
from app.services import stock_validation as stock_validation_service
from decimal import Decimal
import uuid

app = create_app()
app.app_context().push()

units = {u.code: u for u in Unit.query.all()}
def gu(code,label,kind='piece'):
    if code in units: return units[code]
    u=Unit(code=code,label=label,kind=kind); db.session.add(u); db.session.commit(); units[code]=u; return u

ml=gu('ML','Millilitre','volume'); l=gu('L','Litre','volume')
g=gu('G','Gramme','poids'); kg=gu('KG','Kilogramme','poids')
piece=gu('PIECE','Pièce','piece')
cm=gu('CM','Centimètre','longueur'); m=gu('M','Mètre','longueur')
verre=gu('VERRE','Verre','contenance'); bidon=gu('BIDON','Bidon','contenance')
carton=gu('CARTON','Carton','contenance'); bouteille=gu('BOUTEILLE','Bouteille','contenance')
dizaine=gu('DIZAINE','Dizaine','piece'); douzaine=gu('DOUZAINE','Douzaine','piece'); centaine=gu('CENT','Centaine','piece')
sac=gu('SAC','Sac','contenance')

cat = Category.query.first()
if not cat:
    cat = Category(name='Général')
    db.session.add(cat)
    db.session.commit()

def ep(name,base,kind='autre'):
    p=Product.query.filter_by(name=name).first()
    if p: return p
    p=Product(code=f'PRD-{uuid.uuid4().hex[:8].upper()}', name=name, base_unit_id=base.id, category_id=cat.id, kind=kind, currency='CDF', validation_status=ProductStatus.VALIDE, active=True)
    db.session.add(p); db.session.commit(); return p

def add_pu(p,unit,factor,prix):
    if ProductUnit.query.filter_by(product_id=p.id,unit_id=unit.id,factor=factor).first(): return
    db.session.add(ProductUnit(product_id=p.id,unit_id=unit.id,factor=factor,prix_vente=prix,currency='CDF'))
    db.session.commit()

def enter(p,qty_base,cost):
    req=stock_validation_service.create_entry_request(product=p,quantity=qty_base,unit_id=p.base_unit_id,cost_unit=cost,currency='CDF',reason='Exemple',commit=False)
    db.session.commit()
    stock_validation_service.validate_entry_request(req,1,notes='Exemple',commit=True)
    print('OK', p.name, p.stock_qty, p.base_unit.code)

# 1
lait=ep('Lait UHT',ml,'lait')
add_pu(lait,bidon,Decimal('20000'),Decimal('20000'))
add_pu(lait,l,Decimal('1000'),Decimal('1500'))
add_pu(lait,verre,Decimal('100'),Decimal('1000'))
add_pu(lait,verre,Decimal('150'),Decimal('1300'))
add_pu(lait,verre,Decimal('200'),Decimal('1700'))
enter(lait,Decimal('40000'),Decimal('1'))

# 2
eau=ep('Eau minérale',ml,'eau')
add_pu(eau,bidon,Decimal('20000'),Decimal('3000'))
add_pu(eau,l,Decimal('1000'),Decimal('200'))
add_pu(eau,l,Decimal('5000'),Decimal('800'))
add_pu(eau,l,Decimal('10000'),Decimal('1500'))
enter(eau,Decimal('60000'),Decimal('0.1'))

# 3
eaub=ep('Eau en bouteille',piece,'eau')
add_pu(eaub,carton,Decimal('12'),Decimal('10000'))
add_pu(eaub,bouteille,Decimal('1'),Decimal('1000'))
enter(eaub,Decimal('48'),Decimal('666.67'))

# 4
savon=ep('Savon',piece,'accessoire')
add_pu(savon,carton,Decimal('12'),Decimal('12000'))
add_pu(savon,carton,Decimal('24'),Decimal('23000'))
add_pu(savon,piece,Decimal('1'),Decimal('1100'))
enter(savon,Decimal('72'),Decimal('900'))

# 5
bout=ep('Boutons',piece,'accessoire')
add_pu(bout,carton,Decimal('100'),Decimal('14000'))
add_pu(bout,centaine,Decimal('100'),Decimal('14000'))
add_pu(bout,dizaine,Decimal('10'),Decimal('1500'))
add_pu(bout,piece,Decimal('1'),Decimal('150'))
enter(bout,Decimal('200'),Decimal('100'))

# 6
tissu=ep('Tissu coton',m,'autre')
tissu.base_unit_id=m.id; db.session.commit()
add_pu(tissu,m,Decimal('1'),Decimal('2500'))
add_pu(tissu,cm,Decimal('0.01'),Decimal('30'))
enter(tissu,Decimal('50'),Decimal('2000'))

# 7
pdt=ep('Pommes de terre',kg,'autre')
add_pu(pdt,kg,Decimal('1'),Decimal('2500'))
add_pu(pdt,g,Decimal('0.001'),Decimal('3'))
enter(pdt,Decimal('100'),Decimal('2000'))

# 8
far=ep('Farine',kg,'autre')
add_pu(far,sac,Decimal('50'),Decimal('125000'))
add_pu(far,kg,Decimal('1'),Decimal('2500'))
add_pu(far,g,Decimal('0.001'),Decimal('3'))
enter(far,Decimal('200'),Decimal('2200'))

# 9
beign=ep('Beignets',piece,'autre')
add_pu(beign,piece,Decimal('1'),Decimal('200'))
enter(beign,Decimal('200'),Decimal('100'))

# 10
huile=ep('Huile végétale',l,'boisson')
huile.base_unit_id=l.id; db.session.commit()
add_pu(huile,bidon,Decimal('20'),Decimal('32000'))
add_pu(huile,l,Decimal('1'),Decimal('1800'))
add_pu(huile,verre,Decimal('0.25'),Decimal('500'))
enter(huile,Decimal('60'),Decimal('1500'))

db.session.close()
print('DONE')
