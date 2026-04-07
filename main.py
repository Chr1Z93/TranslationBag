import copy
import hashlib
import json
import math
import os
import re
import requests
import shutil
import sys

from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from PIL import Image
import cloudinary
import cloudinary.uploader

# Local module import
from modules.gui import App


class TTSBundleProcessor:
    # Constants
    WHITELIST = ["EncounterCards", "PlayerCards", "Taboo", "Tarot"]
    BACK_SUFFIX = "-back"

    # Specific backs
    BACK_URLS = {
        # Encounter/Player are the "regular" backs
        "Encounter": "https://steamusercontent-a.akamaihd.net/ugc/2342503777940351785/F64D8EFB75A9E15446D24343DA0A6EEF5B3E43DB/",
        "Player": "https://steamusercontent-a.akamaihd.net/ugc/2342503777940352139/A2D42E7E5C43D045D72CE5CFC907E4F886C8C690/",
        # Arkham Woods are used in multiple campaigns
        "ArkhamWoods": "https://steamusercontent-a.akamaihd.net/ugc/10039895077102366513/A4B27CFD64422A1055CA9DBE662A366D9FCA200F/",
        # Artifacts are from TDC
        "Artifact": "https://steamusercontent-a.akamaihd.net/ugc/62595146532712476/4F1C745A4BD1E7F5EA6DA68E2D81F59AC2817D22/",
        # Concealed Mini-Cards are from TSK
        "Concealed": "https://steamusercontent-a.akamaihd.net/ugc/1941643328387229452/B0883940A23A9E63B99FF9CA6A344C3C57EC3257/",
        # Cthulhu-Deck is from TDC
        "Cthulhu-Deck": "https://steamusercontent-a.akamaihd.net/ugc/62595146532775345/8D860CB7316FDC55C2506F6E5A3A56810AB440E9/",
        # Enemy-Deck is from FHV
        "Enemy-Deck": "https://steamusercontent-a.akamaihd.net/ugc/2453969771999768294/54768C2E562D30E34B79EB7A94FCDC792E49FC28/",
        # Tarot cards are from RtTCU
        "Tarot": "https://steamusercontent-a.akamaihd.net/ugc/1697276706767619573/BC43BD2A94446B804BE325C7255D8179DEB2ABE8/",
        # Upgradesheets (Customizable) are from TSK
        "Upgradesheet": "https://steamusercontent-a.akamaihd.net/ugc/1814412497119682452/BD224FCE1980DBA38E5A687FABFD146AA1A30D0E/",
    }

    # Groups of IDs that trigger specific logic
    SPECIAL_ID_MAPS = {
        "ArkhamWoods": ["011" + str(i) for i in range(50, 56)]
        + ["50033", "50034", "50035", "50036", "54021", "54022", "54023"],
        "Artifact": ["11552", "11582", "11611", "11638", "11672", "11688"],
        "Cthulhu-Deck": [str(i) for i in range(11705, 11716)],
        "Encounter": ["06028", "11016"],
        "Enemy-Deck": [
            "10643",
            "10644a",
            "10644b",
            "10644c",
            "10645a",
            "10645b",
            "10645c",
            "10646",
            "10647a",
            "10647b",
            "10647c",
            "10648",
        ],
        "Player": ["085" + str(i) for i in range(87, 96)]
        + ["086" + str(i) for i in range(14, 23)],
    }

    # Additions to the final name if suffix is present
    SUFFIX_MAP = {
        "-p": "(Parallel)",
        "-pf": "(Parallel Front)",
        "-pb": "(Parallel Back)",
        "-t": "(Taboo)",
        "-c": "Upgrade Sheet",
    }

    def __init__(self, cfg):
        self.cfg = cfg
        self.script_dir = os.path.dirname(__file__)
        self.temp_path = os.path.join(self.script_dir, "temp")

        # Configuration
        locale = self.cfg["locale"].lower()
        self.ARKHAM_BUILD_URL = f"https://api.arkham.build/v1/cache/cards/{locale}"

        # State Management
        self.card_index = {}
        self.sheet_parameters = {}
        self.reported_missing_url = {}
        self.deck_id_counter = 0
        self.deck_offset = self.string_to_3_digits(locale)
        self.translation_data = {}

        # Initialize Cloudinary
        cloudinary.config(
            cloud_name=self.cfg["cloud_name"],
            api_key=self.cfg["api_key"],
            api_secret=self.cfg["api_secret"],
        )

        # Maybe load local versions of special card backs
        self.local_backs_path = os.path.join(self.cfg["source_folder"], "Backs")
        self._load_local_backs()

    def _load_local_backs(self):
        """Overrides hardcoded BACK_URLS if a file with the same name exists locally."""
        if not os.path.exists(self.local_backs_path):
            return

        print(f"Checking for local backs in: {self.local_backs_path}")
        # Look for files like "Encounter.png", "Player.jpg", etc.
        for filename in os.listdir(self.local_backs_path):
            name_part = os.path.splitext(filename)[0]
            if name_part in self.BACK_URLS:
                full_path = os.path.join(self.local_backs_path, filename)
                # Store the local path temporarily
                self.BACK_URLS[name_part] = full_path
                print(f"  -> Found local override for {name_part}")

    def string_to_3_digits(self, input_string):
        """Consistently turns any string into a number between 100 and 999."""
        # Create a deterministic hex hash of the string
        hash_object = hashlib.sha256(input_string.encode())
        hash_hex = hash_object.hexdigest()

        # Convert the hex string to a large integer
        hash_int = int(hash_hex, 16)

        # Use modulo to fit it into a 3-digit range (100-999)
        # (hash_int % 900) gives 0-899. Adding 100 gives 100-999.
        three_digit_result = (hash_int % 900) + 100

        return three_digit_result

    def load_translation_data(self):
        try:
            response = requests.get(self.ARKHAM_BUILD_URL)
            response.raise_for_status()

            # Create a lookup map
            for item in response.json()["data"]["all_card"]:
                if "name" in item:
                    key = item["id"]

                    # Special handling for Hank (who uses different IDs in TTS)
                    if key == "10016a":
                        key = "10015-b1"
                    elif key == "10016b":
                        key = "10015-b2"

                    self.translation_data[key] = item

        except Exception as e:
            print(f"Error fetching translation data: {e}")

    def _load_json(self, path, default=None):
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        return default if default is not None else {}

    def resolve_back_url(self, arkham_id, data, translated_data):
        # Double-sided cards use the specific back from the sheet
        if data.get("double_sided"):
            back_id = f"{arkham_id}{self.BACK_SUFFIX}"
            for s_param in self.sheet_parameters.values():
                if (
                    s_param["sheet_type"] == "back"
                    and s_param["start_id"] <= back_id <= s_param["end_id"]
                ):
                    return s_param.get("uploaded_url", self.BACK_URLS["Player"])

        # Check for suffix (Upgradesheets from TSK)
        if arkham_id.endswith("-c"):
            return self.BACK_URLS["Upgradesheet"]

        # Check for prefix (Concealed cards from TSK)
        if arkham_id.startswith("HC"):
            return self.BACK_URLS["Concealed"]

        # Check for prefix (Tarot cards from RtTCU)
        if arkham_id.startswith("TAR"):
            return self.BACK_URLS["Tarot"]

        # Check specific ID lists
        for special_type, id_list in self.SPECIAL_ID_MAPS.items():
            if arkham_id in id_list:
                return self.BACK_URLS[special_type]

        # Check for deck limit (Player Cards including bonded [deck_limit = 0])
        if "deck_limit" in translated_data:
            return self.BACK_URLS["Player"]

        # Check for encounter code (Encounter Cards)
        if "encounter_code" in translated_data:
            return self.BACK_URLS["Encounter"]

        # Final Fallback
        return self.BACK_URLS["Player"]

    def _save_json(self, data, path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def get_arkham_id(self, folder_path, file_name):
        base_name = os.path.splitext(file_name)[0]

        # Assume that base IDs with at least 5 characters are complete
        if len(base_name.removesuffix(self.BACK_SUFFIX)) >= 5:
            return base_name

        folder_name = os.path.basename(folder_path)

        # Calculate padding: 5 total digits - folder name length - existing digits in filename
        digits_in_file = sum(c.isdigit() for c in base_name)
        zero_count = 5 - len(folder_name) - digits_in_file
        if zero_count < 0:
            raise ValueError(f"Invalid ID construction for {file_name}")
        return f"{folder_name}{'0' * zero_count}{base_name}"

    def sort_key(self, item):
        key = item[0]
        pattern = r"^(\d{5})([a-z])?(?:-([a-z]\d+))?$"
        match = re.match(pattern, key)
        if match:
            return (match.group(1), match.group(2) or "", match.group(3) or "")
        return (key,)

    def scan_source(self):
        """Walks the directory and builds the initial card index."""
        print(f"Scanning: {self.cfg['source_folder']}")
        for root, _, files in os.walk(self.cfg["source_folder"]):
            path_parts = root.split(os.sep)

            # Identify which whitelist folder this belongs to
            folder_category = next((f for f in self.WHITELIST if f in path_parts), None)
            if not folder_category:
                continue

            for file in files:
                if not file.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
                    continue
                try:
                    arkham_id = self.get_arkham_id(root, file)
                    is_back = arkham_id.endswith(self.BACK_SUFFIX)
                    actual_id = arkham_id.removesuffix(self.BACK_SUFFIX)

                    if is_back and actual_id in self.card_index:
                        self.card_index[actual_id]["double_sided"] = True

                    self.card_index[arkham_id] = {
                        "cycle_id": int(arkham_id[:2]),
                        "file_path": os.path.join(root, file),
                        "double_sided": is_back,  # Will be updated for fronts in sorting phase
                        "category": folder_category,
                    }
                except Exception as e:
                    print(f"Skip {file}: {e}")

        # Finalize double-sided status for fronts
        for arkham_id in self.card_index:
            if f"{arkham_id}{self.BACK_SUFFIX}" in self.card_index:
                self.card_index[arkham_id]["double_sided"] = True

        # Check if the index is empty and abort
        if not self.card_index:
            print("[ERROR] No valid card images found in the source folder.")
            sys.exit(1)

    def organize_sheets(self):
        """Groups cards into sheet batches separated by WHITELIST and Back URLs."""

        # Loop through each category in the whitelist separately
        for category in self.WHITELIST:
            # Filter the index for only cards in this specific folder
            category_cards = {
                k: v for k, v in self.card_index.items() if v["category"] == category
            }

            if not category_cards:
                continue

            sorted_cards = sorted(category_cards.items(), key=self.sort_key)

            # Pre-calculate back URLs for all cards to allow grouping by back
            enriched_cards = []
            for arkham_id, data in sorted_cards:
                translated_data = self.get_translated_data(arkham_id)
                back_url = self.resolve_back_url(arkham_id, data, translated_data)
                enriched_cards.append((arkham_id, data, back_url))

            batches = {
                "single": [c for c in enriched_cards if not c[1]["double_sided"]],
                "front": [
                    c
                    for c in enriched_cards
                    if c[1]["double_sided"] and not c[0].endswith(self.BACK_SUFFIX)
                ],
                "back": [
                    c
                    for c in enriched_cards
                    if c[1]["double_sided"] and c[0].endswith(self.BACK_SUFFIX)
                ],
            }

            for sheet_type, card_list in batches.items():
                last_group_key = (None, None)
                current_batch = []

                for arkham_id, data, back_url in card_list:
                    # Create a unique key for this specific combination
                    # Double-sided cards don't care about shared backs
                    group_key = (
                        data["cycle_id"],
                        back_url if sheet_type == "single" else "double-sided",
                    )
                    is_first_card = last_group_key == (None, None)

                    # Start new sheet if cycle/back changes OR sheet is full
                    if not is_first_card and (
                        group_key != last_group_key
                        or len(current_batch) >= self.cfg["img_count_per_sheet"]
                    ):
                        self._create_sheet_param(
                            current_batch, sheet_type, last_group_key[1]
                        )
                        current_batch = []

                    data["card_id"] = len(current_batch)
                    data["deck_id"] = self.deck_id_counter + 1
                    current_batch.append((arkham_id, data))
                    last_group_key = group_key

                if current_batch:
                    self._create_sheet_param(
                        current_batch, sheet_type, last_group_key[1]
                    )

    def _create_sheet_param(self, batch, sheet_type, back_url):
        self.deck_id_counter += 1
        self.sheet_parameters[self.deck_id_counter] = {
            "img_path_list": [d["file_path"] for _, d in batch],
            "start_id": batch[0][0],
            "end_id": batch[-1][0],
            "sheet_type": sheet_type,
            "card_count": len(batch),
            "back_url": back_url,
        }

    def _load_and_resize_card(self, args):
        """Helper for parallel processing"""
        path, img_w, img_h = args
        try:
            with Image.open(path) as img:
                return img.resize((img_w, img_h), Image.Resampling.LANCZOS).convert(
                    "RGB"
                )
        except Exception as e:
            print(f"Error loading {path}: {e}")
            return Image.new("RGB", (img_w, img_h), (255, 0, 0))  # Red error card

    def process_images(self):
        """Stitches images and handles uploading."""
        if os.path.exists(self.temp_path):
            shutil.rmtree(self.temp_path)
        os.makedirs(self.temp_path)

        img_w, img_h = self.cfg["img_w"], self.cfg["img_h"]

        for d_id, data in self.sheet_parameters.items():
            if d_id > self.cfg["max_sheet_count"]:
                break

            online_name = f"Sheet_{self.cfg['locale'].upper()}_{data['start_id']}_{data['end_id']}"

            # Check Cloudinary First
            if not self.cfg["dont_upload"]:
                existing_url = self.check_online_exists(online_name)
                if existing_url:
                    data["uploaded_url"] = existing_url
                    continue

            # Create Sheet
            print(f"[CREATING] {online_name}")
            cols = min(data["card_count"], 10)
            rows = math.ceil(data["card_count"] / 10)
            data["grid_size"] = (rows, cols)

            # PARALLEL STEP: Load and resize all images for this sheet at once
            with ThreadPoolExecutor() as executor:
                tasks = [(path, img_w, img_h) for path in data["img_path_list"]]
                resized_images = list(executor.map(self._load_and_resize_card, tasks))

            # Assemble the sheet
            sheet_img = Image.new("RGB", (cols * img_w, rows * img_h))
            for i, img in enumerate(resized_images):
                x = (i % cols) * img_w
                y = (i // cols) * img_h
                sheet_img.paste(img, (x, y))
                img.close()

            out_path = os.path.join(self.temp_path, f"{online_name}.webp")
            self.save_with_retry(sheet_img, out_path)

            # Upload
            if self.cfg["dont_upload"]:
                data["uploaded_url"] = "file:///" + out_path
            else:
                data["uploaded_url"] = self.upload_to_cloud(online_name, out_path)

    def save_with_retry(self, image, path):
        # 6 is "best/slowest", 4 is "balanced", 0 is "fastest".
        # 4 usually gives 95% of the benefit of 6 in 10% of the time.
        webp_method = 4

        name = os.path.basename(path)
        print(f"[SAVING]   {name}...")

        quality = self.cfg["img_quality"]
        while True:
            image.save(path, format="WebP", quality=quality, method=webp_method)
            file_size = os.path.getsize(path)
            if file_size < self.cfg["img_max_byte"] or quality <= 50:
                print(
                    f"[SAVED]    {name} at {quality}% quality ({file_size // 1024} KB)"
                )
                break

            # Adaptive quality drop: if we're way over, drop by 10, else 5
            drop = 10 if file_size > (self.cfg["img_max_byte"] * 1.5) else 5
            quality -= drop

    def check_online_exists(self, name):
        try:
            res = cloudinary.Search().expression(f"public_id={name}").execute()
            if res.get("total_count", 0) > 0:
                return res["resources"][0]["secure_url"]
        except Exception:
            return None

    def upload_to_cloud(self, name, path):
        folder = f"AH_LCG_{self.cfg['locale'].upper()}"
        res = cloudinary.uploader.upload(path, public_id=name, folder=folder)
        return res.get("secure_url")

    def get_translated_data(self, arkham_id):
        # Remove specific suffix if possible
        clean_id = re.sub(r"-(p[fb]|[tcp])$", "", arkham_id)

        if clean_id in self.translation_data:
            return self.translation_data[clean_id]

        return {}

    def build_tts_json(self):
        print("Building TTS Bag...")
        bag_template = self._load_json("TTSBagTemplate.json")
        card_template = bag_template["ObjectStates"][0]["ContainedObjects"][0]
        contained_objects = []

        for arkham_id, data in self.card_index.items():
            if arkham_id.endswith(self.BACK_SUFFIX):
                continue

            # Card Logic
            sheet_info = self.sheet_parameters.get(data["deck_id"])
            if not sheet_info or "uploaded_url" not in sheet_info:
                print(
                    f"[WARNING] Skipping {arkham_id}: No info / URL found for {data['deck_id']}"
                )
                continue

            # Get data from arkham.build API with translated fields
            translated_data = self.get_translated_data(arkham_id)

            # Create a copy of the template
            new_card = copy.deepcopy(card_template)

            # Determine the back url
            if sheet_info["sheet_type"] == "single":
                back_url = sheet_info["back_url"]
            else:
                back_url = self.resolve_back_url(arkham_id, data, translated_data)

            # Build card data
            new_card["GMNotes"] = '{"id":"' + arkham_id + '"}'
            new_card["GUID"] = f"{self.cfg['locale']}_{arkham_id}"

            # Name / Description
            name_suffix = ""
            for suffix, label in self.SUFFIX_MAP.items():
                if arkham_id.endswith(suffix):
                    name_suffix = " " + label
                    break

            new_card["Nickname"] = translated_data.get("name", arkham_id) + name_suffix
            new_card["Description"] = translated_data.get("subname", "")

            # Investigator handling
            if translated_data.get("type_code") == "investigator":
                new_card["SidewaysCard"] = True

            # Image data
            deck_id = data["deck_id"] + self.deck_offset
            new_card["CardID"] = f"{deck_id}{data['card_id']:02}"
            new_card["CustomDeck"] = {
                str(deck_id): {
                    "FaceURL": sheet_info["uploaded_url"],
                    "BackURL": back_url,
                    "NumWidth": sheet_info["grid_size"][1],
                    "NumHeight": sheet_info["grid_size"][0],
                    "BackIsHidden": True,
                    "UniqueBack": data["double_sided"],
                    "Type": 0,
                }
            }
            contained_objects.append(new_card)

        # Set bag data
        date_stamp = datetime.now().strftime("%Y-%m-%d")
        bag_name = f"{date_stamp} - {self.cfg['locale'].upper()}"
        bag_template["ObjectStates"][0]["Nickname"] = bag_name
        bag_template["ObjectStates"][0]["GUID"] = f"{self.cfg['locale']}_bag"
        bag_template["ObjectStates"][0]["ContainedObjects"] = contained_objects

        # Final export
        out_name = f"{bag_name}.json"
        self._save_json(bag_template, os.path.join(self.cfg["output_folder"], out_name))
        print(f"Export complete: {out_name}")

    def cleanup(self):
        if not self.cfg.get("keep_temp_folder") and os.path.exists(self.temp_path):
            shutil.rmtree(self.temp_path)


# --- Execution ---
if __name__ == "__main__":
    gui = App()
    config = gui.get_values()

    proc = TTSBundleProcessor(config)
    proc.load_translation_data()
    proc.scan_source()
    proc.organize_sheets()
    proc.process_images()
    proc.build_tts_json()
    proc.cleanup()
