import json
import os
from typing import Any

class ConfigEntity:
    """Вложенная сущность с автодополнением и поддержкой [] и ."""
    def __init__(self, name: str):
        self._name = name
        self._children = {}  # для ID или вложенных объектов

    def add_data(self, data: Any):
        if isinstance(data, dict):
            for k, v in data.items():
                if isinstance(v, dict):
                    # создаём вложенный объект для ID или группы
                    if k not in self._children:
                        self._children[k] = ConfigEntity(k)
                    self._children[k].add_data(v)
                    setattr(self, k, self._children[k])
                else:
                    # обычное поле
                    setattr(self, k, v)
        else:
            setattr(self, "value", data)

    def __getitem__(self, key):
        return getattr(self, key)

    def __dir__(self):
        # IDE будет видеть все обычные атрибуты + children
        return list(self.__dict__.keys()) + list(self._children.keys())

class Config:
    """Главный объект конфигурации с автозагрузкой всех JSON-файлов"""
    def __init__(self, config_folder: str = None):
        self._entities = {}

        # Если папка не указана, ищем config_files рядом со скриптом
        if config_folder is None:
            project_root = os.path.dirname(os.path.abspath(__file__))
            config_folder = os.path.join(project_root, "varables")

        config_folder = os.path.abspath(config_folder)
        if not os.path.exists(config_folder):
            raise FileNotFoundError(f"Папка с конфигами не найдена: {config_folder}")

        # Загружаем все JSON-файлы
        for filename in os.listdir(config_folder):
            if filename.endswith(".json"):
                path = os.path.join(config_folder, filename)
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._merge_data(data)

    def _merge_data(self, data: dict):
        for name, value in data.items():
            if name not in self._entities:
                self._entities[name] = ConfigEntity(name)
            self._entities[name].add_data(value)

    def __getattr__(self, name):
        if name in self._entities:
            return self._entities[name]
        raise AttributeError(f"Нет сущности с именем '{name}'")

    def __dir__(self):
        # IDE будет видеть все верхнеуровневые сущности
        return list(self._entities.keys())



if __name__ == "__main__":
    # Просто создаём объект — папка выбирается сама
    config = Config()

    # Доступ к аккаунтам
    print(config.SOTEX["5"].login)  # root
    print(config.SOTEX["5"].password)  # R2020t
    print(config.SOTEX["27"].desc)  # Склад ответственного хранения

    # Доступ к RAFARMA
    print(config.RAFARMA["7"].login)  # root