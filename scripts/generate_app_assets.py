import os
import math
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_ICONS_DIR = BASE_DIR / "static" / "img" / "icons"
PLAY_STORE_ASSETS_DIR = BASE_DIR / "play_store" / "assets"
ANDROID_RES_DIR = BASE_DIR / "android" / "app" / "src" / "main" / "res"

for d in [STATIC_ICONS_DIR, PLAY_STORE_ASSETS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

for dpi, size in [
    ("mipmap-mdpi", 48),
    ("mipmap-hdpi", 72),
    ("mipmap-xhdpi", 96),
    ("mipmap-xxhdpi", 144),
    ("mipmap-xxxhdpi", 192),
]:
    (ANDROID_RES_DIR / dpi).mkdir(parents=True, exist_ok=True)

def create_app_icon(size=512, is_maskable=False):
    """Generates modern DigiCampus SmartVision icon."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    pad = 0 if is_maskable else int(size * 0.04)
    radius = int(size * 0.22) if not is_maskable else 0

    # Background gradient approximation (Coral Red #ff4d4f to Crimson #e02424)
    for y in range(pad, size - pad):
        factor = (y - pad) / max(1, (size - 2 * pad))
        r = int(255 - factor * 35)
        g = int(77 - factor * 41)
        b = int(79 - factor * 43)
        draw.line([(pad, y), (size - pad, y)], fill=(r, g, b, 255))

    # Mask corners if not maskable
    if not is_maskable:
        mask = Image.new("L", (size, size), 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.rounded_rectangle([pad, pad, size - pad, size - pad], radius=radius, fill=255)
        img.putalpha(mask)

    draw = ImageDraw.Draw(img)
    cx, cy = size // 2, size // 2

    # Draw Biometric Corner Brackets (White)
    bracket_size = int(size * 0.28)
    bracket_thick = max(3, int(size * 0.032))
    corner_arm = int(size * 0.08)

    # Top-Left Bracket
    draw.line([(cx - bracket_size, cy - bracket_size), (cx - bracket_size + corner_arm, cy - bracket_size)], fill=(255, 255, 255, 240), width=bracket_thick)
    draw.line([(cx - bracket_size, cy - bracket_size), (cx - bracket_size, cy - bracket_size + corner_arm)], fill=(255, 255, 255, 240), width=bracket_thick)

    # Top-Right Bracket
    draw.line([(cx + bracket_size, cy - bracket_size), (cx + bracket_size - corner_arm, cy - bracket_size)], fill=(255, 255, 255, 240), width=bracket_thick)
    draw.line([(cx + bracket_size, cy - bracket_size), (cx + bracket_size, cy - bracket_size + corner_arm)], fill=(255, 255, 255, 240), width=bracket_thick)

    # Bottom-Left Bracket
    draw.line([(cx - bracket_size, cy + bracket_size), (cx - bracket_size + corner_arm, cy + bracket_size)], fill=(255, 255, 255, 240), width=bracket_thick)
    draw.line([(cx - bracket_size, cy + bracket_size), (cx - bracket_size, cy + bracket_size - corner_arm)], fill=(255, 255, 255, 240), width=bracket_thick)

    # Bottom-Right Bracket
    draw.line([(cx + bracket_size, cy + bracket_size), (cx + bracket_size - corner_arm, cy + bracket_size)], fill=(255, 255, 255, 240), width=bracket_thick)
    draw.line([(cx + bracket_size, cy + bracket_size), (cx + bracket_size, cy + bracket_size - corner_arm)], fill=(255, 255, 255, 240), width=bracket_thick)

    # Center Camera Lens / Biometric Pupil (Outer Ring)
    lens_radius = int(size * 0.16)
    draw.ellipse([cx - lens_radius, cy - lens_radius, cx + lens_radius, cy + lens_radius], outline=(255, 255, 255, 255), width=max(3, int(size * 0.026)))

    # Inner Aperture Dot
    inner_dot = int(size * 0.07)
    draw.ellipse([cx - inner_dot, cy - inner_dot, cx + inner_dot, cy + inner_dot], fill=(255, 255, 255, 255))

    # Small Reflection glint
    glint_x, glint_y = cx + int(lens_radius * 0.45), cy - int(lens_radius * 0.45)
    glint_r = max(2, int(size * 0.022))
    draw.ellipse([glint_x - glint_r, glint_y - glint_r, glint_x + glint_r, glint_y + glint_r], fill=(255, 255, 255, 200))

    # Top Mini Academic Star / Badge
    star_y = cy - int(bracket_size * 1.05)
    star_r = max(2, int(size * 0.025))
    draw.ellipse([cx - star_r, star_y - star_r, cx + star_r, star_y + star_r], fill=(255, 255, 255, 220))

    return img

def create_feature_graphic():
    """Generates Google Play Store 1024x500 Feature Graphic."""
    w, h = 1024, 500
    img = Image.new("RGB", (w, h), (15, 23, 42)) # Deep Slate #0f172a
    draw = ImageDraw.Draw(img)

    # Background gradient & subtle geometric circles
    for x in range(w):
        factor = x / w
        r = int(15 + factor * 25)
        g = int(23 + factor * 10)
        b = int(42 + factor * 15)
        draw.line([(x, 0), (x, h)], fill=(r, g, b))

    # Diagonal accent glow (Coral Red)
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ov_draw = ImageDraw.Draw(overlay)
    ov_draw.polygon([(0, 0), (320, 0), (180, h), (0, h)], fill=(255, 77, 79, 35))
    ov_draw.ellipse([w - 400, -100, w + 200, 450], fill=(255, 77, 79, 25))
    img.paste(Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB"))

    draw = ImageDraw.Draw(img)

    # Left Section: Typography & Branding
    # Try default font or clean fallbacks
    try:
        font_large = ImageFont.truetype("arialbd.ttf", 46)
        font_sub = ImageFont.truetype("arialbd.ttf", 24)
        font_body = ImageFont.truetype("arial.ttf", 18)
        font_badge = ImageFont.truetype("arialbd.ttf", 14)
    except Exception:
        font_large = ImageFont.load_default()
        font_sub = font_large
        font_body = font_large
        font_badge = font_large

    # Pill badge "OFFICIAL JIET IDEA LAB ERP"
    draw.rounded_rectangle([60, 60, 310, 92], radius=16, fill=(255, 77, 79, 45), outline=(255, 77, 79))
    draw.text((78, 68), "JIET IDEA LAB ACADEMICS", fill=(255, 255, 255), font=font_badge)

    draw.text((60, 115), "SmartVision AI", fill=(255, 255, 255), font=font_large)
    draw.text((60, 175), "DigiCampus Attendance Portal", fill=(255, 77, 79), font=font_sub)

    desc_lines = [
        "• Edge AI Contactless Facial Recognition",
        "• 2-Slot Lab Schedule & 50% Threshold Tracking",
        "• Full DigiCampus Academic Course Overview",
        "• 100% DPDP & GDPR Biometric Privacy Protected"
    ]
    y_text = 230
    for line in desc_lines:
        draw.text((60, y_text), line, fill=(203, 213, 225), font=font_body)
        y_text += 32

    # Draw Play Store CTA Badge
    draw.rounded_rectangle([60, 390, 240, 440], radius=12, fill=(255, 77, 79))
    draw.text((85, 404), "OFFICIAL APP", fill=(255, 255, 255), font=font_sub)

    # Right Section: Stylized Phone Card Mockup
    mock_x, mock_y = 660, 50
    mock_w, mock_h = 300, 400

    # Phone outline with shadow
    draw.rounded_rectangle([mock_x + 5, mock_y + 5, mock_x + mock_w + 5, mock_y + mock_h + 5], radius=24, fill=(10, 15, 25))
    draw.rounded_rectangle([mock_x, mock_y, mock_x + mock_w, mock_y + mock_h], radius=24, fill=(255, 255, 255))

    # Top red header bar on phone
    draw.rounded_rectangle([mock_x, mock_y, mock_x + mock_w, mock_y + 70], radius=24, fill=(255, 77, 79))
    draw.rectangle([mock_x, mock_y + 40, mock_x + mock_w, mock_y + 70], fill=(255, 77, 79))
    draw.text((mock_x + 20, mock_y + 24), "< Exploratory Project", fill=(255, 255, 255), font=font_sub)

    # Component attendance card on phone
    card_y = mock_y + 85
    draw.rounded_rectangle([mock_x + 15, card_y, mock_x + mock_w - 15, card_y + 110], radius=16, fill=(255, 245, 245), outline=(254, 226, 226))
    draw.text((mock_x + 30, card_y + 15), "Component attendance (i)", fill=(100, 116, 139), font=font_badge)
    draw.text((mock_x + 30, card_y + 35), "100%", fill=(255, 77, 79), font=font_large)
    draw.text((mock_x + 30, card_y + 85), "12 of 12 attended", fill=(100, 116, 139), font=font_badge)

    # Mini circular gauge
    draw.ellipse([mock_x + mock_w - 65, card_y + 35, mock_x + mock_w - 25, card_y + 75], outline=(255, 77, 79), width=3)
    draw.text((mock_x + mock_w - 52, card_y + 42), "✓", fill=(255, 77, 79), font=font_sub)

    # Filter pill
    draw.rounded_rectangle([mock_x + 15, card_y + 125, mock_x + 150, card_y + 155], radius=14, outline=(34, 197, 94), width=2, fill=(255, 255, 255))
    draw.text((mock_x + 28, card_y + 132), "PRESENT (P)  12", fill=(22, 163, 74), font=font_badge)

    # Mini session items
    item1_y = card_y + 170
    draw.rounded_rectangle([mock_x + 15, item1_y, mock_x + mock_w - 15, item1_y + 50], radius=10, fill=(255, 255, 255), outline=(241, 245, 249))
    draw.rectangle([mock_x + 15, item1_y, mock_x + 20, item1_y + 50], fill=(34, 197, 94))
    draw.text((mock_x + 28, item1_y + 10), "16 Nov, 02:10 PM", fill=(15, 23, 42), font=font_badge)
    draw.text((mock_x + 28, item1_y + 28), "Slot 2 (AI Verified)", fill=(100, 116, 139), font=font_badge)

    item2_y = card_y + 230
    draw.rounded_rectangle([mock_x + 15, item2_y, mock_x + mock_w - 15, item2_y + 50], radius=10, fill=(255, 255, 255), outline=(241, 245, 249))
    draw.rectangle([mock_x + 15, item2_y, mock_x + 20, item2_y + 50], fill=(34, 197, 94))
    draw.text((mock_x + 28, item2_y + 10), "16 Nov, 01:20 PM", fill=(15, 23, 42), font=font_badge)
    draw.text((mock_x + 28, item2_y + 28), "Slot 1 (AI Verified)", fill=(100, 116, 139), font=font_badge)

    return img

print("Generating PWA Icons...")
icon_512 = create_app_icon(512, is_maskable=False)
icon_512.save(STATIC_ICONS_DIR / "icon-512.png")
icon_512.save(PLAY_STORE_ASSETS_DIR / "app_icon_512.png")

icon_192 = create_app_icon(192, is_maskable=False)
icon_192.save(STATIC_ICONS_DIR / "icon-192.png")

icon_maskable = create_app_icon(512, is_maskable=True)
icon_maskable.save(STATIC_ICONS_DIR / "icon-maskable.png")

# Android mipmap densities
for dpi, size in [
    ("mipmap-mdpi", 48),
    ("mipmap-hdpi", 72),
    ("mipmap-xhdpi", 96),
    ("mipmap-xxhdpi", 144),
    ("mipmap-xxxhdpi", 192),
]:
    d_icon = create_app_icon(size, is_maskable=False)
    d_icon.save(ANDROID_RES_DIR / dpi / "ic_launcher.png")
    d_icon.save(ANDROID_RES_DIR / dpi / "ic_launcher_round.png")

print("Generating Play Store Feature Graphic (1024x500)...")
feature_img = create_feature_graphic()
feature_img.save(PLAY_STORE_ASSETS_DIR / "feature_graphic_1024x500.png")
print("Assets generated successfully!")
