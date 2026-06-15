class LayoutEngine:
    @staticmethod
    def calculate_dimension(value, total_size):
        """
        Converte porcentagem (string), float multiplicador (0.0 a 1.0) ou inteiro para pixels.
        CORREÇÃO: Interpreta valores <= 1.0 (como "1" ou "0.8") como multiplicadores (100%, 80%),
        evitando que virem 1 pixel.
        """
        try:
            # 1. Trata porcentagem explícita (ex: "80%")
            if isinstance(value, str) and "%" in value:
                percent = float(value.replace("%", "")) / 100.0
                return int(total_size * percent)

            # 2. Converte para float para análise numérica
            float_val = float(value)
            
            # Se for 0, é 0 pixels mesmo
            if float_val == 0:
                return 0
                
            # REGRA INTELIGENTE:
            # Se o valor for <= 1.0 (ex: "1", 1, "0.5"), tratamos como PORCENTAGEM do total.
            # "1" vira 100% (total_size), "0.5" vira 50%.
            if abs(float_val) <= 1.0:
                return int(total_size * float_val)
            
            # Se o valor for > 1.0 (ex: "500", "1080"), tratamos como PIXELS absolutos.
            return int(float_val)

        except (ValueError, TypeError):
            # Fallback seguro em caso de erro
            return int(total_size)

    @staticmethod
    def get_position(layout_pos, element_size, canvas_size, margin=0):
        """Calcula a posição (x, y) simples."""
        w, h = element_size
        cw, ch = canvas_size
        x, y = 0, 0

        if isinstance(layout_pos, list) or isinstance(layout_pos, tuple):
            pos_x = layout_pos[0]
            pos_y = layout_pos[1]
        else:
            pos_x = layout_pos
            pos_y = "center"

        # Calcular X
        if pos_x == "center":
            x = (cw - w) // 2
        elif pos_x == "left":
            x = margin
        elif pos_x == "right":
            x = cw - w - margin
        elif isinstance(pos_x, str) and "%" in pos_x:
            x = int(cw * (float(pos_x.strip('%')) / 100))
        else:
            try: x = LayoutEngine.calculate_dimension(pos_x, cw)
            except: x = (cw - w) // 2

        # Calcular Y
        if pos_y == "center":
            y = (ch - h) // 2
        elif pos_y == "top":
            y = margin
        elif pos_y == "bottom":
            y = ch - h - margin
        elif isinstance(pos_y, str) and "%" in pos_y:
            y = int(ch * (float(pos_y.strip('%')) / 100))
        else:
            try: y = LayoutEngine.calculate_dimension(pos_y, ch)
            except: y = (ch - h) // 2

        return (x, y)

    @staticmethod
    def safe_area(canvas_size, paddings):
        """Retorna o retângulo de área segura (x, y, w, h) a partir dos paddings.

        Paddings significam apenas margem segura — a faixa onde elementos podem
        ser ancorados. `paddings` é um dict/obj com padding_side/top/bottom.
        """
        cw, ch = canvas_size
        pad_side = getattr(paddings, "padding_side", None)
        if pad_side is None and isinstance(paddings, dict):
            pad_side = paddings.get("padding_side", 0)
        pad_top = getattr(paddings, "padding_top", None)
        if pad_top is None and isinstance(paddings, dict):
            pad_top = paddings.get("padding_top", 0)
        pad_bot = getattr(paddings, "padding_bottom", None)
        if pad_bot is None and isinstance(paddings, dict):
            pad_bot = paddings.get("padding_bottom", 0)

        pad_side = int(pad_side or 0)
        pad_top = int(pad_top or 0)
        pad_bot = int(pad_bot or 0)

        x = pad_side
        y = pad_top
        w = max(1, cw - 2 * pad_side)
        h = max(1, ch - pad_top - pad_bot)
        return (x, y, w, h)

    @staticmethod
    def resolve_anchor(placement, element_size, canvas_size, safe_rect):
        """Resolve um bloco `placement` numa posição absoluta (x, y) na tela.

        `placement` = {"anchor": [x, y], "width": ..., "region": ...}
          - anchor[0] (x): left | center | right | "70%" | px
          - anchor[1] (y): top  | center | bottom | "50%" | px
        Âncoras nomeadas (left/right/top/bottom/center) são resolvidas DENTRO da
        área segura (`safe_rect` = (sx, sy, sw, sh)); percentuais/px são relativos
        à área segura também, para manter tudo dentro da margem.

        Retorna (x, y) já considerando o tamanho do elemento (canto superior esq.).
        """
        ew, eh = element_size
        sx, sy, sw, sh = safe_rect

        anchor = placement.get("anchor", ["center", "center"])
        if isinstance(anchor, str):
            ax, ay = anchor, "center"
        elif isinstance(anchor, (list, tuple)):
            ax = anchor[0] if len(anchor) > 0 else "center"
            ay = anchor[1] if len(anchor) > 1 else "center"
        else:
            ax, ay = "center", "center"

        # X dentro da área segura
        if ax == "left":
            x = sx
        elif ax == "right":
            x = sx + sw - ew
        elif ax == "center":
            x = sx + (sw - ew) // 2
        elif isinstance(ax, str) and "%" in ax:
            x = sx + int(sw * (float(ax.strip("%")) / 100.0))
        else:
            x = sx + LayoutEngine.calculate_dimension(ax, sw)

        # Y dentro da área segura
        if ay == "top":
            y = sy
        elif ay == "bottom":
            y = sy + sh - eh
        elif ay == "center":
            y = sy + (sh - eh) // 2
        elif isinstance(ay, str) and "%" in ay:
            y = sy + int(sh * (float(ay.strip("%")) / 100.0))
        else:
            y = sy + LayoutEngine.calculate_dimension(ay, sh)

        return (int(x), int(y))

    @staticmethod
    def process_stack_layout(visual_items, config):
        """
        Calcula posições para empilhar itens visualmente na área verde (entre Topo e Legenda).
        Regra da Imagem: 'VISUAIS: SEMPRE CENTRALIZADOS HORIZONTALMENTE'

        Suporte a posicionamento absoluto por item:
          - layout.position: "center"          → centraliza na tela cheia (ignora padding_top/bottom)
          - layout.position: "top" / "bottom"  → âncora com margin
          - layout.position: ["center","50%"]  → posição explícita [x, y]
        Itens com position explícita são posicionados individualmente e removidos do stack normal.
        """
        
        # 1. Definir a "Arena" (Espaços disponíveis)
        W, H = config.width, config.height
        pad_top = config.padding_top
        pad_bot = config.padding_bottom
        pad_side = config.padding_side
        gap_percent = config.stack_gap_percent

        # Largura Interna da Caixa (Área útil horizontal)
        inner_width = W - (2 * pad_side)

        # Altura disponível para os visuais (Da margem segura até o topo da área da legenda)
        available_visual_height = (H - pad_bot) - pad_top

        # Área segura (margens) — usada pelo posicionamento via `placement`.
        safe_rect = LayoutEngine.safe_area((W, H), config)

        if not visual_items:
            return []

        # --- Separa itens por modo de posicionamento ---
        #  placement (novo) > layout.position explícito (legado) > stack (default)
        EXPLICIT_POSITIONS = {"center", "top", "bottom"}

        stack_items     = []  # índice original → entra no stack
        explicit_items  = []  # (índice original, item, position_value) — modo legado
        placement_items = []  # (índice original, item, placement_dict) — modo novo

        for idx, item in enumerate(visual_items):
            placement = item.get('placement')
            if isinstance(placement, dict) and placement.get('anchor') is not None:
                placement_items.append((idx, item, placement))
                continue

            layout_data = item.get('layout', {})
            pos = layout_data.get('position')
            if pos is not None and (
                (isinstance(pos, str) and pos in EXPLICIT_POSITIONS)
                or isinstance(pos, (list, tuple))
            ):
                explicit_items.append((idx, item, pos))
            else:
                stack_items.append((idx, item))

        # Pré-aloca resultado com None para manter índice original
        final_results = [None] * len(visual_items)

        # --- Posiciona itens via `placement` (área segura + anchor) ---
        for idx, item, placement in placement_items:
            orig_w, orig_h = item.get('original_size', (1920, 1080))
            if orig_h == 0: orig_h = 1080
            aspect_ratio = orig_w / orig_h

            req_width  = placement.get('width')
            req_height = placement.get('height')
            safe_h = safe_rect[3]
            safe_w = safe_rect[2]
            crop_height = None  # altura de crop cover (None = sem crop)

            if req_width is not None and req_height is not None:
                # width + height: cover — o final_size é sempre (target_w, crop_height).
                # Resize pela dimensão que garante cobertura total da caixa, depois crop o excesso.
                desired_w = LayoutEngine.calculate_dimension(req_width, safe_w)
                desired_h = LayoutEngine.calculate_dimension(req_height, safe_h)
                # Escala pela dimensão que mais cresce para garantir cobertura total
                scale_by_w = desired_w / (orig_w or 1)
                scale_by_h = desired_h / (orig_h or 1)
                scale = max(scale_by_w, scale_by_h)
                target_w = int(orig_w * scale)  # pode ser maior que desired_w (crop horizontal)
                target_h = int(orig_h * scale)  # pode ser maior que desired_h (crop vertical)
                crop_height = desired_h          # altura final uniforme
            elif req_height is not None:
                # só height: height-driven, width derivado pelo aspect ratio
                target_h = LayoutEngine.calculate_dimension(req_height, safe_h)
                target_w = int(target_h * aspect_ratio)
            else:
                # só width (comportamento original, width default 100%)
                target_w = LayoutEngine.calculate_dimension(req_width if req_width is not None else 1.0, safe_w)
                target_h = int(target_w / aspect_ratio)

            # Clamp só no modo SEM cover (preserva aspect ratio reduzindo se estourar).
            # No modo cover, target_w/target_h são o tamanho do RESIZE (aspect preservado);
            # o recorte para a caixa é feito via crop_width/crop_height no worker.
            if crop_height is None:
                if target_h > safe_h and target_h > 0:
                    scale = safe_h / target_h
                    target_h = safe_h
                    target_w = int(target_w * scale)
                if target_w > safe_w and target_w > 0:
                    scale = safe_w / target_w
                    target_w = safe_w
                    target_h = int(target_h * scale)

            if target_w < 2: target_w = 2
            if target_h < 2: target_h = 2

            # No modo cover, o tamanho FINAL (caixa) é (desired_w, desired_h);
            # o resize usa (target_w, target_h) e o crop centralizado recorta o excesso.
            if crop_height is not None:
                final_w, final_h = desired_w, desired_h
                crop_width  = desired_w if target_w > desired_w else None
                resize_to   = (target_w, target_h)
                anchor_size = (final_w, final_h)
            else:
                final_w, final_h = target_w, target_h
                crop_width  = None
                resize_to   = (target_w, target_h)
                anchor_size = (target_w, target_h)

            fx, fy = LayoutEngine.resolve_anchor(
                placement, anchor_size, (W, H), safe_rect
            )

            final_results[idx] = {
                'final_size': (final_w, final_h),
                'final_position': (fx, fy),
                'crop_height': crop_height,
                'crop_width': crop_width,
                '_resize_to': resize_to,
                'border_radius': item.get('border_radius', 0),
                # Em modo cover (crop_height != None), animation é adiada e aplicada
                # no worker pós-crop dentro de janela fixa. Fora do cover é None aqui.
                'deferred_animation': item.get('animation') if crop_height is not None else None,
            }

        # --- Posiciona itens explícitos ---
        for idx, item, pos in explicit_items:
            orig_w, orig_h = item.get('original_size', (1920, 1080))
            if orig_h == 0: orig_h = 1080
            aspect_ratio = orig_w / orig_h

            layout_data = item.get('layout', {})
            req_width   = layout_data.get('width', 0.8)
            target_w    = LayoutEngine.calculate_dimension(req_width, inner_width)
            target_h    = int(target_w / aspect_ratio)

            if target_w < 2: target_w = 2
            if target_h < 2: target_h = 2

            margin = layout_data.get('margin', 0)

            fx, fy = LayoutEngine.get_position(pos, (target_w, target_h), (W, H), margin)

            final_results[idx] = {
                'final_size': (target_w, target_h),
                'final_position': (fx, fy),
            }

        # --- Stack normal (comportamento anterior) ---
        if stack_items:
            gap_px = int(H * gap_percent)
            total_stack_height = 0
            processed_items = []

            for _, item in stack_items:
                orig_w, orig_h = item.get('original_size', (1920, 1080))
                if orig_h == 0: orig_h = 1080
                aspect_ratio = orig_w / orig_h

                layout_data = item.get('layout', {})
                req_width   = layout_data.get('width', 1.0)
                target_w    = LayoutEngine.calculate_dimension(req_width, inner_width)
                target_h    = int(target_w / aspect_ratio)

                processed_items.append({
                    'target_w': target_w,
                    'target_h': target_h,
                    'layout': layout_data,
                })
                total_stack_height += target_h

            if len(processed_items) > 1:
                total_stack_height += (len(processed_items) - 1) * gap_px

            scale_factor = 1.0
            if total_stack_height > available_visual_height and total_stack_height > 0:
                scale_factor = available_visual_height / total_stack_height
                scale_factor *= 0.95

            final_total_height_scaled = 0
            for p in processed_items:
                final_total_height_scaled += int(p['target_h'] * scale_factor)
            if len(processed_items) > 1:
                final_total_height_scaled += (len(processed_items) - 1) * int(gap_px * scale_factor)

            free_space = available_visual_height - final_total_height_scaled
            current_y  = pad_top + (free_space // 2)

            for (orig_idx, _), p_item in zip(stack_items, processed_items):
                final_w = int(p_item['target_w'] * scale_factor)
                final_h = int(p_item['target_h'] * scale_factor)
                if final_w < 2: final_w = 2
                if final_h < 2: final_h = 2

                pos_x_req = p_item['layout'].get('position_x')
                if pos_x_req is not None:
                    offset_x = LayoutEngine.calculate_dimension(pos_x_req, inner_width)
                    final_x  = pad_side + offset_x
                else:
                    final_x = (W - final_w) // 2

                final_results[orig_idx] = {
                    'final_size': (final_w, final_h),
                    'final_position': (final_x, int(current_y)),
                }

                current_y += final_h + (gap_px * scale_factor)

        # Garante que nenhum slot ficou None (fallback centro)
        for i in range(len(final_results)):
            if final_results[i] is None:
                final_results[i] = {
                    'final_size': (100, 100),
                    'final_position': (W // 2 - 50, H // 2 - 50),
                }

        return final_results
