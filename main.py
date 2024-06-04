from urllib.request import urlopen
from PIL import Image
import copy
import json
import math
import os
import re
import shutil

# cloud service specifics
import cloudinary
import cloudinary.api
import cloudinary.uploader

# image specifics
max_filesize_byte = 10485760
img_count_per_sheet = 30
img_quality = 100
img_quality_reduction_step = 2
img_w = 750
img_h = 1050

cloudinary.config(
    cloud_name="X",
    api_key="X",
    api_secret="X",
)

# general config
language_key = "de"
source_folder = r"C:\Users\X\Downloads\Spielerkarten\Nach Zyklus"
keep_temp_folder = False

# use TTS' saved objects folder as default output folder
output_folder = (
    os.environ["USERPROFILE"]
    + r"\Documents\My Games\Tabletop Simulator\Saves\Saved Objects"
)

# controls the maximum number of sheets (for testing purposes)
max_sheet_count = 99

# probably don't need to change these
bag_template = "TranslationBagTemplate.json"
arkhamdb_url = "https://" + language_key.lower() + ".arkhamdb.com/api/public/card/"
script_dir = os.path.dirname(__file__)

# keep track of the deckIds that the missing URL was reported for
reported_missing_url = {}


# opens a JSON file in the script_dir
def load_json_file(file_name):
    file_path = os.path.join(script_dir, file_name)
    with open(file_path, "r") as file:
        return json.load(file)


# create card json
def get_card_json(id, data):
    if not ("uploaded_url" in sheet_parameters[int(data["deck_id"])]):
        if reported_missing_url.get(data["deck_id"], False):
            print("Didn't find URL for sheet " + data["deck_id"])
            reported_missing_url[data["deck_id"]] = True
        return "ERROR"

    # collect data for card
    translated_name = get_translated_name(id)
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
    new_card["GMNotes"] = id
    return new_card


# attempts to construct the arkhamdb from filename and foldername
def get_arkhamdb_id(folder_name, file_name):
    # if filename isn't already a full id, contruct it
    if len(file_name) < 5:
        zero_count = 5 - len(folder_name) - sum(c.isdigit() for c in file_name)
        if zero_count < 0:
            print("Error getting ID for " + os.path.join(subdir, file))
            return "ERROR"
        else:
            return folder_name + "0" * zero_count + file_name
    else:
        return file_name


# get combined number from string
def extract_numbers(string):
    numbers = re.findall(r"\d+", string)
    return "".join(numbers)


# this is needed to ensure the card_id field in the resulting Json has two digit length
def add_leading_zero(number):
    if number < 10:
        return "0" + str(number)
    else:
        return str(number)


def create_decksheet(img_path_list, grid_size, img_w, img_h, output_path):
    rows, cols = grid_size

    # Create a blank canvas for the grid
    w = cols * img_w
    h = rows * img_h
    grid_image = Image.new("RGB", (w, h))

    # Paste each image onto the canvas
    for index, img_path in enumerate(img_path_list):
        img = Image.open(img_path)
        img = img.resize((img_w, img_h))
        row = index // cols
        col = index % cols
        position = (col * img_w, row * img_h)
        grid_image.paste(img, position)

    # Save the final grid image with initial quality settings
    quality = img_quality
    grid_image.save(output_path, quality=quality, optimize=True)

    # Check the file size
    file_size = os.path.getsize(output_path)

    # Adjust quality until the file size is within the limit
    while file_size > max_filesize_byte and quality > img_quality_reduction_step:
        quality -= img_quality_reduction_step
        print(
            "File too big ("
            + str(file_size)
            + " B). Running again with quality = "
            + str(quality)
        )
        grid_image.save(output_path, quality=quality, optimize=True)
        file_size = os.path.getsize(output_path)

    return output_path


def upload_file(online_name, file_path):
    # check if file is already uploaded
    result = cloudinary.Search().expression(online_name).max_results("1").execute()

    if result["total_count"] == 1:
        print("Found file online: " + online_name)
        return result["resources"][0]["secure_url"]
    else:
        # upload file
        print("Uploading file: " + online_name)
        result = cloudinary.uploader.upload(
            file_path,
            folder="AH LCG - " + language_key.upper(),
            public_id=online_name,
        )
        return result["secure_url"]


# gets the translated card name from ArkhamDB
def get_translated_name(id):
    response = urlopen(arkhamdb_url + id)
    dataJson = json.loads(response.read())
    return dataJson["name"]


def escape_lua_file(file_path):
    # Read the Lua string from the file
    try:
        with open(file_path, "r") as file:
            lua_str = file.read()
    except FileNotFoundError:
        return "File not found"
    except IOError:
        return "Error reading file"

    # Define a function to escape special characters in Lua strings
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

    # Use a regular expression to find special characters and escape them
    escaped_str = re.sub(r"[\\\"\']|\n|\t", escape_special_chars, lua_str)
    return f'"{escaped_str}"'


# -----------------------------------------------------------
# main script
# -----------------------------------------------------------

# process input files
card_index = {}
for subdir, dirs, files in os.walk(source_folder):
    print("Processing folder: " + subdir)
    for file in files:
        folder_name = os.path.basename(subdir)
        file_name = os.path.splitext(file)[0]
        id = get_arkhamdb_id(folder_name, file_name)

        if id == "ERROR":
            continue

        # get number to sort cards by (suffix for letter appendices)
        sortValue = extract_numbers(id) + str(len(id) - 5)

        # add card to index
        card_index[id] = {
            "cycle_id": int(id[:2]),
            "file_path": os.path.join(subdir, file),
            "sortValue": sortValue,
        }

# sort the card index
card_index = dict(sorted(card_index.items(), key=lambda item: item[1]["sortValue"]))

# loop through index and collect data for decksheets
last_cycle_id, last_id, card_id, deck_id = 0, 0, 0, 0
sheet_parameters = {}

for id, data in card_index.items():
    # we're just starting out or got to a new cycle or have to start a new sheet
    if (
        last_cycle_id == 0
        or last_cycle_id != data["cycle_id"]
        or card_id == (img_count_per_sheet - 1)
    ):
        # add end index to last parameter
        if deck_id != 0:
            sheet_parameters[deck_id]["endId"] = last_id

        deck_id += 1
        card_id = 0

        # initialize dictionary
        sheet_parameters[deck_id] = {"img_path_list": [], "startId": id}
    else:
        card_id += 1

    # store information for next iteration
    last_cycle_id = data["cycle_id"]
    last_id = id

    # add image to list and update card index
    sheet_parameters[deck_id]["img_path_list"].append(data["file_path"])
    data["deck_id"] = str(deck_id)
    data["card_id"] = str(deck_id) + add_leading_zero(card_id)

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
    online_name = "SheetDE" + data["startId"] + "-" + data["endId"]
    sheet_name = online_name + ".jpg"

    print("Creating " + sheet_name)
    sheetPath = create_decksheet(
        data["img_path_list"],
        grid_size,
        img_w,
        img_h,
        temp_path + "/" + sheet_name,
    )

    data["uploaded_url"] = upload_file(online_name, sheetPath)
    data["grid_size"] = grid_size

    if deck_id >= max_sheet_count:
        break

# load the bag template and update it
bag_name = "Translated Cards - " + language_key.upper()
bag = load_json_file(bag_template)
card_template = bag["ObjectStates"][0]["ContainedObjects"][0]
bag["ObjectStates"][0]["Nickname"] = bag_name
bag["ObjectStates"][0]["ContainedObjects"] = []
bag["LuaScript"] = escape_lua_file("TranslationBagLuaScript.lua")

# loop cards and add them to bag
print("Creating output file.")
for id, data in card_index.items():
    cardJson = get_card_json(id, data)
    if cardJson != "ERROR":
        bag["ObjectStates"][0]["ContainedObjects"].append(cardJson)

# output the bag with translated cards
bag_path = output_folder + "/" + bag_name + ".json"
with open(bag_path, "w", encoding="utf8") as f:
    json.dump(bag, f, ensure_ascii=False, indent=2)
print("Successfully created output file.")

# remove temp folder
if keep_temp_folder == False and os.path.exists(temp_path):
    print("Removing temp folder.")
    shutil.rmtree(temp_path)
