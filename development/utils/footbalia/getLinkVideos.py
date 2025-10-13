# carregar bibliotecas para modificar o arquivo json
import json
import os

DIR_SAVE_VIDEOS = "/media/abimael/Grupo Win Lite BR"
JSO_FILE = "myJson.json"
URLS = [
    "https://footballia.net/pt/goals?player_id=5183&competition_id=&team_id=&team_ids=&page=4",
    "https://footballia.net/pt/goals?player_id=5638&competition_id=&team_id=&team_ids=&page=2",
    "https://footballia.net/pt/goals?player_id=4732&competition_id=&team_id=&team_ids=&page=7",
    "https://footballia.net/pt/goals?player_id=5262&competition_id=&team_id=&team_ids=&page=0",
    "https://footballia.net/pt/goals?player_id=20084&competition_id=&team_id=&team_ids=&page=1",
    "https://footballia.net/pt/goals?player_id=27534&competition_id=&team_id=&team_ids=&page=0"
]

BASE_URL = "https://footballia.net"

def makeRequest(url):
    import requests
    response = requests.get(url)
    if response.status_code == 200:
        return response.json()
    else:
        print(f"Erro ao acessar {url}: {response.status_code}")
        return None
    
def addItemsToJsonFile(items, json_file):
    if os.path.exists(json_file):
        with open(json_file, 'r', encoding='utf-8') as file:
            data = json.load(file)
    else:
        data = []

    data.extend(items)

    with open(json_file, 'w', encoding='utf-8') as file:
        json.dump(data, file, ensure_ascii=False, indent=4)

# acessar as urls 
for url in URLS:
    print(f"Acessando {url}")
    # fazer a requisição HTTP
    data = makeRequest(url)
    if len(data['goals']) == 0:
        continue

    ITEMS = []

    # pegar os 10 ultimos
    for item in data['goals'][-20:]:
        if 'file' not in item or not item['file']:
            continue

        video_url = BASE_URL + item['file']
        ITEMS.append(video_url)

    print(f"Adicionando {len(ITEMS)} itens ao arquivo JSON")
    addItemsToJsonFile(ITEMS, JSO_FILE)

print("Processo concluído.")
