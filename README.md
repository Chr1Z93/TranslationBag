# TranslationBag

## Preview of GUI
![image](https://github.com/user-attachments/assets/20410546-c7d4-4ba3-ad2c-70c959929f42)

Takes scanned cards as input and creates a saved object for TTS as output that can be added to the mod's card index.

Currently supports player cards (including investigators) except for taboo. Scenario cards aren't handled yet.

## Process

1) Make sure to have a local folder with the card images. The file names need to be either ArkhamDB IDs (e.g. 01001.jpg and 01001b.jpg for Roland Banks) or set numbers if the files are in subfolders for each cycle (e.g. 01/001.jpg and 01/001b.jpg).
2) Split the files by type and create a folder for each type (atm the only valid folder is 'PlayerCards').
3) Register on https://cloudinary.com/ (free). Get your API credentials. Alternatively, use local paths and upload to the steamcloud from inside TTS.
4) Run the main.py file (e.g. via `py main.py`) and fill in the data in the form.
5) The script should create a saved object in the correct folder for TTS to detect it.
6) Spawn it ingame, add it to the "Additional Cards" box and you're good to go!
