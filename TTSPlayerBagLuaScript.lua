-- add context menu options
function onLoad()
  createButtonByName("Apply")
end

-- main function: copies data from the existing cards
function getMetadata()
  local bag = getObjectFromGUID("15bb07")
  if not bag then
    printToAll("Couldn't find AllCardsBag!")
    return
  end

  -- if the tag is already present, this function was executed before
  if self.hasTag("AllCardsHotfix") then
    -- metadata was already updated, skip this step
    return
  end

  -- add the tag so that the bag will get added to the index
  self.addTag("AllCardsHotfix")
  local data = self.getData()
  for _, objData in ipairs(data["ContainedObjects"] or {}) do
    -- get the data for this ID from the AllCardsBag
    local cardData = bag.call("getCardById", { id = JSON.decode(objData["GMNotes"])["id"] })

    if cardData then
      -- copy the main metadata: GMNotes
      objData["GMNotes"] = JSON.encode(cardData.metadata)

      -- copy the secondary metadata: Tags
      objData["Tags"] = cardData.data["Tags"]

      -- copy script and XML
      objData["LuaScript"] = cardData.data["LuaScript"]
      objData["XmlUI"] = cardData.data["XmlUI"]

      -- copy sideways card information
      objData["SidewaysCard"] = cardData.data["SidewaysCard"]

      -- copy transform
      objData["Transform"] = cardData.data["Transform"]

      -- copy name if translated name couldn't be received
      if objData["Nickname"] == "ERROR" then
        objData["Nickname"] = cardData.data["Nickname"]
      end
    end
  end

  printToAll("Successfully loaded metadata.")

  -- respawn a modified version (with metadata)
  self.destruct()
  spawnObjectData({ data = data })
end

-- instructs the AllCardsBag to rebuild the index
function addToIndex()
  local bag = getObjectFromGUID("15bb07")
  if not bag then
    printToAll("Couldn't find AllCardsBag!")
    return
  end

  printToAll("Updating index.")
  bag.call("rebuildIndexForHotfix")
end

function createButtonByName(label)
  local selfScale = self.getScale()

  self.createButton({
    label = label,
    tooltip = "",
    position = { 2.5, 0.5, 0 },
    rotation = {0, -90, 0},
    height = 500,
    width = 1200,
    font_size = 350,
    font_color = { 1, 1, 1 },
    function_owner = self,
    color = { 0, 0, 0 },
    scale = Vector(1 / selfScale.x, 1, 1 / selfScale.z),
    click_function = "buttonClick_" .. string.lower(string.gsub(label, "%s+", ""))
  })
end

function buttonClick_apply()
  getMetadata()
  addToIndex()
end
