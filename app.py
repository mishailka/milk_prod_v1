from flask import Flask, render_template, request, send_file
import json
import csv
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom.minidom import parseString
from io import StringIO, BytesIO
from xml.etree.ElementTree import Element, SubElement, tostring, ElementTree
import os
import xml.etree.ElementTree as ET

app = Flask(__name__)

def decode_certificate_number(cert_number):
    try:
        # Попытка обычной декодировки Unicode
        decoded = cert_number.encode('utf-8').decode('unicode_escape')
    except Exception:
        decoded = cert_number
    try:
        # Исправляем "ÐÐÐ­Ð¡"-подобные случаи
        decoded = decoded.encode('latin1').decode('utf-8')
    except Exception:
        pass
    return decoded

def generate_csv(codes):
    output = StringIO()
    writer = csv.writer(output)
    for code in codes:
        if code.strip():
            writer.writerow([code.replace('<GS>', '')])
    csv_bytes = BytesIO(output.getvalue().encode('utf-8'))
    output.close()
    return csv_bytes


from xml.dom.minidom import Document
from io import BytesIO


def generate_xml(production_type, data):
    """
    Генерация XML с CDATA, читаемыми отступами и без encoding в шапке.
    production_type: "CONTRACT_PRODUCTION" или "OWN_PRODUCTION"
    data: словарь с ключами:
        producer_inn, owner_inn, production_date, production_order,
        tnved_code, certificate_number, certificate_date,
        vsd_number (опционально), codes (список)
    """
    doc = Document()

    # Корневой тег
    root_tag = "introduce_contract" if production_type == "CONTRACT_PRODUCTION" else "introduce_rf"
    version = "7" if production_type == "CONTRACT_PRODUCTION" else "9"
    root = doc.createElement(root_tag)
    root.setAttribute("version", version)
    doc.appendChild(root)

    # Шапка документа
    producer = doc.createElement("producer_inn")
    producer.appendChild(doc.createTextNode(data.get("producer_inn", "")))
    root.appendChild(producer)

    owner = doc.createElement("owner_inn")
    owner.appendChild(doc.createTextNode(data.get("owner_inn", "")))
    root.appendChild(owner)

    prod_date = doc.createElement("production_date")
    prod_date.appendChild(doc.createTextNode(data.get("production_date", "")))
    root.appendChild(prod_date)

    prod_order = doc.createElement("production_order")
    prod_order.appendChild(doc.createTextNode(data.get("production_order", "")))
    root.appendChild(prod_order)

    # Список продуктов
    products_list = doc.createElement("products_list")
    root.appendChild(products_list)

    for code in data.get("codes", []):
        product = doc.createElement("product")

        # CDATA для кода
        ki = doc.createElement("ki")
        ki.appendChild(doc.createCDATASection(code.split("<GS>")[0]))
        product.appendChild(ki)

        # Остальные поля продукта
        pd = doc.createElement("production_date")
        pd.appendChild(doc.createTextNode(data.get("production_date", "")))
        product.appendChild(pd)

        tnved = doc.createElement("tnved_code")
        tnved.appendChild(doc.createTextNode(data.get("tnved_code", "")))
        product.appendChild(tnved)

        ctype = doc.createElement("certificate_type")
        ctype.appendChild(doc.createTextNode("CONFORMITY_DECLARATION"))
        product.appendChild(ctype)

        cnumber = doc.createElement("certificate_number")
        cnumber.appendChild(doc.createTextNode(data.get("certificate_number", "")))
        product.appendChild(cnumber)

        cdate = doc.createElement("certificate_date")
        cdate.appendChild(doc.createTextNode(data.get("certificate_date", "")))
        product.appendChild(cdate)

        vsd_number = data.get("vsd_number")
        if vsd_number:
            vsd_elem = doc.createElement("vsd_number")
            vsd_elem.appendChild(doc.createTextNode(vsd_number))
            product.appendChild(vsd_elem)

        products_list.appendChild(product)

    # Красивый XML с отступами, без encoding в шапке
    xml_str = doc.toprettyxml(indent="    ", newl="\n")

    # Преобразуем в BytesIO для Flask
    xml_bytes = BytesIO(xml_str.encode("utf-8"))
    return xml_bytes


@app.route('/')
def index():
    return render_template('index.html')

@app.route('/process_json', methods=['POST'])
def process_json():
    file = request.files['json_file']
    data_json = json.load(file)

    producer_inn = data_json.get('producer_inn', 'Не найдено')
    owner_inn = data_json.get('owner_inn', 'Не найдено')
    production_date = data_json.get('production_date', 'Не найдено')
    production_order = data_json.get('production_order', 'OWN_PRODUCTION')

    products = data_json.get('products_list', [])
    if products:
        first_product = products[0]
        vsd_number = first_product.get('vsd_number', 'Не найдено')
        tnved_code = first_product.get('tnved_code', 'Не найдено')
        cert_data = first_product.get('certificate_document_data', [{}])[0]
        certificate_number = decode_certificate_number(cert_data.get('certificate_number', 'Не найдено'))
        certificate_date = cert_data.get('certificate_date', 'Не найдено')
        codes = [p.get('uit', '') for p in products]
    else:
        vsd_number = tnved_code = certificate_number = certificate_date = ''
        codes = []

    production_order_type = "CONTRACT_PRODUCTION" if production_order == "CONTRACT_PRODUCTION" or producer_inn != owner_inn else "OWN_PRODUCTION"

    result = {
        'producer_inn': producer_inn,
        'owner_inn': owner_inn,
        'production_date': production_date,
        'production_order': production_order,
        'codes': codes,
        'certificate_number': certificate_number,
        'certificate_date': certificate_date,
        'vsd_number': vsd_number,
        'tnved_code': tnved_code,
        'production_order_type': production_order_type,
    }

    return render_template('index.html', result=result)

@app.route('/generate_csv', methods=['POST'])
def generate_csv_route():
    codes = request.form.get('codes', '').splitlines()
    filename = request.form.get('filename', 'codes') + '.csv'
    csv_bytes = generate_csv(codes)
    return send_file(csv_bytes, mimetype='text/csv', as_attachment=True, download_name=filename)

@app.route('/generate_xml', methods=['POST'])
def generate_xml_route():
    data = request.form.to_dict()
    codes = request.form.get('codes', '').splitlines()
    filename = request.form.get('filename', 'data') + '.xml'
    data['codes'] = codes
    production_type = data.get('production_order_type', 'OWN_PRODUCTION')
    xml_bytes = generate_xml(production_type, data)
    return send_file(xml_bytes, mimetype='application/xml', as_attachment=True, download_name=filename)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))