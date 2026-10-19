"""FilterGraphBuilder — compila uma cena do JSON em um filtergraph ffmpeg.

Fase 1 do plano de performance. Em vez de o MoviePy compor cada frame em Python,
Python passa a fazer o que faz bem — traduzir o JSON declarativo — e o ffmpeg
executa a composição em C, em streaming, sem frames atravessando o interpretador.

Medido em 1080p, cena de 5 s (fundo cor sólida + zoom + karaokê):
    MoviePy       47,6 s
    filtergraph    2,0 s     (~23x)

Cobertura (o que NÃO é coberto cai no caminho MoviePy — ver `can_handle`):

  suportado                              | mapeamento
  ---------------------------------------|----------------------------------
  background type color                  | lavfi `color`
  background type file/remote (imagem)   | input + `scale`/`crop`
  background fit_mode contain (imagem/ai)| `scale` + `pad` com `fill_color`
  background type video                  | input com `-ss`/`-t` + cover
  background type directory              | N inputs normalizados + `concat`
  background animation zoom              | `zoompan` centrado, expr em `on`
  visual_elements image/remote (estático)| input + `scale` + `overlay`
  visual_elements video/directory        | input + `scale`/`crop` + `overlay`
  visual_elements zoom_in / fade_in      | `zoompan` centrado / `fade`
  border_radius                          | máscara PNG + `alphamerge`
  opacity                                | `colorchannelmixer=aa=`
  legendas classic/karaoke               | `ass` (via AssBuilder)

  NÃO suportado (fallback):
    `fit_mode` contain-blur (e contain em fundo de vídeo/pasta), filtros
    (light_leak, particles, …), transição zoom, text_box, background ai de vídeo.
"""

import os


class Unsupported(Exception):
    """A cena tem algo sem equivalente fiel em filtergraph."""


def _esc_path(path: str) -> str:
    """Escapa um caminho para uso DENTRO de um filtro (ass=, movie=…)."""
    return path.replace("\\", "/").replace(":", r"\:").replace("'", r"\'")


class FilterGraphBuilder:
    def __init__(self, resolution: tuple, fps: int = 30):
        self.width, self.height = int(resolution[0]), int(resolution[1])
        self.fps = int(fps)
        self.inputs: list = []      # args de -i (cada item: lista de tokens)
        self._chains: list = []     # trechos do filter_complex
        self._n = 0

    # -- helpers -----------------------------------------------------------

    # Fator de ampliação da entrada do `zoompan`, para o zoom amostrar
    # pixels reais em vez de esticar o frame já no tamanho final.
    _ZOOM_SS = 2

    @property
    def _ZOOM_T(self) -> str:
        """Tempo, em segundos, dentro de uma expressão do `zoompan`.

        Ele não expõe `t` como o `scale` faz: conta frames de saída em `on`,
        daí a divisão pelo fps.
        """
        return f"(on/{self.fps})"

    def _label(self, prefix: str = "v") -> str:
        self._n += 1
        return f"{prefix}{self._n}"

    def add_input(self, args: list) -> int:
        """Registra um input e devolve seu índice."""
        self.inputs.append(list(args))
        return len(self.inputs) - 1

    def add_chain(self, chain: str):
        self._chains.append(chain)

    # -- fundo -------------------------------------------------------------

    def background_color(self, color: str, duration: float) -> str:
        """Fundo de cor sólida via lavfi."""
        color = color if str(color).startswith("#") else f"#{color}"
        idx = self.add_input([
            "-f", "lavfi",
            "-t", f"{duration:.3f}",
            "-i", f"color=c={color.replace('#', '0x')}:s={self.width}x{self.height}:r={self.fps}",
        ])
        return f"{idx}:v"

    def background_image(self, path: str, duration: float) -> str:
        """Imagem estática como fundo (loop pela duração da cena)."""
        idx = self.add_input([
            "-loop", "1", "-t", f"{duration:.3f}", "-r", str(self.fps), "-i", path,
        ])
        return f"{idx}:v"

    def background_video(self, path: str, start: float, duration: float,
                         loop: bool = False) -> str:
        """Trecho de um arquivo de vídeo como fundo.

        `-ss` antes de `-i` é seek rápido (por keyframe, sem decodificar o que
        vem antes) — a diferença é grande em arquivos longos. `-t` limita o
        trecho lido.

        `loop=True` (arquivo mais curto que o segmento) usa `-stream_loop -1`,
        que repete o input indefinidamente; o `-t` corta na duração pedida.
        Nesse caso o `-ss` é ignorado de propósito: começar fora do zero num
        stream em loop deixaria um salto visível na emenda.
        """
        args = []
        if loop:
            args += ["-stream_loop", "-1"]
        elif start and start > 0:
            args += ["-ss", f"{float(start):.3f}"]
        args += ["-t", f"{float(duration):.3f}", "-i", path]
        idx = self.add_input(args)
        return f"{idx}:v"

    def normalize_segment(self, src: str, duration: float,
                          size: tuple = None) -> str:
        """Deixa um segmento pronto para `concat`: cover + SAR/fps/formato fixos.

        O filtro `concat` exige que TODOS os segmentos tenham a mesma resolução,
        SAR, pixel format e taxa de quadros — se divergirem, ele falha ou emenda
        com timing corrompido. Como os arquivos da pasta têm resoluções e fps
        variados, cada um passa por aqui antes de entrar na concatenação.

        `size` é o alvo do cover: a tela inteira (fundo) ou a caixa do elemento
        (visual_element). `fps` vem antes do trim para a contagem de frames do
        segmento ser previsível; `trim`+`setpts` reancoram o tempo em zero, que
        é o que o `concat` espera de cada entrada.
        """
        w = int(size[0]) if size else self.width
        h = int(size[1]) if size else self.height
        out = self._label("seg")
        self.add_chain(
            f"[{src}]"
            f"scale={w}:{h}:force_original_aspect_ratio=increase,"
            f"crop={w}:{h},"
            f"setsar=1,fps={self.fps},format=rgba,"
            f"trim=duration={float(duration):.3f},setpts=PTS-STARTPTS"
            f"[{out}]"
        )
        return out

    def concat(self, labels: list) -> str:
        """Concatena segmentos já normalizados numa única stream de vídeo."""
        if not labels:
            raise Unsupported("concat sem segmentos")
        if len(labels) == 1:
            return labels[0]
        out = self._label("cat")
        joined = "".join(f"[{lbl}]" for lbl in labels)
        self.add_chain(f"{joined}concat=n={len(labels)}:v=1:a=0[{out}]")
        return out

    def contain(self, src: str, img_w: int, img_h: int, fill_color="#000000") -> str:
        """Encaixa a imagem inteira no quadro; a sobra vira `fill_color` (fit_mode contain).

        Espelha `BackgroundEngine._fit_image`: escala = min(W/w, H/h), tamanho
        truncado com int() e imagem centrada. As contas são feitas aqui em Python
        (e não com `force_original_aspect_ratio=decrease`) porque o arredondamento
        do ffmpeg difere do int() em 1px — e os dois caminhos precisam bater.
        """
        scale = min(self.width / img_w, self.height / img_h)
        nw, nh = max(1, int(img_w * scale)), max(1, int(img_h * scale))
        x, y = (self.width - nw) // 2, (self.height - nh) // 2
        if isinstance(fill_color, (list, tuple)):
            r, g, b = (int(c) for c in list(fill_color)[:3])
            color = f"0x{r:02x}{g:02x}{b:02x}"
        else:
            color = "0x" + str(fill_color).lstrip("#")
        out = self._label("bg")
        self.add_chain(
            f"[{src}]scale={nw}:{nh},setsar=1,"
            f"pad={self.width}:{self.height}:{x}:{y}:color={color},"
            f"format=rgba[{out}]"
        )
        return out

    def cover(self, src: str, duration: float) -> str:
        """Redimensiona cobrindo o quadro e corta o excesso (fit_mode cover)."""
        out = self._label("bg")
        self.add_chain(
            f"[{src}]scale={self.width}:{self.height}:force_original_aspect_ratio=increase,"
            f"crop={self.width}:{self.height},setsar=1,format=rgba[{out}]"
        )
        return out

    def zoom(self, src: str, start_scale: float, end_scale: float,
             duration: float, out_w: int = None, out_h: int = None) -> str:
        """Zoom linear centrado, via `zoompan`.

        Serve zoom_in e zoom_out — a direção é só a ordem de start/end.
        """
        d = max(0.001, float(duration))
        s0, s1 = float(start_scale), float(end_scale)
        tt = self._ZOOM_T
        return self._zoom_expr(src, f"({s0}+({s1}-{s0})*min({tt}/{d}\\,1))",
                               out_w, out_h)

    def zoom_pulse(self, src: str, intensity: float, duration: float,
                   out_w: int = None, out_h: int = None) -> str:
        """Zoom pulsante: escala = 1 + intensity*sin(pi*t/total).

        Espelha `_zoom_resize` do VisualClip para `zoom_pulse`. `PI` é constante
        reconhecida pelo avaliador de expressões do ffmpeg.
        """
        d = max(0.001, float(duration))
        tt = self._ZOOM_T
        return self._zoom_expr(src, f"(1.0+{float(intensity)}*sin(({tt}/{d})*PI))",
                               out_w, out_h)

    def _zoom_expr(self, src: str, scale_expr: str,
                   out_w: int = None, out_h: int = None) -> str:
        """Aplica uma expressão de escala mantendo o centro fixo.

        Usa `zoompan` em vez de `scale`+`crop`: o `crop` recorta a partir de um
        canto e o conteúdo escapa para fora do quadro conforme a imagem cresce —
        o zoom parece "puxar" para o canto superior esquerdo. O `zoompan` recebe
        o ponto de ancoragem explicitamente em `x`/`y`, e centralizá-lo mantém o
        mesmo pixel no meio do quadro do início ao fim.

        A entrada é ampliada por `SS` antes do zoompan porque ele amostra do
        frame de entrada: sem essa margem, ampliar significaria esticar pixels
        do tamanho final e o resultado sairia borrado.
        """
        w = int(out_w or self.width)
        h = int(out_h or self.height)
        out = self._label("z")
        # A escala pode ficar < 1 (zoom_out terminando em 1.0 vindo de cima, ou
        # o pulse com intensity negativa). `max(...)` prende o piso em 1.0: a
        # janela nunca mostra menos que o enquadramento original.
        z = f"max({scale_expr}\\,1.0)"
        sw, sh = w * self._ZOOM_SS, h * self._ZOOM_SS
        self.add_chain(
            f"[{src}]scale={sw}:{sh}:flags=bicubic,"
            f"zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"d=1:s={w}x{h}:fps={self.fps},setsar=1[{out}]"
        )
        return out

    # -- overlay -----------------------------------------------------------

    def overlay(self, base: str, top: str, x, y,
                enable=None, eval_frame: bool = False) -> str:
        """Compõe `top` sobre `base`.

        `x`/`y` aceitam número (posição fixa) ou EXPRESSÃO já escapada, vinda do
        `libs.Motion.compile_ffmpeg` — nesse caso `eval_frame=True` é obrigatório,
        senão o ffmpeg avalia a expressão uma única vez e o elemento fica parado
        no valor do primeiro frame.

        `enable` aceita a tupla `(t0, t1)` legada ou uma expressão pronta.
        """
        out = self._label("o")
        xs = x if isinstance(x, str) else str(int(x))
        ys = y if isinstance(y, str) else str(int(y))

        enable_expr = ""
        if isinstance(enable, str):
            enable_expr = f":enable='{enable}'"
        elif enable:
            t0, t1 = enable
            enable_expr = f":enable='between(t\\,{t0:.3f}\\,{t1:.3f})'"

        ev = ":eval=frame" if eval_frame else ""
        self.add_chain(f"[{base}][{top}]overlay=x='{xs}':y='{ys}'{ev}"
                       f"{enable_expr}[{out}]")
        return out

    # -- motion (libs/Motion) ---------------------------------------------

    def scale_anim(self, src: str, w_expr: str, h_expr: str) -> str:
        """Escala animada quadro a quadro (propriedade `scale` do motion).

        `flags=bilinear` (e não bicubic) porque isto roda em TODO frame; o
        `setsar=1` evita que o overlay herde um SAR estranho do redimensionamento.
        As expressões já chegam com `trunc(x/2)*2` de `compile_ffmpeg.scale_exprs`:
        dimensão ímpar quebra o `yuv420p`.
        """
        out = self._label("sa")
        self.add_chain(
            f"[{src}]scale=w='{w_expr}':h='{h_expr}'"
            f":eval=frame:flags=bilinear,setsar=1[{out}]"
        )
        return out

    def zoom_track(self, src: str, scale_expr: str,
                   out_w: int = None, out_h: int = None) -> str:
        """`zoom` do motion: mesma janela fixa do zoom legado, curva arbitrária."""
        return self._zoom_expr(src, f"({scale_expr})", out_w, out_h)

    def rotate_anim(self, src: str, angle_expr: str, box: tuple) -> str:
        """Rotação animada (propriedade `rotation` do motion).

        O quadro é PRÉ-PREENCHIDO com borda transparente até caber a diagonal
        (um retângulo girado 45° ocupa `hypot(w,h)`) e só então rotacionado,
        com `ow=iw:oh=ih`.

        Por que não `ow='hypot(iw,ih)'`, que seria o caminho óbvio: com a área
        de saída maior que a de entrada e `c=none`, o `rotate` do ffmpeg 4.x
        não limpa a margem — ela mantém o conteúdo do quadro ANTERIOR, e o
        elemento girando deixa um rastro de cópias de si mesmo em leque. Com a
        margem já presente na ENTRADA, cada quadro é desenhado inteiro e o
        rastro some.

        A expressão chega em RADIANOS (o `rotate` não trabalha em graus).
        """
        import math

        w, h = int(box[2]), int(box[3])
        side = int(math.ceil(math.hypot(w, h)))
        side += side % 2                      # ímpar quebra o yuv420p adiante
        x, y = (side - w) // 2, (side - h) // 2
        out = self._label("rot")
        self.add_chain(
            f"[{src}]format=rgba,"
            f"pad={side}:{side}:{x}:{y}:color=0x00000000,"
            f"rotate=a='{angle_expr}':c=none:ow=iw:oh=ih[{out}]"
        )
        return out

    def blur(self, src: str, sigma: float) -> str:
        """Desfoque gaussiano de sigma fixo (propriedade `blur` do motion).

        O `gblur` só aceita `sigma` como número — não há `eval=frame`. Blur que
        muda ao longo do tempo é recusado pelo gate e vai para o MoviePy.
        """
        out = self._label("gb")
        self.add_chain(f"[{src}]gblur=sigma={float(sigma):.3f}[{out}]")
        return out

    def fade_out(self, src: str, duration: float, start: float = 0.0) -> str:
        out = self._label("f")
        self.add_chain(
            f"[{src}]format=rgba,fade=t=out:st={start:.3f}:d={duration:.3f}:alpha=1[{out}]"
        )
        return out

    def alpha_expr(self, src: str, expr: str) -> str:
        """Opacidade por expressão arbitrária, via `geq` no canal alpha.

        Caminho GERAL (e caro): avalia a expressão por pixel. Só é usado quando
        a cadeia de `fade` não dá conta — ver `compile_ffmpeg.opacity_plan`. O
        alpha existente é multiplicado, não substituído, para não apagar a
        transparência própria do PNG.
        """
        out = self._label("ga")
        self.add_chain(
            f"[{src}]format=rgba,geq=r='r(X\\,Y)':g='g(X\\,Y)':b='b(X\\,Y)'"
            f":a='({expr})*alpha(X\\,Y)'[{out}]"
        )
        return out

    def scale_to(self, src: str, w: int, h: int) -> str:
        out = self._label("s")
        self.add_chain(f"[{src}]scale={int(w)}:{int(h)},setsar=1[{out}]")
        return out

    def set_sar(self, src: str) -> str:
        out = self._label("sar")
        self.add_chain(f"[{src}]setsar=1,format=rgba[{out}]")
        return out

    def crop_to(self, src: str, x: int, y: int, w: int, h: int) -> str:
        """Recorte com origem explícita (modo cover + focus point)."""
        out = self._label("c")
        self.add_chain(f"[{src}]crop={int(w)}:{int(h)}:{int(x)}:{int(y)}[{out}]")
        return out

    def opacity(self, src: str, value: float) -> str:
        out = self._label("a")
        self.add_chain(f"[{src}]format=rgba,colorchannelmixer=aa={float(value):.3f}[{out}]")
        return out

    def fade_in(self, src: str, duration: float, start: float = 0.0) -> str:
        out = self._label("f")
        self.add_chain(
            f"[{src}]format=rgba,fade=t=in:st={start:.3f}:d={duration:.3f}:alpha=1[{out}]"
        )
        return out

    def rounded_mask(self, src: str, mask_png: str, w: int, h: int) -> str:
        """Aplica cantos arredondados via máscara PNG (alpha) pré-gerada."""
        idx = self.add_input(["-loop", "1", "-i", mask_png])
        mask_scaled = self._label("m")
        self.add_chain(f"[{idx}:v]scale={int(w)}:{int(h)},format=gray[{mask_scaled}]")
        out = self._label("r")
        self.add_chain(f"[{src}]format=rgba[{out}_p];[{out}_p][{mask_scaled}]alphamerge[{out}]")
        return out

    def subtitles(self, src: str, ass_path: str, fontsdir: str = None) -> str:
        out = self._label("sub")
        args = f"ass={_esc_path(os.path.abspath(ass_path))}"
        if fontsdir:
            args += f":fontsdir={_esc_path(os.path.abspath(fontsdir))}"
        self.add_chain(f"[{src}]{args}[{out}]")
        return out

    def scene_fade(self, src: str, duration: float, fade_in: float,
                   fade_out: float, color: str = "black") -> str:
        """Fade in/out da CENA inteira, misturando com uma cor sólida.

        Equivale ao `libs/Transitions/Fade.py`, que faz
        `alpha*frame + (1-alpha)*color` frame a frame em Python. Aqui é o filtro
        `fade` nativo, que aplica a mesma mistura linear — sem alpha, porque o
        alvo é a cor, não transparência.
        """
        out = self._label("tf")
        parts = []
        if fade_in and fade_in > 0:
            parts.append(f"fade=t=in:st=0:d={float(fade_in):.3f}:c={color}")
        if fade_out and fade_out > 0:
            st = max(0.0, float(duration) - float(fade_out))
            parts.append(f"fade=t=out:st={st:.3f}:d={float(fade_out):.3f}:c={color}")
        if not parts:
            return src
        self.add_chain(f"[{src}]{','.join(parts)}[{out}]")
        return out

    def to_yuv(self, src: str) -> str:
        out = self._label("y")
        self.add_chain(f"[{src}]format=yuv420p[{out}]")
        return out

    # -- saída -------------------------------------------------------------

    def build_args(self, final_label: str) -> tuple:
        """Devolve (input_args, filter_complex, label_final)."""
        flat = []
        for item in self.inputs:
            flat.extend(item)
        return flat, ";".join(self._chains), final_label
