from PIL import Image, ImageDraw, ImageFont
import os


class Headline:
    def __init__(self, params=None):
        defaults = {
            "background_color": (255, 255, 255),
            "title": None,
            "subtitle": None,
            "title_font_path": "./fonts/Poppins/Poppins-Bold.ttf",
            "subtitle_font_path": "./fonts/Lato/Lato-Regular.ttf",
            "title_font_size": 40,
            "subtitle_font_size": 20,
            "title_color": (31, 33, 35),
            "subtitle_color": (79, 82, 93),
            "padding": 20,
            "video_width": 1080,
            "output_path": "headline.png",
            "align": "left",
            "gap": 0,
            "margin_top_percent": 0.05,
            "scale": 2,  # 🔽 Reduzido de 8 → 2
            "antialias": True  # ✅ Novo: reduz imagem no final para suavizar o texto
        }

        if params:
            defaults.update(params)
        for k, v in defaults.items():
            setattr(self, k, v)

        self.width = self.video_width - 2 * self.padding

    def _wrap_text(self, text, font, max_width, draw):
        """Quebra o texto em múltiplas linhas com base na largura máxima."""
        if not text:
            return []

        lines, current_line = [], ""
        for word in text.split():
            test_line = f"{current_line} {word}".strip()
            bbox = draw.textbbox((0, 0), test_line, font=font)
            if bbox[2] - bbox[0] <= max_width:
                current_line = test_line
            else:
                if current_line:
                    lines.append(current_line)
                current_line = word
        if current_line:
            lines.append(current_line)
        return lines

    def generate(self):
        scale = self.scale

        # ✅ Carrega as fontes escalonadas
        title_font = ImageFont.truetype(self.title_font_path, self.title_font_size * scale)
        subtitle_font = ImageFont.truetype(self.subtitle_font_path, self.subtitle_font_size * scale)

        # ✅ Cria um único draw para medições
        measure_img = Image.new("RGB", (10, 10))
        draw = ImageDraw.Draw(measure_img)

        width_scaled = (self.video_width - 2 * self.padding) * scale
        title_lines = self._wrap_text(self.title, title_font, width_scaled, draw)
        subtitle_lines = self._wrap_text(self.subtitle, subtitle_font, width_scaled, draw)

        # ✅ Calcula alturas uma única vez
        line_height_title = draw.textbbox((0, 0), "Ag", font=title_font)[3] + (5 * scale)
        line_height_sub = draw.textbbox((0, 0), "Ag", font=subtitle_font)[3] + (5 * scale)

        total_height = (
            self.padding * scale
            + len(title_lines) * line_height_title
            + (self.gap * scale if subtitle_lines else 0)
            + len(subtitle_lines) * line_height_sub
            + self.padding * scale
        )

        # ✅ Usa RGB (sem alpha) — mais leve
        image = Image.new("RGB", (self.video_width * scale, total_height), self.background_color)
        draw = ImageDraw.Draw(image)

        # === Desenha texto ===
        y = self.padding * scale
        for line in title_lines:
            bbox = draw.textbbox((0, 0), line, font=title_font)
            x = (
                (self.video_width * scale - (bbox[2] - bbox[0])) // 2
                if self.align == "center"
                else self.padding * scale
            )
            draw.text((x, y), line, font=title_font, fill=self.title_color)
            y += line_height_title

        if subtitle_lines:
            y += self.gap * scale

        for line in subtitle_lines:
            bbox = draw.textbbox((0, 0), line, font=subtitle_font)
            x = (
                (self.video_width * scale - (bbox[2] - bbox[0])) // 2
                if self.align == "center"
                else self.padding * scale
            )
            draw.text((x, y), line, font=subtitle_font, fill=self.subtitle_color)
            y += line_height_sub

        # ✅ Antialias opcional: reduz o tamanho final
        if self.antialias and scale > 1:
            image = image.resize(
                (self.video_width, total_height // scale),
                Image.LANCZOS
            )

        if not self.output_path:
            raise ValueError("Defina 'output_path'.")

        image.save(self.output_path, format="PNG")

        return {
            "path": self.output_path,
            "width": image.width,
            "height": image.height
        }
