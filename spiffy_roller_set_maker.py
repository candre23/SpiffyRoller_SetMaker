from __future__ import annotations

import copy
import io
import json
import math
import re
import shutil
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import tkinter as tk
from tkinter import colorchooser, filedialog, messagebox, simpledialog, ttk

from PIL import Image, ImageColor, ImageDraw, ImageOps, ImageTk


APP_TITLE = "Spiffy Roller Set Maker"
APP_VERSION = "1.0"
GRID_SIZE = 48
PIXEL_ZOOM = 10
CANVAS_SIZE = GRID_SIZE * PIXEL_ZOOM
MAX_PALETTE_COLORS = 15

SHAPE_CHOICES = (
    "d4",
    "d6",
    "d8",
    "d10",
    "d12",
    "d20",
    "circle",
    "polygon",
)

MODE_CHOICES = ("1-bit mask", "4-bit indexed")
POLARITY_CHOICES = (
    "Black ink on white / light background",
    "White ink on black / dark background",
    "Alpha only",
)

FACE_DISPLAY_CHOICES = ("label", "value", "image", "blank")


DEFAULT_RULES_SCRIPT = r"""-- Spiffy Roller portable rule script
-- The roller calls resolve(roll, options).
-- roll.dice contains die_id, die_name, face_index, label, value, and symbols.
-- Return { title = "...", lines = {...}, actions = {...} }.

function resolve(roll, options)
    local total = 0
    for _, die in ipairs(roll.dice) do
        if die.value ~= nil then
            total = total + die.value
        end
    end
    return { title = "Total: " .. tostring(total), lines = {} }
end
"""


def slugify(value: str, fallback: str = "dice_set") -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    value = value.strip("_")
    return value or fallback


def normalize_hex(value: str, fallback: str) -> str:
    try:
        rgb = ImageColor.getrgb(value.strip())
        return "#{:02X}{:02X}{:02X}".format(*rgb[:3])
    except Exception:
        return fallback


def parse_optional_int(value: str) -> int | None:
    value = value.strip()
    if not value:
        return None
    return int(value)


def color_tuple(value: str, fallback: str = "#FFFFFF") -> tuple[int, int, int]:
    normalized = normalize_hex(value, fallback)
    return ImageColor.getrgb(normalized)


def blend_hex(color_a: str, color_b: str, amount: float) -> str:
    amount = max(0.0, min(1.0, amount))
    ar, ag, ab = color_tuple(color_a, "#FFFFFF")
    br, bg, bb = color_tuple(color_b, "#FFFFFF")
    rr = round(ar * (1.0 - amount) + br * amount)
    rg = round(ag * (1.0 - amount) + bg * amount)
    rb = round(ab * (1.0 - amount) + bb * amount)
    return f"#{rr:02X}{rg:02X}{rb:02X}"


def checker_colors(tint: str) -> tuple[str, str]:
    normalized = normalize_hex(tint, "#D8D8D8")
    return (
        blend_hex("#FFFFFF", normalized, 0.30),
        blend_hex("#C8C8C8", normalized, 0.30),
    )


def regular_polygon_points(
    sides: int,
    cx: float,
    cy: float,
    radius: float,
    rotation_degrees: float = -90.0,
) -> list[tuple[float, float]]:
    return [
        (
            cx + math.cos(math.radians(rotation_degrees + index * 360 / sides)) * radius,
            cy + math.sin(math.radians(rotation_degrees + index * 360 / sides)) * radius,
        )
        for index in range(sides)
    ]


def create_d20_icon(size: int) -> Image.Image:
    """Create the application icon without requiring a separate asset file."""
    scale = size / 64.0
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    cx = (size - 1) / 2
    cy = (size - 1) / 2
    radius = 27 * scale
    outer = regular_polygon_points(6, cx, cy, radius, -90)

    fill = "#294C78"
    outline = "#15263C"
    facet = "#DDEBFA"
    outer_width = max(1, round(3 * scale))
    facet_width = max(1, round(2 * scale))

    draw.polygon(outer, fill=fill, outline=outline)
    draw.line(outer + [outer[0]], fill=outline, width=outer_width, joint="curve")

    top, upper_right, lower_right, bottom, lower_left, upper_left = outer
    center = (cx, cy)
    inner_top = (cx, cy - 9 * scale)
    inner_bottom = (cx, cy + 9 * scale)

    for point in (top, upper_right, lower_right, bottom, lower_left, upper_left):
        draw.line((point, center), fill=facet, width=facet_width)
    draw.line((upper_left, inner_top, upper_right), fill=facet, width=facet_width)
    draw.line((lower_left, inner_bottom, lower_right), fill=facet, width=facet_width)

    return image


@dataclass
class LayerData:
    pixels: list[list[int]] = field(
        default_factory=lambda: [[-1 for _ in range(GRID_SIZE)] for _ in range(GRID_SIZE)]
    )
    source_path: str = ""
    source_image: Image.Image | None = None
    scale_percent: float = 100.0
    offset_x: int = 0
    offset_y: int = 0
    gamma: float = 1.0
    threshold: int = 128
    polarity: str = "Black ink on white / light background"

    def clone(self) -> "LayerData":
        copied = copy.deepcopy(self)
        if self.source_image is not None:
            copied.source_image = self.source_image.copy()
        return copied

    def clear(self) -> None:
        self.pixels = [[-1 for _ in range(GRID_SIZE)] for _ in range(GRID_SIZE)]
        self.source_path = ""
        self.source_image = None
        self.scale_percent = 100.0
        self.offset_x = 0
        self.offset_y = 0
        self.gamma = 1.0
        self.threshold = 128
        self.polarity = "Black ink on white / light background"


@dataclass
class IconData:
    mode: str = "1-bit mask"
    palette: list[str] = field(default_factory=lambda: ["#000000"] + ["#808080"] * 14)
    checker_tint: str = "#D8D8D8"
    layers: list[LayerData] = field(default_factory=lambda: [LayerData() for _ in range(4)])
    active_layer: int = 0

    def ensure_layers(self) -> None:
        while len(self.layers) < 4:
            self.layers.append(LayerData())
        if len(self.layers) > 4:
            self.layers = self.layers[:4]
        self.active_layer = max(0, min(len(self.layers) - 1, self.active_layer))

    @property
    def polarity(self) -> str:
        self.ensure_layers()
        return self.layers[self.active_layer].polarity

    @polarity.setter
    def polarity(self, value: str) -> None:
        self.ensure_layers()
        self.layers[self.active_layer].polarity = value

    @property
    def source_path(self) -> str:
        self.ensure_layers()
        return self.layers[self.active_layer].source_path

    @source_path.setter
    def source_path(self, value: str) -> None:
        self.ensure_layers()
        self.layers[self.active_layer].source_path = value

    @property
    def source_image(self) -> Image.Image | None:
        self.ensure_layers()
        return self.layers[self.active_layer].source_image

    @source_image.setter
    def source_image(self, value: Image.Image | None) -> None:
        self.ensure_layers()
        self.layers[self.active_layer].source_image = value

    @property
    def scale_percent(self) -> float:
        self.ensure_layers()
        return self.layers[self.active_layer].scale_percent

    @scale_percent.setter
    def scale_percent(self, value: float) -> None:
        self.ensure_layers()
        self.layers[self.active_layer].scale_percent = value

    @property
    def offset_x(self) -> int:
        self.ensure_layers()
        return self.layers[self.active_layer].offset_x

    @offset_x.setter
    def offset_x(self, value: int) -> None:
        self.ensure_layers()
        self.layers[self.active_layer].offset_x = value

    @property
    def offset_y(self) -> int:
        self.ensure_layers()
        return self.layers[self.active_layer].offset_y

    @offset_y.setter
    def offset_y(self, value: int) -> None:
        self.ensure_layers()
        self.layers[self.active_layer].offset_y = value

    @property
    def gamma(self) -> float:
        self.ensure_layers()
        return self.layers[self.active_layer].gamma

    @gamma.setter
    def gamma(self, value: float) -> None:
        self.ensure_layers()
        self.layers[self.active_layer].gamma = value

    @property
    def threshold(self) -> int:
        self.ensure_layers()
        return self.layers[self.active_layer].threshold

    @threshold.setter
    def threshold(self, value: int) -> None:
        self.ensure_layers()
        self.layers[self.active_layer].threshold = value

    @property
    def pixels(self) -> list[list[int]]:
        self.ensure_layers()
        return self.layers[self.active_layer].pixels

    @pixels.setter
    def pixels(self, value: list[list[int]]) -> None:
        self.ensure_layers()
        self.layers[self.active_layer].pixels = value

    def clone(self) -> "IconData":
        copied = copy.deepcopy(self)
        copied.layers = [layer.clone() for layer in self.layers]
        return copied

    def clear(self) -> None:
        self.ensure_layers()
        for layer in self.layers:
            layer.clear()
        self.active_layer = 0

    def composite_pixels(self) -> list[list[int]]:
        self.ensure_layers()
        result = [[-1 for _ in range(GRID_SIZE)] for _ in range(GRID_SIZE)]
        for layer_index in range(len(self.layers) - 1, -1, -1):
            layer = self.layers[layer_index]
            for y in range(GRID_SIZE):
                for x in range(GRID_SIZE):
                    value = layer.pixels[y][x]
                    if value >= 0:
                        result[y][x] = value
        return result

    def composite_with_owners(self) -> tuple[list[list[int]], list[list[int]]]:
        self.ensure_layers()
        result = [[-1 for _ in range(GRID_SIZE)] for _ in range(GRID_SIZE)]
        owners = [[-1 for _ in range(GRID_SIZE)] for _ in range(GRID_SIZE)]
        for layer_index in range(len(self.layers) - 1, -1, -1):
            layer = self.layers[layer_index]
            for y in range(GRID_SIZE):
                for x in range(GRID_SIZE):
                    value = layer.pixels[y][x]
                    if value >= 0:
                        result[y][x] = value
                        owners[y][x] = layer_index
        return result, owners

    def has_visible_pixels(self) -> bool:
        composite = self.composite_pixels()
        return any(value >= 0 for row in composite for value in row)

    def signature(self) -> str:
        composite = self.composite_pixels()
        return json.dumps(
            {"mode": self.mode, "palette": self.palette, "pixels": composite},
            separators=(",", ":"),
        )

    def to_indexed_png(self) -> Image.Image:
        image = Image.new("P", (GRID_SIZE, GRID_SIZE), color=0)
        palette_bytes = [0, 0, 0]
        usable = 1 if self.mode == "1-bit mask" else MAX_PALETTE_COLORS
        for index in range(usable):
            rgb = color_tuple(self.palette[index], "#000000")
            palette_bytes.extend(rgb)
        while len(palette_bytes) < 768:
            palette_bytes.extend((0, 0, 0))
        image.putpalette(palette_bytes[:768])
        data: list[int] = []
        for row in self.composite_pixels():
            for value in row:
                data.append(0 if value < 0 else min(value, usable - 1) + 1)
        image.putdata(data)
        image.info["transparency"] = 0
        return image

    def save_png(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        image = self.to_indexed_png()
        bits = 1 if self.mode == "1-bit mask" else 4
        image.save(path, format="PNG", optimize=True, bits=bits, transparency=0)

    @classmethod
    def from_image(cls, path: Path) -> "IconData":
        image = Image.open(path).convert("RGBA")
        icon = cls()
        icon.ensure_layers()
        for layer in icon.layers:
            layer.clear()
        icon.active_layer = 0
        icon.source_path = str(path)
        icon.source_image = image.copy()
        reduced = image.resize((GRID_SIZE, GRID_SIZE), Image.Resampling.LANCZOS)
        colors = reduced.getcolors(maxcolors=GRID_SIZE * GRID_SIZE)
        opaque_colors = [rgba for _, rgba in colors if rgba[3] > 0] if colors else []
        unique_rgb = {rgba[:3] for rgba in opaque_colors}
        icon.mode = "1-bit mask" if len(unique_rgb) <= 1 else "4-bit indexed"
        icon.polarity = "Alpha only"
        icon.threshold = 8
        icon.scale_percent = min(GRID_SIZE / max(1, image.width), GRID_SIZE / max(1, image.height)) * 100.0
        icon.rebuild_from_source()
        return icon

    def rebuild_from_source(self) -> None:
        self.ensure_layers()
        layer = self.layers[self.active_layer]
        if layer.source_image is None:
            return
        source = layer.source_image.convert("RGBA")
        scale = max(0.01, layer.scale_percent / 100.0)
        target_w = max(1, round(source.width * scale))
        target_h = max(1, round(source.height * scale))
        resized = source.resize((target_w, target_h), Image.Resampling.LANCZOS)
        canvas = Image.new("RGBA", (GRID_SIZE, GRID_SIZE), (0, 0, 0, 0))
        x = (GRID_SIZE - target_w) // 2 + layer.offset_x
        y = (GRID_SIZE - target_h) // 2 + layer.offset_y
        canvas.alpha_composite(resized, (x, y))
        rgba = list(canvas.getdata())

        def corrected_luminance(pixel: tuple[int, int, int, int]) -> float:
            r, g, b, _ = pixel
            luminance = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255.0
            gamma = max(0.05, layer.gamma)
            return pow(luminance, 1.0 / gamma) * 255.0

        opaque_mask: list[bool] = []
        for pixel in rgba:
            alpha = pixel[3]
            lum = corrected_luminance(pixel)
            if layer.polarity == "Black ink on white / light background":
                opaque = alpha > 0 and lum <= layer.threshold
            elif layer.polarity == "White ink on black / dark background":
                opaque = alpha > 0 and lum >= layer.threshold
            elif layer.polarity == "Alpha only":
                opaque = alpha >= layer.threshold
            else:
                opaque = alpha > 0 and lum <= layer.threshold
            opaque_mask.append(opaque)

        if self.mode == "1-bit mask":
            output: list[list[int]] = []
            position = 0
            for _y in range(GRID_SIZE):
                row = []
                for _x in range(GRID_SIZE):
                    row.append(0 if opaque_mask[position] else -1)
                    position += 1
                output.append(row)
            layer.pixels = output
            return

        opaque_image = Image.new("RGBA", (GRID_SIZE, GRID_SIZE), (0, 0, 0, 0))
        opaque_pixels = []
        for pixel, opaque in zip(rgba, opaque_mask):
            opaque_pixels.append((pixel[0], pixel[1], pixel[2], 255) if opaque else (0, 0, 0, 0))
        opaque_image.putdata(opaque_pixels)
        rgb_background = Image.new("RGB", (GRID_SIZE, GRID_SIZE), (0, 0, 0))
        rgb_background.paste(opaque_image.convert("RGB"), mask=opaque_image.getchannel("A"))
        quantized = rgb_background.quantize(colors=MAX_PALETTE_COLORS, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
        raw_palette = quantized.getpalette() or []
        used_indices = sorted(set(quantized.getdata()))
        palette: list[str] = []
        remap: dict[int, int] = {}
        for source_index in used_indices[:MAX_PALETTE_COLORS]:
            offset = source_index * 3
            rgb = tuple(raw_palette[offset : offset + 3])
            if len(rgb) != 3:
                rgb = (128, 128, 128)
            remap[source_index] = len(palette)
            palette.append("#{:02X}{:02X}{:02X}".format(*rgb))
        while len(palette) < MAX_PALETTE_COLORS:
            palette.append("#808080")
        self.palette = palette
        quantized_data = list(quantized.getdata())
        output = []
        position = 0
        for _y in range(GRID_SIZE):
            row = []
            for _x in range(GRID_SIZE):
                row.append(-1 if not opaque_mask[position] else remap.get(quantized_data[position], 0))
                position += 1
            output.append(row)
        layer.pixels = output


@dataclass
class FaceData:
    label: str = ""
    value: int | None = None
    display_mode: str = "label"
    image_mode: str = "mask"
    image_path: str = ""
    body_color: str = ""
    ink_color: str = ""
    symbols: dict[str, int] = field(default_factory=dict)
    icon: IconData = field(default_factory=IconData)
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class DieData:
    id: str = "die_1"
    name: str = "Die 1"
    sides: int = 6
    shape: str = "d6"
    polygon_sides: int = 6
    body_color: str = "#294C78"
    ink_color: str = "#FFFFFF"
    faces: list[FaceData] = field(default_factory=lambda: [FaceData(label=str(i), value=i) for i in range(1, 7)])
    extra: dict[str, Any] = field(default_factory=dict)

    def resize_faces(self, sides: int) -> None:
        sides = max(1, min(100, int(sides)))
        while len(self.faces) < sides:
            index = len(self.faces) + 1
            self.faces.append(FaceData(label=str(index), value=index))
        if len(self.faces) > sides:
            self.faces = self.faces[:sides]
        self.sides = sides


@dataclass
class SetData:
    id: str = "new_dice_set"
    name: str = "New Dice Set"
    dice: list[DieData] = field(default_factory=lambda: [DieData()])
    rules_text: str = json.dumps(
        {
            "format": "spiffy-roller-rules",
            "format_version": 2,
            "engine": "lua",
            "script": "rules.lua",
            "entry": "resolve",
            "action_entry": "perform_action",
            "limits": {"instructions": 50000, "memory_kb": 96},
        },
        indent=2,
    )
    rules_script: str = DEFAULT_RULES_SCRIPT
    extra: dict[str, Any] = field(default_factory=dict)


PROJECT_FORMAT = "spiffy-roller-set-project"
PROJECT_VERSION = 1


def _layer_to_project_dict(
    layer: LayerData,
    source_ref: str,
) -> dict[str, Any]:
    return {
        "pixels": layer.pixels,
        "source_ref": source_ref,
        "source_name": Path(layer.source_path).name if layer.source_path else "",
        "scale_percent": layer.scale_percent,
        "offset_x": layer.offset_x,
        "offset_y": layer.offset_y,
        "gamma": layer.gamma,
        "threshold": layer.threshold,
        "polarity": layer.polarity,
    }


def _icon_to_project_dict(
    icon: IconData,
    archive: zipfile.ZipFile,
    die_index: int,
    face_index: int,
) -> dict[str, Any]:
    icon.ensure_layers()
    layers = []
    for layer_index, layer in enumerate(icon.layers):
        source_ref = ""
        if layer.source_image is not None:
            source_ref = (
                f"sources/die_{die_index + 1}/"
                f"face_{face_index + 1}/layer_{layer_index + 1}.png"
            )
            buffer = io.BytesIO()
            layer.source_image.convert("RGBA").save(buffer, format="PNG")
            archive.writestr(source_ref, buffer.getvalue())
        layers.append(_layer_to_project_dict(layer, source_ref))

    return {
        "mode": icon.mode,
        "palette": icon.palette,
        "checker_tint": icon.checker_tint,
        "active_layer": icon.active_layer,
        "layers": layers,
    }


def _face_to_project_dict(
    face: FaceData,
    archive: zipfile.ZipFile,
    die_index: int,
    face_index: int,
) -> dict[str, Any]:
    return {
        "label": face.label,
        "value": face.value,
        "display_mode": face.display_mode,
        "image_mode": face.image_mode,
        "image_path": face.image_path,
        "body_color": face.body_color,
        "ink_color": face.ink_color,
        "symbols": face.symbols,
        "extra": face.extra,
        "icon": _icon_to_project_dict(
            face.icon,
            archive,
            die_index,
            face_index,
        ),
    }


def write_srs_project(path: Path, set_data: SetData) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        dice_data = []
        for die_index, die in enumerate(set_data.dice):
            dice_data.append(
                {
                    "id": die.id,
                    "name": die.name,
                    "sides": die.sides,
                    "shape": die.shape,
                    "polygon_sides": die.polygon_sides,
                    "body_color": die.body_color,
                    "ink_color": die.ink_color,
                    "extra": die.extra,
                    "faces": [
                        _face_to_project_dict(
                            face,
                            archive,
                            die_index,
                            face_index,
                        )
                        for face_index, face in enumerate(die.faces)
                    ],
                }
            )

        project = {
            "format": PROJECT_FORMAT,
            "format_version": PROJECT_VERSION,
            "application": APP_TITLE,
            "set": {
                "id": set_data.id,
                "name": set_data.name,
                "rules_text": set_data.rules_text,
                "rules_script": set_data.rules_script,
                "extra": set_data.extra,
                "dice": dice_data,
            },
        }
        archive.writestr(
            "project.json",
            json.dumps(project, indent=2) + "\n",
        )


def _layer_from_project_dict(
    data: dict[str, Any],
    archive: zipfile.ZipFile,
) -> LayerData:
    layer = LayerData()
    pixels = data.get("pixels")
    if isinstance(pixels, list) and len(pixels) == GRID_SIZE:
        layer.pixels = pixels
    layer.scale_percent = float(data.get("scale_percent", 100.0))
    layer.offset_x = int(data.get("offset_x", 0))
    layer.offset_y = int(data.get("offset_y", 0))
    layer.gamma = float(data.get("gamma", 1.0))
    layer.threshold = int(data.get("threshold", 128))
    layer.polarity = str(
        data.get(
            "polarity",
            "Black ink on white / light background",
        )
    )
    source_ref = str(data.get("source_ref", ""))
    source_name = str(data.get("source_name", ""))
    if source_ref:
        try:
            image_bytes = archive.read(source_ref)
            with Image.open(io.BytesIO(image_bytes)) as image:
                layer.source_image = image.convert("RGBA").copy()
            layer.source_path = source_name or source_ref
        except Exception:
            layer.source_image = None
            layer.source_path = ""
    return layer


def _icon_from_project_dict(
    data: dict[str, Any],
    archive: zipfile.ZipFile,
) -> IconData:
    icon = IconData()
    icon.mode = str(data.get("mode", "1-bit mask"))
    palette = data.get("palette")
    if isinstance(palette, list):
        icon.palette = [str(value) for value in palette[:MAX_PALETTE_COLORS]]
        while len(icon.palette) < MAX_PALETTE_COLORS:
            icon.palette.append("#808080")
    icon.checker_tint = normalize_hex(
        str(data.get("checker_tint", "#D8D8D8")),
        "#D8D8D8",
    )
    layer_data = data.get("layers")
    if isinstance(layer_data, list):
        icon.layers = [
            _layer_from_project_dict(item, archive)
            for item in layer_data[:4]
            if isinstance(item, dict)
        ]
    icon.ensure_layers()
    icon.active_layer = max(
        0,
        min(3, int(data.get("active_layer", 0))),
    )
    return icon


def read_srs_project(path: Path) -> SetData:
    with zipfile.ZipFile(path, "r") as archive:
        project = json.loads(
            archive.read("project.json").decode("utf-8")
        )
        if project.get("format") != PROJECT_FORMAT:
            raise ValueError("This is not a Spiffy Roller .srs project.")
        set_json = project.get("set")
        if not isinstance(set_json, dict):
            raise ValueError("The .srs project does not contain valid set data.")

        model = SetData()
        model.id = str(set_json.get("id", "new_dice_set"))
        model.name = str(set_json.get("name", "New Dice Set"))
        model.rules_text = str(set_json.get("rules_text", "{}"))
        model.rules_script = str(set_json.get("rules_script", DEFAULT_RULES_SCRIPT))
        model.extra = copy.deepcopy(set_json.get("extra") or {})
        model.dice = []

        for die_json in set_json.get("dice", []):
            if not isinstance(die_json, dict):
                continue
            die = DieData()
            die.id = str(die_json.get("id", "die"))
            die.name = str(die_json.get("name", die.id))
            die.sides = int(die_json.get("sides", 6))
            die.shape = str(die_json.get("shape", "d6"))
            die.polygon_sides = int(die_json.get("polygon_sides", 6))
            die.body_color = normalize_hex(
                str(die_json.get("body_color", "#294C78")),
                "#294C78",
            )
            die.ink_color = normalize_hex(
                str(die_json.get("ink_color", "#FFFFFF")),
                "#FFFFFF",
            )
            die.extra = copy.deepcopy(die_json.get("extra") or {})
            die.faces = []

            for face_json in die_json.get("faces", []):
                if not isinstance(face_json, dict):
                    continue
                face = FaceData()
                face.label = str(face_json.get("label", ""))
                face.value = face_json.get("value")
                face.display_mode = str(face_json.get("display_mode", "label"))
                face.image_mode = str(face_json.get("image_mode", "mask"))
                face.image_path = str(face_json.get("image_path", ""))
                if face.display_mode not in FACE_DISPLAY_CHOICES:
                    if face.image_path:
                        face.display_mode = "image"
                    elif face.label:
                        face.display_mode = "label"
                    elif face.value is not None:
                        face.display_mode = "value"
                    else:
                        face.display_mode = "blank"
                face.body_color = str(face_json.get("body_color", ""))
                face.ink_color = str(face_json.get("ink_color", ""))
                face.symbols = {
                    str(key): int(value)
                    for key, value in (face_json.get("symbols") or {}).items()
                }
                face.extra = copy.deepcopy(face_json.get("extra") or {})
                icon_json = face_json.get("icon")
                if isinstance(icon_json, dict):
                    face.icon = _icon_from_project_dict(icon_json, archive)
                die.faces.append(face)

            die.resize_faces(max(1, die.sides))
            model.dice.append(die)

        if not model.dice:
            model.dice = [DieData()]
        return model


class FaceIconEditor(ttk.Frame):
    def __init__(
        self,
        master: tk.Misc,
        shape_getter: Callable[[], tuple[str, int]],
        preview_color_getter: Callable[[], tuple[str, str]],
    ) -> None:
        super().__init__(master)
        self.shape_getter = shape_getter
        self.preview_color_getter = preview_color_getter
        self.icon = IconData()
        self.selected_color = 0
        self._updating_controls = False
        self._palette_buttons: list[tk.Button] = []
        self._layer_buttons: list[tk.Button] = []
        self._preview_photo: ImageTk.PhotoImage | None = None

        controls = ttk.Frame(self)
        controls.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        ttk.Label(controls, text="Icon mode").pack(anchor=tk.W)
        self.mode_var = tk.StringVar(value=self.icon.mode)
        mode_combo = ttk.Combobox(controls, textvariable=self.mode_var, values=MODE_CHOICES, state="readonly", width=24)
        mode_combo.pack(fill=tk.X, pady=(0, 8))
        mode_combo.bind("<<ComboboxSelected>>", self._control_changed)
        ttk.Label(controls, text="Background / ink interpretation").pack(anchor=tk.W)
        self.polarity_var = tk.StringVar(value=self.icon.polarity)
        polarity_combo = ttk.Combobox(controls, textvariable=self.polarity_var, values=POLARITY_CHOICES, state="readonly", width=24)
        polarity_combo.pack(fill=tk.X, pady=(0, 8))
        polarity_combo.bind("<<ComboboxSelected>>", self._control_changed)
        ttk.Button(controls, text="Import image...", command=self.import_image).pack(fill=tk.X, pady=2)
        ttk.Button(controls, text="Rebuild from source", command=self.rebuild).pack(fill=tk.X, pady=2)
        ttk.Button(controls, text="Clear active layer", command=self.clear_pixels).pack(fill=tk.X, pady=(2, 10))

        self.scale_var = tk.DoubleVar(value=100.0)
        self.offset_x_var = tk.IntVar(value=0)
        self.offset_y_var = tk.IntVar(value=0)
        self.gamma_var = tk.DoubleVar(value=1.0)
        self.threshold_var = tk.IntVar(value=128)
        self._make_scale_row(controls, "Scale", self.scale_var, 10, 400, 1, is_float=False)
        self._make_scale_row(controls, "Horz.", self.offset_x_var, -48, 48, 1, is_float=False)
        self._make_scale_row(controls, "Vert.", self.offset_y_var, -48, 48, 1, is_float=False)
        self._make_scale_row(controls, "Gamma", self.gamma_var, 0.2, 3.0, 0.05, is_float=True)
        self._make_scale_row(controls, "Thresh.", self.threshold_var, 0, 255, 1, is_float=False)

        center = ttk.Frame(self)
        center.pack(side=tk.LEFT, fill=tk.BOTH, expand=False)
        self.canvas = tk.Canvas(center, width=CANVAS_SIZE, height=CANVAS_SIZE, background="#FFFFFF", highlightthickness=1, highlightbackground="#606060")
        self.canvas.pack(anchor=tk.NW)
        self.canvas.bind("<Button-1>", self.paint_foreground)
        self.canvas.bind("<B1-Motion>", self.paint_foreground)
        self.canvas.bind("<Button-3>", self.paint_transparent)
        self.canvas.bind("<B3-Motion>", self.paint_transparent)
        layers_row = ttk.Frame(center)
        layers_row.pack(anchor=tk.W, pady=(6, 0))
        ttk.Label(layers_row, text="Layers:").pack(side=tk.LEFT, padx=(0, 6))
        for index in range(4):
            button = tk.Button(layers_row, text=str(index + 1), width=4, command=lambda i=index: self.select_layer(i))
            button.pack(side=tk.LEFT, padx=2)
            self._layer_buttons.append(button)
        ttk.Label(
            center,
            text=(
                "Left click: foreground    Right click: transparent\n"
                "Controls affect the active layer    Sliders update imported artwork in real time"
            ),
            justify=tk.LEFT,
            wraplength=CANVAS_SIZE,
        ).pack(anchor=tk.W, pady=(6, 0))

        sidebar = ttk.Frame(self)
        sidebar.pack(side=tk.LEFT, fill=tk.Y, padx=(10, 0))
        preview_box = ttk.LabelFrame(sidebar, text="Real-size preview", padding=8)
        preview_box.pack(fill=tk.X)
        self.preview_label = ttk.Label(preview_box)
        self.preview_label.pack(anchor=tk.CENTER)
        palette_frame = ttk.LabelFrame(sidebar, text="Foreground palette", padding=8)
        palette_frame.pack(fill=tk.X, pady=(10, 0))
        for index in range(MAX_PALETTE_COLORS):
            button = tk.Button(palette_frame, width=4, height=2, command=lambda i=index: self.select_palette(i))
            button.grid(row=index // 3, column=index % 3, padx=2, pady=2, sticky="nsew")
            button.bind("<Double-Button-1>", lambda _event, i=index: self.edit_palette_color(i))
            self._palette_buttons.append(button)
        for column in range(3):
            palette_frame.grid_columnconfigure(column, weight=1)
        ttk.Button(sidebar, text="Edit selected color...", command=lambda: self.edit_palette_color(self.selected_color)).pack(fill=tk.X, pady=(8, 0))
        checker_box = ttk.LabelFrame(sidebar, text="Checkerboard background", padding=8)
        checker_box.pack(fill=tk.X, pady=(10, 0))
        ttk.Button(checker_box, text="Choose tint...", command=self.choose_checker_tint).pack(fill=tk.X)
        self.checker_color_label = ttk.Label(checker_box, text=self.icon.checker_tint)
        self.checker_color_label.pack(anchor=tk.CENTER, pady=(6, 0))
        self.load_icon(self.icon)

    def _make_scale_row(
        self,
        parent: ttk.Frame,
        label: str,
        variable: tk.Variable,
        start: float,
        end: float,
        resolution: float,
        is_float: bool,
    ) -> None:
        row = ttk.Frame(parent)
        row.pack(fill=tk.X, pady=2)
        ttk.Label(row, text=label, width=8).pack(side=tk.LEFT)
        scale = tk.Scale(
            row,
            variable=variable,
            from_=start,
            to=end,
            resolution=resolution,
            orient=tk.HORIZONTAL,
            length=165,
            showvalue=False,
            command=lambda _value: self._control_changed(),
        )
        scale.pack(side=tk.LEFT, fill=tk.X, expand=True)
        entry = ttk.Entry(row, textvariable=variable, width=7, justify=tk.CENTER)
        entry.pack(side=tk.LEFT, padx=(6, 0))
        entry.bind("<KeyRelease>", self._control_changed)
        entry.bind("<FocusOut>", self._control_changed)
        variable.trace_add("write", lambda *_args: self._control_changed())


    def _current_layer(self) -> LayerData:
        self.icon.ensure_layers()
        return self.icon.layers[self.icon.active_layer]

    def _control_changed(self, _event: object | None = None) -> None:
        if self._updating_controls:
            return
        self._sync_controls_to_icon()
        if self._current_layer().source_image is not None:
            self.icon.rebuild_from_source()
            self.refresh_palette_buttons()
        self.redraw()

    def _sync_controls_to_icon(self) -> None:
        layer = self._current_layer()
        self.icon.mode = self.mode_var.get()
        layer.polarity = self.polarity_var.get()
        layer.scale_percent = float(self.scale_var.get())
        layer.offset_x = int(self.offset_x_var.get())
        layer.offset_y = int(self.offset_y_var.get())
        layer.gamma = float(self.gamma_var.get())
        layer.threshold = int(self.threshold_var.get())

    def _load_controls_from_layer(self) -> None:
        layer = self._current_layer()
        self._updating_controls = True
        self.mode_var.set(self.icon.mode)
        self.polarity_var.set(layer.polarity)
        self.scale_var.set(layer.scale_percent)
        self.offset_x_var.set(layer.offset_x)
        self.offset_y_var.set(layer.offset_y)
        self.gamma_var.set(layer.gamma)
        self.threshold_var.set(layer.threshold)
        self._updating_controls = False

    def load_icon(self, icon: IconData) -> None:
        self.icon = icon
        self.icon.ensure_layers()
        self.selected_color = 0
        self._load_controls_from_layer()
        self.refresh_palette_buttons()
        self._update_layer_buttons()
        self.redraw()

    def import_image(self) -> None:
        filename = filedialog.askopenfilename(title="Import source image", filetypes=[("Supported images", "*.png *.bmp *.jpg *.jpeg *.gif *.webp"), ("All files", "*.*")])
        if not filename:
            return
        try:
            source = Image.open(filename).convert("RGBA")
        except Exception as exc:
            messagebox.showerror(APP_TITLE, f"Could not open image:\n{exc}")
            return
        layer = self._current_layer()
        layer.source_path = filename
        layer.source_image = source
        layer.scale_percent = min(GRID_SIZE / max(1, source.width), GRID_SIZE / max(1, source.height)) * 100.0
        layer.offset_x = 0
        layer.offset_y = 0
        self._load_controls_from_layer()
        self.rebuild()

    def rebuild(self) -> None:
        self._sync_controls_to_icon()
        if self._current_layer().source_image is None:
            messagebox.showinfo(APP_TITLE, "Import a source image first.")
            return
        self.icon.rebuild_from_source()
        self.refresh_palette_buttons()
        self.redraw()

    def clear_pixels(self) -> None:
        if messagebox.askyesno(APP_TITLE, f"Clear active layer {self.icon.active_layer + 1}?"):
            self._current_layer().clear()
            self.redraw()

    def choose_checker_tint(self) -> None:
        chosen = colorchooser.askcolor(initialcolor=self.icon.checker_tint, title="Choose checkerboard tint")
        if chosen[1]:
            self.icon.checker_tint = chosen[1].upper()
            self.redraw()

    def select_palette(self, index: int) -> None:
        self.selected_color = 0 if self.icon.mode == "1-bit mask" else index
        self.refresh_palette_buttons()
        self.redraw()

    def edit_palette_color(self, index: int) -> None:
        if self.icon.mode == "1-bit mask":
            index = 0
        initial = self.icon.palette[index]
        chosen = colorchooser.askcolor(initialcolor=initial, title="Choose palette color")
        if chosen[1]:
            self.icon.palette[index] = chosen[1].upper()
            self.selected_color = index
            self.refresh_palette_buttons()
            self.redraw()

    def refresh_palette_buttons(self) -> None:
        usable = 1 if self.icon.mode == "1-bit mask" else MAX_PALETTE_COLORS
        for index, button in enumerate(self._palette_buttons):
            state = tk.NORMAL if index < usable else tk.DISABLED
            relief = tk.SUNKEN if index == self.selected_color and index < usable else tk.RAISED
            button.configure(background=self.icon.palette[index], activebackground=self.icon.palette[index], state=state, relief=relief)

    def _update_layer_buttons(self) -> None:
        for index, button in enumerate(self._layer_buttons):
            active = index == self.icon.active_layer
            button.configure(relief=tk.SUNKEN if active else tk.RAISED, bg="#88B6FF" if active else "#E0E0E0")

    def select_layer(self, index: int) -> None:
        self._sync_controls_to_icon()
        self.icon.active_layer = index
        self._load_controls_from_layer()
        self._update_layer_buttons()
        self.redraw()

    def _event_pixel(self, event: tk.Event) -> tuple[int, int] | None:
        x = int(event.x // PIXEL_ZOOM)
        y = int(event.y // PIXEL_ZOOM)
        return (x, y) if 0 <= x < GRID_SIZE and 0 <= y < GRID_SIZE else None

    def paint_foreground(self, event: tk.Event) -> None:
        point = self._event_pixel(event)
        if point is None:
            return
        x, y = point
        self._current_layer().pixels[y][x] = 0 if self.icon.mode == "1-bit mask" else self.selected_color
        self.redraw()

    def paint_transparent(self, event: tk.Event) -> None:
        point = self._event_pixel(event)
        if point is None:
            return
        x, y = point
        self._current_layer().pixels[y][x] = -1
        self.redraw()

    def redraw(self) -> None:
        self.refresh_palette_buttons()
        self._update_layer_buttons()
        self.checker_color_label.configure(text=self.icon.checker_tint)
        self.canvas.delete("all")
        light, dark = checker_colors(self.icon.checker_tint)
        composite, owners = self.icon.composite_with_owners()
        for y in range(GRID_SIZE):
            for x in range(GRID_SIZE):
                value = composite[y][x]
                x1 = x * PIXEL_ZOOM
                y1 = y * PIXEL_ZOOM
                bg = light if (x + y) % 2 == 0 else dark
                if value < 0:
                    self.canvas.create_rectangle(x1, y1, x1 + PIXEL_ZOOM, y1 + PIXEL_ZOOM, fill=bg, outline="#B0B0B0", width=1)
                    continue

                palette_index = 0 if self.icon.mode == "1-bit mask" else value
                fill = self.icon.palette[max(0, min(MAX_PALETTE_COLORS - 1, palette_index))]
                if owners[y][x] == self.icon.active_layer:
                    self.canvas.create_rectangle(x1, y1, x1 + PIXEL_ZOOM, y1 + PIXEL_ZOOM, fill=fill, outline="#B0B0B0", width=1)
                else:
                    self.canvas.create_rectangle(x1, y1, x1 + PIXEL_ZOOM, y1 + PIXEL_ZOOM, fill=bg, outline="#B0B0B0", width=1)
                    half = PIXEL_ZOOM / 2
                    self.canvas.create_rectangle(x1, y1, x1 + half, y1 + half, fill=fill, outline="")
                    self.canvas.create_rectangle(x1 + half, y1 + half, x1 + PIXEL_ZOOM, y1 + PIXEL_ZOOM, fill=fill, outline="")
        self._draw_shape_outline()
        self.update_preview(composite)

    def update_preview(self, composite: list[list[int]] | None = None) -> None:
        if composite is None:
            composite = self.icon.composite_pixels()

        body_color, ink_color = self.preview_color_getter()
        face_size = 54
        icon_offset = 3

        preview = Image.new("RGBA", (face_size, face_size), (0, 0, 0, 0))
        face_mask = self._create_preview_shape_mask(face_size)

        body_layer = Image.new(
            "RGBA",
            (face_size, face_size),
            color_tuple(body_color, "#FFFFFF") + (255,),
        )
        preview.alpha_composite(
            Image.composite(
                body_layer,
                Image.new("RGBA", (face_size, face_size), (0, 0, 0, 0)),
                face_mask,
            )
        )

        pixels = preview.load()
        mask_pixels = face_mask.load()
        for y in range(GRID_SIZE):
            for x in range(GRID_SIZE):
                value = composite[y][x]
                target_x = x + icon_offset
                target_y = y + icon_offset
                if value < 0 or mask_pixels[target_x, target_y] == 0:
                    continue

                if self.icon.mode == "1-bit mask":
                    color = color_tuple(ink_color, "#000000")
                else:
                    color = color_tuple(
                        self.icon.palette[
                            max(0, min(MAX_PALETTE_COLORS - 1, value))
                        ],
                        "#000000",
                    )
                pixels[target_x, target_y] = color + (255,)

        self._preview_photo = ImageTk.PhotoImage(preview)
        self.preview_label.configure(image=self._preview_photo)

    def _create_preview_shape_mask(self, size: int) -> Image.Image:
        mask = Image.new("L", (size, size), 0)
        draw = ImageDraw.Draw(mask)
        shape, polygon_sides = self.shape_getter()
        margin = 0
        left = margin
        top = margin
        right = size - 1 - margin
        bottom = size - 1 - margin
        center_x = (size - 1) / 2
        center_y = (size - 1) / 2
        radius = (size - 1 - margin * 2) / 2

        if shape == "d4":
            points = [(center_x, top), (right, bottom), (left, bottom)]
            draw.polygon(points, fill=255)
        elif shape == "d8":
            points = [(left, top), (right, top), (center_x, bottom)]
            draw.polygon(points, fill=255)
        elif shape == "d10":
            points = [
                (center_x, top),
                (right, center_y),
                (center_x, bottom),
                (left, center_y),
            ]
            draw.polygon(points, fill=255)
        elif shape == "d12":
            draw.polygon(
                regular_polygon_points(
                    5,
                    center_x,
                    center_y,
                    radius,
                    -90,
                ),
                fill=255,
            )
        elif shape == "d20":
            draw.polygon(
                regular_polygon_points(
                    6,
                    center_x,
                    center_y,
                    radius,
                    -90,
                ),
                fill=255,
            )
        elif shape == "circle":
            draw.ellipse((left, top, right, bottom), fill=255)
        elif shape == "polygon":
            sides = max(3, min(12, int(polygon_sides)))
            draw.polygon(
                regular_polygon_points(
                    sides,
                    center_x,
                    center_y,
                    radius,
                    -90,
                ),
                fill=255,
            )
        else:
            draw.rectangle((left, top, right, bottom), fill=255)

        return mask

    def _draw_shape_outline(self) -> None:
        shape, polygon_sides = self.shape_getter()
        margin = 2.5 * PIXEL_ZOOM
        left = margin
        top = margin
        right = CANVAS_SIZE - margin
        bottom = CANVAS_SIZE - margin
        center_x = CANVAS_SIZE / 2
        center_y = CANVAS_SIZE / 2
        points: list[float] = []
        if shape == "d4":
            points = [center_x, top, right, bottom, left, bottom]
        elif shape == "d8":
            points = [left, top, right, top, center_x, bottom]
        elif shape == "d10":
            points = [center_x, top, right, center_y, center_x, bottom, left, center_y]
        elif shape == "d12":
            points = regular_polygon_points(5, center_x, center_y, (right - left) / 2, -90)
        elif shape == "d20":
            points = regular_polygon_points(6, center_x, center_y, (right - left) / 2, -90)
        elif shape == "circle":
            self.canvas.create_oval(left, top, right, bottom, outline="#FF00FF", width=3, dash=(6, 4))
            return
        elif shape == "polygon":
            sides = max(3, min(12, int(polygon_sides)))
            points = regular_polygon_points(sides, center_x, center_y, (right - left) / 2, -90)
        else:
            points = [left, top, right, top, right, bottom, left, bottom]
        self.canvas.create_polygon(points, outline="#FF00FF", fill="", width=3, dash=(6, 4))




class DieEditor(ttk.Frame):
    def __init__(self, master: tk.Misc, die: DieData, on_name_changed: Callable[[], None]) -> None:
        super().__init__(master)
        self.die = die
        self.on_name_changed = on_name_changed
        self.current_face_index = 0
        self._loading = False

        paned = ttk.Panedwindow(self, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True)
        left = ttk.Frame(paned, padding=8)
        right = ttk.Frame(paned, padding=8)
        paned.add(left, weight=1)
        paned.add(right, weight=3)
        properties = ttk.LabelFrame(left, text="Die properties", padding=8)
        properties.pack(fill=tk.X)

        self.id_var = tk.StringVar(value=die.id)
        self.name_var = tk.StringVar(value=die.name)
        self.sides_var = tk.IntVar(value=die.sides)
        self.shape_var = tk.StringVar(value=die.shape)
        self.polygon_sides_var = tk.IntVar(value=die.polygon_sides)
        self.body_color_var = tk.StringVar(value=die.body_color)
        self.ink_color_var = tk.StringVar(value=die.ink_color)
        self._entry_row(properties, "ID", self.id_var)
        self._entry_row(properties, "Name", self.name_var)

        row = ttk.Frame(properties)
        row.pack(fill=tk.X, pady=2)
        ttk.Label(row, text="Sides", width=15).pack(side=tk.LEFT)
        ttk.Spinbox(row, from_=1, to=100, textvariable=self.sides_var, width=8).pack(side=tk.LEFT)
        ttk.Button(row, text="Apply", command=self.apply_sides).pack(side=tk.LEFT, padx=4)
        row = ttk.Frame(properties)
        row.pack(fill=tk.X, pady=2)
        ttk.Label(row, text="Shape", width=15).pack(side=tk.LEFT)
        shape_combo = ttk.Combobox(row, textvariable=self.shape_var, values=SHAPE_CHOICES, state="readonly", width=14)
        shape_combo.pack(side=tk.LEFT, fill=tk.X, expand=True)
        shape_combo.bind("<<ComboboxSelected>>", lambda _event: self.icon_editor.redraw())
        row = ttk.Frame(properties)
        row.pack(fill=tk.X, pady=2)
        ttk.Label(row, text="Polygon sides", width=15).pack(side=tk.LEFT)
        polygon_spin = ttk.Spinbox(row, from_=3, to=12, textvariable=self.polygon_sides_var, width=8, command=lambda: self.icon_editor.redraw())
        polygon_spin.pack(side=tk.LEFT)
        polygon_spin.bind("<KeyRelease>", lambda _event: self.icon_editor.redraw())
        self._color_row(properties, "Body color", self.body_color_var)
        self._color_row(properties, "Ink color", self.ink_color_var)

        faces_box = ttk.LabelFrame(left, text="Faces", padding=8)
        faces_box.pack(fill=tk.BOTH, expand=True, pady=(8, 0))
        self.face_list = tk.Listbox(faces_box, exportselection=False, height=15, activestyle="none", selectmode=tk.SINGLE)
        self.face_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar = ttk.Scrollbar(faces_box, orient=tk.VERTICAL, command=self.face_list.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.face_list.configure(yscrollcommand=scrollbar.set)
        self.face_list.bind("<<ListboxSelect>>", self.face_selected)

        metadata = ttk.LabelFrame(right, text="Selected face", padding=8)
        metadata.pack(fill=tk.X)
        self.face_label_var = tk.StringVar()
        self.face_value_var = tk.StringVar()
        self.face_mode_var = tk.StringVar(value="label")
        self.face_image_var = tk.StringVar()
        self.face_body_var = tk.StringVar()
        self.face_ink_var = tk.StringVar()
        self.face_symbols_var = tk.StringVar(value="{}")
        self._entry_row(metadata, "Label", self.face_label_var)
        self._entry_row(metadata, "Numeric value", self.face_value_var)
        row = ttk.Frame(metadata)
        row.pack(fill=tk.X, pady=2)
        ttk.Label(row, text="Face Display", width=15).pack(side=tk.LEFT)
        ttk.Combobox(row, textvariable=self.face_mode_var, values=FACE_DISPLAY_CHOICES, state="readonly", width=14).pack(side=tk.LEFT)
        self._entry_row(metadata, "Image path", self.face_image_var)
        self._entry_row(metadata, "Body override", self.face_body_var)
        self._entry_row(metadata, "Ink override", self.face_ink_var)
        self._entry_row(metadata, "Symbols JSON", self.face_symbols_var)
        action_row = ttk.Frame(metadata)
        action_row.pack(fill=tk.X, pady=(4, 0))
        ttk.Button(action_row, text="Copy icon from...", command=self.copy_icon_from_face).pack(side=tk.LEFT)
        ttk.Button(action_row, text="Apply face metadata", command=self.save_current_face).pack(side=tk.RIGHT)

        icon_box = ttk.LabelFrame(right, text="48×48 face icon generator", padding=8)
        icon_box.pack(fill=tk.BOTH, expand=True, pady=(8, 0))
        self.icon_editor = FaceIconEditor(icon_box, self.get_shape, self.get_preview_colors)
        self.icon_editor.pack(fill=tk.BOTH, expand=True)

        self.name_var.trace_add("write", lambda *_args: self._name_changed())
        for variable in (self.body_color_var, self.ink_color_var, self.face_body_var, self.face_ink_var):
            variable.trace_add("write", lambda *_args: self.icon_editor.redraw())
        self.refresh_face_list()
        self.load_face(0)

    def _entry_row(self, parent: ttk.Frame, label: str, variable: tk.Variable) -> None:
        row = ttk.Frame(parent)
        row.pack(fill=tk.X, pady=2)
        ttk.Label(row, text=label, width=15).pack(side=tk.LEFT)
        ttk.Entry(row, textvariable=variable).pack(side=tk.LEFT, fill=tk.X, expand=True)

    def _color_row(self, parent: ttk.Frame, label: str, variable: tk.StringVar) -> None:
        row = ttk.Frame(parent)
        row.pack(fill=tk.X, pady=2)
        ttk.Label(row, text=label, width=15).pack(side=tk.LEFT)
        ttk.Entry(row, textvariable=variable).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(row, text="...", width=3, command=lambda: self.choose_color(variable)).pack(side=tk.LEFT, padx=(4, 0))

    def choose_color(self, variable: tk.StringVar) -> None:
        chosen = colorchooser.askcolor(initialcolor=variable.get())
        if chosen[1]:
            variable.set(chosen[1].upper())

    def _name_changed(self) -> None:
        if self._loading:
            return
        self.die.name = self.name_var.get()
        if not self.id_var.get().strip():
            self.id_var.set(slugify(self.die.name, "die"))
        self.on_name_changed()

    def get_shape(self) -> tuple[str, int]:
        return self.shape_var.get(), int(self.polygon_sides_var.get())

    def get_preview_colors(self) -> tuple[str, str]:
        body = normalize_hex(self.face_body_var.get().strip() or self.body_color_var.get().strip(), self.die.body_color)
        ink = normalize_hex(self.face_ink_var.get().strip() or self.ink_color_var.get().strip(), self.die.ink_color)
        return body, ink

    def apply_sides(self) -> None:
        self.save_current_face()
        sides = max(1, min(100, int(self.sides_var.get())))
        if sides < len(self.die.faces):
            if not messagebox.askyesno(APP_TITLE, f"Reducing this die to {sides} sides will delete {len(self.die.faces) - sides} face definitions. Continue?"):
                self.sides_var.set(len(self.die.faces))
                return
        self.die.resize_faces(sides)
        self.refresh_face_list()
        self.current_face_index = min(self.current_face_index, sides - 1)
        self.load_face(self.current_face_index)

    def refresh_face_list(self) -> None:
        self.face_list.delete(0, tk.END)
        for index, face in enumerate(self.die.faces, start=1):
            if getattr(face, "display_mode", "label") == "blank":
                description = "[Blank]"
            elif getattr(face, "display_mode", "label") == "image":
                description = face.label or Path(face.image_path).name or ("[Image]" if face.icon.has_visible_pixels() else f"Face {index}")
            elif getattr(face, "display_mode", "label") == "value":
                description = "Value: " + ("" if face.value is None else str(face.value))
                if description == "Value: ":
                    description = "[Value]"
            else:
                description = face.label or f"Face {index}"
            self.face_list.insert(tk.END, f"{index}: {description}")
        if self.die.faces:
            self.face_list.selection_clear(0, tk.END)
            self.face_list.selection_set(self.current_face_index)
            self.face_list.activate(self.current_face_index)
            self.face_list.see(self.current_face_index)

    def face_selected(self, _event: object | None = None) -> None:
        selection = self.face_list.curselection()
        if not selection:
            return
        new_index = int(selection[0])
        if new_index == self.current_face_index:
            return
        self.save_current_face()
        self.load_face(new_index)

    def load_face(self, index: int) -> None:
        self.current_face_index = index
        face = self.die.faces[index]
        self._loading = True
        self.face_label_var.set(face.label)
        self.face_value_var.set("" if face.value is None else str(face.value))
        self.face_mode_var.set(getattr(face, "display_mode", "label"))
        self.face_image_var.set(face.image_path)
        self.face_body_var.set(face.body_color)
        self.face_ink_var.set(face.ink_color)
        self.face_symbols_var.set(json.dumps(face.symbols, separators=(",", ":")))
        self._loading = False
        self.face_list.selection_clear(0, tk.END)
        self.face_list.selection_set(index)
        self.face_list.activate(index)
        self.face_list.see(index)
        self.icon_editor.load_icon(face.icon)

    def copy_icon_from_face(self) -> None:
        if len(self.die.faces) <= 1:
            return
        source = simpledialog.askinteger(APP_TITLE, f"Copy icon from which face number? (1-{len(self.die.faces)})", minvalue=1, maxvalue=len(self.die.faces), parent=self)
        if source is None:
            return
        source_index = source - 1
        if source_index == self.current_face_index:
            return
        self.save_current_face()
        self.die.faces[self.current_face_index].icon = self.die.faces[source_index].icon.clone()
        self.icon_editor.load_icon(self.die.faces[self.current_face_index].icon)

    def save_current_face(self) -> None:
        if not self.die.faces:
            return
        face = self.die.faces[self.current_face_index]
        face.label = self.face_label_var.get()
        try:
            face.value = parse_optional_int(self.face_value_var.get())
        except ValueError:
            messagebox.showerror(APP_TITLE, "Numeric value must be an integer or blank.")
            return
        face.display_mode = self.face_mode_var.get()
        face.image_path = self.face_image_var.get().strip()
        face.body_color = self.face_body_var.get().strip()
        face.ink_color = self.face_ink_var.get().strip()
        try:
            symbols = json.loads(self.face_symbols_var.get() or "{}")
            if not isinstance(symbols, dict):
                raise ValueError("Symbols must be a JSON object.")
            face.symbols = {str(key): int(value) for key, value in symbols.items() if int(value) != 0}
        except Exception as exc:
            messagebox.showerror(APP_TITLE, f"Invalid Symbols JSON:\n{exc}")
            return
        face.icon = self.icon_editor.icon
        self.refresh_face_list()

    def save_die(self) -> None:
        self.save_current_face()
        self.die.id = slugify(self.id_var.get(), "die")
        self.id_var.set(self.die.id)
        self.die.name = self.name_var.get().strip() or self.die.id
        self.die.sides = len(self.die.faces)
        self.die.shape = self.shape_var.get()
        self.die.polygon_sides = int(self.polygon_sides_var.get())
        self.die.body_color = normalize_hex(self.body_color_var.get(), "#294C78")
        self.die.ink_color = normalize_hex(self.ink_color_var.get(), "#FFFFFF")


class TemplateMakerApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self._window_icons = [
            ImageTk.PhotoImage(create_d20_icon(size))
            for size in (64, 32, 16)
        ]
        self.iconphoto(True, *self._window_icons)
        self.title(f"{APP_TITLE} {APP_VERSION}")
        self.geometry("1500x930")
        self.minsize(1200, 780)

        self.set_data = SetData()
        self.die_editors: list[DieEditor] = []
        self.import_root: Path | None = None
        self.import_tempdir: tempfile.TemporaryDirectory[str] | None = None
        self.current_project_path: Path | None = None

        self._build_menu()

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        self.general_tab = ttk.Frame(self.notebook, padding=12)
        self.notebook.add(self.general_tab, text="General")
        self._build_general_tab()

        self.rebuild_die_tabs()
        self.protocol("WM_DELETE_WINDOW", self.close_app)
        self._update_window_title()

    def _build_menu(self) -> None:
        menu = tk.Menu(self)
        file_menu = tk.Menu(menu, tearoff=False)
        file_menu.add_command(label="New set project", command=self.new_template)
        file_menu.add_command(label="Open existing project", command=self.open_project)
        file_menu.add_command(label="Save project", command=self.save_project)
        file_menu.add_command(label="Save project as...", command=self.save_project_as)
        file_menu.add_separator()
        file_menu.add_command(label="Import dice set folder", command=self.import_folder)
        file_menu.add_command(label="Import .set file", command=self.import_zip)
        file_menu.add_separator()
        file_menu.add_command(label="Export dice set folder", command=self.export_folder)
        file_menu.add_command(label="Export .set file", command=self.export_zip)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.close_app)
        menu.add_cascade(label="File", menu=file_menu)
        help_menu = tk.Menu(menu, tearoff=False)
        help_menu.add_command(label="About", command=self.show_about)
        menu.add_cascade(label="Help", menu=help_menu)
        self.configure(menu=menu)

    def _update_window_title(self) -> None:
        suffix = ""
        if self.current_project_path is not None:
            suffix = f" - {self.current_project_path.name}"
        self.title(f"{APP_TITLE} {APP_VERSION}{suffix}")

    def _build_general_tab(self) -> None:
        top = ttk.LabelFrame(self.general_tab, text="Set properties", padding=10)
        top.pack(fill=tk.X)

        self.set_name_var = tk.StringVar(value=self.set_data.name)
        self.set_id_var = tk.StringVar(value=self.set_data.id)
        self.die_count_var = tk.IntVar(value=len(self.set_data.dice))

        self._general_row(top, "Set name", self.set_name_var)
        self._general_row(top, "Set ID", self.set_id_var)

        row = ttk.Frame(top)
        row.pack(fill=tk.X, pady=3)
        ttk.Label(row, text="Number of die types", width=20).pack(side=tk.LEFT)
        ttk.Spinbox(row, from_=1, to=32, textvariable=self.die_count_var, width=8).pack(side=tk.LEFT)
        ttk.Button(row, text="Apply", command=self.apply_die_count).pack(side=tk.LEFT, padx=5)

        rules_book = ttk.Notebook(self.general_tab)
        rules_book.pack(fill=tk.BOTH, expand=True, pady=(10, 0))
        manifest_tab = ttk.Frame(rules_book, padding=8)
        script_tab = ttk.Frame(rules_book, padding=8)
        rules_book.add(manifest_tab, text="Rules manifest")
        rules_book.add(script_tab, text="Roll script")

        manifest_frame = ttk.LabelFrame(manifest_tab, text="rules.json", padding=8)
        manifest_frame.pack(fill=tk.BOTH, expand=True)
        self.rules_text = tk.Text(manifest_frame, wrap=tk.NONE, undo=True)
        self.rules_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        manifest_y = ttk.Scrollbar(manifest_frame, orient=tk.VERTICAL, command=self.rules_text.yview)
        manifest_y.pack(side=tk.RIGHT, fill=tk.Y)
        self.rules_text.configure(yscrollcommand=manifest_y.set)
        self.rules_text.insert("1.0", self.set_data.rules_text)
        ttk.Button(manifest_tab, text="Validate rules manifest", command=self.validate_rules).pack(anchor=tk.E, pady=(8,0))

        script_frame = ttk.LabelFrame(script_tab, text="rules.lua", padding=8)
        script_frame.pack(fill=tk.BOTH, expand=True)
        self.rules_script_text = tk.Text(script_frame, wrap=tk.NONE, undo=True, font=("TkFixedFont", 10))
        self.rules_script_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        script_y = ttk.Scrollbar(script_frame, orient=tk.VERTICAL, command=self.rules_script_text.yview)
        script_y.pack(side=tk.RIGHT, fill=tk.Y)
        self.rules_script_text.configure(yscrollcommand=script_y.set)
        self.rules_script_text.insert("1.0", self.set_data.rules_script)

        script_actions = ttk.Frame(script_tab)
        script_actions.pack(fill=tk.X, pady=(8, 0))
        ttk.Label(
            script_actions,
            text=(
                "Packaged with the set and intended for a restricted Lua "
                "sandbox with hard memory and instruction limits."
            ),
            wraplength=900,
        ).pack(side=tk.LEFT, anchor=tk.W, fill=tk.X, expand=True)
        ttk.Button(
            script_actions,
            text="Validate rules.lua syntax",
            command=self.validate_lua_syntax,
        ).pack(side=tk.RIGHT, padx=(8, 0))

    def _general_row(self, parent: ttk.Frame, label: str, variable: tk.Variable) -> None:
        row = ttk.Frame(parent)
        row.pack(fill=tk.X, pady=3)
        ttk.Label(row, text=label, width=20).pack(side=tk.LEFT)
        ttk.Entry(row, textvariable=variable).pack(side=tk.LEFT, fill=tk.X, expand=True)

    def validate_rules(self) -> bool:
        try:
            parsed = json.loads(self.rules_text.get("1.0", tk.END))
            if not isinstance(parsed, dict):
                raise ValueError("The root of rules.json must be a JSON object.")
        except Exception as exc:
            messagebox.showerror(APP_TITLE, f"Rules JSON is invalid:\n{exc}")
            return False
        messagebox.showinfo(APP_TITLE, "Rules JSON is valid.")
        return True

    def validate_lua_syntax(self) -> bool:
        source = self.rules_script_text.get("1.0", tk.END)

        if not source.strip():
            messagebox.showerror(
                APP_TITLE,
                "rules.lua is empty.",
            )
            return False

        try:
            from luaparser import ast
        except ImportError:
            messagebox.showerror(
                APP_TITLE,
                "Lua syntax validation requires the 'luaparser' package.\n\n"
                "Install the updated requirements with:\n"
                "python -m pip install -r requirements.txt",
            )
            return False

        try:
            ast.parse(source)
        except Exception as exc:
            message = str(exc).strip() or exc.__class__.__name__
            messagebox.showerror(
                APP_TITLE,
                f"rules.lua contains a syntax error:\n\n{message}",
            )
            return False

        messagebox.showinfo(
            APP_TITLE,
            "rules.lua syntax is valid.",
        )
        return True

    def sync_model_from_ui(self) -> bool:
        for editor in self.die_editors:
            editor.save_die()
        self.set_data.name = self.set_name_var.get().strip() or "Unnamed Dice Set"
        self.set_data.id = slugify(self.set_id_var.get(), slugify(self.set_data.name))
        self.set_id_var.set(self.set_data.id)
        self.set_data.rules_text = self.rules_text.get("1.0", tk.END).strip()
        self.set_data.rules_script = self.rules_script_text.get("1.0", tk.END).rstrip() + "\n"
        try:
            rules = json.loads(self.set_data.rules_text)
            if not isinstance(rules, dict):
                raise ValueError("rules.json must contain a JSON object.")
            if rules.get("engine") == "lua":
                if rules.get("script") != "rules.lua":
                    raise ValueError("Lua rules must reference rules.lua.")
                if "function resolve" not in self.set_data.rules_script:
                    raise ValueError("rules.lua must define function resolve(roll, options).")
        except Exception as exc:
            messagebox.showerror(APP_TITLE, f"Rules are invalid:\n{exc}")
            return False
        return True

    def apply_die_count(self) -> None:
        desired = max(1, min(32, int(self.die_count_var.get())))
        current = len(self.set_data.dice)

        if desired < current:
            if not messagebox.askyesno(
                APP_TITLE,
                f"Remove {current - desired} die tab(s) and all of their face definitions?",
            ):
                self.die_count_var.set(current)
                return

        for editor in self.die_editors:
            editor.save_die()

        while len(self.set_data.dice) < desired:
            index = len(self.set_data.dice) + 1
            self.set_data.dice.append(
                DieData(
                    id=f"die_{index}",
                    name=f"Die {index}",
                )
            )
        if len(self.set_data.dice) > desired:
            self.set_data.dice = self.set_data.dice[:desired]

        self.rebuild_die_tabs()

    def rebuild_die_tabs(self) -> None:
        for editor in self.die_editors:
            self.notebook.forget(editor)
            editor.destroy()
        self.die_editors.clear()

        for index, die in enumerate(self.set_data.dice, start=1):
            editor = DieEditor(self.notebook, die, self.update_die_tab_titles)
            self.die_editors.append(editor)
            self.notebook.add(editor, text=f"Die {index}: {die.name}")

        self.die_count_var.set(len(self.set_data.dice))

    def update_die_tab_titles(self) -> None:
        for index, editor in enumerate(self.die_editors, start=1):
            title = editor.name_var.get().strip() or f"Die {index}"
            self.notebook.tab(editor, text=f"Die {index}: {title}")

    def new_template(self) -> None:
        if not messagebox.askyesno(APP_TITLE, "Discard the current template and start a new one?"):
            return
        self.set_data = SetData()
        self.current_project_path = None
        self.import_root = None
        if self.import_tempdir is not None:
            self.import_tempdir.cleanup()
            self.import_tempdir = None
        self.load_model_into_ui()

    def open_project(self) -> None:
        filename = filedialog.askopenfilename(
            title="Open Spiffy Roller Set project",
            filetypes=[
                ("Spiffy Roller Set projects", "*.srs"),
                ("All files", "*.*"),
            ],
        )
        if not filename:
            return
        try:
            self.set_data = read_srs_project(Path(filename))
        except Exception as exc:
            messagebox.showerror(APP_TITLE, f"Could not open project:\n{exc}")
            return
        self.current_project_path = Path(filename)
        self.import_root = None
        self.load_model_into_ui()
        self._update_window_title()

    def save_project(self) -> None:
        if self.current_project_path is None:
            self.save_project_as()
            return
        if not self.sync_model_from_ui():
            return
        try:
            write_srs_project(self.current_project_path, self.set_data)
        except Exception as exc:
            messagebox.showerror(APP_TITLE, f"Could not save project:\n{exc}")
            return
        self._update_window_title()
        messagebox.showinfo(
            APP_TITLE,
            f"Project saved to:\n{self.current_project_path}",
        )

    def save_project_as(self) -> None:
        if not self.sync_model_from_ui():
            return
        filename = filedialog.asksaveasfilename(
            title="Save Spiffy Roller Set project",
            initialfile=f"{self.set_data.id}.srs",
            defaultextension=".srs",
            filetypes=[
                ("Spiffy Roller Set projects", "*.srs"),
            ],
        )
        if not filename:
            return
        self.current_project_path = Path(filename)
        try:
            write_srs_project(self.current_project_path, self.set_data)
        except Exception as exc:
            messagebox.showerror(APP_TITLE, f"Could not save project:\n{exc}")
            return
        self._update_window_title()
        messagebox.showinfo(
            APP_TITLE,
            f"Project saved to:\n{self.current_project_path}",
        )

    def import_folder(self) -> None:
        folder = filedialog.askdirectory(title="Choose template folder")
        if not folder:
            return
        self.load_template(Path(folder))

    def import_zip(self) -> None:
        filename = filedialog.askopenfilename(
            title="Choose exported Spiffy Roller set",
            filetypes=[
                ("Spiffy Roller set archives", "*.set"),
                ("ZIP archives", "*.zip"),
                ("All files", "*.*"),
            ],
        )
        if not filename:
            return

        if self.import_tempdir is not None:
            self.import_tempdir.cleanup()
        self.import_tempdir = tempfile.TemporaryDirectory(prefix="dice_template_maker_")
        temp_root = Path(self.import_tempdir.name)

        try:
            with zipfile.ZipFile(filename, "r") as archive:
                archive.extractall(temp_root)
        except Exception as exc:
            messagebox.showerror(APP_TITLE, f"Could not extract ZIP:\n{exc}")
            return

        set_files = list(temp_root.rglob("set.json"))
        if not set_files:
            messagebox.showerror(APP_TITLE, "No set.json was found in the ZIP.")
            return
        self.load_template(set_files[0].parent)

    def load_template(self, folder: Path) -> None:
        try:
            set_path = folder / "set.json"
            set_json = json.loads(set_path.read_text(encoding="utf-8"))
        except Exception as exc:
            messagebox.showerror(APP_TITLE, f"Could not read set.json:\n{exc}")
            return

        model = SetData()
        model.id = str(set_json.get("id") or slugify(str(set_json.get("name", "dice_set"))))
        model.name = str(set_json.get("name") or model.id)
        model.extra = {
            key: value
            for key, value in set_json.items()
            if key not in {"format", "format_version", "id", "name", "rules", "dice"}
        }

        rules_name = str(set_json.get("rules") or "rules.json")
        rules_path = folder / rules_name
        if rules_path.exists():
            model.rules_text = rules_path.read_text(encoding="utf-8")
            try:
                manifest = json.loads(model.rules_text)
            except Exception:
                manifest = {}
            script_name = str(manifest.get("script") or "")
            script_path = folder / script_name if script_name else None
            if script_path is not None and script_path.exists():
                model.rules_script = script_path.read_text(encoding="utf-8")
            else:
                model.rules_script = DEFAULT_RULES_SCRIPT
        else:
            model.rules_text = SetData().rules_text
            model.rules_script = DEFAULT_RULES_SCRIPT

        model.dice = []
        for die_index, die_json in enumerate(set_json.get("dice", []), start=1):
            die = DieData()
            die.id = str(die_json.get("id") or f"die_{die_index}")
            die.name = str(die_json.get("name") or die.id)
            die.sides = int(die_json.get("sides") or len(die_json.get("faces", [])) or 6)
            die.shape = str(die_json.get("shape") or "d6")
            die.polygon_sides = int(die_json.get("polygon_sides") or 6)
            die.body_color = normalize_hex(str(die_json.get("body_color", "#294C78")), "#294C78")
            die.ink_color = normalize_hex(str(die_json.get("ink_color", "#FFFFFF")), "#FFFFFF")
            die.extra = {
                key: value
                for key, value in die_json.items()
                if key not in {
                    "id",
                    "name",
                    "sides",
                    "shape",
                    "polygon_sides",
                    "body_color",
                    "ink_color",
                    "faces",
                }
            }
            die.faces = []

            for face_index, face_json in enumerate(die_json.get("faces", []), start=1):
                face = FaceData()
                face.label = str(face_json.get("label", ""))
                face.value = face_json.get("value")
                face.display_mode = str(face_json.get("display_mode", "label"))
                face.image_mode = str(face_json.get("image_mode", "mask"))
                face.image_path = str(face_json.get("image", ""))
                face.body_color = str(face_json.get("body_color", ""))
                face.ink_color = str(face_json.get("ink_color", ""))
                face.symbols = {
                    str(key): int(value)
                    for key, value in (face_json.get("symbols") or {}).items()
                }
                face.extra = {
                    key: value
                    for key, value in face_json.items()
                    if key not in {
                        "label",
                        "value",
                        "image",
                        "image_mode",
                        "display_mode",
                        "body_color",
                        "ink_color",
                        "symbols",
                    }
                }

                if face.image_path:
                    asset_path = folder / face.image_path
                    if asset_path.exists():
                        try:
                            face.icon = IconData.from_image(asset_path)
                            face.icon.source_path = str(asset_path)
                        except Exception:
                            pass
                die.faces.append(face)

            die.resize_faces(die.sides)
            model.dice.append(die)

        if not model.dice:
            model.dice = [DieData()]

        self.set_data = model
        self.current_project_path = None
        self.import_root = folder
        self.load_model_into_ui()
        messagebox.showinfo(APP_TITLE, f"Imported template:\n{folder}")

    def load_model_into_ui(self) -> None:
        self.set_name_var.set(self.set_data.name)
        self.set_id_var.set(self.set_data.id)
        self.rules_text.delete("1.0", tk.END)
        self.rules_text.insert("1.0", self.set_data.rules_text)
        self.rules_script_text.delete("1.0", tk.END)
        self.rules_script_text.insert("1.0", self.set_data.rules_script)
        self.rebuild_die_tabs()
        self.notebook.select(self.general_tab)

    def export_folder(self) -> None:
        if not self.sync_model_from_ui():
            return
        parent = filedialog.askdirectory(title="Choose destination folder")
        if not parent:
            return

        destination = Path(parent) / self.set_data.id
        if destination.exists():
            if not messagebox.askyesno(
                APP_TITLE,
                f"{destination} already exists. Replace it?",
            ):
                return
            shutil.rmtree(destination)

        try:
            self.write_template(destination)
        except Exception as exc:
            messagebox.showerror(APP_TITLE, f"Export failed:\n{exc}")
            return
        messagebox.showinfo(APP_TITLE, f"Template exported to:\n{destination}")

    def export_zip(self) -> None:
        if not self.sync_model_from_ui():
            return
        filename = filedialog.asksaveasfilename(
            title="Export Spiffy Roller set archive",
            initialfile=f"{self.set_data.id}.set",
            defaultextension=".set",
            filetypes=[("Spiffy Roller set archives", "*.set")],
        )
        if not filename:
            return

        with tempfile.TemporaryDirectory(prefix="dice_template_export_") as temp:
            folder = Path(temp) / self.set_data.id
            try:
                self.write_template(folder)
                with zipfile.ZipFile(filename, "w", zipfile.ZIP_DEFLATED) as archive:
                    for path in folder.rglob("*"):
                        if path.is_file():
                            archive.write(path, path.relative_to(folder.parent))
            except Exception as exc:
                messagebox.showerror(APP_TITLE, f"Export failed:\n{exc}")
                return
        messagebox.showinfo(APP_TITLE, f"Template ZIP exported to:\n{filename}")

    def write_template(self, destination: Path) -> None:
        destination.mkdir(parents=True, exist_ok=True)
        icons_dir = destination / "icons"

        dice_json = []
        written_icons: dict[str, str] = {}
        for die_index, die in enumerate(self.set_data.dice, start=1):
            die_json = copy.deepcopy(die.extra)
            die_json.update(
                {
                    "id": die.id,
                    "name": die.name,
                    "sides": len(die.faces),
                    "shape": die.shape,
                    "body_color": die.body_color,
                    "ink_color": die.ink_color,
                }
            )
            if die.shape == "polygon":
                die_json["polygon_sides"] = die.polygon_sides

            faces_json = []
            for face_index, face in enumerate(die.faces, start=1):
                face_json = copy.deepcopy(face.extra)
                if face.label:
                    face_json["label"] = face.label
                if face.value is not None:
                    face_json["value"] = face.value
                if face.symbols:
                    face_json["symbols"] = face.symbols
                if face.body_color:
                    face_json["body_color"] = normalize_hex(face.body_color, die.body_color)
                if face.ink_color:
                    face_json["ink_color"] = normalize_hex(face.ink_color, die.ink_color)

                display_mode = getattr(face, "display_mode", "label")
                if display_mode not in FACE_DISPLAY_CHOICES:
                    display_mode = "label"
                face_json["display_mode"] = display_mode

                has_pixels = face.icon.has_visible_pixels()
                if has_pixels:
                    signature = face.icon.signature()
                    relative_path = written_icons.get(signature, "")
                    if not relative_path:
                        image_name = f"{die.id}_face_{face_index}.png"
                        relative_path = f"icons/{image_name}"
                        face.icon.save_png(icons_dir / image_name)
                        written_icons[signature] = relative_path
                    face.image_path = relative_path
                    face_json["image"] = relative_path
                    face_json["image_mode"] = ("mask" if face.icon.mode == "1-bit mask" else "indexed")
                elif face.image_path:
                    original = self.import_root / face.image_path if self.import_root else None
                    if original and original.exists():
                        destination_asset = destination / face.image_path
                        destination_asset.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(original, destination_asset)
                        face_json["image"] = face.image_path
                        face_json["image_mode"] = face.image_mode

                faces_json.append(face_json)

            die_json["faces"] = faces_json
            dice_json.append(die_json)

        set_json = copy.deepcopy(self.set_data.extra)
        set_json.update(
            {
                "format": "universal-dice-set",
                "format_version": 1,
                "id": self.set_data.id,
                "name": self.set_data.name,
                "rules": "rules.json",
                "dice": dice_json,
            }
        )

        (destination / "set.json").write_text(
            json.dumps(set_json, indent=2) + "\n",
            encoding="utf-8",
        )
        rules_object = json.loads(self.set_data.rules_text)
        (destination / "rules.json").write_text(
            json.dumps(rules_object, indent=2) + "\n",
            encoding="utf-8",
        )
        if rules_object.get("engine") == "lua":
            (destination / "rules.lua").write_text(
                self.set_data.rules_script.rstrip() + "\n",
                encoding="utf-8",
            )

    def show_about(self) -> None:
        messagebox.showinfo(
            APP_TITLE,
            (
                f"{APP_TITLE} {APP_VERSION}\n\n"
                "Repo for this software: https://github.com/candre23/SpiffyRoller_SetMaker \n\n"
                "Spiffy Roller firmware: https://github.com/candre23/SpiffyRoller \n\n"
                "Custom dice templates: https://github.com/candre23/SpiffyRoller_DiceSets \n\n\n"
                "Spiffy Roller Set Maker is public domain software\n"
                "No rights reserved\n"
                "Copyleft 2026\n"
            ),
        )

    def close_app(self) -> None:
        if self.import_tempdir is not None:
            self.import_tempdir.cleanup()
        self.destroy()


if __name__ == "__main__":
    app = TemplateMakerApp()
    app.mainloop()
