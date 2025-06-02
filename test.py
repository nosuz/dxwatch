import os
import requests

print(requests.__version__)
print("Hello")

venv_path = os.environ.get("VIRTUAL_ENV")

if venv_path:
    print(f"VIRTUAL_ENV is set to: {venv_path}")
else:
    print("VIRTUAL_ENV is not set.")
