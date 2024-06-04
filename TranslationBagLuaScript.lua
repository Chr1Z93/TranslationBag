function onLoad()
  self.addContextMenuItem("Get metadata", getMetadata)
  self.addContextMenuItem("Add to index", addToIndex)
end

function getMetadata()
  local bag = getObjectFromGUID("15bb07")
  if not bag then
    printToAll("Couldn't find AllCardsBag!")
    return
  end

  if self.hasTag("AllCardsHotfix") then
    printToAll("Metadata was already updated!")
    return
  end

  self.addTag("AllCardsHotfix")
  local data = self.getData()
  for _, objData in ipairs(data["ContainedObjects"] or {}) do
    local cardData = bag.call("getCardById", { id = objData["GMNotes"] })
    objData["GMNotes"] = JSON.encode(cardData.metadata)
  end

  printToAll("Successfully loaded metadata.")
  self.destruct()
  spawnObjectData({ data = data })
end

function addToIndex()
  local bag = getObjectFromGUID("15bb07")
  if not bag then
    printToAll("Couldn't find AllCardsBag!")
    return
  end

  printToAll("Updating index.")
  bag.call("rebuildIndexForHotfix")
end
