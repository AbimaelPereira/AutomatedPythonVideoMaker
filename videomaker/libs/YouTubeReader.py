"""Leitura de tudo o que as APIs do YouTube dão sobre um canal.

Data API v3 (canal, vídeos, playlists) + Analytics API v2 (métricas de canal e
por vídeo, tráfego, geografia, dispositivos, retenção, receita).

Contraparte de leitura do `YouTube.py`, que só escreve. O token é o mesmo; os
escopos de Analytics vêm do `YouTube.SCOPES`.

    from libs.YouTube import YouTube
    from libs.YouTubeReader import YouTubeReader

    yt = YouTube(params={"token_file_name": "/caminho/token.json"})
    leitor = YouTubeReader(yt._get_credentials(), canal_id="UC...")
    dados = leitor.coletar_tudo()

Um canal com N vídeos custa ~6N requisições de Analytics, então `coletar_tudo()`
leva minutos. Quem chama por HTTP deve rodar em job.
"""
import time
from datetime import datetime, timedelta, timezone

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


def _ymd(d) -> str:
    return d.strftime("%Y-%m-%d")


def _hoje() -> str:
    return _ymd(datetime.now(timezone.utc).date())


class YouTubeReader:
    """Coletor de dados de um canal. Uma instância por canal."""

    # Métricas de engajamento que o Analytics aceita juntas numa query.
    METRICAS = ("views,estimatedMinutesWatched,averageViewDuration,"
                "averageViewPercentage,likes,dislikes,comments,shares,"
                "subscribersGained,subscribersLost,annotationClickThroughRate,"
                "annotationCloseRate,videosAddedToPlaylists,"
                "videosRemovedFromPlaylists")

    # Exigem o escopo `yt-analytics-monetary.readonly` e canal monetizado.
    # Num canal sem monetização a query é recusada e cai em `erros`.
    MONETARIAS = ("estimatedRevenue,estimatedAdRevenue,grossRevenue,cpm,"
                  "playbackBasedCpm,adImpressions,monetizedPlaybacks")

    def __init__(self, credentials, canal_id: str, inicio: str = "2020-01-01",
                 fim: str | None = None, verbose: bool = True):
        self.canal_id = canal_id
        self.inicio = inicio
        self.fim = fim or _hoje()
        self.verbose = verbose
        # cache_discovery=False: o cache em disco do googleapiclient quebra em
        # processo sem permissão de escrita (é o caso do worker da API).
        self.yt = build("youtube", "v3", credentials=credentials, cache_discovery=False)
        self.an = build("youtubeAnalytics", "v2", credentials=credentials,
                        cache_discovery=False)
        self.erros = []

    def _log(self, msg):
        if self.verbose:
            print(f"[YouTubeReader] {msg}", flush=True)

    # ------------------------------------------------------------------
    # INFRA
    # ------------------------------------------------------------------
    @staticmethod
    def _paginar(req_fn, **kwargs) -> list:
        """Percorre todas as páginas de um endpoint de listagem da Data API."""
        itens, token = [], None
        while True:
            r = req_fn(pageToken=token, **kwargs).execute()
            itens += r.get("items", [])
            token = r.get("nextPageToken")
            if not token:
                return itens

    def _query(self, **kwargs):
        """Query de Analytics. Devolve lista de dicts, ou None se a API recusar.

        Uma dimensão recusada não pode derrubar a coleta inteira — o Analytics
        nega consultas por motivos que variam por canal (sem monetização,
        `subscribedStatus` devolvendo 500, dados insuficientes). O erro vai para
        `self.erros` e a chave fica None no resultado.
        """
        kwargs.setdefault("ids", f"channel=={self.canal_id}")
        kwargs.setdefault("startDate", self.inicio)
        kwargs.setdefault("endDate", self.fim)
        rotulo = kwargs.get("dimensions") or "totais"

        # 500/503 são intermitentes em algumas dimensões; 3 tentativas.
        r = None
        for tentativa in range(3):
            try:
                r = self.an.reports().query(**kwargs).execute()
                break
            except HttpError as e:
                if e.resp.status in (500, 503) and tentativa < 2:
                    time.sleep(2 * (tentativa + 1))
                    continue
                self.erros.append({"consulta": rotulo,
                                   "filtros": kwargs.get("filters"),
                                   "erro": str(e)[:300]})
                return None
            except Exception as e:  # rede, credencial expirada no meio, etc.
                self.erros.append({"consulta": rotulo,
                                   "filtros": kwargs.get("filters"),
                                   "erro": f"{type(e).__name__}: {e}"[:300]})
                return None

        if r is None:
            return None
        cols = [c["name"] for c in r.get("columnHeaders", [])]
        return [dict(zip(cols, linha)) for linha in r.get("rows") or []]

    # ------------------------------------------------------------------
    # DATA API
    # ------------------------------------------------------------------
    def canal(self) -> dict | None:
        r = self.yt.channels().list(
            part="snippet,statistics,contentDetails,status,topicDetails,"
                 "brandingSettings,localizations",
            id=self.canal_id).execute()
        return (r.get("items") or [None])[0]

    def canal_do_token(self) -> dict | None:
        """O canal dono do token (`mine=true`), para descobrir o ID."""
        r = self.yt.channels().list(part="snippet,contentDetails,statistics",
                                    mine=True).execute()
        return (r.get("items") or [None])[0]

    def videos(self, uploads_playlist: str) -> list:
        """Todos os vídeos do canal, incluindo privados e agendados.

        A playlist de uploads não lista o que está privado, então o
        `search(forMine=True)` entra para completar — ele enxerga o que o token
        tem permissão de ver. Os dois conjuntos se sobrepõem; a ordem de
        inserção é preservada na deduplicação.
        """
        itens = self._paginar(self.yt.playlistItems().list, part="contentDetails",
                              playlistId=uploads_playlist, maxResults=50)
        ids = [i["contentDetails"]["videoId"] for i in itens]

        try:
            buscados = self._paginar(self.yt.search().list, part="id", forMine=True,
                                     type="video", maxResults=50)
            ids += [i["id"]["videoId"] for i in buscados]
        except Exception as e:
            # `forMine` exige escopo amplo; sem ele perdemos só os privados.
            self.erros.append({"consulta": "search.forMine",
                               "erro": f"{type(e).__name__}: {e}"[:300]})

        ids = list(dict.fromkeys(ids))
        self._log(f"{len(ids)} vídeos encontrados")

        videos = []
        for i in range(0, len(ids), 50):     # `videos().list` aceita 50 por vez
            lote = self.yt.videos().list(
                part="snippet,statistics,contentDetails,status,topicDetails,"
                     "liveStreamingDetails,player,recordingDetails",
                id=",".join(ids[i:i + 50])).execute()
            videos += lote.get("items", [])
        return videos

    def playlists(self) -> list:
        return self._paginar(self.yt.playlists().list,
                             part="snippet,status,contentDetails",
                             channelId=self.canal_id, maxResults=50)

    # ------------------------------------------------------------------
    # ANALYTICS
    # ------------------------------------------------------------------
    def analytics_canal(self) -> dict:
        d = {
            "totais": self._query(metrics=self.METRICAS),
            "monetizacao": self._query(metrics=self.MONETARIAS),
            "por_dia": self._query(
                metrics="views,estimatedMinutesWatched,averageViewDuration,"
                        "subscribersGained,subscribersLost,likes,comments,shares",
                dimensions="day", sort="day"),
            "fontes_de_trafego": self._query(
                metrics="views,estimatedMinutesWatched",
                dimensions="insightTrafficSourceType", sort="-views"),
            "detalhe_trafego_externo": self._query(
                metrics="views", dimensions="insightTrafficSourceDetail",
                filters="insightTrafficSourceType==EXT_URL",
                sort="-views", maxResults=25),
            "geografia": self._query(
                metrics="views,estimatedMinutesWatched,averageViewDuration",
                dimensions="country", sort="-views"),
            "dispositivos": self._query(metrics="views,estimatedMinutesWatched",
                                        dimensions="deviceType", sort="-views"),
            "sistemas_operacionais": self._query(metrics="views",
                                                 dimensions="operatingSystem",
                                                 sort="-views"),
            "local_de_reproducao": self._query(
                metrics="views,estimatedMinutesWatched",
                dimensions="insightPlaybackLocationType", sort="-views"),
            "idade_e_genero": self._query(metrics="viewerPercentage",
                                          dimensions="ageGroup,gender",
                                          sort="-viewerPercentage"),
            "compartilhamento": self._query(metrics="shares",
                                            dimensions="sharingService",
                                            sort="-shares"),
            "tipo_de_video": self._query(metrics="views,estimatedMinutesWatched",
                                         dimensions="creatorContentType",
                                         sort="-views"),
        }
        ini = _ymd(datetime.now(timezone.utc).date() - timedelta(days=28))
        d["ultimos_28_dias"] = self._query(metrics=self.METRICAS, startDate=ini)
        return d

    def analytics_video(self, video_id: str) -> dict:
        f = f"video=={video_id}"
        return {
            "totais": self._query(metrics=self.METRICAS, filters=f),
            "por_dia": self._query(
                metrics="views,estimatedMinutesWatched,averageViewDuration,"
                        "subscribersGained,likes",
                dimensions="day", filters=f, sort="day"),
            "fontes_de_trafego": self._query(
                metrics="views,estimatedMinutesWatched",
                dimensions="insightTrafficSourceType", filters=f, sort="-views"),
            "geografia": self._query(metrics="views,estimatedMinutesWatched",
                                     dimensions="country", filters=f,
                                     sort="-views", maxResults=25),
            "dispositivos": self._query(metrics="views", dimensions="deviceType",
                                        filters=f, sort="-views"),
            "retencao": self._query(
                metrics="audienceWatchRatio,relativeRetentionPerformance",
                dimensions="elapsedVideoTimeRatio", filters=f),
        }

    # ------------------------------------------------------------------
    # COLETA COMPLETA
    # ------------------------------------------------------------------
    def coletar_tudo(self, com_analytics_por_video: bool = True) -> dict:
        """Snapshot completo: canal + playlists + todos os vídeos + analytics.

        `com_analytics_por_video=False` corta a parte mais lenta (6 queries por
        vídeo) quando só os metadados interessam.
        """
        canal = self.canal()
        if not canal:
            raise RuntimeError(f"Canal {self.canal_id} não encontrado — "
                               "token sem acesso ou ID errado?")

        uploads = canal["contentDetails"]["relatedPlaylists"]["uploads"]
        videos = self.videos(uploads)

        if com_analytics_por_video:
            for i, v in enumerate(videos, 1):
                self._log(f"analytics do vídeo {i}/{len(videos)}: {v['id']}")
                v["analytics"] = self.analytics_video(v["id"])

        self._log("analytics do canal")
        analytics_canal = self.analytics_canal()

        agora = datetime.now(timezone.utc)
        return {
            "ultima_busca": agora.astimezone().isoformat(timespec="seconds"),
            "ultima_busca_utc": agora.isoformat(timespec="seconds"),
            "periodo": {"inicio": self.inicio, "fim": self.fim},
            "canal_id": self.canal_id,
            "canal": canal,
            "analytics_canal": analytics_canal,
            "playlists": self.playlists(),
            "total_videos": len(videos),
            "videos": videos,
            "erros": self.erros,
        }
