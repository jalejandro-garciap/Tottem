import yaml
from pathlib import Path

path = Path("config/config.yaml")
with open(path, "r", encoding="utf-8") as f:
    try:
        data = yaml.safe_load(f)
        print("Success:", data)
    except Exception as e:
        print("Error Type:", type(e))
        print("Error Msg:", e)
