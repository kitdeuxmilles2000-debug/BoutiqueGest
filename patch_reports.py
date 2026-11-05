path = 'app/templates/reports/index.html'
with open(path, encoding='utf-8', errors='ignore') as f:
    c = f.read()

old = '{% block heading %}Rapports{% endblock %}'
new = '''{% block heading %}Rapports{% endblock %}
{% block content %}
<div class="print-header" style="display:none">
  <table style="width:100%">
    <tr>
      <td style="width:70px"><img src="{{ url_for('static', filename='img/logo.png') }}" style="height:55px" onerror="this.style.display='none'"></td>
      <td style="text-align:center">
        <div style="font-weight:bold;text-transform:uppercase">BOUTIQUEGEST</div>
        <div>RAPPORT SYNTHETIQUE</div>
        <div>Du {{ debut.strftime('%d/%m/%Y') }} au {{ fin.strftime('%d/%m/%Y') }} - {{ periode_labels[periode] }}</div>
      </td>
    </tr>
  </table>
  <hr style="border:1px solid #000;margin:6px 0 10px">
</div>'''

if old in c and 'print-header' not in c:
    c2 = c.replace(old, new)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(c2)
    print('ok')
else:
    print('skip')
