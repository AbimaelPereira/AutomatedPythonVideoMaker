from moviepy.editor import TextClip

class LayoutEngine:
    @staticmethod
    def calculate_dimension(value, total_size):
        """Converte porcentagem (string), float multiplicador (0.0 a 1.0) ou inteiro para pixels."""
        if isinstance(value, str) and "%" in value:
            try:
                percent = float(value.replace("%", "")) / 100
                return int(total_size * percent)
            except ValueError:
                return int(total_size) # Fallback seguro
            
        if isinstance(value, float) and 0.0 <= value <= 1.0:
            return int(total_size * value)
            
        try:
            return int(value)
        except (ValueError, TypeError):
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
            try: x = int(pos_x)
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
            try: y = int(pos_y)
            except: y = (ch - h) // 2

        return (x, y)

    @staticmethod
    def process_stack_layout(visual_items, config):
        """
        Calcula posições para empilhar itens visualmente na área verde (entre Topo e Legenda).
        Regra da Imagem: 'VISUAIS: SEMPRE CENTRALIZADOS HORIZONTALMENTE'
        """
        
        # 1. Definir a "Arena" (Espaços disponíveis)
        W, H = config.width, config.height
        pad_top = config.padding_top
        pad_bot = config.padding_bottom # Altura da caixa de legenda azul
        pad_side = config.padding_side
        gap_percent = config.stack_gap_percent

        # Largura Interna da Caixa (Área útil horizontal)
        inner_width = W - (2 * pad_side)

        # A área de visuais termina onde começa a área da legenda (Box Azul)
        # Visual Area Bottom = H - pad_bot
        
        # Altura disponível para os visuais (Da margem segura até o topo da área da legenda)
        available_visual_height = (H - pad_bot) - pad_top
        
        if not visual_items:
            return []

        # 2. Cálculo "Dry Run"
        processed_items = []
        
        gap_px = int(H * gap_percent)
        total_stack_height = 0

        for item in visual_items:
            # Tenta pegar tamanho original, senão assume 16:9 landscape padrão
            orig_w, orig_h = item.get('original_size', (1920, 1080)) 
            if orig_h == 0: orig_h = 1080
            aspect_ratio = orig_w / orig_h
            
            # Layout data do JSON
            layout_data = item.get('layout', {})
            
            # Largura desejada: padrão 100% da caixa interna (inner_width)
            # Se o usuário especificou 'width' no json (ex: "80%"), respeita
            req_width = layout_data.get('width', 1.0) 
            
            target_w = LayoutEngine.calculate_dimension(req_width, inner_width)
            
            # Altura proporcional
            target_h = int(target_w / aspect_ratio)
            
            processed_items.append({
                'target_w': target_w,
                'target_h': target_h,
                'layout': layout_data # Mantém ref para overrides manuais se existirem
            })
            
            total_stack_height += target_h

        # Adicionar o espaço dos gaps na altura total
        if len(processed_items) > 1:
            total_stack_height += (len(processed_items) - 1) * gap_px

        # 3. Tratamento de Overflow (Escalonamento)
        # Se a pilha for maior que o espaço verde disponível, reduz tudo proporcionalmente
        scale_factor = 1.0
        if total_stack_height > available_visual_height and total_stack_height > 0:
            scale_factor = available_visual_height / total_stack_height
            # Reduz um pouco mais para garantir margem de respiro
            scale_factor *= 0.95 
        
        # 4. Calcular posições finais
        final_results = []
        
        # Recalcula altura total escalonada
        final_total_height_scaled = 0
        for p in processed_items:
            final_total_height_scaled += int(p['target_h'] * scale_factor)
        
        if len(processed_items) > 1:
            final_total_height_scaled += (len(processed_items) - 1) * (gap_px * scale_factor)

        # Definir ponto de partida Y para CENTRALIZAR O BLOCO VISUAL VERTICALMENTE
        # na área disponível (pad_top até H-pad_bot)
        free_space = available_visual_height - final_total_height_scaled
        current_y = pad_top + (free_space // 2)

        for p_item in processed_items:
            # Aplicar escala nas dimensões
            final_w = int(p_item['target_w'] * scale_factor)
            final_h = int(p_item['target_h'] * scale_factor)
            
            # Segurança
            if final_w < 2: final_w = 2
            if final_h < 2: final_h = 2

            # Calcular X (Sempre centralizado horizontalmente segundo a imagem)
            # Se o JSON forçar 'position_x', obedece relativo ao inner_box, senão centraliza
            pos_x_req = p_item['layout'].get('position_x')
            
            if pos_x_req is not None:
                offset_x = LayoutEngine.calculate_dimension(pos_x_req, inner_width)
                final_x = pad_side + offset_x
            else:
                # Centro exato da tela
                final_x = (W - final_w) // 2

            final_results.append({
                'final_size': (final_w, final_h),
                'final_position': (final_x, int(current_y))
            })
            
            # Avança Y
            current_y += final_h + (gap_px * scale_factor)

        return final_results