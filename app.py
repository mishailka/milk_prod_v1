import os
import re
import json
import tempfile
from datetime import datetime
from io import BytesIO
from flask_session import Session


import requests
from flask import (
    Flask, render_template, request, redirect, url_for,
    session, send_file, flash
)

# === Твои модули/конфиги ===
from config import Config  # динамически грузит varables/*.json :contentReference[oaicite:4]{index=4}
from requests_service import (
    send_auth_request,        # авторизация   :contentReference[oaicite:5]{index=5}
    send_accept_request,      # заявка на приёмку
    send_incom_request,       # имитация сканирования (приёмка)
    send_outcom_request,      # перемещение
    send_ungroup_request      # разгруппировка
)

app = Flask(__name__)
app.secret_key = os.urandom(24)
# --- серверные сессии ---
app.config['SESSION_TYPE'] = 'filesystem'          # хранить сессии на диске
app.config['SESSION_FILE_DIR'] = './.flask_session'  # каталог для файлов
app.config['SESSION_PERMANENT'] = False
app.config['SESSION_USE_SIGNER'] = True
app.config['SESSION_FILE_THRESHOLD'] = 200          # максимум файлов
Session(app)
# =========================
# 🔧 Режим отладки (debug)
# =========================
DEBUG_MODE = True  # 👉 ВКЛ/ВЫКЛ интерактивные подтверждения шагов


# =========================================================
# ============== Блок 1. МОЛОЧНЫЙ JSON-СЕРВИС =============
# =========================================================

def parse_json(file_content: str) -> dict:
    """Разбор молочного JSON (из твоего предыдущего кода)"""
    try:
        data = json.loads(file_content)
    except Exception:
        return {}

    result = {
        'producer_inn': data.get('producer_inn') or data.get('participant_inn'),
        'owner_inn': data.get('owner_inn') or data.get('producer_inn'),
        'production_date': data.get('production_date', ''),
        'production_type': data.get('production_type', ''),
        'products': []
    }

    if not result['production_type']:
        result['production_type'] = 'OWN_PRODUCTION' if result['producer_inn'] == result['owner_inn'] else 'CONTRACT_PRODUCTION'

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


def generate_xml(data: dict, codes: list[str]) -> BytesIO:
    """Генерация XML для молочного блока (из твоего кода)"""
    lines = []
    codes_clean = [line.strip() for line in codes if line.strip()]

    if data.get('production_type') == 'CONTRACT_PRODUCTION':
        lines.append('<introduce_contract version="7">')
        lines.append(f'    <producer_inn>{data.get("producer_inn","")}</producer_inn>')
        lines.append(f'    <owner_inn>{data.get("owner_inn","")}</owner_inn>')
        lines.append(f'    <production_date>{data.get("production_date","")}</production_date>')
        lines.append(f'    <production_order>{data.get("production_type","")}</production_order>')
    else:
        lines.append('<introduce_rf version="9">')
        lines.append(f'    <trade_participant_inn>{data.get("producer_inn","")}</trade_participant_inn>')
        lines.append(f'    <producer_inn>{data.get("producer_inn","")}</producer_inn>')
        lines.append(f'    <owner_inn>{data.get("owner_inn","")}</owner_inn>')
        lines.append(f'    <production_date>{data.get("production_date","")}</production_date>')
        lines.append(f'    <production_order>{data.get("production_type","")}</production_order>')

    lines.append('    <products_list>')

    p = (data.get('products') or [{}])[0]

    for code in codes_clean:
        lines.append('        <product>')
        lines.append(f'            <ki><![CDATA[{code.split("<GS>")[0].strip()}]]></ki>')
        lines.append(f'            <production_date>{data.get("production_date","")}</production_date>')
        lines.append(f'            <tnved_code>{p.get("tnved_code","")}</tnved_code>')
        lines.append('            <certificate_type>CONFORMITY_DECLARATION</certificate_type>')
        lines.append(f'            <certificate_number>{p.get("certificate_number","")}</certificate_number>')
        lines.append(f'            <certificate_date>{p.get("certificate_date","")}</certificate_date>')
        if p.get("vsd_number"):
            lines.append(f'            <vsd_number>{p["vsd_number"]}</vsd_number>')
        lines.append('        </product>')

    lines.append('    </products_list>')
    lines.append('</introduce_contract>' if data.get('production_type') == 'CONTRACT_PRODUCTION' else '</introduce_rf>')
    return BytesIO("\n".join(lines).encode('utf-8'))


@app.route('/milk_upload_json', methods=['POST'])
def milk_upload_json():
    """Загрузка JSON на первой вкладке: сохраняем во временный файл и показываем распарсенные поля"""
    file = request.files.get('json_file')
    if not file:
        flash("Не выбран JSON-файл")
        return redirect(url_for('index'))

    content = file.read()
    try:
        text = content.decode('utf-8') if isinstance(content, bytes) else content
        parsed = parse_json(text)
        # сохраним исходник в temp — для генерации XML по кнопке
        f = tempfile.NamedTemporaryFile(delete=False, suffix='.json', mode='w', encoding='utf-8')
        f.write(text)
        f.close()
        session['json_path'] = f.name
        session['milk_parsed'] = parsed
        flash("✅ JSON загружен и распарсен")
    except Exception as e:
        flash(f"Ошибка парсинга JSON: {e}")
    return redirect(url_for('index'))


@app.route('/download_csv', methods=['POST'])
def download_csv():
    """Скачивание CSV (вкладка 1)"""
    codes_text = request.form.get('codes', '')
    file_name = request.form.get('file_name', 'codes')
    codes_clean = [line.strip() for line in codes_text.splitlines() if line.strip()]
    csv_content = "\n".join([c.replace('<GS>', '\x1D') for c in codes_clean])
    return send_file(BytesIO(csv_content.encode('utf-8')), mimetype='text/csv',
                     as_attachment=True, download_name=f"{file_name}.csv")


@app.route('/download_xml', methods=['POST'])
def download_xml():
    """Скачивание XML (вкладка 1)"""
    codes_text = request.form.get('codes', '')
    codes_clean = [line.strip() for line in codes_text.splitlines() if line.strip()]
    file_name = request.form.get('file_name', 'file')

    json_path = session.get('json_path')
    if not json_path or not os.path.exists(json_path):
        flash("JSON не загружен")
        return redirect(url_for('index'))

    with open(json_path, 'r', encoding='utf-8') as f:
        data = parse_json(f.read())
    xml_bytes = generate_xml(data, codes_clean)
    return send_file(xml_bytes, mimetype='application/xml', as_attachment=True, download_name=f"{file_name}.xml")


# =========================================================
# ============== Блок 2. XML-ПЕРЕМЕЩЕНИЕ ==================
# =========================================================

def _clean_xml(text: str) -> str:
    return re.sub(r"^[^<]+<", "<", text.strip(), flags=re.DOTALL)

def extract_sscc_codes_from_text(xml_text: str) -> list[str]:
    """Извлекаем все <sscc>...</sscc> из XML (устойчиво к мусору в начале)"""
    xml_text = _clean_xml(xml_text)
    # сначала CDATA, затем обычный
    codes = re.findall(r"<\s*sscc\s*>\s*<!\[CDATA\[(.*?)\]\]>\s*</\s*sscc\s*>", xml_text, flags=re.IGNORECASE)
    if not codes:
        codes = re.findall(r"<\s*sscc\s*>\s*([^<]+)\s*</\s*sscc\s*>", xml_text, flags=re.IGNORECASE)
    return [c.strip() for c in codes if c and c.strip()]

def parse_move_info(xml_text: str) -> dict:
    """Достаём doc_num и doc_date (YYYY-MM-DD) из <move_order_notification> (или просто doc_num/doc_date в документе)"""
    xml_text = _clean_xml(xml_text)
    out = {}
    m_num = re.search(r"<\s*doc_num\s*>\s*([^<]+)\s*</\s*doc_num\s*>", xml_text, flags=re.IGNORECASE)
    if m_num:
        out["doc_num"] = m_num.group(1).strip()
    m_date = re.search(r"<\s*doc_date\s*>\s*([^<]+)\s*</\s*doc_date\s*>", xml_text, flags=re.IGNORECASE)
    if m_date:
        raw = m_date.group(1).strip()
        iso = None
        for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%S%z"):
            try:
                dt = datetime.strptime(raw, fmt)
                iso = dt.strftime("%Y-%m-%d")
                break
            except Exception:
                pass
        if not iso:
            m_iso = re.search(r"(\d{4}-\d{2}-\d{2})", raw)
            if m_iso:
                iso = m_iso.group(1)
        if iso:
            out["doc_date"] = iso
    return out

def compare_arrays(a: list[str], b: list[str]) -> dict:
    sa, sb = set(a), set(b)
    return {
        "equal": sa == sb,
        "only_in_first": sorted(sa - sb),
        "only_in_second": sorted(sb - sa)
    }

def vendor_base_url(cfg: Config, vendor: str) -> str:
    vendor = vendor.strip().upper()
    try:
        return getattr(getattr(cfg, vendor), "dev")
    except Exception:
        raise ValueError(f"Нет ссылки dev для {vendor} в varables/links.json")
OBJECT_TO_MD = {
    "431982": "27",
    "528771": "45",
    "3057": "5",
    "3060": "7"
}
def get_creds_for(cfg: Config, vendor: str, object_id: str) -> tuple[str, str]:
    md = OBJECT_TO_MD.get(str(object_id), object_id)
    entity = getattr(cfg, vendor.upper())
    try:
        node = entity[md]
        return node.login, node.password
    except Exception:
        raise ValueError(f"Нет логина/пароля для {vendor}:{object_id} (МД {md}) в varables/accounts.json")

# ---------- Логи (в сессии) ----------
def add_log(step, action, status, message):
    session.setdefault("flow_logs", []).append({
        "time": datetime.now().strftime("%H:%M:%S"),
        "step": step,
        "action": action,
        "status": status,   # 🟢/🔴
        "message": message
    })
    session.modified = True

@app.route("/clear_logs")
def clear_logs():
    session["flow_logs"] = []
    flash("Лог очищен")
    return redirect(url_for("index"))


# =========================================================
# ======= Debug-подтверждение шага перед отправкой ========
# =========================================================

def _confirm_or_send(step_key: str, title: str, url: str, payload: dict, method: str = "POST"):
    """
    Если DEBUG_MODE: показываем confirm.html с возможностью правки payload.
    Иначе — сразу отправляем запрос.
    """
    if DEBUG_MODE:
        session["pending_request"] = {
            "step_key": step_key,
            "title": title,
            "url": url,
            "payload": payload,
            "method": method
        }
        session.modified = True
        return render_template("confirm.html", title=title, url=url, step=step_key, payload=payload)

    # обычный режим — просто отправляем
    return _send_raw_request(step_key, url, payload, method)


@app.route("/confirm_request", methods=["POST"])
def confirm_request():
    """Обработчик формы подтверждения/отмены"""
    action = request.form.get("action")
    step_key = request.form.get("step")
    try:
        pending = session.get("pending_request") or {}
        url = pending.get("url")
        payload_text = request.form.get("payload", "")
        payload = json.loads(payload_text) if payload_text.strip() else {}
        method = pending.get("method", "POST")

        if action == "cancel":
            add_log(step_key, "Отмена шага", "🔴", "Пользователь отменил отправку")
            # завершаем процесс
            flash("Процесс остановлен пользователем")
            session.pop("pending_request", None)
            return redirect(url_for("index"))

        # action == "send"
        session.pop("pending_request", None)
        return _send_raw_request(step_key, url, payload, method)

    except Exception as e:
        add_log(step_key or "—", "Ошибка подтверждения", "🔴", str(e))
        flash(f"Ошибка подтверждения: {e}")
        session.pop("pending_request", None)
        return redirect(url_for("index"))


def _send_raw_request(step_key: str, url: str, payload: dict, method: str = "POST"):
    """Фактическая отправка запроса (используется подтверждением и авто-режимом)"""
    try:
        resp = requests.request(method, url, json=payload, headers={"Content-Type": "application/json"})
        status = f"{resp.status_code}"
        text = resp.text
        # короткий лог
        add_log(step_key, f"HTTP {method}", "🟢" if resp.ok else "🔴", f"{url} → {status}")
        # Сохраним ответ в контекст, чтобы следующий шаг мог вытащить токен/id
        session.setdefault("raw_responses", {})[step_key] = {
            "status": resp.status_code,
            "json": safe_json(resp),
            "text": text[:1000]  # safety
        }
        session.modified = True
        return _advance_flow_after(step_key)
    except Exception as e:
        add_log(step_key, "Ошибка HTTP", "🔴", str(e))
        flash(f"Ошибка запроса: {e}")
        return redirect(url_for("index"))


def safe_json(resp):
    try:
        return resp.json()
    except Exception:
        return None


def _advance_flow_after(step_key: str):
    """
    Переход к следующему шагу цепочки (в debug-режиме после отправки).
    Извлекаем нужные данные из ответа прошлого шага и двигаемся дальше.
    """
    ctx = session.get("flow_ctx") or {}
    raw = session.get("raw_responses", {})
    cfg = Config()

    vendor = ctx.get("vendor")
    base = vendor_base_url(cfg, vendor)

    # вспомогалки для чтения ответов, в твоих ответах поля такие:
    # auth:   {"token":{"id": "..."}}
    # accept: {"data":{"id": "..."}}
    def get_token(step_name):
        j = raw.get(step_name, {}).get("json") or {}
        return (((j.get("token") or {}).get("id")) if isinstance(j, dict) else None)

    def get_doc_id(step_name):
        j = raw.get(step_name, {}).get("json") or {}
        data = j.get("data") if isinstance(j, dict) else None
        if isinstance(data, dict):
            return data.get("id") or data.get("doc_id")
        return None

    # шаги
    if step_key == "auth1":
        token1 = get_token("auth1")
        if not token1:
            add_log("auth1", "Ошибка", "🔴", "Не получили token1")
            return redirect(url_for("index"))
        ctx["token1"] = token1
        session["flow_ctx"] = ctx
        # → заявка 1
        payload = {
            "data": {"action_id": 701, "doc_date_mdlp": ctx["doc_date"], "doc_num_mdlp": ctx["doc_num"]},
            "doc_date": ctx["doc_date"],
            "doc_id": ctx["doc_num"],
            "doc_num": ctx["doc_num"],
            "facility_id": int(ctx["md1"]),
            "object_id": int(ctx["md1"]),
            "product_group_id": 12,
            "type_id": 35
        }
        url = f'{base}/api/v1/document/tsd-run?access-token={token1}'
        return _confirm_or_send("accept1", "Заявка на приёмку (1)", url, payload)

    if step_key == "accept1":
        doc_id1 = get_doc_id("accept1")
        if not doc_id1:
            add_log("accept1", "Ошибка", "🔴", "Не получили document_id (1)")
            return redirect(url_for("index"))
        ctx["doc_id1"] = doc_id1
        session["flow_ctx"] = ctx
        # → имитация ТСД (1)
        payload = {
            "codes": ctx["codes"],
            "document_id": doc_id1,
            "hasStaffed": True,
            "object_uid": int(ctx["md1"])
        }
        url = f'{base}/api/incom?access-token={ctx["token1"]}'
        return _confirm_or_send("incom1", "Имитация ТСД (1)", url, payload)

    if step_key == "incom1":
        # → перемещение
        payload = {
            "codes": ctx["codes"],
            "hasStaffed": False,
            "invoice": ctx["invoice"],
            "invoiceDate": ctx["transfer_date"],
            "object_uid": int(ctx["md2"])
        }
        url = f'{base}/api/outcom?access-token={ctx["token1"]}'
        return _confirm_or_send("outcom", "Перемещение", url, payload)

    if step_key == "outcom":
        # → авторизация 2
        login2, pass2 = get_creds_for(cfg, vendor, ctx["md2"])
        payload = {"login": login2, "password": pass2}
        url = f'{base}/api/auth'
        return _confirm_or_send("auth2", "Авторизация (2)", url, payload)

    if step_key == "auth2":
        token2 = get_token("auth2")
        if not token2:
            add_log("auth2", "Ошибка", "🔴", "Не получили token2")
            return redirect(url_for("index"))
        ctx["token2"] = token2
        session["flow_ctx"] = ctx
        # → заявка 2
        payload = {
            "data": {"action_id": 701, "doc_date_mdlp": ctx["transfer_date"], "doc_num_mdlp": ctx["invoice"]},
            "doc_date": ctx["transfer_date"],
            "doc_id": ctx["invoice"],
            "doc_num": ctx["invoice"],
            "facility_id": int(ctx["md2"]),
            "object_id": int(ctx["md2"]),
            "product_group_id": 12,
            "type_id": 35
        }
        url = f'{base}/api/v1/document/tsd-run?access-token={token2}'
        return _confirm_or_send("accept2", "Заявка на приёмку (2)", url, payload)

    if step_key == "accept2":
        doc_id2 = get_doc_id("accept2")
        if not doc_id2:
            add_log("accept2", "Ошибка", "🔴", "Не получили document_id (2)")
            return redirect(url_for("index"))
        ctx["doc_id2"] = doc_id2
        session["flow_ctx"] = ctx
        # → имитация ТСД (2)
        payload = {
            "codes": ctx["codes"],
            "document_id": doc_id2,
            "hasStaffed": True,
            "object_uid": int(ctx["md2"])
        }
        url = f'{base}/api/incom?access-token={ctx["token2"]}'
        return _confirm_or_send("incom2", "Имитация ТСД (2)", url, payload)

    if step_key == "incom2":
        add_log("finish", "Готово", "🟢", "Цепочка завершена")
        flash("✅ Процесс успешно завершён")
        return redirect(url_for("index"))

    # если не узнали шаг — просто на индекс
    return redirect(url_for("index"))


# =========================================================
# ============== Запуск цепочки перемещения ===============
# =========================================================

def _start_flow_context(vendor, md1, md2, invoice, transfer_date, codes, doc_num, doc_date):
    """Инициализация контекста процесса"""
    session["flow_ctx"] = {
        "vendor": vendor.strip().upper(),
        "md1": md1.strip(),
        "md2": md2.strip(),
        "invoice": invoice.strip(),
        "transfer_date": transfer_date.strip(),
        "codes": codes,
        "doc_num": doc_num,
        "doc_date": doc_date
    }
    session["raw_responses"] = {}
    session["flow_logs"] = []
    session.modified = True


@app.route("/upload_xmls", methods=["POST"])
def upload_xmls():
    """Загрузка двух XML на вкладке 2 и сравнение их кодов"""
    f1 = request.files.get("xml1")
    f2 = request.files.get("xml2")
    if not f1 or not f2:
        flash("Загрузите два XML-файла")
        return redirect(url_for("index"))

    t1 = f1.read().decode("utf-8", errors="ignore")
    t2 = f2.read().decode("utf-8", errors="ignore")

    codes1 = extract_sscc_codes_from_text(t1)
    codes2 = extract_sscc_codes_from_text(t2)
    cmpres = compare_arrays(codes1, codes2)

    info = parse_move_info(t1) or {}
    if not info.get("doc_num") or not info.get("doc_date"):
        info2 = parse_move_info(t2) or {}
        if not info.get("doc_num"):
            info["doc_num"] = info2.get("doc_num")
        if not info.get("doc_date"):
            info["doc_date"] = info2.get("doc_date")

    session.update({
        "xml1_name": f1.filename, "xml2_name": f2.filename,
        "codes_equal": cmpres["equal"],
        "only_in_first": cmpres["only_in_first"],
        "only_in_second": cmpres["only_in_second"],
        "codes_base": codes1,            # берём коды из первого (равны второму, если equal=True)
        "doc_num_xml": info.get("doc_num"),
        "doc_date_xml": info.get("doc_date"),
        "flow_logs": [],
        "flow_ctx": None,
        "pending_request": None,
        "raw_responses": {}
    })
    return redirect(url_for("index"))


@app.route("/run_flow", methods=["POST"])
def run_flow_route():
    """Старт цепочки со вкладки 2"""
    if not session.get("codes_equal"):
        flash("XML-коды не совпадают — запуск невозможен")
        return redirect(url_for("index"))

    vendor = request.form.get("vendor", "SOTEX")
    md1 = request.form.get("md1", "")
    md2 = request.form.get("md2", "")
    invoice = request.form.get("invoice", "") or session.get("doc_num_xml", "")
    transfer_date = request.form.get("transfer_date", "") or session.get("doc_date_xml", "")

    if not (vendor and md1 and md2 and invoice and transfer_date):
        flash("Заполните все поля для запуска процесса")
        return redirect(url_for("index"))

    codes = session.get("codes_base", [])
    doc_num = session.get("doc_num_xml")
    doc_date = session.get("doc_date_xml")

    _start_flow_context(vendor, md1, md2, invoice, transfer_date, codes, doc_num, doc_date)

    # шаг 1: авторизация 1 (debug-страница или автомат)
    cfg = Config()
    base = vendor_base_url(cfg, vendor)
    login1, pass1 = get_creds_for(cfg, vendor, md1)
    url = f"{base}/api/auth"
    payload = {"login": login1, "password": pass1}
    return _confirm_or_send("auth1", "Авторизация (1)", url, payload)


# =========================================================
# ===================== ГЛАВНАЯ СТРАНИЦА ==================
# =========================================================

@app.route("/", methods=["GET"])
def index():
    state = {
        # Вкладка 1 (молочная)
        "milk_parsed": session.get("milk_parsed"),
        "json_path": session.get("json_path"),

        # Вкладка 2 (перемещение)
        "xml1_name": session.get("xml1_name"),
        "xml2_name": session.get("xml2_name"),
        "codes_equal": session.get("codes_equal"),
        "only_in_first": session.get("only_in_first", []),
        "only_in_second": session.get("only_in_second", []),
        "doc_num_xml": session.get("doc_num_xml"),
        "doc_date_xml": session.get("doc_date_xml"),
        "flow_logs": session.get("flow_logs", []),
        "debug_mode": DEBUG_MODE
    }
    return render_template("index.html", state=state)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
