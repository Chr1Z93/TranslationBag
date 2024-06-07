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

# open the main window to collect data
form = App()

# get data from form
cfg = form.get_values()

# use TTS' saved objects folder as default output folder
output_folder = (
    os.environ["USERPROFILE"]
    + r"\Documents\My Games\Tabletop Simulator\Saves\Saved Objects"
)

# probably don't need to change these
bag_template = "TTSBagTemplate.json"
arkhamdb_url = f"https://{cfg["locale"].lower()}.arkhamdb.com/api/public/card/"
script_dir = os.path.dirname(__file__)

cloudinary.config(
    cloud_name=cfg["cloud_name"],
    api_key=cfg["api_key"],
    api_secret=cfg["api_secret"],
)

# keep track of the deckIds that the missing URL was reported for
reported_missing_url = {}


# opens a JSON file in the script_dir
def load_json_file(file_name):
    file_path = os.path.join(script_dir, file_name)
    with open(file_path) as file:
        return json.load(file)


# create card json
def get_card_json(adb_id, data):
    if "uploaded_url" not in sheet_parameters[int(data["deck_id"])]:
        if reported_missing_url.get(data["deck_id"], False):
            print(f"Didn't find URL for sheet {data["deck_id"]}")
            reported_missing_url[data["deck_id"]] = True
        return "ERROR"

    # collect data for card
    translated_name = get_translated_name(adb_id)
    uploaded_url = sheet_parameters[int(data["deck_id"])]["uploaded_url"]
    h, w = sheet_parameters[int(data["deck_id"])]["grid_size"]

    # create Json element
    new_card = copy.deepcopy(card_template)
    back_url = new_card["CustomDeck"]["123"]["BackURL"]
    new_card["Nickname"] = translated_name
    new_card["CardID"] = data["card_id"]
    new_card["CustomDeck"][data["deck_id"]] = new_card["CustomDeck"].pop("123")
    new_card["CustomDeck"][data["deck_id"]]["FaceURL"] = uploaded_url
    new_card["CustomDeck"][data["deck_id"]]["BackURL"] = back_url
    new_card["CustomDeck"][data["deck_id"]]["NumWidth"] = w
    new_card["CustomDeck"][data["deck_id"]]["NumHeight"] = h
    new_card["GMNotes"] = adb_id
    return new_card


# constructs the ArkhamDB ID
def get_arkhamdb_id(folder_name, file_name):
    # if filename isn't already a full adb_id, construct it
    if len(file_name) < 5:
        zero_count = 5 - len(folder_name) - sum(c.isdigit() for c in file_name)
        if zero_count < 0:
            print(f"Error getting ID for {os.path.join(subdir, file)}")
            return "ERROR"
        else:
            return f"{folder_name}{'0'*zero_count}{file_name}"
    else:
        return file_name


# only get numbers from string
def extract_numbers(string):
    numbers = re.findall(r"\d+", string)
    return "".join(numbers)


def create_decksheet(img_path_list, grid_size, img_w, img_h, output_path):
    rows, cols = grid_size

    # Create a blank canvas for the grid
    grid_image = Image.new("RGB", (cols * img_w, rows * img_h))

    # Paste each image onto the canvas
    for index, img_path in enumerate(img_path_list):
        img = Image.open(img_path)
        img = img.resize((img_w, img_h))
        row = index // cols
        col = index % cols
        position = (col * img_w, row * img_h)
        grid_image.paste(img, position)

    # Save the final grid image with initial quality cfg
    quality = cfg["img_quality"]
    grid_image.save(output_path, quality=quality, cfgimize=True)

    # Check the file size
    file_size = os.path.getsize(output_path)

    # Adjust quality until the file size is within the limit
    while file_size > cfg["img_max_byte"] and quality > cfg["img_quality_reduce"]:
        quality -= cfg["img_quality_reduce"]
        print(f"File too big ({file_size} B). Running again with quality = {quality} %")
        grid_image.save(output_path, quality=quality, cfgimize=True)
        file_size = os.path.getsize(output_path)
    return output_path


def upload_file(online_name, file_path):
    # check if file is already uploaded
    result = cloudinary.Search().expression(online_name).max_results("1").execute()

    if result["total_count"] == 1:
        print(f"Found file online: {online_name}")
        return result["resources"][0]["secure_url"]
    else:
        # upload file
        print(f"Uploading file: {online_name}")
        result = cloudinary.uploader.upload(
            file_path,
            folder=f"AH LCG - {cfg["locale"].upper()}",
            public_id=online_name,
        )
        return result["secure_url"]


# gets the translated card name from ArkhamDB
def get_translated_name(adb_id):
    try:
        response = urlopen(arkhamdb_url + adb_id)
        data_json = json.loads(response.read())
        return data_json["name"]
    except HTTPError as e:
        print(f"Couldn't get translated name for ID: {adb_id} (HTTP {e.code})")
        return adb_id
    except URLError as e:
        print(f"Couldn't get translated name for ID: {adb_id} (URL {e.reason})")
        return adb_id


def escape_lua_file(file_path):
    try:
        with open(file_path) as file:
            lua_str = file.read()
    except FileNotFoundError:
        return "File not found"
    except OSError:
        return "Error reading file"

    def escape_special_chars(match):
        char = match.group(0)
        if char == "\\":
            return "\\\\"
        elif char == '"':
            return '\\"'
        elif char == "'":
            return "\\'"
        elif char == "\n":
            return "\\n"
        elif char == "\t":
            return "\\t"
        else:
            return char

    escaped_str = re.sub(r"[\\\"\']|\n|\t", escape_special_chars, lua_str)
    return f'"{escaped_str}"'


# -----------------------------------------------------------
# main script
# -----------------------------------------------------------

# process input files
card_index = {}
for subdir, dirs, files in os.walk(cfg["source_folder"]):
    print(f"Processing folder: {subdir}")
    for file in files:
        folder_name = os.path.basename(subdir)
        file_name = os.path.splitext(file)[0]
        adb_id = get_arkhamdb_id(folder_name, file_name)

        # skip this file because we don't have a proper ArkhamDB ID for it
        if adb_id == "ERROR":
            continue

        # get number to sort cards by (suffix for letter appendices)
        sort_value = extract_numbers(adb_id) + str(len(adb_id) - 5)

        # add card to index
        card_index[adb_id] = {
            "cycle_id": int(adb_id[:2]),
            "file_path": os.path.join(subdir, file),
            "sort_value": sort_value,
        }

# sort the card index
card_index = dict(sorted(card_index.items(), key=lambda item: item[1]["sort_value"]))

# loop through index and collect data for decksheets
last_cycle_id, last_id, card_id, deck_id = 0, 0, 0, 0
sheet_parameters = {}

for adb_id, data in card_index.items():
    # we're just starting out or got to a new cycle or have to start a new sheet
    if (
        last_cycle_id == 0
        or last_cycle_id != data["cycle_id"]
        or card_id == (cfg["img_count_per_sheet"] - 1)
    ):
        # add end index to last parameter
        if deck_id != 0:
            sheet_parameters[deck_id]["endId"] = last_id

        deck_id += 1
        card_id = 0

        # initialize dictionary
        sheet_parameters[deck_id] = {"img_path_list": [], "startId": adb_id}
    else:
        card_id += 1

    # store information for next iteration
    last_cycle_id = data["cycle_id"]
    last_id = adb_id

    # add image to list and update card index
    sheet_parameters[deck_id]["img_path_list"].append(data["file_path"])
    data["deck_id"] = f"{deck_id}"

    # ensure the card_id field has two digit length
    data["card_id"] = f"{deck_id}{card_id:02}"

# add end index for last item
sheet_parameters[deck_id]["endId"] = last_id

# create temp folder for decksheets
temp_path = os.path.join(script_dir, "temp")
if os.path.exists(temp_path):
    shutil.rmtree(temp_path)
os.mkdir(temp_path)

# create decksheets with previously collected information
for deck_id, data in sheet_parameters.items():
    card_count = len(data["img_path_list"])
    grid_size = (math.ceil(card_count / 10), 10)
    online_name = f"SheetDE{data["startId"]}-{data["endId"]}"
    sheet_name = f"{online_name}.jpg"

    print(f"Creating {sheet_name}")
    sheet_path = create_decksheet(
        data["img_path_list"],
        grid_size,
        cfg["img_w"],
        cfg["img_h"],
        f"{temp_path}/{sheet_name}",
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
bag["LuaScript"] = escape_lua_file("TTSBagLuaScript.lua")

# loop cards and add them to bag
print("Creating output file.")
for adb_id, data in card_index.items():
    card_json = get_card_json(adb_id, data)
    if card_json != "ERROR":
        bag["ObjectStates"][0]["ContainedObjects"].append(card_json)

# output the bag with translated cards
bag_path = f"{output_folder}/{bag_name}.json"
with open(bag_path, "w", encoding="utf8") as f:
    json.dump(bag, f, ensure_ascii=False, indent=2)
print("Successfully created output file.")

# remove temp folder
if not cfg["keep_temp_folder"] and os.path.exists(temp_path):
    print("Removing temp folder.")
    shutil.rmtree(temp_path)
