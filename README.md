# TranslationBag

## Preview of GUI
![image](https://github.com/user-attachments/assets/20410546-c7d4-4ba3-ad2c-70c959929f42)

Takes scanned cards as input and creates a saved object for TTS as output that can be added to the mod's card index.

Supports player (including investigators) and campaign cards.

## Process

1) Make sure to have a local folder with the card images. The file names need to be either ArkhamDB IDs (e.g. 01001.jpg and 01001-back.jpg for Roland Banks) or set numbers if the files are in subfolders for each cycle (e.g. 01/001.jpg and 01/001-back.jpg). Taboo cards are named as "002-t.png" and "002-t-back.png"
2) I recommend to split the files by type, e.g. "Investigators", "PlayerCards" and "EncounterCards" and create a folder for each type (the three aforementioned folder names will be checked, other names are invalid).
3) Register on https://cloudinary.com/ (free). Get your API credentials.
4) Run the main.py file (e.g. via `py main.py`) and fill in the data in the form.
5) The script should create a saved object in the correct folder for TTS to detect it.
6) Spawn it ingame and select "Get metadata" from the context menu. This will update the created bag with all the scripts and data from the currently loaded mod.
7) Finally, select "Add to index" from the context menu and you're good to go!

## Known Bugs

- Sometimes, ArkhamDB gives name of the wrong card side as localized nickname for double-sided cards, which can lead to spoilers if player reads on-hover tooltip in TTS. (Known cases: Back Hall Corridor cards in TDL House Always Wins and locations in Carcosa finale)  
