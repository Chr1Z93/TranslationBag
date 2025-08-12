# TranslationBag

## Preview of GUI
![image](https://github.com/user-attachments/assets/20410546-c7d4-4ba3-ad2c-70c959929f42)

Takes scanned cards as input and creates a saved object for TTS as output that can be added to the mod's card index.

Currently supports player cards (including investigators) except for taboo. Scenario cards aren't handled yet.

## Process

1) Make sure to have a local folder with the card images. The file names need to be either ArkhamDB IDs (e.g. 01001.jpg and 01001b.jpg for Roland Banks) or set numbers if the files are in subfolders for each cycle (e.g. 01/001.jpg and 01/001b.jpg).
2) I recommend to split the files by type, e.g. "Investigators" and "PlayerCards" and create a folder for each type (the two aforementioned folder names will be checked, other names are invalid).
3) Register on https://cloudinary.com/ (free). Get your API credentials.
4) Run the main.py file (e.g. via `py main.py`) and fill in the data in the form.
5) The script should create a saved object in the correct folder for TTS to detect it.
6) Spawn it ingame and select "Get metadata" from the context menu. This will update the created bag with all the scripts and data from the currently loaded mod.
7) Finally, select "Add to index" from the context menu and you're good to go!
