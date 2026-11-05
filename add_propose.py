code = r'''

@products_bp.route("/proposer", methods=["GET", "POST"])
@login_required
@permission_required(P.PRODUCTS_VIEW)
def proposer():
    if request.method == "POST":
        code = (request.form.get("code") or "").strip().upper()
        name = (request.form.get("name") or "").strip()
        base_unit_id = request.form.get("base_unit_id", type=int)
        category_id = request.form.get("category_id", type=int)
        currency = request.form.get("currency") or "CDF"
        kind = request.form.get("kind") or ProductKind.AUTRE
        seuil = dec(request.form.get("seuil_alerte"))

        errors = []
        if not name:
            errors.append("Le nom du produit est obligatoire.")
        if not base_unit_id:
            errors.append("L'unité de stock est obligatoire.")
        if not code:
            code = _next_product_code()
        existing = Product.query.filter_by(code=code).first()
        if existing:
            errors.append("Ce code produit existe déjà.")

        if errors:
            for message in errors:
                flash(message, "danger")
            return render_template(
                "products/proposer.html",
                units=_units(),
                categories=_categories(),
                kinds=ProductKind,
                currencies=CURRENCIES,
            )

        product = Product()
        product.code = code
        product.name = name
        product.base_unit_id = base_unit_id
        product.category_id = category_id or None
        product.currency = currency
        product.kind = kind
        product.seuil_alerte = seuil
        product.active = False
        product.validation_status = ProductStatus.EN_ATTENTE
        product.proposed_by_id = current_user.id
        db.session.add(product)
        db.session.flush()

        log_action(
            "product_propose",
            entity="product",
            entity_uuid=product.uuid,
            after={"code": code, "name": name},
            commit=True,
        )
        flash("Produit proposé. En attente de validation par un administrateur.", "warning")
        return redirect(url_for("products.index"))

    return render_template(
        "products/proposer.html",
        units=_units(),
        categories=_categories(),
        kinds=ProductKind,
        currencies=CURRENCIES,
    )


@products_bp.route("/<int:product_id>/valider", methods=["POST"])
@login_required
@permission_required(P.PRODUCTS_MANAGE)
def valider_proposition(product_id):
    product = db.session.get(Product, product_id) or abort(404)
    if product.validation_status != ProductStatus.EN_ATTENTE:
        flash("Ce produit n'est pas en attente de validation.", "warning")
        return redirect(url_for("products.index"))
    product.validation_status = ProductStatus.VALIDE
    product.active = True
    product.validated_by_id = current_user.id
    product.validated_at = utcnow()
    product.validation_note = (request.form.get("note") or "").strip() or None
    log_action("product_validate", entity="product", entity_uuid=product.uuid, commit=True)
    flash(f"Produit « {product.name} » validé.", "success")
    return redirect(url_for("products.index"))


@products_bp.route("/<int:product_id>/rejeter", methods=["POST"])
@login_required
@permission_required(P.PRODUCTS_MANAGE)
def rejeter_proposition(product_id):
    product = db.session.get(Product, product_id) or abort(404)
    if product.validation_status != ProductStatus.EN_ATTENTE:
        flash("Ce produit n'est pas en attente de validation.", "warning")
        return redirect(url_for("products.index"))
    product.validation_status = ProductStatus.REJETE
    product.active = False
    product.validated_by_id = current_user.id
    product.validated_at = utcnow()
    product.validation_note = (request.form.get("note") or "").strip() or None
    log_action("product_reject", entity="product", entity_uuid=product.uuid, reason=product.validation_note, commit=True)
    flash(f"Produit « {product.name} » rejeté.", "warning")
    return redirect(url_for("products.index"))
'''
with open('app/routes/products.py','a',encoding='utf-8') as f:
    f.write(code)
print('ok')
