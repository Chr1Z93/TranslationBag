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
maxUploadByte = 10485760
imagesPerSheet = 30
imageQuality = 100
imageSize = (750, 1050)
qualityReductionStep = 2

cloudinary.config(
    cloud_name="X",
    api_key="X",
    api_secret="X",
)

# general config
languageKey = "de"
sourceFolder = r"C:\Users\X\Downloads\Spielerkarten\Nach Zyklus"
keepTempFolder = False

# use TTS' saved objects folder as default output folder
outputFolder = (
    os.environ["USERPROFILE"]
    + r"\Documents\My Games\Tabletop Simulator\Saves\Saved Objects"
)

# controls the maximum number of sheets (for testing purposes)
maxSheets = 99

# probably don't need to change these
bagTemplate = "TranslationBagTemplate.json"
arkhamdbUrl = "https://" + languageKey.lower() + ".arkhamdb.com/api/public/card/"
scriptDir = os.path.dirname(__file__)
reportedMissingURL = {}


# opens a JSON file in the scriptDir
def loadJsonFile(fileName):
    filePath = os.path.join(scriptDir, fileName)
    with open(filePath, "r") as file:
        return json.load(file)


# create card json
def getCardJson(id, data):
    if not ("uploadedUrl" in decksheetParameters[int(data["deckId"])]):
        if reportedMissingURL.get(data["deckId"], False):
            print("Didn't find URL for sheet " + data["deckId"])
            reportedMissingURL[data["deckId"]] = True
        return "ERROR"

    # collect data for card
    translatedName = getTranslatedName(id)
    uploadedUrl = decksheetParameters[int(data["deckId"])]["uploadedUrl"]
    h, w = decksheetParameters[int(data["deckId"])]["gridSize"]

    # create Json element
    newCard = copy.deepcopy(cardTemplate)
    backUrl = newCard["CustomDeck"]["123"]["BackURL"]
    newCard["Nickname"] = translatedName
    newCard["CardID"] = data["cardId"]
    newCard["CustomDeck"][data["deckId"]] = newCard["CustomDeck"].pop("123")
    newCard["CustomDeck"][data["deckId"]]["FaceURL"] = uploadedUrl
    newCard["CustomDeck"][data["deckId"]]["BackURL"] = backUrl
    newCard["CustomDeck"][data["deckId"]]["NumWidth"] = w
    newCard["CustomDeck"][data["deckId"]]["NumHeight"] = h
    newCard["GMNotes"] = id
    return newCard


# attempts to construct the arkhamdb from filename and foldername
def getArkhamDbId(folderName, fileName):
    # if filename isn't already a full id, contruct it
    if len(fileName) < 5:
        missingZeros = 5 - len(folderName) - sum(c.isdigit() for c in fileName)
        if missingZeros < 0:
            print("Error getting ID for " + os.path.join(subdir, file))
            return "ERROR"
        else:
            return folderName + "0" * missingZeros + fileName
    else:
        return fileName


# get combined number from string
def extractNumbers(string):
    numbers = re.findall(r"\d+", string)
    return "".join(numbers)


# this is needed to ensure the cardId field in the resulting Json has two digit length
def addLeadingZero(number):
    if number < 10:
        return "0" + str(number)
    else:
        return str(number)


def createDecksheet(imagePaths, gridSize, imageSize, outputPath):
    rows, cols = gridSize

    # Create a blank canvas for the grid
    gridWidth = cols * imageSize[0]
    gridHeight = rows * imageSize[1]
    gridImage = Image.new("RGB", (gridWidth, gridHeight))

    # Paste each image onto the canvas
    for index, imagePath in enumerate(imagePaths):
        img = Image.open(imagePath)
        img = img.resize(imageSize)
        row = index // cols
        col = index % cols
        position = (col * imageSize[0], row * imageSize[1])
        gridImage.paste(img, position)

    # Save the final grid image with initial quality settings
    quality = imageQuality
    gridImage.save(outputPath, quality=quality, optimize=True)

    # Check the file size
    fileSize = os.path.getsize(outputPath)

    # Adjust quality until the file size is within the limit
    while fileSize > maxUploadByte and quality > qualityReductionStep:
        quality -= qualityReductionStep
        print(
            "File too big ("
            + str(fileSize)
            + " B). Running again with quality = "
            + str(quality)
        )
        gridImage.save(outputPath, quality=quality, optimize=True)
        fileSize = os.path.getsize(outputPath)

    return outputPath


def uploadFile(onlineName, filePath):
    # check if file is already uploaded
    result = cloudinary.Search().expression(onlineName).max_results("1").execute()

    if result["total_count"] == 1:
        print("Found file online: " + onlineName)
        return result["resources"][0]["secure_url"]
    else:
        # upload file
        print("Uploading file: " + onlineName)
        result = cloudinary.uploader.upload(
            filePath,
            folder="AH LCG - " + languageKey.upper(),
            public_id=onlineName,
        )
        return result["secure_url"]


# gets the translated card name from ArkhamDB
def getTranslatedName(id):
    response = urlopen(arkhamdbUrl + id)
    dataJson = json.loads(response.read())
    return dataJson["name"]


# -----------------------------------------------------------
# main script
# -----------------------------------------------------------

# process input files
cardIndex = {}
for subdir, dirs, files in os.walk(sourceFolder):
    print("Processing folder: " + subdir)
    for file in files:
        folderName = os.path.basename(subdir)
        fileName = os.path.splitext(file)[0]
        id = getArkhamDbId(folderName, fileName)

        if id == "ERROR":
            continue

        # get number to sort cards by (suffix for letter appendices)
        sortValue = extractNumbers(id) + str(len(id) - 5)

        # add card to index
        cardIndex[id] = {
            "cycleId": int(id[:2]),
            "filePath": os.path.join(subdir, file),
            "sortValue": sortValue,
        }

# sort the card index
cardIndex = dict(sorted(cardIndex.items(), key=lambda item: item[1]["sortValue"]))

# loop through index and collect data for decksheets
lastCycleId, lastId, cardId, deckId = 0, 0, 0, 0
decksheetParameters = {}

for id, data in cardIndex.items():
    # we're just starting out or got to a new cycle or have to start a new sheet
    if (
        lastCycleId == 0
        or lastCycleId != data["cycleId"]
        or cardId == (imagesPerSheet - 1)
    ):
        # add end index to last parameter
        if deckId != 0:
            decksheetParameters[deckId]["endId"] = lastId

        deckId += 1
        cardId = 0

        # initialize dictionary
        decksheetParameters[deckId] = {"imagePaths": [], "startId": id}
    else:
        cardId += 1

    # store information for next iteration
    lastCycleId = data["cycleId"]
    lastId = id

    # add image to list and update card index
    decksheetParameters[deckId]["imagePaths"].append(data["filePath"])
    data["deckId"] = str(deckId)
    data["cardId"] = str(deckId) + addLeadingZero(cardId)

# add end index for last item
decksheetParameters[deckId]["endId"] = lastId

# create temp folder for decksheets
tempPath = os.path.join(scriptDir, "temp")
if os.path.exists(tempPath):
    shutil.rmtree(tempPath)
os.mkdir(tempPath)

# create decksheets with previously collected information
for deckId, data in decksheetParameters.items():
    cardCount = len(data["imagePaths"])
    gridSize = (math.ceil(cardCount / 10), 10)
    onlineName = "SheetDE" + data["startId"] + "-" + data["endId"]
    sheetName = onlineName + ".jpg"

    print("Creating " + sheetName)
    sheetPath = createDecksheet(
        data["imagePaths"], gridSize, imageSize, tempPath + "/" + sheetName
    )

    data["uploadedUrl"] = uploadFile(onlineName, sheetPath)
    data["gridSize"] = gridSize

    if deckId >= maxSheets:
        break

# load the bag template and update it
bagName = "Translated Cards - " + languageKey.upper()
bag = loadJsonFile(bagTemplate)
cardTemplate = bag["ObjectStates"][0]["ContainedObjects"][0]
bag["ObjectStates"][0]["Nickname"] = bagName
bag["ObjectStates"][0]["ContainedObjects"] = []

# loop cards and add them to bag
print("Creating output file.")
for id, data in cardIndex.items():
    cardJson = getCardJson(id, data)
    if cardJson != "ERROR":
        bag["ObjectStates"][0]["ContainedObjects"].append(cardJson)

# output the bag with translated cards
bagPath = outputFolder + "/" + bagName + ".json"
with open(bagPath, "w", encoding="utf8") as f:
    json.dump(bag, f, ensure_ascii=False, indent=2)
print("Successfully created output file.")

# remove temp folder
if keepTempFolder == False and os.path.exists(tempPath):
    print("Removing temp folder.")
    shutil.rmtree(tempPath)
