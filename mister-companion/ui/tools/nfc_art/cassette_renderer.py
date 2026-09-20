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


def _load_bold_font(size):
    try:
        if sys.platform.startswith("win"):
            return ImageFont.truetype("arialbd.ttf", size)
        if sys.platform.startswith("linux"):
            return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", size)
        if sys.platform == "darwin":
            return ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", size)
    except Exception:
        pass
    return ImageFont.load_default()


def _wrap_text_to_width(text, font, max_width):
    lines = []
    for raw_line in text.splitlines() or [text]:
        if raw_line.strip() == "":
            lines.append("")
            continue

        words = raw_line.split()
        if not words:
            lines.append("")
            continue

        current = words[0]
        for word in words[1:]:
            candidate = f"{current} {word}"
            if font.getlength(candidate) <= max_width:
                current = candidate
                continue

            lines.append(current)

            if font.getlength(word) <= max_width:
                current = word
                continue

            fragment = ""
            for char in word:
                test = fragment + char
                if fragment and font.getlength(test) > max_width:
                    lines.append(fragment)
                    fragment = char
                else:
                    fragment = test
            current = fragment or word

        lines.append(current)

    return lines


def _line_height(font):
    try:
        ascent, descent = font.getmetrics()
        return ascent + descent
    except Exception:
        bbox = font.getbbox("Ag")
        return bbox[3] - bbox[1]


def _measure_wrapped_text(lines, font, paragraph_gap=0):
    line_height = _line_height(font)
    height = 0
    for idx, line in enumerate(lines):
        height += line_height
        if line == "" and idx != len(lines) - 1:
            height += paragraph_gap
    return height, line_height


def _fit_summary_block(text, max_width, max_height, start_size=32, min_size=14):
    text = text.strip()
    if not text or max_width <= 0 or max_height <= 0:
        return [], _load_bold_font(start_size), 0

    best = None

    for font_size in range(start_size, min_size - 1, -1):
        font = _load_bold_font(font_size)
        paragraph_gap = max(2, font_size // 5)
        lines = _wrap_text_to_width(text, font, max_width)
        height, line_height = _measure_wrapped_text(lines, font, paragraph_gap)

        best = (lines, font, line_height, paragraph_gap)
        if height <= max_height:
            return best

    return best


def _truncate_lines_to_height(lines, font, line_height, paragraph_gap, max_width, max_height):
    if not lines:
        return []

    fitted = []
    used_height = 0
    ellipsis = "..."

    for idx, line in enumerate(lines):
        extra_gap = paragraph_gap if line == "" and idx != len(lines) - 1 else 0
        needed = line_height + extra_gap

        if used_height + needed <= max_height:
            fitted.append(line)
            used_height += needed
            continue

        if line == "":
            break

        base = line.rstrip()
        while base and font.getlength(base + ellipsis) > max_width:
            base = base[:-1].rstrip()

        if base:
            fitted.append(base + ellipsis)
        elif fitted:
            prev = fitted.pop()
            prev = prev.rstrip()
            while prev and font.getlength(prev + ellipsis) > max_width:
                prev = prev[:-1].rstrip()
            fitted.append((prev + ellipsis) if prev else ellipsis)
        else:
            fitted.append(ellipsis)
        break

    return fitted


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
            # Calculate bottom limit dynamically, including items that live below
            # the summary area on the back cover.
            bottom_reserved = NFC_MARGIN

            if nfc_back:
                bottom_reserved += nfc_back.height

            if sys_back:
                bottom_reserved += BACK_GAP + sys_back.height

            original_cover = self.assets["original_cover_back"]
            original_img = None
            if original_cover:
                original_img = fit_image(original_cover, *ORIGINAL_COVER_BACK_MAX)
                bottom_reserved += BACK_GAP + original_img.height

            max_text_height = max(0, CARD_H - bottom_reserved - y)

            # Match text width to screenshot if present
            if self.assets["screenshot"]:
                text_width = shot.width
                x_pos = (BACK_W - shot.width) // 2
            else:
                text_width = BACK_W - 2 * PADDING
                x_pos = (BACK_W - text_width) // 2

            lines, font, line_height, paragraph_gap = _fit_summary_block(
                self.assets["summary"],
                text_width,
                max_text_height,
                start_size=32,
                min_size=14,
            )

            if lines and max_text_height > 0:
                fitted_lines = _truncate_lines_to_height(
                    lines, font, line_height, paragraph_gap, text_width, max_text_height
                )
                text_height, _ = _measure_wrapped_text(fitted_lines, font, paragraph_gap)

                text_box = Image.new(
                    "RGBA",
                    (text_width, max_text_height),
                    (0, 0, 0, 0)
                )
                td = ImageDraw.Draw(text_box)

                y_offset = 0
                for idx, line in enumerate(fitted_lines):
                    if line == "":
                        y_offset += line_height
                        if idx != len(fitted_lines) - 1:
                            y_offset += paragraph_gap
                        continue

                    td.text((0, y_offset), line, fill=self.colors["text"], font=font)
                    y_offset += line_height

                img.paste(text_box, (x_pos, y), text_box)
                y += text_height + BACK_GAP

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
