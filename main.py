import copy
from datetime import datetime
import json
import math
import os
import random
import re
import shutil

from enum import Enum
from PIL import Image
from urllib.request import urlopen
from urllib.error import URLError, HTTPError

# import from subfolder 'modules'
from modules.gui import App

# cloud service specifics
import cloudinary
import cloudinary.api
import cloudinary.uploader


class IndexType(Enum):
    PLAYER = 1
    CAMPAIGN = 2


def load_json_file(file_name):
    """Opens a JSON file in the script_dir"""
    file_path = os.path.join(script_dir, file_name)
    with open(file_path, 'r', encoding='utf-8') as file:
        return json.load(file)


def get_card_json(adb_id, data, index_type):
    """Create a JSON object for a card"""
    deck_id = data["deck_id"]
    card_id = data["card_id"]
    sheet_param = sheet_parameters[deck_id]

    # Check if 'uploaded_url' exists in sheet_parameters
    if "uploaded_url" not in sheet_param:
        if not reported_missing_url.get(deck_id, False):
            print(f"Didn't find URL for sheet {deck_id}")
            reported_missing_url[deck_id] = True
        raise KeyError("uploaded_url not found in sheet_parameters")

    # create Json element
    new_card = copy.deepcopy(card_template)

    # collect data for card
    h, w = sheet_param["grid_size"]

    if data["double_sided"] == False:
        if index_type == IndexType.PLAYER:
            back_url = player_card_back_url
        elif index_type == IndexType.CAMPAIGN:
            back_url = encounter_card_back_url
    else:
        try:
            back_url = get_back_url(sheet_param["uploaded_url"])
        except KeyError as e:
            if not reported_missing_url.get(deck_id, False):
                print(f"{adb_id} - {e}")
                reported_missing_url[deck_id] = True
            return

    id = {"id": adb_id}
    new_card["GMNotes"] = json.dumps(id)
    new_card["Nickname"] = get_translated_name(adb_id)
    new_card["CardID"] = f"{deck_id + random_num}{card_id:02}"
    new_card["CustomDeck"][f"{deck_id + random_num}"] = {
        "FaceURL": sheet_param["uploaded_url"],
        "BackURL": back_url,
        "NumWidth": w,
        "NumHeight": h,
        "BackIsHidden": True,
        "UniqueBack": data["double_sided"],
        "Type": 0
    }
    return new_card


def get_arkhamdb_id(current_path, file):
    """Constructs the ArkhamDB ID"""
    folder_name = os.path.basename(current_path)
    file_name = os.path.splitext(file)[0]

    # assume that file names with at least 5 digits are valid ArkhamDB IDs
    digit_count = sum(c.isdigit() for c in file_name)
    if digit_count < 5:
        # if filename isn't already a full adb_id, construct it from folder name + file name
        zero_count = 5 - len(folder_name) - digit_count
        if zero_count < 0:
            raise ValueError(f"Error getting ID for {os.path.join(current_path, file)}")
        return f"{folder_name}{'0'*zero_count}{file_name}"
    return file_name


def create_decksheet(img_path_list, grid_size, img_w, img_h, output_path):
    """Stitches the provided images together to deck sheet"""
    rows, cols = grid_size

    # create a blank canvas for the grid
    grid_image = Image.new("RGB", (cols * img_w, rows * img_h))

    # paste each image onto the canvas
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

    # save the final grid image with initial quality cfg
    quality = cfg["img_quality"]
    grid_image.save(output_path, quality=quality, optimize=True)

    # check the file size
    file_size = os.path.getsize(output_path)

    # adjust quality until the file size is within the limit
    while file_size > cfg["img_max_byte"]:
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


def file_already_uploaded(online_name):
    """Checks if a file is already uploaded."""
    try:
        result = cloudinary.Search().expression(f"filename={online_name}").max_results("1").execute()
        if result["total_count"] == 1:
            print(f"{online_name} - already uploaded")
            return result["resources"][0]["secure_url"]
    except Exception as e:
        print(f"Error when checking if file exists: {e}")


def upload_file(online_name, file_path):
    """Uploads a file to the cloud and returns the URL"""
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
    """Get the translated card name from cache / ArkhamDB"""
    global translation_cache

    if adb_id.endswith('-t'):
        adb_id = adb_id[:-2]

    if adb_id in translation_cache:
        return translation_cache[adb_id]

    try:
        response = urlopen(arkhamdb_url + adb_id)
    except HTTPError as e:
        print(f"{adb_id} - couldn't get translated name (HTTP {e.code})")
        return "ERROR"
    except URLError as e:
        print(f"{adb_id} - couldn't get translated name (URL {e.reason})")
        return "ERROR"

    try:
        data_json = json.loads(response.read())
    except json.JSONDecodeError:
        print(f"{adb_id} - couldn't parse JSON")
        return "ERROR"

    try:
        translation_cache[adb_id] = data_json["name"]
        return data_json["name"]
    except KeyError:
        print(f"{adb_id} - JSON response did not contain 'name' key")
        return "ERROR"


def get_lua_file(file_path):
    """Gets the script from a Lua file to be included in JSON."""
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            return file.read()
    except (FileNotFoundError, OSError) as e:
        raise IOError(f"Error reading Lua file: {e}")


def get_back_url(sheet_url):
    """Finds the URL of the sheet that has the cardbacks for the provided sheet."""
    for _, data in sheet_parameters.items():
        if data["sheet_type"] == "back" and data["start_id"][:5] in sheet_url and data["end_id"][:5] in sheet_url:
            if "uploaded_url" in data:
                return data["uploaded_url"]
            else:
                raise KeyError(f"uploaded_url not found in sheet_parameters")
    raise KeyError(f"no matching back URL found")


def process_cards(card_list, sheet_type):
    """Processes a list of cards and collects the data for the decksheet creation."""
    global last_cycle_id, last_id, card_id, deck_id, separate_by_cycle, sheet_parameters

    for adb_id, data in card_list:
        # we're just starting out or got to a new cycle or have to start a new sheet
        # (either because img count per sheet is exhausted or because we are processing new sheet type)
        if (
            last_cycle_id == 0
            or (separate_by_cycle and last_cycle_id != data["cycle_id"])
            or card_id == (cfg["img_count_per_sheet"] - 1)
            or sheet_parameters[deck_id]["sheet_type"] != sheet_type
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


def is_whitelisted(path):
    """Checks if a folder path contains a whitelisted folder name"""
    path_parts = path.split(os.sep)
    return any(folder in path_parts for folder in whitelist)


def fetch_index_type_from_path(path):
    """Return index card type based on dirpath"""
    path_parts = path.split(os.sep)
    # reversed(path_parts) cause we want to check index type against deepest folder in path
    for folder in reversed(path_parts):
        if folder in card_types_dict:
            return card_types_dict[folder]
    raise IOError("No whitelisted folder in processed path")


def prepare_bag(index, index_type: IndexType):
    """Process cards in index and return bag info with said cards"""
    single_sided_cards = []
    double_sided_cards_front = []
    double_sided_cards_back = []

    # separate single-sided and double-sided cards
    for adb_id, data in index.items():
        if data["double_sided"] == True:
            if adb_id.endswith(card_back_suffix):
                double_sided_cards_back.append((adb_id, data))
            else:
                double_sided_cards_front.append((adb_id, data))
        else:
            single_sided_cards.append((adb_id, data))

    return {"index_type": index_type,
            "single_sided_cards": single_sided_cards,
            "double_sided_cards_front": double_sided_cards_front,
            "double_sided_cards_back": double_sided_cards_back}


# -----------------------------------------------------------
# main script
# -----------------------------------------------------------

# open the main window to collect data
form = App()

# get data from form
cfg = form.get_values()

# probably don't need to change these
player_card_back_url = "https://steamusercontent-a.akamaihd.net/ugc/2342503777940352139/A2D42E7E5C43D045D72CE5CFC907E4F886C8C690/"
encounter_card_back_url = "https://steamusercontent-a.akamaihd.net/ugc/2342503777940351785/F64D8EFB75A9E15446D24343DA0A6EEF5B3E43DB/"
card_back_suffix = "-back"
bag_template = "TTSBagTemplate.json"
translation_cache_file = f"translation_cache_{cfg['locale'].lower()}.json"
arkhamdb_url = f"https://{cfg['locale'].lower()}.arkhamdb.com/api/public/card/"
script_dir = os.path.dirname(__file__)
cycle_names = { # Using for bag names
    "00": "Investigator Cards",
    "01": "Core Set",
    "02": "The Dunwich Legacy",
    "03": "Path To Carcosa",
    "81": "Curse of the Rougarou"
}

# Expansion campaigns require core set to be playable.
# While assembling campaign bags, we check bag's cycle_id against this list,
# if this list contains processed bag cycle_id - we add core set cards to the bag
campaigns_with_core = ["02", "03"]

# create translation cache
if os.path.exists(os.path.join(script_dir, translation_cache_file)):
    translation_cache = load_json_file(translation_cache_file)
else:
    translation_cache = {}

# whitelisted folder names and their corresponded card type
card_types_dict = {
    "PlayerCards":      IndexType.PLAYER,
    "Investigators":    IndexType.PLAYER,
    "EncounterCards":   IndexType.CAMPAIGN
}
whitelist = card_types_dict.keys()

# cloudinary api settings
cloudinary.config(
    cloud_name=cfg["cloud_name"],
    api_key=cfg["api_key"],
    api_secret=cfg["api_secret"],
)

# add random value to deck_id as a first measure against deck_id clashes
random_num = random.randint(1000, 3000) * 10

# keep track of the deckIds that the missing URL was reported for
reported_missing_url = {}

# creating indexes
# player_index - one dict, investigators and investigator cards, resulting in one bag
# campaign_index - dict of dicts, encounter/act/agenda cards, separated by cycle id, resulting in one bag per cycle
player_index = {}
campaign_index = {}

# process input files
for current_path, directories, files in os.walk(cfg["source_folder"]):
    if not is_whitelisted(current_path):
        continue
    print(f"Processing folder: {current_path}")
    for file in files:
        try:
            adb_id = get_arkhamdb_id(current_path, file)
        except Exception as e:
            print(f"{e}")
            continue  # skip this file because we don't have a proper ArkhamDB ID for it

        # determine index to add card to
        index_type = fetch_index_type_from_path(current_path)
        if index_type == IndexType.PLAYER:
            card_index = player_index
        elif index_type == IndexType.CAMPAIGN:
            cycle_id = int(adb_id[:2])
            card_index = campaign_index.setdefault(cycle_id, {})
        else:
            raise ValueError(f"Undefined index type {index_type}")

        # check if a face for this card is already added to the index and mark it as double-sided
        # or check if the index contains back for this card and mark card being processed as double-sided
        double_sided = False
        if adb_id.endswith(card_back_suffix):
            face_id = adb_id[:-5]
            double_sided = True

            if face_id in card_index:
                card_index[face_id]["double_sided"] = True
        else:
            back_id = adb_id + card_back_suffix
            if back_id in card_index:
                double_sided = True

        # add card to index
        card_index[adb_id] = {
            "cycle_id": int(adb_id[:2]),
            "file_path": os.path.join(current_path, file),
            "double_sided": double_sided
        }

# sort the indexes (numbers first, than by letter appendix)
player_index = dict(sorted(player_index.items(), key=sort_key))
for key, cards in campaign_index.items():
    campaign_index[key] = dict(sorted(cards.items(), key=sort_key))

# prepare bags, loop through indexes and collect data for decksheets
bags = []
if len(player_index) != 0:
    bags.append(prepare_bag(player_index, IndexType.PLAYER))
for cycle_id, index in campaign_index.items():
    bag = prepare_bag(index, IndexType.CAMPAIGN)
    bag["cycle_id"] = cycle_id
    bags.append(bag)

for bag in bags:
    # log number of cards in each bag and check for inconsistencies in number of double-sided cards
    print(f"Cycle Id: {bag.get('cycle_id')}") if "cycle_id" in bag else 0
    print(f"Type: {bag.get('index_type').name}")
    print(f"Single: {len(bag.get('single_sided_cards'))}")
    print(f"Front Double: {len(bag.get('double_sided_cards_front'))}")
    print(f"Back Double: {len(bag.get('double_sided_cards_back'))}")
    print(f"Total indexed: {len(bag.get('single_sided_cards')) + len(bag.get('double_sided_cards_front'))}")
    print("-"*80)

    if len(bag['double_sided_cards_front']) != len(bag['double_sided_cards_back']):
        print("Error: Number of fronts is not equal to the number of card backs!\nExiting app...")
        exit()


# create temp folder for decksheets
temp_path = os.path.join(script_dir, "temp")
if os.path.exists(temp_path):
    shutil.rmtree(temp_path)
os.mkdir(temp_path)

# process cards inside each bag
last_cycle_id, last_id, card_id, deck_id = 0, 0, 0, 0
sheet_parameters = {}
for bagInfo in bags:
    separate_by_cycle = bagInfo["index_type"] == IndexType.CAMPAIGN
    process_cards(bagInfo["single_sided_cards"], "single")
    process_cards(bagInfo["double_sided_cards_front"], "front")
    process_cards(bagInfo["double_sided_cards_back"], "back")

# create decksheets with previously collected information
for deck_id, data in sheet_parameters.items():
    card_count = len(data["img_path_list"])
    images_per_row = 10

    # if there is just a single row of images, shrink the grid
    if card_count < images_per_row:
        images_per_row = card_count

    data["grid_size"] = (math.ceil(card_count / 10), images_per_row)
    online_name = f"Sheet{cfg['locale'].upper()}{data['start_id']}-{data['end_id']}"
    sheet_name = f"{online_name}.jpg"

    if not cfg["dont_upload"]:
        # check if file is already uploaded
        result = file_already_uploaded(online_name)

        if result:
            data["uploaded_url"] = result
        else:
            print(f"{online_name} - creation")
            sheet_path = create_decksheet(
                data["img_path_list"],
                data["grid_size"],
                cfg["img_w"],
                cfg["img_h"],
                os.path.join(temp_path, sheet_name),
            )
            data["uploaded_url"] = upload_file(online_name, sheet_path)
    else:
        print(f"{online_name} - creation")
        sheet_path = create_decksheet(
                        data["img_path_list"],
                        data["grid_size"],
                        cfg["img_w"],
                        cfg["img_h"],
                        os.path.join(temp_path, sheet_name),
                    )
        data["uploaded_url"] = sheet_path

    if deck_id >= cfg["max_sheet_count"]:
        print("Max sheet count exceeded! No new decksheets will be created.")
        break

# we set aside Core cards, for them to be added to other campaign bags
core_set_list = []
for bagInfo in bags:
    # load the bag template and update it
    cycle_str = str(bagInfo.get('cycle_id', 0)).zfill(2)
    bag_name = f"{datetime.now().strftime('%Y-%m-%d')}_SCED-lang_{cycle_str}_{cfg['locale'].upper()}"
    bag = load_json_file(bag_template)
    card_template = bag["ObjectStates"][0]["ContainedObjects"][0]
    bag["ObjectStates"][0]["Nickname"] = f"{cycle_names[cycle_str]}: {cfg['locale'].upper()} language pack"
    bag["ObjectStates"][0]["ContainedObjects"] = []
    if bagInfo["index_type"] == IndexType.PLAYER:
        bag["ObjectStates"][0]["LuaScript"] = get_lua_file("TTSPlayerBagLuaScript.lua")
    else:
        bag["ObjectStates"][0]["LuaScript"] = get_lua_file("TTSCampaignBagLuaScript.lua")

    # loop cards and add them to bag
    print("Creating output file.")
    if bagInfo['index_type'] == IndexType.PLAYER:
        card_index = player_index
    else:
        card_index = campaign_index[bagInfo['cycle_id']]
    for adb_id, data in card_index.items():
        # skip card backs of double-sided cards
        if not adb_id.endswith(card_back_suffix):
            card_json = get_card_json(adb_id, data, bagInfo['index_type'])
            if card_json:
                bag["ObjectStates"][0]["ContainedObjects"].append(card_json)
            else:
                print(f"{adb_id} - failed to get card JSON")
    if cycle_str == "01":
        core_set_list = bag["ObjectStates"][0]["ContainedObjects"].copy()
    if cycle_str in campaigns_with_core:
        bag["ObjectStates"][0]["ContainedObjects"].extend(core_set_list)

    # output the bags with translated cards
    bag_path = os.path.join(cfg["output_folder"], f"{bag_name}.json")
    with open(bag_path, "w", encoding="utf8") as f:
        json.dump(bag, f, ensure_ascii=False, indent=2)
    print(f"Successfully created output file at {bag_path}.")


# save translation cache
with open(os.path.join(script_dir, translation_cache_file), "w", encoding="utf8") as f:
    json.dump(translation_cache, f, ensure_ascii=False, indent=2)

# remove temp folder
if not cfg["keep_temp_folder"] and os.path.exists(temp_path):
    print("Removing temp folder.")
    shutil.rmtree(temp_path)
