"""Playlists do canal: listar, criar e inserir vídeos.

Tudo aqui é IDEMPOTENTE. Uma playlist com o mesmo título é reaproveitada em vez
de duplicada, e um vídeo já presente não é inserido de novo — a API do YouTube
aceita de bom grado duas playlists homônimas e o mesmo vídeo repetido, então a
checagem tem que ser nossa.

    from libs.YouTube import YouTube
    from libs.YouTubePlaylists import YouTubePlaylists

    yt = YouTube(params={"token_file_name": "/caminho/token.json"})
    pl = YouTubePlaylists(yt._get_credentials())
    info = pl.garantir("The Last Page", "Descrição da série", default_language="en")
    pl.adicionar(info["id"], "dQw4w9WgXcQ")
"""
from googleapiclient.discovery import build


class YouTubePlaylists:
    def __init__(self, credentials, verbose: bool = True):
        self.yt = build("youtube", "v3", credentials=credentials,
                        cache_discovery=False)
        self.verbose = verbose

    def _log(self, msg):
        if self.verbose:
            print(f"[YouTubePlaylists] {msg}", flush=True)

    # ------------------------------------------------------------------
    # LEITURA
    # ------------------------------------------------------------------
    def listar(self) -> list:
        """Todas as playlists do canal autenticado."""
        itens, token = [], None
        while True:
            r = self.yt.playlists().list(part="snippet,status,contentDetails",
                                         mine=True, maxResults=50,
                                         pageToken=token).execute()
            itens += r.get("items", [])
            token = r.get("nextPageToken")
            if not token:
                return itens

    def por_titulo(self) -> dict:
        """{título: id} das playlists do canal."""
        return {p["snippet"]["title"]: p["id"] for p in self.listar()}

    def itens(self, playlist_id: str) -> list:
        """Os video_ids dentro de uma playlist, na ordem."""
        ids, token = [], None
        while True:
            r = self.yt.playlistItems().list(part="contentDetails",
                                             playlistId=playlist_id,
                                             maxResults=50,
                                             pageToken=token).execute()
            ids += [i["contentDetails"]["videoId"] for i in r.get("items", [])]
            token = r.get("nextPageToken")
            if not token:
                return ids

    # ------------------------------------------------------------------
    # ESCRITA
    # ------------------------------------------------------------------
    def garantir(self, titulo: str, descricao: str = "",
                 privacy_status: str = "public",
                 default_language: str | None = None) -> dict:
        """Devolve a playlist de título `titulo`, criando-a se não existir.

        `{"id": ..., "titulo": ..., "criada": True|False}` — `criada` diz se
        houve escrita, para quem chama saber se a operação foi um no-op.
        """
        existentes = self.por_titulo()
        if titulo in existentes:
            self._log(f"já existe: {titulo} ({existentes[titulo]})")
            return {"id": existentes[titulo], "titulo": titulo, "criada": False}

        snippet = {"title": titulo, "description": descricao}
        if default_language:
            snippet["defaultLanguage"] = default_language

        r = self.yt.playlists().insert(
            part="snippet,status",
            body={"snippet": snippet,
                  "status": {"privacyStatus": privacy_status}}).execute()
        self._log(f"criada: {titulo} ({r['id']})")
        return {"id": r["id"], "titulo": titulo, "criada": True}

    def adicionar(self, playlist_id: str, video_id: str) -> dict:
        """Insere o vídeo na playlist, se ainda não estiver lá."""
        if video_id in self.itens(playlist_id):
            self._log(f"{video_id} já está na playlist {playlist_id}")
            return {"playlist_id": playlist_id, "video_id": video_id,
                    "adicionado": False}

        self.yt.playlistItems().insert(
            part="snippet",
            body={"snippet": {"playlistId": playlist_id,
                              "resourceId": {"kind": "youtube#video",
                                             "videoId": video_id}}}).execute()
        self._log(f"{video_id} adicionado à playlist {playlist_id}")
        return {"playlist_id": playlist_id, "video_id": video_id,
                "adicionado": True}
