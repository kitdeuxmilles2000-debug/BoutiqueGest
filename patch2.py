with open('app/templates/products/index.html') as f:
    c=f.read()
old = "      <p class=\"sub\">{{ products|length }} produit(s) affiché(s).</p>\n    </div>\n    <div class=\"actions\">\n      <a href=\"{{ url_for('products.new') }}\" class=\"btn sm\">+ Nouveau produit</a>"
new = "      <p class=\"sub\">{{ products|length }} produit(s) affiché(s).</p>\n    </div>\n    <div class=\"actions\" style=\"display:flex;gap:6px\">\n      <a href=\"{{ url_for('products.proposer') }}\" class=\"btn sm\">Proposer un article</a>\n      <a href=\"{{ url_for('products.new') }}\" class=\"btn sm\">+ Nouveau produit</a>"
if old in c:
    c2=c.replace(old,new)
    with open('app/templates/products/index.html','w') as f:
        f.write(c2)
    print('ok')
else:
    print('skip')
