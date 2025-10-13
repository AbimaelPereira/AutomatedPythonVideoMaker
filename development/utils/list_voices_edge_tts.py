# list_filtered_voices.py
import asyncio
import edge_tts

FILTER_LANGS = ("pt-", "es-", "en-")  # Português, Espanhol e Inglês
FILTER_GENDER = "Male"  # Somente vozes masculinas

async def list_filtered_voices():
    voices = await edge_tts.list_voices()
    filtered = [
        v for v in voices
        if v["Gender"] == FILTER_GENDER and v["Locale"].startswith(FILTER_LANGS)
    ]

    print(f"🔊 Total de vozes masculinas encontradas: {len(filtered)}\n")

    for voice in filtered:
        print(f"Nome: {voice['Name']}")
        print(f"ShortName: {voice['ShortName']}")
        print(f"Gênero: {voice['Gender']}")
        print(f"Idioma: {voice['Locale']}")
        print("-" * 40)

if __name__ == "__main__":
    asyncio.run(list_filtered_voices())
