import copy
import json
import math
import os
import re
import shutil
from PIL import Image
from urllib.request import urlopen
from urllib.error import URLError, HTTPError

# import from subfolder 'modules'
from modules.gui import App

# cloud service specifics
import cloudinary
import cloudinary.api
import cloudinary.uploader


def load_json_file(file_name):
    """Opens a JSON file in the script_dir"""
    file_path = os.path.join(script_dir, file_name)
    with open(file_path) as file:
        return json.load(file)


def get_card_json(adb_id, data):
    """Create a JSON object for a card"""
    deck_id = data["deck_id"]
    card_id = data["card_id"]
    sheet_param = sheet_parameters[deck_id]
    
    # Check if 'uploaded_url' exists in sheet_parameters
    if "uploaded_url" not in sheet_param:
        if reported_missing_url.get(deck_id, False):
            print(f"Didn't find URL for sheet {deck_id}")
            reported_missing_url[deck_id] = True
        raise ValueError("uploaded_url not found in sheet_parameters")
    
    # create Json element
    new_card = copy.deepcopy(card_template)
    
    # collect data for card
    translated_name = get_translated_name(adb_id)
    face_url = sheet_param["uploaded_url"]
    h, w = sheet_param["grid_size"]
    
    if data["double_sided"] == False:
        unique_back = False
        back_url = player_card_back_url
    else:
        unique_back = False
        back_url = find_back_url(adb_id)
        
        if back_url == "ERROR":
            if reported_missing_url.get(deck_id, False):
                print(f"Didn't find back URL for sheet {deck_id}")
                reported_missing_url[deck_id] = True
            raise ValueError("uploaded_url not found in sheet_parameters")
        
    new_card["GMNotes"] = adb_id
    new_card["Nickname"] = translated_name
    new_card["CardID"] = f"{deck_id}{card_id:02}"
    new_card["CustomDeck"][f"{deck_id}"] = {
        "FaceURL": face_url,
        "BackURL": back_url,
        "NumWidth": w,
        "NumHeight": h,
        "BackIsHidden": True,
        "UniqueBack": unique_back,
        "Type": 0
    }
    return new_card


def get_arkhamdb_id(current_path, file):
    """Constructs the ArkhamDB ID"""
    folder_name = os.path.basename(current_path)
    file_name = os.path.splitext(file)[0]
        
    # assume that file names with at least 5 digits are valid ArkhamDB IDs
    if len(file_name) < 5:
        # if filename isn't already a full adb_id, construct it from folder name + file name
        zero_count = 5 - len(folder_name) - sum(c.isdigit() for c in file_name)
        if zero_count < 0:
            print(f"Error getting ID for {os.path.join(current_path, file)}")
            return "ERROR"
        return f"{folder_name}{'0'*zero_count}{file_name}"
    return file_name


def create_decksheet(img_path_list, grid_size, img_w, img_h, output_path):
    """Stitches the provided images together to deck sheet"""
    rows, cols = grid_size

    # Create a blank canvas for the grid
    grid_image = Image.new("RGB", (cols * img_w, rows * img_h))

    # Paste each image onto the canvas
    for index, img_path in enumerate(img_path_list):
        try:
            with Image.open(img_path) as img:
                img = img.resize((img_w, img_h))
                row = index // cols
                col = index % cols
                position = (col * img_w, row * img_h)
                grid_image.paste(img, position)
        except IOError:
            print(f"Error opening image {img_path}")
            continue

    # Save the final grid image with initial quality cfg
    quality = cfg["img_quality"]
    grid_image.save(output_path, quality=quality, optimize=True)

    # Check the file size
    file_size = os.path.getsize(output_path)

    # Adjust quality until the file size is within the limit
    while file_size > cfg["img_max_byte"] and quality > cfg["img_quality_reduce"]:
        reduction_ratio = cfg["img_max_byte"] / file_size
        quality = int(quality * reduction_ratio)
        print(f"File too big ({file_size} B). Running again with quality = {quality} %")
        try:
            grid_image.save(output_path, quality=quality, optimize=True)
        except IOError:
            print("Error saving image")
            return None
        file_size = os.path.getsize(output_path)
    return output_path


def upload_file(online_name, file_path):
    """Uploads a file if it isn't already uploaded."""
    
    # check if the file is already uploaded
    try:
        result = cloudinary.Search().expression(online_name).max_results("1").execute()
        if result["total_count"] == 1:
            print(f"{online_name} - already uploaded")
            return result["resources"][0]["secure_url"]
    except Exception as e:
        print(f"Error when checking if file exists: {e}")

    # upload the file since it wasn't found in the cloud
    print(f"{online_name} - uploading")
    try:
        result = cloudinary.uploader.upload(
            file_path,
            folder=f"AH LCG - {cfg['locale'].upper()}",
            public_id=online_name,
        )
        return result["secure_url"]
    except Exception as e:
        print(f"Error when uploading file: {e}")


def get_translated_name(adb_id):
    """Get the translated card name from ArkhamDB"""
    try:
        response = urlopen(arkhamdb_url + adb_id)
    except HTTPError as e:
        print(f"Couldn't get translated name for ID: {adb_id} (HTTP {e.code})")
        return adb_id
    except URLError as e:
        print(f"Couldn't get translated name for ID: {adb_id} (URL {e.reason})")
        return adb_id

    try:
        data_json = json.loads(response.read())
    except json.JSONDecodeError:
        print(f"Couldn't parse JSON for ID: {adb_id}")
        return adb_id

    try:
        return data_json["name"]
    except KeyError:
        print(f"JSON for ID: {adb_id} did not contain 'name' key")
        return adb_id


def escape_lua_file(file_path):
    """Escapes the script from a Lua file to be included in JSON."""
    try:
        with open(file_path, 'r') as file:
            lua_str = file.read()
    except (FileNotFoundError, OSError) as e:
        return str(e)

    # Python's built-in functions can handle all required escape sequences
    return json.dumps(lua_str)

def find_back_url(adb_id):
    """Finds the URL of the sheet that has the cardbacks for the provided ID."""
    for _, data in sheet_parameters.items():
        if data["sheet_type"] == "back" and is_URL_contained(adb_id, data["start_id"], data["end_id"]):
            if "uploaded_url" in data:
                return data["uploaded_url"]
            else:
                return "ERROR"

def is_URL_contained(adb_id, start_id, end_id):
    """Returns true if the ArkhamDB ID is part of this range."""
    return sort_key(start_id) <= sort_key(adb_id) <= sort_key(end_id)

def process_cards(card_list, sheet_type):
    """Processes a list of cards and collects the data for the decksheet creation."""
    global last_cycle_id, last_id, card_id, deck_id, sheet_parameters

    for adb_id, data in card_list:
        # we're just starting out or got to a new cycle or have to start a new sheet
        if (
            last_cycle_id == 0
            or last_cycle_id != data["cycle_id"]
            or card_id == (cfg["img_count_per_sheet"] - 1)
        ):
            # add end index to last parameter
            if deck_id != 0:
                sheet_parameters[deck_id]["end_id"] = last_id

            deck_id += 1
            card_id = 0

            # initialize dictionary
            sheet_parameters[deck_id] = {"img_path_list": [], "start_id": adb_id, "sheet_type": sheet_type}
        else:
            card_id += 1

        # store information for next iteration
        last_cycle_id = data["cycle_id"]
        last_id = adb_id

        # add image to list
        sheet_parameters[deck_id]["img_path_list"].append(data["file_path"])
        
        # add data to sheet
        data["deck_id"] = deck_id
        data["card_id"] = card_id

    # Add end index for the last sheet
    if deck_id != 0:
        sheet_parameters[deck_id]["end_id"] = last_id
        
        
def sort_key(item):
    """sort function for the card index"""
    key = item[0]
    
    # regular expression to match the pattern
    pattern = r'^(\d{5})([a-z])?(?:-([a-z]\d+))?$'
    match = re.match(pattern, key)
    
    if match:
        number = match.group(1)  # 5-digit part
        letter = match.group(2) or ''  # optional letter appendix
        suffix = match.group(3) or ''  # optional suffix
        
        # return a tuple for sorting
        return (number, letter, suffix)
    else:
        # fallback for any items that don't match the expected pattern
        return (key,)
    
# -----------------------------------------------------------
# main script
# -----------------------------------------------------------

# open the main window to collect data
form = App()

# get data from form
cfg = form.get_values()

# use TTS' saved objects folder as default output folder
output_folder = os.path.join(
    os.environ["USERPROFILE"],
    "Documents",
    "My Games",
    "Tabletop Simulator",
    "Saves",
    "Saved Objects"
)

# probably don't need to change these
player_card_back_url = "https://steamusercontent-a.akamaihd.net/ugc/2342503777940352139/A2D42E7E5C43D045D72CE5CFC907E4F886C8C690/"
bag_template = "TTSBagTemplate.json"
arkhamdb_url = f"https://{cfg["locale"].lower()}.arkhamdb.com/api/public/card/"
script_dir = os.path.dirname(__file__)

# cloudinary api settings
cloudinary.config(
    cloud_name=cfg["cloud_name"],
    api_key=cfg["api_key"],
    api_secret=cfg["api_secret"],
)

# keep track of the deckIds that the missing URL was reported for
reported_missing_url = {}

# process input files
card_index = {}
for current_path, directories, files in os.walk(cfg["source_folder"]):
    print(f"Processing folder: {current_path}")
    for file in files:
        adb_id = get_arkhamdb_id(current_path, file)

        # skip this file because we don't have a proper ArkhamDB ID for it
        if adb_id == "ERROR":
            continue
        
        # check if a face for this card is already added to the index and mark it as double-sided
        double_sided = False
        if adb_id.endswith('b'):
            face_id = adb_id[:-1]
            
            if face_id in card_index:
                double_sided = True
                card_index[face_id]["double_sided"] = True

        # add card to index
        card_index[adb_id] = {
            "cycle_id": int(adb_id[:2]),
            "file_path": os.path.join(current_path, file),
            "double_sided": double_sided
        }

# sort the card index (numbers first, than by letter appendix)    
card_index = dict(sorted(card_index.items(), key=sort_key))

# loop through index and collect data for decksheets
single_sided_cards = []
double_sided_cards_front = []
double_sided_cards_back = []

# separate single-sided and double-sided cards
for adb_id, data in card_index.items():
    if data["double_sided"] == True:
        if adb_id.endswith('b'):
            double_sided_cards_back.append((adb_id, data))
        else:
            double_sided_cards_front.append((adb_id, data))
    else:
        single_sided_cards.append((adb_id, data))

# process cards
last_cycle_id, last_id, card_id, deck_id = 0, 0, 0, 0
sheet_parameters = {}

process_cards(single_sided_cards, "single")
process_cards(double_sided_cards_front, "front")
process_cards(double_sided_cards_back, "back")

# create temp folder for decksheets
temp_path = os.path.join(script_dir, "temp")
if os.path.exists(temp_path):
    shutil.rmtree(temp_path)
os.mkdir(temp_path)

# create decksheets with previously collected information
for deck_id, data in sheet_parameters.items():
    card_count = len(data["img_path_list"])
    images_per_row = 10

    # if there is just a single row of images, shrink the grid
    if card_count < images_per_row:
        images_per_row = card_count

    grid_size = (math.ceil(card_count / 10), images_per_row)
    online_name = f"Sheet{cfg["locale"].upper()}{data["start_id"]}-{data["end_id"]}"
    sheet_name = f"{online_name}.jpg"

    print(f"{online_name} - creation")
    sheet_path = create_decksheet(
        data["img_path_list"],
        grid_size,
        cfg["img_w"],
        cfg["img_h"],
        os.path.join(temp_path, sheet_name),
    )

    data["uploaded_url"] = upload_file(online_name, sheet_path)
    data["grid_size"] = grid_size

    if deck_id >= cfg["max_sheet_count"]:
        break

# load the bag template and update it
bag_name = "Translated Cards - " + cfg["locale"].upper()
bag = load_json_file(bag_template)
card_template = bag["ObjectStates"][0]["ContainedObjects"][0]
bag["ObjectStates"][0]["Nickname"] = bag_name
bag["ObjectStates"][0]["ContainedObjects"] = []
bag["ObjectStates"][0]["LuaScript"] = escape_lua_file("TTSBagLuaScript.lua")

# loop cards and add them to bag
print("Creating output file.")
for adb_id, data in card_index.items():
    # skip card backs of double-sided cards
    if not adb_id.endswith('b'):
        card_json = get_card_json(adb_id, data)
        if card_json != "ERROR":
            bag["ObjectStates"][0]["ContainedObjects"].append(card_json)

# output the bag with translated cards
bag_path = os.path.join(output_folder, f"{bag_name}.json")
with open(bag_path, "w", encoding="utf8") as f:
    json.dump(bag, f, ensure_ascii=False, indent=2)
print("Successfully created output file.")

# remove temp folder
if not cfg["keep_temp_folder"] and os.path.exists(temp_path):
    print("Removing temp folder.")
    shutil.rmtree(temp_path)
