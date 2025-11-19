import yaml

class DotDict(dict):
    """Простая реализация для доступа к ключам словаря через точку."""
    def __getattr__(self, item):
        val = self.get(item)
        if isinstance(val, dict) and not isinstance(val, DotDict):
            return DotDict(val)
        return val

    __setattr__ = dict.__setitem__
    __delattr__ = dict.__delitem__

def get_config() -> DotDict:
    """Загружает конфигурацию из config.yaml и возвращает её в виде удобного объекта."""
    with open("config.yaml", "r") as f:
        config_dict = yaml.safe_load(f)
    return DotDict(config_dict)
