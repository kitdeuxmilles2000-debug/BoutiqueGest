with open('app/routes/products.py') as f:
    c=f.read()
old2='        familles=familles,\n        couleurs=couleurs,\n    )'
new2='        familles=familles,\n        couleurs=couleurs,\n        product_status_labels=PRODUCT_STATUS_LABELS,\n        product_status_badges=PRODUCT_STATUS_BADGES,\n    )'
if old2 in c and 'product_status_labels' not in c:
    c=c.replace(old2,new2)
    with open('app/routes/products.py','w') as f:
        f.write(c)
    print('ok')
else:
    print('skip')
