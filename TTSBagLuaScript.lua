-- add context menu options
function onLoad()
  self.addContextMenuItem("Get metadata", getMetadata)
  self.addContextMenuItem("Add to index", addToIndex)
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
    printToAll("Metadata was already updated!")
    return
  end

  -- add the tag so that the bag will get added to the index
  self.addTag("AllCardsHotfix")
  local data = self.getData()
  for _, objData in ipairs(data["ContainedObjects"] or {}) do
    -- get the data for this ID from the AllCardsBag
    local cardData = bag.call("getCardById", { id = objData["GMNotes"] })

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
