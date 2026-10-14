"""Endpoints de YouTube por canal: upload, playlists, token e coleta de dados.

Centraliza o que antes vivia espalhado em scripts dos repos dos canais
(`subir_video.py`, `playlists_series.py`, `coletar_dados_canal.py`).

As operações longas — upload de MP4 e sync do canal — entram na fila de
`app_jobs` e devolvem `job_id`; acompanhe em `GET /jobs/{id}`. O sync aceita
`?wait=true` para rodar na própria request quando for mais prático (canal
pequeno, chamada por curl), com o risco de timeout do cliente.
"""
import json

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from pydantic import BaseModel
from sqlmodel import Session
from typing import Optional

from database import get_session
from middleware.auth import get_current_user, require_service_token
from auth.models import User
from jobs.models import Job
from jobs import worker
from youtube import service
from youtube.service import CanalNaoEncontrado

router = APIRouter()


# ---------------------------------------------------------------------------
# SCHEMAS
# ---------------------------------------------------------------------------
class UploadRequest(BaseModel):
    """Overrides do `channels_config.youtube`. Tudo opcional: o que vier nulo
    mantém o valor do canal."""
    model_config = {"json_schema_extra": {"example": {
        "video_path": "/caminho/para/video.mp4",
        "title": "Título do vídeo (máx. 100 chars)",
        "privacy_status": "private"}}}

    video_path: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[list[str]] = None
    category_id: Optional[str] = None
    privacy_status: Optional[str] = None
    publish_at: Optional[str] = None
    timezone: Optional[str] = None
    thumbnail: Optional[dict] = None
    default_language: Optional[str] = None
    default_audio_language: Optional[str] = None
    contains_synthetic_media: Optional[bool] = None


class ThumbnailRequest(BaseModel):
    video_id: str
    path: Optional[str] = None


class PlaylistRequest(BaseModel):
    titulo: str
    descricao: str = ""
    privacy_status: str = "public"
    default_language: Optional[str] = None


class PlaylistItemRequest(BaseModel):
    video_id: str


class SyncRequest(BaseModel):
    model_config = {"json_schema_extra": {"example": {
        "path": None, "inicio": "2026-08-01", "fim": None,
        "com_analytics_por_video": True}}}

    # Fallback: videomaker/output/analytics/{slug}.json
    path: Optional[str] = None
    inicio: str = "2020-01-01"
    fim: Optional[str] = None
    # False corta 6 queries por vídeo — bem mais rápido, só metadados.
    com_analytics_por_video: bool = True


def _nao_encontrado(e: CanalNaoEncontrado):
    return HTTPException(status_code=404, detail=str(e))


def _enfileirar(session: Session, user: User, background: BackgroundTasks,
                tipo: str, config: dict) -> dict:
    job = Job(id_user=user.id, type=tipo, config=json.dumps(config))
    session.add(job)
    session.commit()
    session.refresh(job)
    background.add_task(worker.run_job, job.id)
    return {"job_id": job.id, "status": job.status, "type": tipo}


# ---------------------------------------------------------------------------
# API interna — consumida por cron/scripts, autenticada por X-Service-Token
# em vez de JWT de usuário (que expira em 15 min e não serve para cron).
# Declarada ANTES das rotas /{slug}/... para não colidir no path matching.
# ---------------------------------------------------------------------------
@router.post("/internal/{slug}/sync", summary="Coletar dados do canal (cron)",
             dependencies=[Depends(require_service_token)],
             responses={404: {"description": "Canal sem channels_config ou sem token"}})
def internal_sync(slug: str, body: SyncRequest = SyncRequest()):
    """Igual ao `/sync?wait=true`, mas para chamadas de processo.

    Síncrono de propósito: o cron precisa do código de saída e do resumo no
    log, e não teria como acompanhar um `job_id` depois.

    O `path` manda — é assim que a coleta continua caindo na pasta do canal
    (ex. `PoG/data/canal.json`) em vez do default do pipeline.
    """
    try:
        return service.sync(slug, path=body.path, inicio=body.inicio,
                            fim=body.fim,
                            com_analytics_por_video=body.com_analytics_por_video)
    except CanalNaoEncontrado as e:
        raise _nao_encontrado(e)


# ---------------------------------------------------------------------------
# TOKEN
# ---------------------------------------------------------------------------
@router.get("/{slug}/token", summary="Diagnosticar token OAuth",
            responses={404: {"description": "Canal sem channels_config"}})
def token(slug: str, _: User = Depends(get_current_user)):
    """Diagnóstico do token OAuth: existe, vale, quais escopos.

    Não existe rota para GERAR token: o fluxo OAuth abre um navegador e espera
    um clique, o que não cabe numa request HTTP. Gere com
    `YouTube.generate_token()` numa máquina com navegador.
    """
    try:
        return service.status_token(slug)
    except CanalNaoEncontrado as e:
        raise _nao_encontrado(e)


# ---------------------------------------------------------------------------
# UPLOAD
# ---------------------------------------------------------------------------
@router.post("/{slug}/validate", summary="Validar metadados (dry-run)",
             responses={404: {"description": "Canal sem channels_config"}})
def validate(slug: str, body: UploadRequest = UploadRequest(),
             check_video: bool = Query(True, description="exigir que o MP4 exista"),
             _: User = Depends(get_current_user)):
    """Checa os metadados sem subir nada — o dry-run do `subir_video.py`.

    Vale rodar antes de um render: título longo, tag estourada ou token ausente
    só apareceriam como erro no fim do upload, horas depois.
    """
    try:
        return service.validar(slug, body.model_dump(), check_video=check_video)
    except CanalNaoEncontrado as e:
        raise _nao_encontrado(e)


@router.post("/{slug}/upload", summary="Subir MP4 já renderizado (job)",
             responses={404: {"description": "Canal sem channels_config"},
                        422: {"description": "Metadados inválidos — nada foi enviado"}})
def upload(slug: str, body: UploadRequest, background_tasks: BackgroundTasks,
           session: Session = Depends(get_session),
           current_user: User = Depends(get_current_user)):
    """Sobe um MP4 já renderizado. Devolve `job_id`.

    Valida antes de começar: metadado inválido falha o job na hora, sem gastar
    banda. O upload é resumável em blocos de 10MB, então uma queda de conexão
    retoma de onde parou em vez de reiniciar.
    """
    try:
        resumo = service.validar(slug, body.model_dump())
    except CanalNaoEncontrado as e:
        raise _nao_encontrado(e)

    if not resumo["ok"]:
        raise HTTPException(status_code=422,
                            detail={"erro": "Metadados inválidos",
                                    "problemas": resumo["problemas"]})

    return _enfileirar(session, current_user, background_tasks, "youtube_upload",
                       {"slug": slug, "overrides": body.model_dump()})


@router.post("/{slug}/thumbnail", summary="Reenviar thumbnail de um vídeo",
             responses={404: {"description": "Canal sem channels_config"},
                        422: {"description": "Thumbnail inexistente ou não configurada"}})
def thumbnail(slug: str, body: ThumbnailRequest,
              _: User = Depends(get_current_user)):
    """Reenvia a thumbnail de um vídeo que já está no canal.

    Síncrono: é um PNG de até 2MB, não um MP4.
    """
    try:
        return service.enviar_thumbnail(slug, body.video_id, body.path)
    except CanalNaoEncontrado as e:
        raise _nao_encontrado(e)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


# ---------------------------------------------------------------------------
# PLAYLISTS
# ---------------------------------------------------------------------------
@router.get("/{slug}/playlists", summary="Listar playlists do canal",
            responses={404: {"description": "Canal sem channels_config"}})
def listar_playlists(slug: str, _: User = Depends(get_current_user)):
    try:
        return service.listar_playlists(slug)
    except CanalNaoEncontrado as e:
        raise _nao_encontrado(e)


@router.post("/{slug}/playlists", summary="Criar playlist (idempotente)",
             responses={404: {"description": "Canal sem channels_config"}})
def criar_playlist(slug: str, body: PlaylistRequest,
                   _: User = Depends(get_current_user)):
    """Garante a playlist. Idempotente: título existente é reaproveitado.

    `criada: false` na resposta significa que já existia e nada foi escrito.
    """
    try:
        return service.garantir_playlist(slug, body.titulo, body.descricao,
                                         body.privacy_status, body.default_language)
    except CanalNaoEncontrado as e:
        raise _nao_encontrado(e)


@router.post("/{slug}/playlists/{playlist_id}/items",
             summary="Inserir vídeo na playlist (idempotente)",
             responses={404: {"description": "Canal sem channels_config"}})
def adicionar_na_playlist(slug: str, playlist_id: str, body: PlaylistItemRequest,
                          _: User = Depends(get_current_user)):
    """Insere o vídeo na playlist. Idempotente (`adicionado: false` = já estava)."""
    try:
        return service.adicionar_na_playlist(slug, playlist_id, body.video_id)
    except CanalNaoEncontrado as e:
        raise _nao_encontrado(e)


# ---------------------------------------------------------------------------
# SYNC / ANALYTICS
# ---------------------------------------------------------------------------
@router.post("/{slug}/sync", summary="Coletar TUDO do canal num JSON",
             responses={404: {"description": "Canal sem channels_config ou sem token"}})
def sync(slug: str, background_tasks: BackgroundTasks,
         body: SyncRequest = SyncRequest(),
         wait: bool = Query(False, description="roda na request em vez de job"),
         session: Session = Depends(get_session),
         current_user: User = Depends(get_current_user)):
    """Coleta TUDO sobre o canal e grava num JSON.

    Canal + todos os vídeos (inclusive privados e agendados) + playlists +
    analytics de canal e de cada vídeo (tráfego, geografia, dispositivos,
    retenção, receita).

    Default: job, porque são ~6 requisições de Analytics por vídeo e um canal
    com dezenas de vídeos leva minutos — mais que o timeout de um cliente HTTP.
    `?wait=true` roda na própria request e devolve o resumo direto.
    """
    config = {"slug": slug, **body.model_dump()}

    if wait:
        try:
            return service.sync(slug, path=body.path, inicio=body.inicio,
                                fim=body.fim,
                                com_analytics_por_video=body.com_analytics_por_video)
        except CanalNaoEncontrado as e:
            raise _nao_encontrado(e)

    return _enfileirar(session, current_user, background_tasks, "youtube_sync", config)


@router.get("/{slug}/analytics", summary="Ler o último snapshot coletado",
            responses={404: {"description": "Nenhum snapshot gravado ainda"}})
def analytics(slug: str, path: Optional[str] = Query(None),
              resumo: bool = Query(False, description="só os totais, sem os vídeos"),
              _: User = Depends(get_current_user)):
    """Devolve o último snapshot gravado pelo sync.

    `?resumo=true` corta a lista de vídeos — o JSON completo de um canal com
    dezenas de vídeos tem alguns MB.
    """
    try:
        dados = service.ler_analytics(slug, path)
    except CanalNaoEncontrado as e:
        raise _nao_encontrado(e)

    if resumo:
        return {k: v for k, v in dados.items() if k != "videos"}
    return dados
