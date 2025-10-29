import os
import json
import tempfile
from io import BytesIO
from flask import Flask, render_template, request, redirect, url_for, session, send_file

app = Flask(__name__)
app.secret_key = os.urandom(24)  # безопасный ключ для сессии


def parse_json(file_content):
    """Парсим JSON, обрабатывая разные форматы структуры"""
    try:
        data = json.loads(file_content)
    except Exception:
        return {}

    # Определяем поля
    result = {
        'producer_inn': data.get('producer_inn') or data.get('participant_inn'),
        'owner_inn': data.get('owner_inn') or data.get('producer_inn'),
        'production_date': data.get('production_date', ''),
        'production_type': data.get('production_type', ''),
        'products': []
    }

    # Если все INN одинаковы и production_type не указан — считаем OWN_PRODUCTION
    if not result['production_type']:
        if result['producer_inn'] == result['owner_inn']:
            result['production_type'] = 'OWN_PRODUCTION'
        else:
            result['production_type'] = 'CONTRACT_PRODUCTION'

    # Продукты
    products = data.get('products_list') or data.get('products') or []
    for p in products:
        product = {
            'uit_code': p.get('uit') or p.get('uit_code', ''),
            'tnved_code': p.get('tnved_code', ''),
            'production_date': p.get('production_date', ''),
            'certificate_number': '',
            'certificate_date': '',
            'vsd_number': p.get('vsd_number', '')
        }
        certs = p.get('certificate_document_data', [])
        if certs:
            c = certs[0]
            product['certificate_number'] = c.get('certificate_number', '')
            product['certificate_date'] = c.get('certificate_date', '')
        result['products'].append(product)
    return result


def generate_xml(data, codes):
    """Генерация XML с разными шапками для контрактного/собственного производства"""
    lines = []
    codes_clean = [line.strip() for line in codes if line.strip()]

    if data['production_type'] == 'CONTRACT_PRODUCTION':
        lines.append(f'<introduce_contract version="7">')
        lines.append(f'    <producer_inn>{data["producer_inn"]}</producer_inn>')
        lines.append(f'    <owner_inn>{data["owner_inn"]}</owner_inn>')
        lines.append(f'    <production_date>{data["production_date"]}</production_date>')
        lines.append(f'    <production_order>{data["production_type"]}</production_order>')
    else:
        lines.append(f'<introduce_rf version="9">')
        lines.append(f'    <trade_participant_inn>{data["producer_inn"]}</trade_participant_inn>')
        lines.append(f'    <producer_inn>{data["producer_inn"]}</producer_inn>')
        lines.append(f'    <owner_inn>{data["owner_inn"]}</owner_inn>')
        lines.append(f'    <production_date>{data["production_date"]}</production_date>')
        lines.append(f'    <production_order>{data["production_type"]}</production_order>')

    lines.append('    <products_list>')

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
    lines.append('</introduce_contract>' if data['production_type']=='CONTRACT_PRODUCTION' else '</introduce_rf>')

    xml_text = "\n".join(lines)
    return BytesIO(xml_text.encode('utf-8'))


@app.route('/', methods=['GET', 'POST'])
def index():
    data = {}
    error = None
    json_path = session.get('json_path')

    # Чтение ранее загруженного файла
    if json_path and os.path.exists(json_path):
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = parse_json(f.read())
        except Exception as e:
            print(f"Ошибка чтения JSON: {e}")
            data = {}

    # Загрузка нового файла
    if request.method == 'POST' and 'json_file' in request.files:
        file = request.files['json_file']
        content = file.read()
        try:
            file_content = content
            if isinstance(file_content, bytes):
                file_content = file_content.decode('utf-8')

            parsed = parse_json(file_content)

            f = tempfile.NamedTemporaryFile(delete=False, suffix='.json', mode='w', encoding='utf-8')
            f.write(file_content)
            f.close()
            session['json_path'] = f.name
            return redirect(url_for('index'))
        except Exception as e:
            print(f"Ошибка при парсинге JSON: {e}")
            error = "Неверный формат JSON файла"

    return render_template('index.html', data=data, error=error)


@app.route('/download_csv', methods=['POST'])
def download_csv():
    codes_text = request.form.get('codes', '')
    file_name = request.form.get('file_name', 'codes')
    codes_clean = [line.strip() for line in codes_text.splitlines() if line.strip()]
    csv_content = "\n".join([c.replace('<GS>', '\x1D') for c in codes_clean])
    return send_file(BytesIO(csv_content.encode('utf-8')), mimetype='text/csv',
                     as_attachment=True, download_name=f"{file_name}.csv")


@app.route('/download_xml', methods=['POST'])
def download_xml():
    codes_text = request.form.get('codes', '')
    codes_clean = [line.strip() for line in codes_text.splitlines() if line.strip()]
    file_name = request.form.get('file_name', 'file')

    json_path = session.get('json_path')
    if json_path and os.path.exists(json_path):
        with open(json_path, 'r', encoding='utf-8') as f:
            try:
                data = parse_json(f.read())
            except Exception as e:
                print(f"Ошибка парсинга JSON для XML: {e}")
                data = {}
    else:
        data = {}

    xml_bytes = generate_xml(data, codes_clean)
    return send_file(xml_bytes, mimetype='application/xml', as_attachment=True, download_name=f"{file_name}.xml")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
