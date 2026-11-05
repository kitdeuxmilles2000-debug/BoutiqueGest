with open('app/routes/products.py', encoding='utf-8', errors='ignore') as f:
    data = f.read()
idx = data.find('/<int:product_id>/modifier')
if idx >= 0:
    start = max(0, idx-60)
    end = min(len(data), idx+5500)
    print(data[start:end])
