from app import create_app
from app.extensions import db
app = create_app()
with app.app_context():
    from app.models.catalog import Product, Unit, ProductUnit, Category
    from app.models.stock import StockEntryRequest
    print('Products:', Product.query.count())
    print('Units:', Unit.query.count())
    print('ProductUnits:', ProductUnit.query.count())
    print('StockEntryRequests:', StockEntryRequest.query.count())
    for u in Unit.query.all():
        print('U:', u.code, u.label, u.kind)
