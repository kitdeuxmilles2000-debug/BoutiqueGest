with open('app/routes/products.py') as f:
    for i,l in enumerate(f,1):
        if 'products.new' in l or ('@products_bp.route' in l and 'nouveau' in l):
            print(i,l.rstrip())
            if i>500: break
