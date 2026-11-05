with open('app/routes/products.py') as f:
    for i,l in enumerate(f,1):
        if '/<int:product_id>' in l or 'products.new' in l:
            print(i,l.rstrip())
            if i>200: break
