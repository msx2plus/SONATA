# CONVERTS S_MAP, S_COL, S_TILE, S_BG (unused layer) GRAPHICS TO ACS COLLISION DATA AND TEXTURE LUMP COMPOSITES
# SHOULD HAVE JUST PARSED PYXELEDIT'S XML EXPORT BUT HIGH COMPATABILITY IS NEAT
# DESTROYS YOUR CPU SORRY

import os
import hashlib
from PIL import Image

TILE_SIZE = 16
ROOM_WIDTH = 320
ROOM_HEIGHT = 224

def is_valid_tile(tile):
    extrema = tile.getextrema()
    return extrema[3][1] != 0

def is_empty(tile):
    pixels = tile.getdata()
    return all(p[:3] == (0, 0, 0) and p[3] == 255 for p in pixels)

def hash_tile(tile):
    return hashlib.md5(tile.tobytes()).hexdigest()

def get_tile_variants(tile):
    return [
        (tile, ""),
        (tile.transpose(Image.FLIP_LEFT_RIGHT), "FlipX"),
        (tile.transpose(Image.FLIP_TOP_BOTTOM), "FlipY"),
        (tile.transpose(Image.FLIP_LEFT_RIGHT).transpose(Image.FLIP_TOP_BOTTOM), "FlipX\nFlipY"),
    ]

def get_tiles(tile_image):
    tiles = []
    for y in range(0, tile_image.height, TILE_SIZE):
        for x in range(0, tile_image.width, TILE_SIZE):
            tile = tile_image.crop((x, y, x + TILE_SIZE, y + TILE_SIZE)).convert("RGBA")
            if not is_valid_tile(tile) or is_empty(tile):
                continue
            tiles.append(tile)
    return tiles

def class_tile(collide_img, x0, y0):
    block = collide_img.crop((x0, y0, x0 + TILE_SIZE, y0 + TILE_SIZE)).convert("RGB")
    pixels = block.getdata()
    if any(p == (0, 255, 0) for p in pixels): return "1"
    if any(p == (255, 0, 0) for p in pixels): return "2"
    if any(p == (0, 0, 255) for p in pixels): return "2"
    return "0"

def get_bgs(bg_img, total_rooms):
    backgrounds = {}
    bg_hash_to_name = {}
    for room_index in range(total_rooms):
        rx = room_index % (bg_img.width // ROOM_WIDTH)
        ry = room_index // (bg_img.width // ROOM_WIDTH)
        offset_x = rx * ROOM_WIDTH
        offset_y = ry * ROOM_HEIGHT
        room_bg = bg_img.crop((offset_x, offset_y, offset_x + ROOM_WIDTH, offset_y + ROOM_HEIGHT)).convert("RGBA")

        h = hash_tile(room_bg)
        if h in bg_hash_to_name:
            backgrounds[room_index] = bg_hash_to_name[h]
        else:
            bg_name = f"_SBG{len(bg_hash_to_name):03}"
            room_bg.save(f"{bg_name}.png")
            backgrounds[room_index] = bg_name
            bg_hash_to_name[h] = bg_name
    return backgrounds

def build_rooms(map_img, collide_img, base_tiles, backgrounds):
    rooms_x = map_img.width // ROOM_WIDTH
    rooms_y = map_img.height // ROOM_HEIGHT
    texture_tiles = []
    collision_tiles = []
    used_tile_ids = set()

    for room_index in range(rooms_x * rooms_y):
        rx = room_index % rooms_x
        ry = room_index // rooms_x
        offset_x = rx * ROOM_WIDTH
        offset_y = ry * ROOM_HEIGHT
        bg_patch_name = backgrounds.get(room_index, "_SBLACK")
        texture_patches = [f'']
        collide_data = []

        for y in range(ROOM_HEIGHT // TILE_SIZE):
            collide_row = []
            for x in range(ROOM_WIDTH // TILE_SIZE):
                px = offset_x + x * TILE_SIZE
                py = offset_y + y * TILE_SIZE
                tile = map_img.crop((px, py, px + TILE_SIZE, py + TILE_SIZE)).convert("RGBA")
                collision_val = class_tile(collide_img, px, py)
                collide_row.append(collision_val)

                if not is_valid_tile(tile) or is_empty(tile):
                    continue

                tile_h = hash_tile(tile)
                matched_id = None
                transform = ""

                for base_index, base_tile in enumerate(base_tiles):
                    for variant, tf in get_tile_variants(base_tile):
                        if hash_tile(variant) == tile_h:
                            matched_id = f"{base_index + 1:03}"
                            transform = tf
                            used_tile_ids.add(matched_id)
                            break
                    if matched_id:
                        break

                if matched_id:
                    tile_name = f"_ST{matched_id}"
                    patch = f'\tPatch "{tile_name}", {x * TILE_SIZE}, {y * TILE_SIZE}'
                    if transform:
                        patch += "\n\t{\n\t\t" + "\n\t\t".join(transform.split()) + "\n\t}"
                    texture_patches.append(patch)

            if collide_row:
                collide_data.append(",".join(collide_row))

        texture_tiles.append((room_index, texture_patches))
        collision_tiles.append((room_index, collide_data))

    return used_tile_ids, texture_tiles, collision_tiles

def save_outputs(used_tile_ids, base_tiles, texture_tiles, collision_tiles):

    with open("TEXTURES.SN1", "w") as tex:
        for room_index, patches in texture_tiles:
            room_id = str(room_index)
            tex.write(f'Graphic "_SRM{room_id}", 320, 224 // ROOM {room_id}\n')
            tex.write("{\n")
            for patch in patches:
                tex.write(f"{patch}\n")
            tex.write("}\n\n")

    for file in os.listdir():
        if file.startswith("_ST") and file.endswith(".png"):
            os.remove(file)

    for tid in used_tile_ids:
        index = int(tid) - 1
        if 0 <= index < len(base_tiles):
            tile = base_tiles[index]
            if is_empty(tile):
                continue
            tile.save(f"_ST{tid}.png")

    row_count = ROOM_HEIGHT // TILE_SIZE
    col_count = ROOM_WIDTH // TILE_SIZE
    total_per_room = row_count * col_count
    room_count = len(collision_tiles)

    with open("SONATA.ACS", "w") as acs:
        acs.write(f"int screenDB[{room_count}][{total_per_room}] =\n{{\n")
        for room_index, rows in collision_tiles:
            acs.write(f"\t// ROOM {str(room_index).zfill(2)}\n")
            acs.write("\t{\n")
            for row in rows:
                acs.write(f"\t\t{row},\n")
            acs.write("\t},\n")
        acs.write("};\n")

def main():
    tiles_img = Image.open("S_TILE.PNG").convert("RGBA")
    map_img = Image.open("S_MAP.PNG").convert("RGBA")
    collide_img = Image.open("S_COL.PNG").convert("RGBA")
    bg_img = Image.open("S_BG.PNG").convert("RGBA")

    base_tiles = get_tiles(tiles_img)
    total_rooms = (map_img.width // ROOM_WIDTH) * (map_img.height // ROOM_HEIGHT)
    backgrounds = get_bgs(bg_img, total_rooms)
    used_tile_ids, texture_tiles, collision_tiles = build_rooms(map_img, collide_img, base_tiles, backgrounds)
    save_outputs(used_tile_ids, base_tiles, texture_tiles, collision_tiles)

if __name__ == "__main__":
    main()
