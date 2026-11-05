with open('app/routes/products.py') as f:
    c=f.read()
start=c.find('def index')
end=c.find('\n@products_bp.route', start)
if start>=0 and end>start:
    new='''def index():
    search = (request.args.get("q") or "").strip()
    category_id = request.args.get("category", type=int)
    alert = request.args.get("alert")
    statut = (request.args.get("statut") or "").strip()

    query = Product.query
    if search:
        like = f"%{search}%"
        query = query.filter(db.or_(Product.name.ilike(like), Product.code.ilike(like)))
    if category_id:
        query = query.filter(Product.category_id == category_id)

    products = query.order_by(Product.name).all()
    if alert == "low":
        products = [p for p in products if p.is_low_stock or p.is_out_of_stock]

    from app.models.stock import StockEntryRequest, StockEntryStatus

    pending_rows = (
        db.session.query(StockEntryRequest.product_id, db.func.sum(StockEntryRequest.qty_base))
        .filter(StockEntryRequest.status == StockEntryStatus.EN_ATTENTE)
        .group_by(StockEntryRequest.product_id)
        .all()
    )
    pending_qty = {pid: (qty or dec(0)) for pid, qty in pending_rows}
    if statut == "attente":
        validated_ids = {
            pid
            for (pid,) in db.session.query(StockEntryRequest.product_id)
            .filter(StockEntryRequest.status == StockEntryStatus.VALIDEE)
            .distinct()
            .all()
        }
        products = [
            p for p in products
            if p.id not in validated_ids and dec(p.stock_qty) <= 0
        ]

    pager = paginate_list(products)
    products = pager.items
    views = {}
    for p in products:
        pu = pricing_service.default_sale_unit(p)
        target = pricing_service.target_margin(p)
        if pu is not None:
            status_m = pricing_service.margin_status(
                pu.prix_vente, pricing_service.sale_unit_cost(p, pu), target
            )
        else:
            status_m = pricing_service.margin_status(0, 0, target)
        views[p.id] = {
            "stock_text": pricing_service.stock_in_sale_units(p, pu),
            "margin": status_m,
            "target": target,
        }

    familles = sorted({getattr(p, 'famille', None) for p in Product.query.all() if getattr(p, 'famille', None)})
    couleurs = sorted({getattr(p, 'couleur', None) for p in Product.query.all() if getattr(p, 'couleur', None)})

    return render_template(
        "products/index.html",
        products=products,
        pager=pager,
        views=views,
        categories=_categories(),
        category_id=category_id,
        search=search,
        alert=alert,
        statut=statut,
        pending_qty=pending_qty,
        familles=familles,
        couleurs=couleurs,
        product_status_labels=PRODUCT_STATUS_LABELS,
        product_status_badges=PRODUCT_STATUS_BADGES,
    )
'''
    c2=c[:start]+new+c[end:]
    with open('app/routes/products.py','w') as f:
        f.write(c2)
    print('ok')
else:
    print('skip')
