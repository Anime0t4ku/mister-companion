from datetime import datetime
from io import BytesIO
import os

import requests
from PIL import Image, ImageDraw, ImageFile, ImageOps

from .config import resource_path, sanitize_filename, WEB_POSTER_DIR, WEB_LOGO_DIR, load_cache_posters, load_cache_logos

ImageFile.LOAD_TRUNCATED_IMAGES = True
Image.MAX_IMAGE_PIXELS = 60000000
MAX_LOADED_IMAGE_PIXELS = 36000000
MAX_LOADED_IMAGE_SIDE = 6000

CLEAR_W = 609
T4_POSTER_W = 619
T4_POSTER_H = 834
T4_POSTER_Y = 80
THUMB_W = 160
THUMB_H = 240
ICON_THUMB_SIZE = 160
THUMBS_PER_ROW = 3
TEMPLATE_THUMB_W = 140
TEMPLATE_THUMB_H = 200
SYSTEM_ICON_RESULT_LIMIT = 200
PREVIEW_MIN_W = 340
PREVIEW_MIN_H = 520

TEMPLATES = {
    'Black with Pins': {'image_path': 'templates/template_1.png', 'center': {'x': 10, 'y': 59, 'w': 597, 'h': 855}, 'footer': {'height': 90, 'logo_height': 46, 'max_width': 300, 'logo_margin': 25}, 'mode': 'framed'},
    'White with Pins': {'image_path': 'templates/template_2.png', 'center': {'x': 14, 'y': 63, 'w': 589, 'h': 847}, 'footer': {'height': 90, 'logo_height': 46, 'max_width': 300, 'logo_margin': 25}, 'mode': 'framed'},
    'HuCard Style': {'image_path': 'templates/template_3.png', 'poster_y': 150, 'header_logo': {'height': 63, 'max_width': 250, 'top_margin': 62, 'left_margin': 24}, 'mode': 'layered'},
    'Black': {'image_path': 'templates/template_4.png', 'header_logo': {'max_height': 62, 'max_width': 300, 'top_margin': 10}, 'mode': 'framed-top-logo'},
    'White': {'image_path': 'templates/template_5.png', 'header_logo': {'max_height': 62, 'max_width': 300, 'top_margin': 10}, 'mode': 'framed-top-logo'},
    'Poster Only': {'image_path': 'templates/template_6.png', 'size': {'w': 619, 'h': 994}, 'corner_radius': 22, 'mode': 'full-poster-rounded'},
    'Bottom Logo Black Panel': {'image_path': 'templates/template_7.png', 'size': {'w': 619, 'h': 994}, 'corner_radius': 22, 'panel': {'logo_max_height': 50, 'logo_max_width': 270, 'padding': 3, 'outline_width': 6, 'bg_color': (0, 0, 0, 255), 'outline_color': (255, 255, 255, 255)}, 'mode': 'full-poster-bottom-panel'},
    'Bottom Logo White Panel': {'image_path': 'templates/template_8.png', 'size': {'w': 619, 'h': 994}, 'corner_radius': 22, 'panel': {'logo_max_height': 50, 'logo_max_width': 270, 'padding': 3, 'outline_width': 6, 'bg_color': (255, 255, 255, 255), 'outline_color': (0, 0, 0, 255)}, 'mode': 'full-poster-bottom-panel'},
    'SV-001 (By R_NEES)': {'image_path': 'templates/template_9.png', 'corner_radius': 22, 'nls': {'max_width': 220, 'max_height': 60, 'margin': 40}, 'system_logo': {'max_width': 200, 'max_height': 60, 'margin': 40}, 'mode': 'layered-dual-corner'},
}


def normalize_image(img):
    img.load()
    img = ImageOps.exif_transpose(img)
    if img.width <= 0 or img.height <= 0:
        raise ValueError('Image has an invalid size')
    if img.width * img.height > MAX_LOADED_IMAGE_PIXELS or img.width > MAX_LOADED_IMAGE_SIDE or img.height > MAX_LOADED_IMAGE_SIDE:
        img.thumbnail((MAX_LOADED_IMAGE_SIDE, MAX_LOADED_IMAGE_SIDE), Image.LANCZOS)
    return img.convert('RGBA')


def load_image_from_bytes(data):
    if not data:
        raise ValueError('Image data is empty')
    with Image.open(BytesIO(data)) as img:
        return normalize_image(img)


def load_image_from_file(path):
    with Image.open(path) as img:
        return normalize_image(img)


def fit_inside(img, max_w, max_h):
    scale = min(max_w / img.width, max_h / img.height)
    new_w = max(1, int(img.width * scale))
    new_h = max(1, int(img.height * scale))
    resized = img.resize((new_w, new_h), Image.LANCZOS)
    canvas = Image.new('RGBA', (max_w, max_h), (0, 0, 0, 0))
    canvas.paste(resized, ((max_w - new_w) // 2, (max_h - new_h) // 2), resized)
    return canvas


def load_image_from_url(url, timeout=10):
    if not url.lower().startswith(('http://', 'https://')):
        raise ValueError('Only http(s) URLs are supported')
    r = requests.get(url, timeout=timeout)
    r.raise_for_status()
    return load_image_from_bytes(r.content)


def maybe_cache_web_image(img, url, kind='poster'):
    if kind == 'poster' and not load_cache_posters():
        return img
    if kind == 'logo' and not load_cache_logos():
        return img
    base_dir = WEB_LOGO_DIR if kind == 'logo' else WEB_POSTER_DIR
    os.makedirs(base_dir, exist_ok=True)
    name = os.path.basename(url.split('?')[0]) or f'{kind}_{datetime.now().strftime("%Y%m%d_%H%M%S")}'
    name = os.path.splitext(name)[0] + '.png'
    path = os.path.join(base_dir, sanitize_filename(name))
    try:
        img.convert('RGBA').save(path, format='PNG')
    except Exception:
        pass
    return img


def cover_image(img, w, h):
    ratio = max(w / img.width, h / img.height)
    r = img.resize((int(img.width * ratio), int(img.height * ratio)), Image.LANCZOS)
    x = (r.width - w) // 2
    y = (r.height - h) // 2
    return r.crop((x, y, x + w, y + h))


def cover_image_top(img, w, h):
    ratio = max(w / img.width, h / img.height)
    r = img.resize((int(img.width * ratio), int(img.height * ratio)), Image.LANCZOS)
    x = (r.width - w) // 2
    return r.crop((x, 0, x + w, h))


def cover_image_bottom(img, w, h):
    ratio = max(w / img.width, h / img.height)
    r = img.resize((int(img.width * ratio), int(img.height * ratio)), Image.LANCZOS)
    x = (r.width - w) // 2
    y = r.height - h
    return r.crop((x, y, x + w, y + h))


def cover_image_manual(img, w, h, offset):
    ratio = max(w / img.width, h / img.height)
    r = img.resize((int(img.width * ratio), int(img.height * ratio)), Image.LANCZOS)
    x = (r.width - w) // 2
    max_y = r.height - h
    y = int((offset / 1000) * max_y) if max_y > 0 else 0
    return r.crop((x, y, x + w, y + h))


def cover_image_left(img, w, h):
    ratio = max(w / img.width, h / img.height)
    r = img.resize((int(img.width * ratio), int(img.height * ratio)), Image.LANCZOS)
    y = (r.height - h) // 2
    return r.crop((0, y, w, y + h))


def cover_image_right(img, w, h):
    ratio = max(w / img.width, h / img.height)
    r = img.resize((int(img.width * ratio), int(img.height * ratio)), Image.LANCZOS)
    y = (r.height - h) // 2
    x = r.width - w
    return r.crop((x, y, x + w, y + h))


def cover_image_manual_x(img, w, h, offset):
    ratio = max(w / img.width, h / img.height)
    r = img.resize((int(img.width * ratio), int(img.height * ratio)), Image.LANCZOS)
    y = (r.height - h) // 2
    max_x = r.width - w
    x = max(0, min(max_x, int((offset / 1000) * max_x))) if max_x > 0 else 0
    return r.crop((x, y, x + w, y + h))


def apply_rounded_corners(img, radius):
    mask = Image.new('L', img.size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle((0, 0, img.width, img.height), radius=radius, fill=255)
    out = Image.new('RGBA', img.size, (0, 0, 0, 0))
    out.paste(img, (0, 0), mask)
    return out


def apply_rounded_mask(img, radius):
    mask = Image.new('L', img.size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle((2, 2, img.width - 2, img.height - 2), radius=radius - 2, fill=255)
    out = Image.new('RGBA', img.size, (0, 0, 0, 0))
    out.paste(img, (0, 0), mask)
    return out


def apply_footer_logo(base, logo, cfg):
    f = cfg['footer']
    scale = f['logo_height'] / logo.height
    logo = logo.resize((int(logo.width * scale), f['logo_height']), Image.LANCZOS)
    if 'max_width' in f and logo.width > f['max_width']:
        scale = f['max_width'] / logo.width
        logo = logo.resize((f['max_width'], int(logo.height * scale)), Image.LANCZOS)
    y = base.height - f['height'] + (f['height'] - logo.height) // 2
    base.paste(logo, (f['logo_margin'], y), logo)


def apply_header_logo(base, logo, cfg):
    h = cfg['header_logo']
    scale = h['height'] / logo.height
    logo = logo.resize((int(logo.width * scale), h['height']), Image.LANCZOS)
    if logo.width > h['max_width']:
        scale = h['max_width'] / logo.width
        logo = logo.resize((h['max_width'], int(logo.height * scale)), Image.LANCZOS)
    x = h['left_margin']
    y = h['top_margin'] + (h['height'] - logo.height) // 2
    base.paste(logo, (x, y), logo)


def apply_top_center_logo(base, logo, cfg):
    h = cfg['header_logo']
    if logo.height > h['max_height']:
        scale = h['max_height'] / logo.height
        logo = logo.resize((int(logo.width * scale), h['max_height']), Image.LANCZOS)
    if 'max_width' in h and logo.width > h['max_width']:
        scale = h['max_width'] / logo.width
        logo = logo.resize((h['max_width'], int(logo.height * scale)), Image.LANCZOS)
    x = (base.width - logo.width) // 2
    y = h['top_margin'] + (h['max_height'] - logo.height) // 2
    base.paste(logo, (x, y), logo)


def draw_bottom_logo_panel(base, logo, panel_cfg):
    max_h = panel_cfg['logo_max_height']
    max_w = panel_cfg.get('logo_max_width', 9999)
    scale = min(max_h / logo.height, max_w / logo.width, 1)
    logo = logo.resize((int(logo.width * scale), int(logo.height * scale)), Image.LANCZOS)
    padding = panel_cfg['padding']
    outline_w = panel_cfg['outline_width']
    extra_w, extra_h, radius = 40, 18, 22
    inner_w = logo.width + padding * 2 + extra_w
    inner_h = logo.height + padding * 2 + extra_h
    outer_w = inner_w + outline_w * 2
    outer_h = inner_h + outline_w * 2
    outer = Image.new('RGBA', (outer_w, outer_h), (0, 0, 0, 0))
    d = ImageDraw.Draw(outer)
    oc = panel_cfg['outline_color']
    d.rectangle((0, radius, outer_w, outer_h), fill=oc)
    d.rectangle((radius, 0, outer_w - radius, radius), fill=oc)
    d.pieslice((0, 0, radius * 2, radius * 2), 180, 270, fill=oc)
    d.pieslice((outer_w - radius * 2, 0, outer_w, radius * 2), 270, 360, fill=oc)
    inner = Image.new('RGBA', (inner_w, inner_h), (0, 0, 0, 0))
    d = ImageDraw.Draw(inner)
    bc = panel_cfg['bg_color']
    d.rectangle((0, radius, inner_w, inner_h), fill=bc)
    d.rectangle((radius, 0, inner_w - radius, radius), fill=bc)
    d.pieslice((0, 0, radius * 2, radius * 2), 180, 270, fill=bc)
    d.pieslice((inner_w - radius * 2, 0, inner_w, radius * 2), 270, 360, fill=bc)
    outer.paste(inner, (outline_w, outline_w), inner)
    outer.paste(logo, ((outer_w - logo.width) // 2, (outer_h - logo.height) // 2), logo)
    base.paste(outer, ((base.width - outer_w) // 2, base.height - outer_h), outer)


def paste_corner(base, logo, corner, margin):
    if corner == 'top-left':
        x, y = margin, margin
    elif corner == 'top-right':
        x, y = base.width - logo.width - margin, margin
    elif corner == 'bottom-left':
        x, y = margin, base.height - logo.height - margin
    else:
        x, y = base.width - logo.width - margin, base.height - logo.height - margin
    base.paste(logo, (x, y), logo)


def render_card(template_name, poster_image=None, logo_image=None, crop_mode='center', crop_offset=0, poster_orientation='vertical', nfc_logo_color='white', nfc_corner='top-right', system_corner='bottom-left'):
    cfg = TEMPLATES[template_name]
    mode = cfg.get('mode')

    def crop(img, w, h):
        if poster_orientation == 'horizontal':
            if crop_mode == 'top':
                return cover_image_left(img, w, h)
            if crop_mode == 'bottom':
                return cover_image_right(img, w, h)
            if crop_mode == 'manual':
                return cover_image_manual_x(img, w, h, crop_offset)
            return cover_image(img, w, h)
        if crop_mode == 'top':
            return cover_image_top(img, w, h)
        if crop_mode == 'bottom':
            return cover_image_bottom(img, w, h)
        if crop_mode == 'manual':
            return cover_image_manual(img, w, h, crop_offset)
        return cover_image(img, w, h)

    if mode == 'layered-dual-corner':
        template_img = load_image_from_file(resource_path(cfg['image_path']))
        base = Image.new('RGBA', template_img.size, (0, 0, 0, 0))
        if poster_image:
            pad = 3
            poster = crop(poster_image, base.width - pad * 2, base.height - pad * 2)
            poster = apply_rounded_corners(poster, cfg.get('corner_radius', 22) - pad)
            base.paste(poster, (pad, pad), poster)
        base.paste(template_img, (0, 0), template_img)
        nls_file = 'templates/nls_white.png' if nfc_logo_color == 'white' else 'templates/nls_black.png'
        if os.path.exists(resource_path(nls_file)):
            nls_logo = load_image_from_file(resource_path(nls_file))
            nls_cfg = cfg['nls']
            scale = min(nls_cfg['max_width'] / nls_logo.width, nls_cfg['max_height'] / nls_logo.height, 1)
            nls_logo = nls_logo.resize((int(nls_logo.width * scale), int(nls_logo.height * scale)), Image.LANCZOS)
            paste_corner(base, nls_logo, nfc_corner, nls_cfg['margin'])
        if logo_image:
            sys_logo = logo_image.copy()
            sys_cfg = cfg['system_logo']
            scale = min(sys_cfg['max_width'] / sys_logo.width, sys_cfg['max_height'] / sys_logo.height, 1)
            sys_logo = sys_logo.resize((int(sys_logo.width * scale), int(sys_logo.height * scale)), Image.LANCZOS)
            paste_corner(base, sys_logo, system_corner, sys_cfg['margin'])
        return base

    if mode == 'full-poster-bottom-panel':
        w, h = cfg['size']['w'], cfg['size']['h']
        poster = crop(poster_image, w, h) if poster_image else Image.new('RGBA', (w, h), (0, 0, 0, 0))
        poster = apply_rounded_corners(poster, cfg.get('corner_radius', 24))
        if logo_image:
            draw_bottom_logo_panel(poster, logo_image, cfg['panel'])
        return apply_rounded_corners(poster, cfg.get('corner_radius', 24))

    if mode == 'full-poster-rounded':
        if not poster_image:
            w, h = cfg['size']['w'], cfg['size']['h']
            return Image.new('RGBA', (w, h), (0, 0, 0, 0))
        poster = crop(poster_image, cfg['size']['w'], cfg['size']['h'])
        return apply_rounded_corners(poster, cfg.get('corner_radius', 24))

    template_img = load_image_from_file(resource_path(cfg['image_path']))

    if mode == 'layered':
        base = Image.new('RGBA', template_img.size, (0, 0, 0, 0))
        if poster_image:
            visible_h = template_img.height - cfg['poster_y']
            poster = crop(poster_image, CLEAR_W, visible_h)
            x = (template_img.width - CLEAR_W) // 2
            base.paste(poster, (x, cfg['poster_y']), poster)
        base.paste(template_img, (0, 0), template_img)
        base = apply_rounded_mask(base, radius=22)
        if logo_image:
            apply_header_logo(base, logo_image, cfg)
        return base

    if mode == 'framed-top-logo':
        base = template_img.copy()
        if poster_image:
            poster = crop(poster_image, T4_POSTER_W, T4_POSTER_H)
            x = (base.width - T4_POSTER_W) // 2
            base.paste(poster, (x, T4_POSTER_Y), poster)
        if logo_image:
            apply_top_center_logo(base, logo_image, cfg)
        return base

    base = template_img.copy()
    if logo_image:
        apply_footer_logo(base, logo_image, cfg)
    if poster_image:
        c = cfg['center']
        poster = crop(poster_image, c['w'], c['h'])
        base.paste(poster, (c['x'], c['y']), poster)
    return base


def flatten_visible_artwork_keep_outer_transparency(img):
    """Return a PNG-safe RGBA image for Silhouette-style imports.

    The rendered card can contain semi-transparent pixels from pasted logos or
    artwork inside the visible card area. Some design/cutting apps can preview
    those pixels as white seams. This keeps the original outer rounded-corner
    transparency, but makes all non-edge-connected pixels fully opaque so the
    visible artwork is flattened.
    """
    img = img.convert('RGBA')
    w, h = img.size
    alpha = img.getchannel('A')
    alpha_px = alpha.load()

    # Track alpha pixels that are connected to the canvas edge. Those are the
    # real outside/corner transparency pixels that must remain for rounded cuts.
    outer = bytearray(w * h)
    queue = []

    def add_if_outer(x, y):
        i = y * w + x
        if not outer[i] and alpha_px[x, y] < 255:
            outer[i] = 1
            queue.append((x, y))

    for x in range(w):
        add_if_outer(x, 0)
        add_if_outer(x, h - 1)
    for y in range(h):
        add_if_outer(0, y)
        add_if_outer(w - 1, y)

    head = 0
    while head < len(queue):
        x, y = queue[head]
        head += 1
        if x > 0:
            add_if_outer(x - 1, y)
        if x < w - 1:
            add_if_outer(x + 1, y)
        if y > 0:
            add_if_outer(x, y - 1)
        if y < h - 1:
            add_if_outer(x, y + 1)

    new_alpha = Image.new('L', (w, h), 255)
    new_alpha_px = new_alpha.load()
    for y in range(h):
        row = y * w
        for x in range(w):
            if outer[row + x]:
                new_alpha_px[x, y] = alpha_px[x, y]

    out = img.copy()
    out.putalpha(new_alpha)
    return out


def render_nfc_print_sheet(slots, show_cutlines=False):
    page_w, page_h = 2480, 3508
    page = Image.new('RGB', (page_w, page_h), 'white')

    def mm_to_px(mm):
        return round((mm / 25.4) * 300)

    card_w, card_h = mm_to_px(52.41), mm_to_px(84.16)

    # Cards are rotated on the sheet, so their placed size is swapped.
    placed_w, placed_h = card_h, card_w

    cols, rows = 2, 5
    slot_count = cols * rows

    margin_x = 90
    margin_y = 120

    available_w = page_w - margin_x * 2
    available_h = page_h - margin_y * 2

    gap_x = max(0, (available_w - (cols * placed_w)) // (cols - 1))
    gap_y = max(0, (available_h - (rows * placed_h)) // (rows - 1))

    grid_w = cols * placed_w + (cols - 1) * gap_x
    grid_h = rows * placed_h + (rows - 1) * gap_y

    start_x = (page_w - grid_w) // 2
    start_y = (page_h - grid_h) // 2

    draw = ImageDraw.Draw(page)

    for i in range(min(slot_count, len(slots))):
        img = slots[i]

        row, col = i // cols, i % cols
        x = start_x + col * (placed_w + gap_x)
        y = start_y + row * (placed_h + gap_y)

        if img is not None:
            card = (
                img.convert('RGBA')
                .resize((card_w, card_h), Image.LANCZOS)
                .rotate(-90, expand=True)
            )
            page.paste(card, (x, y), card)

        if show_cutlines:
            draw.rectangle(
                (x, y, x + placed_w - 1, y + placed_h - 1),
                outline=(0, 0, 0),
                width=2,
            )

    return page
