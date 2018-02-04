# Pokémon TCG Data tools and reprint detection

This is a set of tools for operating on the Pokémon TCG data either through the API located here [Pokémon TCG API](https://pokemontcg.io/) or directly against the underlying files used by the API located at [pokemon-tcg-data](https://github.com/PokemonTCG/pokemon-tcg-data)

## bin/fixcards
```
usage: fixcards [-h] [-v] [-d] --carddir CARDDIR [--formats FORMATS]
```

fixcards is intended to be used on the [pokemon-tcg-data](https://github.com/PokemonTCG/pokemon-tcg-data) files specified by CARDDIR, it reads all the data into memory, implements a series of filters on the data to correct common mistakes, and then writes the files back out.  Current implemented filters include:
* **sort_energy** - sorts the energy in attack costs in the order of [Free, Fire, Grass, Water, Psychic, Darkness, Fairy, Lighting, Fighting, Metal, Colorless].  This is consistent with the card data for most sets (see below for exceptions)
* **apostrophe_to_quotes** - changes apostrophe (’) to single quote (') when followed by 's' or 't' and a word break.
* **x_to_times** - Change x to 'times' when letter x is used in x+d (e.g. x2) or d+ (e.g. 20x)
* **clean_attack_text** - Fix common mistakes in attack test:
  * Remove when attack damage is included in the attack text e.g. "(20+) This attack does 20 damage plus ...

# formats.json
The tool expects a propely formatted FORMATS file (see below)  Specifically, fixcards looks for the following keys in FORMATS:

*setfiles*: specifies the particular sets and filenames to load
```
"setfiles": {
  "xy7": "Ancient Origins.json",
  "ecard2": "Aquapolis.json",
  "pl4": "Arceus.json",
  "xy9": "BREAKpoint.json",
  "xy8": "BREAKthrough.json",
  ...
```
*dont_sort_energy*: sets to **not** sort energy in attack costs.  These particular sets don't follow the typical sorting pattern, so for now - they are not sorted other than placing 'colorless' energy at the end
```
"dont_sort_energy": [
  "ecard",
  "ecard2",
  "ecard3",
  "pl4",
  "ex8",
  ...
  ```
*keyorder*: specifies the order of the keys to write into the files.  While not at all relevant for using the jsons, it helps ensure when a new key (e.g. a missing ability) is added, it's inserted in a consistent location.  The order of the files are very consistent except for older files swapping the position of "imageUrlHiRes" and "nationalPokedexNumber", so the first time fixcards is run, it will likely modify several of the files.
```
"keyorder": {
  ".": [
    "id",
    "name",
    "imageUrl",
    "subtype",
    "supertype",
    "level",
    "evolvesFrom",
    "ability",
    "ancientTrait",
    "hp",
    "retreatCost",
    "number",
    ...
  ".ability": [
    "name",
    "text",
    "type"
  ],
  ".ancientTrait": [
    "name",
    "text"
    ...
```

The FORMATS file I use is located in tcgdata/formats.json
