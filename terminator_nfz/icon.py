"""Ikona programu rysowana w kodzie (bez plików binarnych w repozytorium)."""


def make_icon_image(size=256):
    """Czerwony krzyż na białym kółku z czerwoną obwódką."""
    from PIL import Image, ImageDraw

    red = (211, 47, 47, 255)
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    border = max(size // 16, 1)
    draw.ellipse((border, border, size - border - 1, size - border - 1), fill="white", outline=red, width=border * 2)
    arm, length = size * 18 // 100, size * 58 // 100
    lo, hi = (size - arm) // 2, (size + arm) // 2
    start, end = (size - length) // 2, (size + length) // 2
    draw.rectangle((lo, start, hi, end), fill=red)
    draw.rectangle((start, lo, end, hi), fill=red)
    return img


def save_ico(path):
    make_icon_image().save(path, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
