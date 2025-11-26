from moviepy.editor import TextClip

class LayoutEngine:
    @staticmethod
    def calculate_dimension(value, total_size):
        """Converte porcentagem (string) ou inteiro para pixels."""
        if isinstance(value, str) and "%" in value:
            percent = float(value.replace("%", "")) / 100
            return int(total_size * percent)
        return int(value)

    @staticmethod
    def get_position(layout_pos, element_size, canvas_size, margin=0):
        """
        Mantido para compatibilidade ou uso isolado.
        Calcula a posição (x, y) baseada em keywords ou coordenadas.
        """
        w, h = element_size
        cw, ch = canvas_size
        x, y = 0, 0

        if isinstance(layout_pos, list):
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
            x = int(pos_x)

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
            y = int(pos_y)

        return (x, y)

    @staticmethod
    def process_stack_layout(visual_items, subtitle_height, config):
        """
        Calcula posições e tamanhos para um layout de Pilha Vertical (Stack) com Legenda Fixa.
        """
        
        # 1. Definir a "Arena" (Espaços disponíveis)
        W, H = config.width, config.height
        pad_top = config.padding_top
        pad_bot = config.padding_bottom
        pad_side = config.padding_side
        gap_percent = config.stack_gap_percent

        # Largura Interna da Caixa (Área útil horizontal)
        inner_width = W - (2 * pad_side)

        # Posição Y fixa da Legenda (Ancorada no padding inferior)
        subtitle_y = H - pad_bot - subtitle_height
        subtitle_x = (W - config.width * 0.9) // 2 # Exemplo: centralizado ou conforme lógica da legenda

        # Altura disponível para os visuais (Do topo seguro até o topo da legenda)
        available_visual_height = subtitle_y - pad_top
        
        if not visual_items:
            return [], (subtitle_x, subtitle_y)

        # 2. Cálculo "Dry Run" (Rascunho) das dimensões ideais
        # Aqui calculamos quanto cada visual QUER ocupar baseada na largura e aspect ratio
        processed_items = []
        
        # Gap em pixels inicial
        gap_px = int(H * gap_percent)
        
        total_stack_height = 0

        for item in visual_items:
            # Recupera tamanho original para saber Aspect Ratio
            orig_w, orig_h = item.get('original_size', (1920, 1080)) # fallback 16:9 se falhar
            aspect_ratio = orig_w / orig_h if orig_h > 0 else 1.77
            
            # Largura desejada
            # Se o JSON define layout.width (ex: 0.8 ou "80%"), respeita. Se não, 100% da caixa interna.
            layout_data = item.get('layout', {})
            # Usa 1.0 como default se "width" não estiver presente
            req_width = layout_data.get('width', 1.0) 
            
            target_w = LayoutEngine.calculate_dimension(req_width, inner_width)
            
            # Altura é consequência da largura e do aspect ratio
            target_h = int(target_w / aspect_ratio)
            
            processed_items.append({
                'target_w': target_w,
                'target_h': target_h,
                'layout': layout_data
            })
            
            total_stack_height += target_h

        # Adicionar o espaço dos gaps na altura total
        total_stack_height += (len(processed_items) - 1) * gap_px

        # 3. Tratamento de Overflow (Escalonamento)
        # Se a pilha for maior que o espaço disponível, calculamos um fator de redução (scale)
        scale_factor = 1.0
        if total_stack_height > available_visual_height and total_stack_height > 0:
            scale_factor = available_visual_height / total_stack_height
        elif available_visual_height <= 0:
            # Caso o espaço seja zero ou negativo (padding/legenda cobrem tudo)
            scale_factor = 0.001 


        # 4. Calcular posições finais
        final_results = []
        
        # Aplicar escala (se houver) para ajustar ao espaço
        final_gap = gap_px * scale_factor
        final_total_height_scaled = total_stack_height * scale_factor
        
        # Definir ponto de partida Y (Centralizar verticalmente no espaço disponível)
        # Espaço livre acima da pilha escalonada
        free_space = available_visual_height - final_total_height_scaled
        current_y = pad_top + (free_space / 2)

        for p_item in processed_items:
            # Aplicar escala nas dimensões
            final_w = int(p_item['target_w'] * scale_factor)
            final_h = int(p_item['target_h'] * scale_factor)
            
            # >>>>> VERIFICAÇÃO DE SEGURANÇA CONTRA ERRO OPENCV <<<<<
            # Garante que a dimensão nunca seja zero para o resize funcionar
            if final_w < 1: final_w = 1
            if final_h < 1: final_h = 1
            # >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>

            # Calcular X
            # Se tiver 'position_x' no JSON, é relativo à caixa interna.
            # Se não, centraliza na caixa interna.
            pos_x_req = p_item['layout'].get('position_x')
            
            if pos_x_req is not None:
                # Calcula offset X relativo ao inicio da caixa interna
                offset_x = LayoutEngine.calculate_dimension(pos_x_req, inner_width)
                final_x = pad_side + offset_x
            else:
                # Centraliza
                final_x = pad_side + ((inner_width - final_w) // 2)

            final_results.append({
                'final_size': (final_w, final_h),
                'final_position': (final_x, int(current_y))
            })
            
            # Avança o cursor Y para o próximo item
            current_y += final_h + final_gap

        return final_results, (int(subtitle_x), int(subtitle_y))