from flask import Flask, render_template, request, send_file, session, redirect, url_for
import json
from io import BytesIO
from xml.dom.minidom import Document
import html
import tempfile
import os

app = Flask(__name__)
app.secret_key = 'your_random_secret_key_123'  # обязательно для сессии


# =========================
# Парсер JSON
# =========================
def parse_json(file_content):
    data = json.loads(file_content)

    producer_inn = data.get('producer_inn') or data.get('participant_inn')
    owner_inn = data.get('owner_inn') or data.get('participant_inn')
    production_date = data.get('production_date', '')
    production_type = data.get('production_type', '')

    if producer_inn == owner_inn:
        production_type = 'OWN_PRODUCTION'
    else:
        production_type = 'CONTRACT_PRODUCTION'

    products_raw = data.get('products', []) or data.get('products_list', [])
    products = []
    for p in products_raw:
        uit = html.escape(p.get('uit_code') or p.get('uit', ''))
        vsd_number = p.get('vsd_number', '')
        tnved_code = p.get('tnved_code', '')
        cert = p.get('certificate_document_data', [{}])[0]
        certificate_number = html.escape(cert.get('certificate_number', ''))
        certificate_date = cert.get('certificate_date', '')
        products.append({
            'uit': uit,
            'vsd_number': vsd_number,
            'tnved_code': tnved_code,
            'certificate_number': certificate_number,
            'certificate_date': certificate_date
        })

    return {
        'producer_inn': producer_inn,
        'owner_inn': owner_inn,
        'production_date': production_date,
        'production_type': production_type,
        'products': products
    }


# =========================
# Генерация CSV
# =========================
def generate_csv(codes):
    output = BytesIO()
    # убираем пробелы в начале/конце каждой строки
    codes_clean = [line.strip() for line in codes if line.strip()]
    text = '\n'.join(codes_clean).replace('<GS>', '\x1d')
    output.write(text.encode('utf-8'))
    output.seek(0)
    return output


# =========================
# Генерация XML
# =========================
def generate_xml(data, codes):
    """
    Генерация XML вручную с разной шапкой для CONTRACT и OWN производства
    """
    lines = []

    codes_clean = [line.strip() for line in codes if line.strip()]

    if data['production_type'] == 'CONTRACT_PRODUCTION':
        # Шапка контрактного производства
        lines.append(f'<introduce_contract version="7">')
        lines.append(f'    <producer_inn>{data["producer_inn"]}</producer_inn>')
        lines.append(f'    <owner_inn>{data["owner_inn"]}</owner_inn>')
        lines.append(f'    <production_date>{data["production_date"]}</production_date>')
        lines.append(f'    <production_order>{data["production_type"]}</production_order>')
    else:
        # Шапка собственного производства
        lines.append(f'<introduce_rf version="9">')
        lines.append(f'    <trade_participant_inn>{data["producer_inn"]}</trade_participant_inn>')
        lines.append(f'    <producer_inn>{data["producer_inn"]}</producer_inn>')
        lines.append(f'    <owner_inn>{data["owner_inn"]}</owner_inn>')
        lines.append(f'    <production_date>{data["production_date"]}</production_date>')
        lines.append(f'    <production_order>{data["production_type"]}</production_order>')

    lines.append('    <products_list>')

    # Берем первый продукт для заполнения полей
    p = data['products'][0] if data['products'] else {}

    for code in codes_clean:
        lines.append('        <product>')
        lines.append(f'            <ki><![CDATA[{code.split("<GS>")[0].strip()}]]></ki>')
        lines.append(f'            <production_date>{data["production_date"]}</production_date>')
        lines.append(f'            <tnved_code>{p.get("tnved_code","")}</tnved_code>')
        lines.append('            <certificate_type>CONFORMITY_DECLARATION</certificate_type>')
        lines.append(f'            <certificate_number>{p.get("certificate_number","")}</certificate_number>')
        lines.append(f'            <certificate_date>{p.get("certificate_date","")}</certificate_date>')
        if p.get("vsd_number"):
            lines.append(f'            <vsd_number>{p["vsd_number"]}</vsd_number>')
        lines.append('        </product>')

    lines.append('    </products_list>')

    # Закрывающий тег
    if data['production_type'] == 'CONTRACT_PRODUCTION':
        lines.append('</introduce_contract>')
    else:
        lines.append('</introduce_rf>')

    xml_text = "\n".join(lines)
    return BytesIO(xml_text.encode('utf-8'))





# =========================
# Flask routes
# =========================
@app.route('/', methods=['GET', 'POST'])
def index():
    json_path = session.get('json_path')
    data = {}
    if json_path and os.path.exists(json_path):
        with open(json_path, 'r', encoding='utf-8') as f:
            data = parse_json(f.read())

    if request.method == 'POST' and 'json_file' in request.files:
        file = request.files['json_file']
        content = file.read()
        f = tempfile.NamedTemporaryFile(delete=False, suffix='.json', mode='w', encoding='utf-8')
        f.write(content.decode('utf-8') if isinstance(content, bytes) else content)
        f.close()
        session['json_path'] = f.name
        return redirect(url_for('index'))

    return render_template('index.html', data=data)


@app.route('/download_csv', methods=['POST'])
def download_csv():
    codes_text = request.form.get('codes', '')
    filename = request.form.get('filename', 'codes') + '.csv'
    codes = [line.strip() for line in codes_text.splitlines() if line.strip()]
    csv_file = generate_csv(codes)
    return send_file(csv_file, mimetype='text/csv', as_attachment=True, download_name=filename)


@app.route('/download_xml', methods=['POST'])
def download_xml():
    codes_text = request.form.get('codes', '')
    filename = request.form.get('filename', 'codes') + '.xml'
    codes = [line.strip() for line in codes_text.splitlines() if line.strip()]

    # Читаем JSON с диска
    json_path = session.get('json_path')
    if json_path and os.path.exists(json_path):
        with open(json_path, 'r', encoding='utf-8') as f:
            data = parse_json(f.read())
    else:
        data = {}

    xml_file = generate_xml(data, codes)

    # Удаляем временный файл после генерации XML
    if json_path and os.path.exists(json_path):
        os.unlink(json_path)
        session.pop('json_path', None)

    return send_file(xml_file, mimetype='application/xml', as_attachment=True, download_name=filename)


if __name__ == '__main__':
    import os

    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
