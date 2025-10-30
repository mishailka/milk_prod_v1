import xml.etree.ElementTree as ET

def compare_string_arrays(arr1: list[str], arr2: list[str]):
    """
    Сравнивает два массива строк и возвращает словарь с результатом.

    Если массивы совпадают, возвращает {"equal": True}.
    Если нет — {"equal": False, "only_in_first": [...], "only_in_second": [...]}.
    """

    # Преобразуем в множества, чтобы легко найти различия
    set1, set2 = set(arr1), set(arr2)

    # Разности
    only_in_first = sorted(list(set1 - set2))
    only_in_second = sorted(list(set2 - set1))

    if not only_in_first and not only_in_second:
        print("✅ Массивы совпадают полностью.")
        return {"equal": True}
    else:
        print("❌ Массивы различаются.")
        if only_in_first:
            print("➡️ Есть только в первом массиве:", only_in_first)
        if only_in_second:
            print("⬅️ Есть только во втором массиве:", only_in_second)

        return {
            "equal": False,
            "only_in_first": only_in_first,
            "only_in_second": only_in_second
        }


import re
import xml.etree.ElementTree as ET


def extract_sscc_codes(xml_source: str) -> list[str]:
    """
    Извлекает все <sscc>...</sscc> из XML-файла или XML-строки.

    Поддерживает:
      - путь к файлу (.xml)
      - XML в виде строки (в том числе с HTML-мусором в начале)

    :param xml_source: путь к файлу или XML-строка
    :return: список кодов (list[str])
    """
    try:
        # Определяем, это путь к файлу или XML-текст
        if xml_source.strip().endswith(".xml") or "\n" not in xml_source:
            with open(xml_source, "r", encoding="utf-8") as f:
                xml_content = f.read()
        else:
            xml_content = xml_source

        # Очищаем возможные "мусорные" префиксы вроде "This XML file does not appear..."
        xml_content = re.sub(r"^[^<]+<", "<", xml_content.strip(), flags=re.DOTALL)

        # Парсим XML
        root = ET.fromstring(xml_content)

        # Ищем все теги <sscc> на любом уровне
        codes = [el.text.strip() for el in root.iter() if el.tag.endswith("sscc") and el.text]

        print(f"✅ Найдено {len(codes)} код(ов) SSCC")
        return codes

    except ET.ParseError as e:
        print(f"❌ Ошибка парсинга XML: {e}")
        return []
    except FileNotFoundError:
        print(f"❌ Файл не найден: {xml_source}")
        return []
    except Exception as e:
        print(f"⚠️ Ошибка при обработке XML: {e}")
        return []


if __name__ =="__main__":
    codes = extract_sscc_codes("601.xml")
    # print(codes)
    codes2 = extract_sscc_codes("701.xml")
    # print(codes2)


    a = compare_string_arrays(codes,codes2)
    print(a)