with open('app/routes/stock.py', encoding='utf-8', errors='ignore') as f:
    data = f.read()
idx = data.find('/entree"')
if idx >= 0:
    idx2 = data.rfind('@', 0, idx)
    end = data.find('\n@stock_bp.route', idx+1)
    if end < idx2:
        end = idx + 7000
    print(data[idx2:end])
