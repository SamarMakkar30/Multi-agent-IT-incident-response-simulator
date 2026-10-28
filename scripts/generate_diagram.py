"""Generate docs/architecture.png using Python standard library (offline, zero-dependency)."""

import struct
import zlib
from pathlib import Path

# 5x7 bitmap font for ASCII 32..126
FONT_5X7: dict[str, list[str]] = {
    "A": ["01110", "10001", "10001", "11111", "10001", "10001", "10001"],
    "B": ["11110", "10001", "10001", "11110", "10001", "10001", "11110"],
    "C": ["01111", "10000", "10000", "10000", "10000", "10000", "01111"],
    "D": ["11110", "10001", "10001", "10001", "10001", "10001", "11110"],
    "E": ["11111", "10000", "10000", "11110", "10000", "10000", "11111"],
    "F": ["11111", "10000", "10000", "11110", "10000", "10000", "10000"],
    "G": ["01111", "10000", "10000", "10011", "10001", "10001", "01111"],
    "H": ["10001", "10001", "10001", "11111", "10001", "10001", "10001"],
    "I": ["11111", "00100", "00100", "00100", "00100", "00100", "11111"],
    "J": ["00111", "00010", "00010", "00010", "00010", "10010", "01100"],
    "K": ["10001", "10010", "10100", "11000", "10100", "10010", "10001"],
    "L": ["10000", "10000", "10000", "10000", "10000", "10000", "11111"],
    "M": ["10001", "11011", "10101", "10101", "10001", "10001", "10001"],
    "N": ["10001", "11001", "10101", "10011", "10001", "10001", "10001"],
    "O": ["01110", "10001", "10001", "10001", "10001", "10001", "01110"],
    "P": ["11110", "10001", "10001", "11110", "10000", "10000", "10000"],
    "Q": ["01110", "10001", "10001", "10001", "10101", "10010", "01101"],
    "R": ["11110", "10001", "10001", "11110", "10100", "10010", "10001"],
    "S": ["01111", "10000", "10000", "01110", "00001", "00001", "11110"],
    "T": ["11111", "00100", "00100", "00100", "00100", "00100", "00100"],
    "U": ["10001", "10001", "10001", "10001", "10001", "10001", "01110"],
    "V": ["10001", "10001", "10001", "10001", "10001", "01010", "00100"],
    "W": ["10001", "10001", "10001", "10101", "10101", "11011", "10001"],
    "X": ["10001", "10001", "01010", "00100", "01010", "10001", "10001"],
    "Y": ["10001", "10001", "01010", "00100", "00100", "00100", "00100"],
    "Z": ["11111", "00001", "00010", "00100", "01000", "10000", "11111"],
    "a": ["00000", "01110", "00001", "01111", "10001", "10001", "01111"],
    "b": ["10000", "10000", "11110", "10001", "10001", "10001", "11110"],
    "c": ["00000", "01110", "10001", "10000", "10000", "10001", "01110"],
    "d": ["00001", "00001", "01111", "10001", "10001", "10001", "01111"],
    "e": ["00000", "01110", "10001", "11111", "10000", "10001", "01110"],
    "f": ["00110", "01001", "01000", "11100", "01000", "01000", "01000"],
    "g": ["00000", "01111", "10001", "10001", "01111", "00001", "01110"],
    "h": ["10000", "10000", "11110", "10001", "10001", "10001", "10001"],
    "i": ["00100", "00000", "01100", "00100", "00100", "00100", "01110"],
    "j": ["00010", "00000", "00110", "00010", "00010", "10010", "01100"],
    "k": ["10000", "10000", "10010", "10100", "11000", "10100", "10010"],
    "l": ["01100", "00100", "00100", "00100", "00100", "00100", "01110"],
    "m": ["00000", "11010", "10101", "10101", "10101", "10101", "10001"],
    "n": ["00000", "11110", "10001", "10001", "10001", "10001", "10001"],
    "o": ["00000", "01110", "10001", "10001", "10001", "10001", "01110"],
    "p": ["00000", "11110", "10001", "10001", "11110", "10000", "10000"],
    "q": ["00000", "01111", "10001", "10001", "01111", "00001", "00001"],
    "r": ["00000", "10110", "11001", "10000", "10000", "10000", "10000"],
    "s": ["00000", "01111", "10000", "01110", "00001", "00001", "11110"],
    "t": ["01000", "01000", "11100", "01000", "01000", "01001", "00110"],
    "u": ["00000", "10001", "10001", "10001", "10001", "10011", "01101"],
    "v": ["00000", "10001", "10001", "10001", "10001", "01010", "00100"],
    "w": ["00000", "10001", "10001", "10101", "10101", "11011", "10001"],
    "x": ["00000", "10001", "01010", "00100", "01010", "10001", "10001"],
    "y": ["00000", "10001", "10001", "01111", "00001", "00010", "01100"],
    "z": ["00000", "11111", "00010", "00100", "01000", "10000", "11111"],
    "0": ["01110", "10001", "10011", "10101", "11001", "10001", "01110"],
    "1": ["00100", "01100", "00100", "00100", "00100", "00100", "01110"],
    "2": ["01110", "10001", "00001", "00110", "01000", "10000", "11111"],
    "3": ["11110", "00001", "00001", "01110", "00001", "00001", "11110"],
    "4": ["00010", "00110", "01010", "10010", "11111", "00010", "00010"],
    "5": ["11111", "10000", "11110", "00001", "00001", "10001", "01110"],
    "6": ["00110", "01000", "10000", "11110", "10001", "10001", "01110"],
    "7": ["11111", "00001", "00010", "00100", "01000", "01000", "01000"],
    "8": ["01110", "10001", "10001", "01110", "10001", "10001", "01110"],
    "9": ["01110", "10001", "10001", "01111", "00001", "00010", "01100"],
    "-": ["00000", "00000", "00000", "11111", "00000", "00000", "00000"],
    "+": ["00000", "00100", "00100", "11111", "00100", "00100", "00000"],
    "=": ["00000", "11111", "00000", "11111", "00000", "00000", "00000"],
    "(": ["00010", "00100", "01000", "01000", "01000", "00100", "00010"],
    ")": ["01000", "00100", "00010", "00010", "00010", "00100", "01000"],
    "[": ["01110", "01000", "01000", "01000", "01000", "01000", "01110"],
    "]": ["01110", "00010", "00010", "00010", "00010", "00010", "01110"],
    ":": ["00000", "00100", "00000", "00000", "00100", "00000", "00000"],
    ";": ["00000", "00100", "00000", "00000", "00100", "00100", "01000"],
    ",": ["00000", "00000", "00000", "00000", "00100", "00100", "01000"],
    ".": ["00000", "00000", "00000", "00000", "00000", "00100", "00000"],
    ">": ["10000", "01000", "00100", "00010", "00100", "01000", "10000"],
    "<": ["00001", "00010", "00100", "01000", "00100", "00010", "00001"],
    "/": ["00001", "00010", "00100", "01000", "10000", "00000", "00000"],
    "|": ["00100", "00100", "00100", "00100", "00100", "00100", "00100"],
    " ": ["00000", "00000", "00000", "00000", "00000", "00000", "00000"],
}


class Canvas:
    def __init__(self, width: int, height: int, bg=(245, 247, 250)):
        self.width = width
        self.height = height
        self.pixels = bytearray(width * height * 4)
        for i in range(width * height):
            self.pixels[i * 4] = bg[0]
            self.pixels[i * 4 + 1] = bg[1]
            self.pixels[i * 4 + 2] = bg[2]
            self.pixels[i * 4 + 3] = 255

    def set_pixel(self, x: int, y: int, r: int, g: int, b: int, a: int = 255):
        if 0 <= x < self.width and 0 <= y < self.height:
            idx = (y * self.width + x) * 4
            self.pixels[idx] = r
            self.pixels[idx + 1] = g
            self.pixels[idx + 2] = b
            self.pixels[idx + 3] = a

    def draw_rect(self, x: int, y: int, w: int, h: int, fill, border=(30, 41, 59), border_w=2):
        # fill
        for cy in range(y, y + h):
            for cx in range(x, x + w):
                self.set_pixel(cx, cy, fill[0], fill[1], fill[2])
        # border
        for bw in range(border_w):
            for cx in range(x, x + w):
                self.set_pixel(cx, y + bw, border[0], border[1], border[2])
                self.set_pixel(cx, y + h - 1 - bw, border[0], border[1], border[2])
            for cy in range(y, y + h):
                self.set_pixel(x + bw, cy, border[0], border[1], border[2])
                self.set_pixel(x + w - 1 - bw, cy, border[0], border[1], border[2])

    def draw_text(self, text: str, x: int, y: int, color=(15, 23, 42), scale: int = 2):
        cursor_x = x
        for ch in text:
            glyph = FONT_5X7.get(ch, FONT_5X7[" "])
            for r_idx, row in enumerate(glyph):
                for c_idx, val in enumerate(row):
                    if val == "1":
                        for sy in range(scale):
                            for sx in range(scale):
                                self.set_pixel(
                                    cursor_x + c_idx * scale + sx,
                                    y + r_idx * scale + sy,
                                    color[0],
                                    color[1],
                                    color[2],
                                )
            cursor_x += (5 + 1) * scale

    def draw_line(self, x1: int, y1: int, x2: int, y2: int, color=(71, 85, 105), width=2):
        dx = abs(x2 - x1)
        dy = abs(y2 - y1)
        sx = 1 if x1 < x2 else -1
        sy = 1 if y1 < y2 else -1
        err = dx - dy
        cx, cy = x1, y1
        while True:
            for wx in range(-width // 2, width // 2 + 1):
                for wy in range(-width // 2, width // 2 + 1):
                    self.set_pixel(cx + wx, cy + wy, color[0], color[1], color[2])
            if cx == x2 and cy == y2:
                break
            e2 = 2 * err
            if e2 > -dy:
                err -= dy
                cx += sx
            if e2 < dx:
                err += dx
                cy += sy

    def save_png(self, path: Path):
        raw = bytearray()
        for y in range(self.height):
            raw.append(0)
            start = y * self.width * 4
            raw.extend(self.pixels[start : start + self.width * 4])

        def chunk(tag: bytes, data: bytes) -> bytes:
            crc = zlib.crc32(tag + data)
            return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)

        header = b"\x89PNG\r\n\x1a\n"
        ihdr = struct.pack(">IIBBBBB", self.width, self.height, 8, 6, 0, 0, 0)
        idat = zlib.compress(bytes(raw), 9)
        png_data = header + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")
        path.write_bytes(png_data)


def main():
    w, h = 1200, 750
    c = Canvas(w, h, bg=(248, 250, 252))

    # Title Banner
    c.draw_rect(20, 20, 1160, 50, fill=(30, 41, 59), border=(15, 23, 42), border_w=2)
    c.draw_text(
        "IT INCIDENT RESPONSE WAR-ROOM: BLACKBOARD ARCHITECTURE",
        40,
        36,
        color=(255, 255, 255),
        scale=2,
    )

    # 1. Alert Box
    c.draw_rect(40, 140, 180, 70, fill=(254, 243, 199), border=(217, 119, 6), border_w=2)
    c.draw_text("Alert Payload", 55, 155, color=(146, 64, 14), scale=2)
    c.draw_text("JSON Webhook", 55, 175, color=(146, 64, 14), scale=2)

    # Arrow Alert -> Alert Agent
    c.draw_line(220, 175, 270, 175, color=(100, 116, 139), width=2)

    # 2. Alert Agent
    c.draw_rect(270, 140, 180, 70, fill=(224, 231, 255), border=(79, 70, 229), border_w=2)
    c.draw_text("Alert Agent", 295, 155, color=(49, 46, 129), scale=2)
    c.draw_text("SEV Score / Meta", 285, 175, color=(49, 46, 129), scale=2)

    # Arrow Alert Agent -> Incident Board
    c.draw_line(450, 175, 520, 175, color=(79, 70, 229), width=3)
    c.draw_text("incident_signal", 420, 125, color=(79, 70, 229), scale=1)

    # 3. Incident Board (Blackboard Centerpiece)
    c.draw_rect(520, 100, 260, 530, fill=(241, 245, 249), border=(30, 41, 59), border_w=3)
    c.draw_rect(530, 110, 240, 40, fill=(15, 23, 42), border=(15, 23, 42), border_w=1)
    c.draw_text("SHARED INCIDENT BOARD", 540, 122, color=(255, 255, 255), scale=2)

    c.draw_text("- Append-Only Posts", 540, 170, color=(51, 65, 85), scale=2)
    c.draw_text("- Monotonic Seq Lock", 540, 205, color=(51, 65, 85), scale=2)
    c.draw_text("- Author-Bound Handles", 540, 240, color=(51, 65, 85), scale=2)
    c.draw_text("- Matrix Permission Check", 540, 275, color=(51, 65, 85), scale=2)
    c.draw_text("- Zero Cross-Agent Calls", 540, 310, color=(51, 65, 85), scale=2)
    c.draw_text("- Untrusted Data Flags", 540, 345, color=(51, 65, 85), scale=2)
    c.draw_text("- Injected Clock Ts", 540, 380, color=(51, 65, 85), scale=2)
    c.draw_text("- Post ID References", 540, 415, color=(51, 65, 85), scale=2)

    # 4. Round 1: Logs Agent & Dependency Agent
    # Logs Agent
    c.draw_rect(840, 110, 190, 70, fill=(220, 252, 231), border=(22, 163, 74), border_w=2)
    c.draw_text("Logs Agent", 870, 125, color=(20, 83, 45), scale=2)
    c.draw_text("search/signatures", 855, 145, color=(20, 83, 45), scale=2)

    # Arrow Board <-> Logs Agent
    c.draw_line(780, 145, 840, 145, color=(22, 163, 74), width=3)
    c.draw_text("log_finding", 790, 130, color=(22, 163, 74), scale=1)

    # Dependency Agent
    c.draw_rect(840, 200, 190, 70, fill=(220, 252, 231), border=(22, 163, 74), border_w=2)
    c.draw_text("Dependency Agent", 850, 215, color=(20, 83, 45), scale=2)
    c.draw_text("topology/blast radius", 845, 235, color=(20, 83, 45), scale=2)

    # Arrow Board <-> Dependency Agent
    c.draw_line(780, 235, 840, 235, color=(22, 163, 74), width=3)
    c.draw_text("dependency_finding", 785, 220, color=(22, 163, 74), scale=1)

    # 5. Round 2: Mitigation Agent
    c.draw_rect(840, 300, 190, 75, fill=(254, 240, 138), border=(202, 138, 4), border_w=2)
    c.draw_text("Mitigation Agent", 855, 315, color=(113, 63, 18), scale=2)
    c.draw_text("BM25 RAG & Memory", 850, 335, color=(113, 63, 18), scale=2)

    # Arrow Board <-> Mitigation Agent
    c.draw_line(780, 340, 840, 340, color=(202, 138, 4), width=3)
    c.draw_text("mitigation_proposal", 785, 325, color=(202, 138, 4), scale=1)

    # 6. Round 3: Incident Commander
    c.draw_rect(840, 410, 200, 85, fill=(254, 202, 202), border=(220, 38, 38), border_w=2)
    c.draw_text("Incident Commander", 845, 425, color=(153, 27, 27), scale=2)
    c.draw_text("Decide from evidence", 845, 445, color=(153, 27, 27), scale=2)
    c.draw_text("Deterministic timeline", 845, 465, color=(153, 27, 27), scale=2)

    # Arrow Board <-> Commander
    c.draw_line(780, 450, 840, 450, color=(220, 38, 38), width=3)
    c.draw_text("decision/timeline", 785, 435, color=(220, 38, 38), scale=1)

    # Escalation to Human on-call
    c.draw_rect(1060, 415, 120, 70, fill=(243, 244, 246), border=(107, 114, 128), border_w=2)
    c.draw_text("Human", 1085, 430, color=(31, 41, 55), scale=2)
    c.draw_text("On-Call", 1080, 450, color=(31, 41, 55), scale=2)
    c.draw_line(1040, 450, 1060, 450, color=(220, 38, 38), width=2)

    # 7. Round 4: Comms Agent
    c.draw_rect(840, 520, 190, 70, fill=(233, 213, 255), border=(147, 51, 234), border_w=2)
    c.draw_text("Comms Agent", 870, 535, color=(88, 28, 135), scale=2)
    c.draw_text("Status update draft", 855, 555, color=(88, 28, 135), scale=2)

    # Arrow Board <-> Comms Agent
    c.draw_line(780, 555, 840, 555, color=(147, 51, 234), width=3)
    c.draw_text("status_update", 790, 540, color=(147, 51, 234), scale=1)

    # 8. Append-Only Run Log
    c.draw_rect(100, 480, 320, 130, fill=(241, 245, 249), border=(30, 41, 59), border_w=2)
    c.draw_text("APPEND-ONLY RUN LOG", 120, 500, color=(15, 23, 42), scale=2)
    c.draw_text("- SHA-256 Hash Chain", 120, 530, color=(71, 85, 105), scale=2)
    c.draw_text("- logs/run_log.jsonl", 120, 555, color=(71, 85, 105), scale=2)
    c.draw_text("- verify_chain() Audit", 120, 580, color=(71, 85, 105), scale=2)

    # Arrow Board -> Run Log
    c.draw_line(520, 550, 420, 550, color=(30, 41, 59), width=2)
    c.draw_text("append events", 430, 535, color=(30, 41, 59), scale=1)

    # Save to docs/architecture.png
    out_path = Path("docs/architecture.png")
    c.save_png(out_path)
    print(f"Saved {out_path} ({out_path.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
