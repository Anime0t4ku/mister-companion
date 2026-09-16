import sys

from PIL import Image, ImageDraw, ImageFont


CARD_W = 1629

CARD_H = 1600

BACK_W = 403

SPINE_W = 199

FRONT_W = 1027

FRONT_X = BACK_W + SPINE_W

BANNER_H = 165

POSTER_H = 1435

PADDING = 16

NFC_MARGIN = 30

NFC_FRONT_MAX = (360, 150)

NFC_SPINE_MAX = (270, 150)

NFC_BACK_MAX = (300, 100)

TITLE_LOGO_BACK_MAX = (375, 180)

TITLE_LOGO_SPINE_MAX = (183, 520)

SCREENSHOT_MAX = (350, 420)

EDITOR_HANDLE_SIZE = 10

ORIGINAL_COVER_BACK_MAX = (320, 320)

SYSTEM_LOGO_FRONT_MAX = (360, 100)

SYSTEM_LOGO_SPINE_MAX = (120, 300)

SYSTEM_LOGO_BACK_MAX = (300, 100)

BACK_TEXT_H = 520

BACK_BRAND_ZONE_H = 220

BACK_GAP = 30

def fit_image(img, max_w, max_h):
    img = img.copy()
    iw, ih = img.size

    # Only shrink if bigger than max
    if iw > max_w or ih > max_h:
        scale = min(max_w / iw, max_h / ih)
        new_w = int(iw * scale)
        new_h = int(ih * scale)
        img = img.resize((new_w, new_h), Image.LANCZOS)

    return img


def fit_image_upscale_only(img, max_w, max_h):
    img = img.copy()
    iw, ih = img.size
    if iw < max_w and ih < max_h:
        scale = min(max_w / iw, max_h / ih)
        img = img.resize((int(iw * scale), int(ih * scale)), Image.LANCZOS)
    return img

def fit_fill(img, w, h):
    iw, ih = img.size
    scale = max(w / iw, h / ih)
    img = img.resize((int(iw * scale), int(ih * scale)), Image.LANCZOS)
    left = (img.width - w) // 2
    top = (img.height - h) // 2
    return img.crop((left, top, left + w, top + h))

class CassetteRendererMixin:
    def render(self):
        img = Image.new("RGB", (CARD_W, CARD_H), self.colors["back"])
        draw = ImageDraw.Draw(img)

        # Spine background
        draw.rectangle((BACK_W, 0, BACK_W + SPINE_W, CARD_H), fill=self.colors["spine"])

        # Front banner
        draw.rectangle((FRONT_X, 0, CARD_W, BANNER_H), fill=self.colors["banner"])

        # FRONT
        if self.assets["poster"]:

            poster = self.crop_poster(self.assets["poster"], FRONT_W, POSTER_H)

            # ---------------------------------
            # Apply Poster Editor overlays
            # ---------------------------------
            if self.poster_overlays:

                poster = poster.convert("RGBA")

                scale_x = FRONT_W / self.editor_w
                scale_y = POSTER_H / self.editor_h

                for overlay in self.poster_overlays:
                    overlay_img = overlay["image"].copy()

                    w, h = overlay_img.size
                    overlay_img = overlay_img.resize(
                        (
                            int(w * overlay["scale"] * scale_x),
                            int(h * overlay["scale"] * scale_y)
                        ),
                        Image.LANCZOS
                    )

                    x = int((overlay["x"] * scale_x) - overlay_img.width / 2)
                    y = int((overlay["y"] * scale_y) - overlay_img.height / 2)

                    poster.paste(overlay_img, (x, y), overlay_img)

                poster = poster.convert("RGB")

            img.paste(poster, (FRONT_X, BANNER_H))

        logo = self.assets["system_logo_front"] or self.assets["system_logo_default"]

        if logo:
            logo_img = fit_image(logo, *SYSTEM_LOGO_FRONT_MAX)
            img.paste(
                logo_img,
                (FRONT_X + PADDING, (BANNER_H - logo_img.height) // 2),
                logo_img
            )
        # NFC FRONT
        mode = self.nfc_logo_colors["front"]

        if mode != "none":
            nfc_front = fit_image(
                self.nfc_logos[mode],
                *NFC_FRONT_MAX
            )

            img.paste(
                nfc_front,
                (CARD_W - nfc_front.width - NFC_MARGIN, NFC_MARGIN),
                nfc_front
            )
        # SPINE
        logo = self.assets["system_logo_spine"] or self.assets["system_logo_default"]

        if logo:
            rotated = logo.rotate(-90, expand=True)
            sys_spine = fit_image(rotated, *SYSTEM_LOGO_SPINE_MAX)
            img.paste(
                sys_spine,
                (BACK_W + (SPINE_W - sys_spine.width) // 2, NFC_MARGIN),
                sys_spine
            )

        title_spine = self.assets["title_logo_spine"] or self.assets["title_logo_default"]

        if title_spine:
            rotated_logo = title_spine.rotate(-90, expand=True)
            title_spine = fit_image(rotated_logo, *TITLE_LOGO_SPINE_MAX)

            img.paste(
                title_spine,
                (BACK_W + (SPINE_W - title_spine.width) // 2,
                 (CARD_H - title_spine.height) // 2),
                title_spine
            )

        mode = self.nfc_logo_colors["spine"]

        if mode != "none":
            nfc_spine = fit_image(
                self.nfc_logos[mode],
                *NFC_SPINE_MAX
            ).rotate(-90, expand=True)

            img.paste(
                nfc_spine,
                (
                    BACK_W + (SPINE_W - nfc_spine.width) // 2,
                    CARD_H - nfc_spine.height - NFC_MARGIN
                ),
                nfc_spine
            )

        # BACK
        y = PADDING

        mode = self.nfc_logo_colors["back"]

        nfc_back = None

        if mode != "none":
            nfc_back = fit_image(
                self.nfc_logos[mode],
                *NFC_BACK_MAX
            )

        back_logo_asset = self.assets["system_logo_back"] or self.assets["system_logo_default"]

        sys_back = None
        if back_logo_asset:
            sys_back = fit_image(back_logo_asset, *SYSTEM_LOGO_BACK_MAX)

        title_back = self.assets["title_logo_back"] or self.assets["title_logo_default"]

        if title_back:
            back_logo = fit_image(title_back, *TITLE_LOGO_BACK_MAX)
            img.paste(back_logo, ((BACK_W - back_logo.width) // 2, y), back_logo)
            y += back_logo.height + BACK_GAP

        if self.assets["screenshot"]:
            shot = fit_image(self.assets["screenshot"], *SCREENSHOT_MAX)
            shot = fit_image_upscale_only(shot, *SCREENSHOT_MAX)
            x_pos = (BACK_W - shot.width) // 2
            img.paste(shot, (x_pos, y))
            y += shot.height + BACK_GAP

        if self.assets["summary"]:
            # Calculate bottom limit dynamically
            bottom_reserved = NFC_MARGIN + BACK_GAP

            if nfc_back:
                bottom_reserved += nfc_back.height

            if sys_back:
                bottom_reserved += sys_back.height + BACK_GAP

            max_text_height = CARD_H - bottom_reserved - y

            # Match text width to screenshot if present
            if self.assets["screenshot"]:
                text_width = shot.width
            else:
                text_width = BACK_W - 2 * PADDING

            text_box = Image.new(
                "RGBA",
                (text_width, max_text_height),
                (0, 0, 0, 0)
            )
            td = ImageDraw.Draw(text_box)

            text = self.assets["summary"]

            # Safe font loading
            try:
                # Windows
                if sys.platform.startswith("win"):
                    font = ImageFont.truetype("arialbd.ttf", 32)

                # Linux
                elif sys.platform.startswith("linux"):
                    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 32)

                # macOS
                elif sys.platform == "darwin":
                    font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 32)

                else:
                    font = ImageFont.load_default()

            except Exception:
                font = ImageFont.load_default()

            max_width = text_box.width
            max_height = text_box.height

            # Proper line height from font metrics
            ascent, descent = font.getmetrics()
            line_height = ascent + descent + 4

            # Improved wrapping engine (preserves empty lines)
            lines = []

            for raw_line in text.split("\n"):

                # Preserve empty paragraphs
                if raw_line.strip() == "":
                    lines.append("")  # blank line
                    continue

                words = raw_line.split(" ")
                current = ""

                for word in words:
                    test = word if current == "" else current + " " + word
                    width = font.getlength(test)

                    if width <= max_width:
                        current = test
                    else:
                        if current:
                            lines.append(current)
                        current = word

                if current:
                    lines.append(current)

            # Exact line height from font
            ascent, descent = font.getmetrics()
            line_height = ascent + descent

            y_offset = 0

            for line in lines:

                # Stop if next line would overflow
                if y_offset >= max_height:
                    break

                if line == "":
                    y_offset += line_height
                    continue

                td.text((0, y_offset), line, fill=self.colors["text"], font=font)
                y_offset += line_height

            if self.assets["screenshot"]:
                x_pos = (BACK_W - shot.width) // 2
            else:
                x_pos = (BACK_W - text_box.width) // 2
            img.paste(text_box, (x_pos, y), text_box)

            y += text_box.height + BACK_GAP

        # --- ORIGINAL COVER  ---

        original_cover = self.assets["original_cover_back"]

        # Calculate base Y positions
        if nfc_back:
            nfc_y = CARD_H - nfc_back.height - NFC_MARGIN
        else:
            nfc_y = CARD_H - NFC_MARGIN

        sys_y = None
        if sys_back:
            sys_y = nfc_y - sys_back.height - BACK_GAP

        orig_y = None
        if original_cover:
            original_img = fit_image(original_cover, *ORIGINAL_COVER_BACK_MAX)

            if sys_back:
                orig_y = sys_y - original_img.height - BACK_GAP
            else:
                orig_y = nfc_y - original_img.height - BACK_GAP

            img.paste(
                original_img,
                ((BACK_W - original_img.width) // 2, orig_y),
                original_img
            )

        # --- Paste system logo ---
        if sys_back:
            img.paste(
                sys_back,
                ((BACK_W - sys_back.width) // 2, sys_y),
                sys_back
            )

        # --- Paste NFC back ---
        if nfc_back:
            img.paste(
                nfc_back,
                ((BACK_W - nfc_back.width) // 2, nfc_y),
                nfc_back
            )

        return img

    def crop_poster(self, img, target_w, target_h):
        iw, ih = img.size

        # Determine orientation
        landscape = iw > ih

        # Scale to fill
        scale = max(target_w / iw, target_h / ih)
        new_w = int(iw * scale)
        new_h = int(ih * scale)

        img = img.resize((new_w, new_h), Image.LANCZOS)

        mode = self.crop_mode_var.get()

        if landscape:
            # Horizontal crop
            overflow = new_w - target_w

            if mode == "center":
                left = overflow // 2
            elif mode == "top":  # means Left in landscape
                left = 0
            elif mode == "bottom":  # means Right in landscape
                left = overflow
            else:  # manual
                percent = self.crop_offset_var.get() / 1000
                left = int(overflow * percent)

            top = (new_h - target_h) // 2

        else:
            # Vertical crop
            overflow = new_h - target_h

            if mode == "center":
                top = overflow // 2
            elif mode == "top":
                top = 0
            elif mode == "bottom":
                top = overflow
            else:  # manual
                percent = self.crop_offset_var.get() / 1000
                top = int(overflow * percent)

            left = (new_w - target_w) // 2

        return img.crop((left, top, left + target_w, top + target_h))
