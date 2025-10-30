import requests
import json


def send_auth_request(base_url, login, password):
    url = f"{base_url}/api/auth"
    payload = {"login": login, "password": password}
    headers = {"Content-Type": "application/json"}

    try:
        response = requests.post(url, data=json.dumps(payload), headers=headers)
        if response.status_code == 200:
            print("✅ Авторизация успешна")
            return response.json()
        else:
            print(f"❌ Ошибка авторизации: {response.status_code}")
            print(response.text)
            return None
    except Exception as e:
        print(f"⚠️ Ошибка при отправке запроса авторизации: {e}")
        return None


# ===============================
# 🔹 1. Заявка на приёмку
# ===============================
def send_accept_request(base_url, token, object_id, doc_id, doc_date):
    url = f"{base_url}/api/v1/document/tsd-run?access-token={token}"

    payload = {
        "data": {
            "action_id": 701,
            "doc_date_mdlp": doc_date,
            "doc_num_mdlp": doc_id
        },
        "doc_date": doc_date,
        "doc_id": doc_id,
        "doc_num": doc_id,
        "facility_id": object_id,
        "object_id": object_id,
        "product_group_id": 12,
        "type_id": 35
    }

    return _post_request(url, payload)


# ===============================
# 🔹 2. Имитация сканирования — приёмка
# ===============================
def send_incom_request(base_url, token, document_id, object_id, codes: list):
    url = f"{base_url}/api/incom?access-token={token}"

    payload = {
        "codes": codes,
        "document_id": document_id,
        "hasStaffed": True,
        "object_uid": object_id
    }

    return _post_request(url, payload)


# ===============================
# 🔹 3. Имитация сканирования — перемещение
# ===============================
def send_outcom_request(base_url, token, invoice, invoice_date, object_id, codes: list):
    url = f"{base_url}/api/outcom?access-token={token}"

    payload = {
        "codes": codes,
        "hasStaffed": False,
        "invoice": invoice,
        "invoiceDate": invoice_date,
        "object_uid": object_id
    }

    return _post_request(url, payload)


# ===============================
# 🔹 4. Разгруппировка
# ===============================
def send_ungroup_request(base_url, token, group_code):
    url = f"{base_url}/api/unGroup?access-token={token}"

    payload = {
        "groupCode": group_code,
        "note": "Другое - разгруппировано"
    }

    return _post_request(url, payload)


# ===============================
# ⚙️ Вспомогательная функция
# ===============================
def _post_request(url, payload):
    """Отправка POST-запроса с логом"""
    headers = {"Content-Type": "application/json"}

    print(f"\n➡️ Отправляем запрос на: {url}")
    print("📦 Тело запроса:")
    print(json.dumps(payload, indent=4, ensure_ascii=False))

    try:
        response = requests.post(url, json=payload, headers=headers)
        print(f"\n🔄 Код ответа: {response.status_code}")
        if response.status_code == 200:
            print("✅ Успешный ответ:")
            print(response.json())
            return response.json()
        else:
            print(f"❌ Ошибка {response.status_code}: {response.text}")
            return None
    except Exception as e:
        print(f"⚠️ Ошибка при выполнении запроса: {e}")
        return None


# ===============================
# 🧪 Пример использования
# ===============================
if __name__ == "__main__":
    from config import Config
    config = Config()

    base_url = config.SOTEX.dev
    creds = config.SOTEX["27"]

    # Авторизация
    auth = send_auth_request(base_url, creds.login, creds.password)
    token = auth["token"]["id"]
    print(token)
    # Примеры:
    # send_accept_request(base_url, token, 27, "00000013978", "2025-10-28")
    #
    # send_incom_request(base_url, token, "e4d7ae03-ce00-4ee9-824d-b883f7e706f8", 27,
    #                    ["046501092025896050", "046501092025936305"])
    #
    # send_outcom_request(base_url, token, "00000013978", "2025-10-28", 27,
    #                     ["046501092025896050", "046501092025936305"])
    #
    # send_ungroup_request(base_url, token, "046501092025936602")
