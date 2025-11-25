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
        Calcula a posição (x, y) baseada em keywords ou coordenadas.
        layout_pos: "center", ["center", "top"], [100, 200]
        """
        w, h = element_size
        cw, ch = canvas_size
        
        # Padrões
        x, y = 0, 0

        # Se for lista ex: [x, y] ou ["center", 0.5]
        if isinstance(layout_pos, list):
            pos_x = layout_pos[0]
            pos_y = layout_pos[1]
        else:
            # Se for string única ex: "center" -> ["center", "center"]
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