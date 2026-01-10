import requests
from urllib.parse import quote

API_TOKEN = "sk_LWBaRZ8YI4SXWmRTpfscqJkrsEcvvOGd"

prompt = (
    "A minimalist stick figure standing with one hand placed over chest area in heart region, "
    "other arm relaxed at side, head slightly bowed, constructed with straight lines and circle "
    "in #E8E4DD, centered on solid #121212 background, vertical 9:16 composition, flat design."
)

url = f"https://gen.pollinations.ai/image/{quote(prompt)}"

headers = {
    "Authorization": f"Bearer {API_TOKEN}"
}

params = {
    "model": "zimage", # sdxl-turbo|zimage
    "width": 576,
    "height": 1024,
    "seed": 1,
    "safe": "false"
}

response = requests.get(url, headers=headers, params=params, timeout=60)

if response.status_code == 200 and response.headers.get("content-type", "").startswith("image"):
    with open("image.png", "wb") as f:
        f.write(response.content)
    print("✅ Imagem gerada com sucesso")
else:
    print("❌ Erro")
    print(response.status_code)
    print(response.text)
