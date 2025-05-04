-- add context menu options
function onLoad()
  createButtonByName("Apply")
end

-- instructs the AllCardsBag to rebuild the index
function addToIndex()
  local bag = getObjectFromGUID("aa12bb")
  if not bag then
    printToAll("Couldn't find AllEncounterCardsBag!")
    return
  end

  printToAll("Updating encounter cards index.")
  bag.call("rebuildIndex")
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
  self.addTag("AllEncounterCardsHotfix")
  addToIndex()
end
