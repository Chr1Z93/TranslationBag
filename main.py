import copy
import json
import math
import os
import random
import re
import shutil
from datetime import datetime
import requests
from concurrent.futures import ThreadPoolExecutor

from PIL import Image
import cloudinary
import cloudinary.uploader

# Local module import
from modules.gui import App


class TTSBundleProcessor:
    def __init__(self, cfg):
        self.cfg = cfg
        self.script_dir = os.path.dirname(__file__)
        self.temp_path = os.path.join(self.script_dir, "temp")

        # Constants & Configuration
        locale = self.cfg["locale"].lower()
        self.PLAYER_BACK_URL = "https://steamusercontent-a.akamaihd.net/ugc/2342503777940352139/A2D42E7E5C43D045D72CE5CFC907E4F886C8C690/"
        self.WHITELIST = ["PlayerCards"]
        self.BACK_SUFFIX = "-back"
        self.ARKHAM_BUILD_URL = f"https://api.arkham.build/v1/cache/cards/{locale}"

        # State Management
        self.card_index = {}
        self.sheet_parameters = {}
        self.reported_missing_url = {}
        self.deck_id_counter = 0
        self.random_offset = random.randint(1000, 3000) * 10
        self.translation_data = {}

        # Initialize Cloudinary
        cloudinary.config(
            cloud_name=self.cfg["cloud_name"],
            api_key=self.cfg["api_key"],
            api_secret=self.cfg["api_secret"],
        )

    def load_translation_data(self):
        try:
            response = requests.get(self.ARKHAM_BUILD_URL)
            response.raise_for_status()

            # Create a lookup map
            for item in response.json()["data"]["all_card"]:
                if "name" in item:
                    key = item["id"]
                    self.translation_data[key] = item["name"]

        except Exception as e:
            print(f"Error fetching translation data: {e}")

    def _load_json(self, path, default=None):
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        return default if default is not None else {}

    def _save_json(self, data, path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def get_arkhamdb_id(self, folder_path, file_name):
        base_name = os.path.splitext(file_name)[0]
        if len(base_name) >= 5:
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
            if not any(folder in path_parts for folder in self.WHITELIST):
                continue

            for file in files:
                if not file.lower().endswith((".png", ".jpg", ".jpeg")):
                    continue
                try:
                    adb_id = self.get_arkhamdb_id(root, file)
                    is_back = adb_id.endswith(self.BACK_SUFFIX)
                    actual_id = adb_id[:-5] if is_back else adb_id

                    if is_back and actual_id in self.card_index:
                        self.card_index[actual_id]["double_sided"] = True

                    self.card_index[adb_id] = {
                        "cycle_id": int(adb_id[:2]),
                        "file_path": os.path.join(root, file),
                        "double_sided": is_back,  # Will be updated for fronts in sorting phase
                    }
                except Exception as e:
                    print(f"Skip {file}: {e}")

        # Finalize double-sided status for fronts
        for adb_id in self.card_index:
            if f"{adb_id}{self.BACK_SUFFIX}" in self.card_index:
                self.card_index[adb_id]["double_sided"] = True

    def organize_sheets(self):
        """Groups cards into sheet batches based on cycle and double-sided status."""
        sorted_cards = sorted(self.card_index.items(), key=self.sort_key)

        batches = {
            "single": [c for c in sorted_cards if not c[1]["double_sided"]],
            "front": [
                c
                for c in sorted_cards
                if c[1]["double_sided"] and not c[0].endswith(self.BACK_SUFFIX)
            ],
            "back": [
                c
                for c in sorted_cards
                if c[1]["double_sided"] and c[0].endswith(self.BACK_SUFFIX)
            ],
        }

        for sheet_type, card_list in batches.items():
            last_cycle = None
            current_batch = []

            for adb_id, data in card_list:
                # Start new sheet if cycle changes OR sheet is full
                if (last_cycle is not None and data["cycle_id"] != last_cycle) or len(
                    current_batch
                ) >= self.cfg["img_count_per_sheet"]:
                    self._create_sheet_param(current_batch, sheet_type)
                    current_batch = []

                data["card_id"] = len(current_batch)
                data["deck_id"] = self.deck_id_counter + 1  # Preview ID
                current_batch.append((adb_id, data))
                last_cycle = data["cycle_id"]

            if current_batch:
                self._create_sheet_param(current_batch, sheet_type)

    def _create_sheet_param(self, batch, sheet_type):
        self.deck_id_counter += 1
        self.sheet_parameters[self.deck_id_counter] = {
            "img_path_list": [d["file_path"] for _, d in batch],
            "start_id": batch[0][0],
            "end_id": batch[-1][0],
            "sheet_type": sheet_type,
            "card_count": len(batch),
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
            print(f"Creating Sheet: {online_name}")
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
        print(f"Starting to save {name}...")

        quality = self.cfg["img_quality"]
        while True:
            image.save(path, format="WebP", quality=quality, method=webp_method)
            file_size = os.path.getsize(path)
            if file_size < self.cfg["img_max_byte"] or quality <= 50:
                print(f"Saved {name} at {quality}% quality ({file_size // 1024} KB)")
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

    def get_translated_name(self, adb_id):
        clean_id = adb_id[:-2] if adb_id.endswith("-t") else adb_id
        if clean_id in self.translation_data:
            return self.translation_data[clean_id]
        return adb_id

    def build_tts_json(self):
        print("Building TTS Bag...")
        bag_template = self._load_json("TTSBagTemplate.json")
        card_base = bag_template["ObjectStates"][0]["ContainedObjects"][0]
        contained_objects = []

        for adb_id, data in self.card_index.items():
            if adb_id.endswith(self.BACK_SUFFIX):
                continue

            # Card Logic
            sheet_info = self.sheet_parameters.get(data["deck_id"])
            if not sheet_info or "uploaded_url" not in sheet_info:
                continue

            new_card = copy.deepcopy(card_base)
            back_url = self.PLAYER_BACK_URL

            if data["double_sided"]:
                # Logic to find the matching back sheet URL
                for s_id, s_param in self.sheet_parameters.items():
                    if s_param["sheet_type"] != "back":
                        continue

                    back_id = f"{adb_id}{self.BACK_SUFFIX}"
                    if s_param["start_id"] <= back_id <= s_param["end_id"]:
                        back_url = s_param.get("uploaded_url", self.PLAYER_BACK_URL)
                        break

            deck_id = data["deck_id"] + self.random_offset
            new_card["GMNotes"] = '{\n  "id": "' + adb_id + '"\n}'
            new_card["Nickname"] = self.get_translated_name(adb_id)
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
