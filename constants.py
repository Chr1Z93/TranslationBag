# Using for bag names
CYCLE_NAMES = {
  "00": "Investigator Cards",
  "01": "Core Set",
  "02": "The Dunwich Legacy",
  "81": "Curse of the Rougarou"
}

# Expansion campaigns require core set to be playable.
# While assembling campaign bags, we check bag's cycle_id against this list,
# if this list contains processed bag cycle_id - we add core set cards to the bag
CAMPAIGNS_WITH_CORE = ["02"]
