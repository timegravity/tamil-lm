"""Build the nature pack: the knowledge source for the photo-identification feature.

  .venv/bin/python build_pack_nature.py             # build data/packs/nature/ (offline dump + a few API calls)
  .venv/bin/python build_pack_nature.py --no-fetch  # build from the cache in data/raw/packs/nature only
  .venv/bin/python build_pack_nature.py --titles    # print the Tamil Wikipedia titles that would be selected

The model guesses a category label from a photo. The Tamil name, the alternative names and the
description that the user sees must come from this pack, never from the weights, so the pack carries a
matching table (entities.jsonl) as well as retrieval text (chunks.jsonl).

Source, primary: the OFFLINE family-safe copy of the Tamil Wikipedia dump at
data/index/tawiki_20260801_fs/articles.jsonl (186,741 articles). English names and scientific names are
read out of the Tamil article's own lead, which almost always carries them in brackets.

Source, gap fill only: the live ta.wikipedia MediaWiki API, for
  a. the licence, read from the wiki's own siteinfo rightsinfo API on the build date,
  b. alternative Tamil names, taken from the redirects that point at each entity's article (batched
     50 titles per request),
  c. the handful of coverage-list species whose article the offline dump does not resolve, looked up by
     scientific name with list=search.
Every request carries the User-Agent tamil-lm-research (contact@timegravity.ai) and is spaced to stay
under two requests per second. Responses are cached under data/raw/packs/nature so a rebuild costs none.

CPU only: no model, no embeddings. The dense index over chunks.jsonl is built separately.
"""
import argparse, json, os, re, sys, time, urllib.parse, urllib.request
from collections import Counter, OrderedDict

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
import family_safe as FS
import build_pack_cooking as CK      # chunking, dump-text blocks, MediaWiki helpers: same shape as the cooking pack

PACK = os.path.join(ROOT, "data", "packs", "nature")
CACHE = os.path.join(ROOT, "data", "raw", "packs", "nature")
TAWIKI = os.path.join(ROOT, "data", "index", "tawiki_20260801_fs", "articles.jsonl")
HOST = "ta.wikipedia.org"
VERSION = "2026-09-09"
LICENSE = "CC BY-SA 4.0"

# ------------------------------------------------------------------ coverage list 1: 100 common Indian birds
# (english name, scientific name, one-line English gloss, extra match terms)
# Written from ornithological common knowledge; the Tamil name, the article and the Tamil description are
# whatever the pack actually resolves, so a blank in the coverage table is a real gap, not a guess.
BIRDS = [
 ("house crow", "Corvus splendens", "a grey-necked black crow that lives close to people in Indian towns and villages", ["crow", "indian house crow"]),
 ("large-billed crow", "Corvus macrorhynchos", "an all-black crow of groves and hill country, heavier billed than the house crow", ["jungle crow"]),
 ("house sparrow", "Passer domesticus", "a small brown and grey bird that nests in house eaves and feeds on grain and crumbs", ["sparrow"]),
 ("common myna", "Acridotheres tristis", "a brown bird with a yellow bill, a yellow eye patch and white wing flashes, at home on the ground near people", ["myna", "mynah", "indian myna"]),
 ("jungle myna", "Acridotheres fuscus", "a myna with a tuft of feathers over the bill, found near groves and grazing cattle", []),
 ("bank myna", "Acridotheres ginginianus", "a grey myna with a brick-red patch behind the eye that nests in river banks and walls", []),
 ("brahminy starling", "Sturnia pagodarum", "a small buff and grey starling with a loose black crest", ["brahminy myna"]),
 ("rosy starling", "Pastor roseus", "a pink and black starling that arrives in India in large winter flocks", ["rosy pastor"]),
 ("rock pigeon", "Columba livia", "the blue-grey pigeon of temples, ledges and city squares", ["pigeon", "blue rock pigeon", "rock dove"]),
 ("spotted dove", "Spilopelia chinensis", "a warm brown dove with a black and white spotted collar", ["dove"]),
 ("laughing dove", "Spilopelia senegalensis", "a small pinkish-brown dove with a speckled breast band", []),
 ("eurasian collared dove", "Streptopelia decaocto", "a pale grey dove with a thin black half-collar", ["collared dove"]),
 ("red-vented bulbul", "Pycnonotus cafer", "a dark garden bird with a black crest and a red patch under the tail", ["bulbul"]),
 ("red-whiskered bulbul", "Pycnonotus jocosus", "a crested bulbul with a red spot behind the eye and a white cheek", []),
 ("white-browed bulbul", "Pycnonotus luteolus", "a plain olive bulbul of scrub, heard far more often than seen", []),
 ("black kite", "Milvus migrans", "a dark brown raptor with a forked tail that circles over towns and rubbish grounds", ["kite", "pariah kite"]),
 ("brahminy kite", "Haliastur indus", "a chestnut raptor with a white head and breast, usually near water", []),
 ("shikra", "Accipiter badius", "a small grey hawk with finely barred underparts that hunts lizards and small birds in gardens", ["hawk"]),
 ("black-winged kite", "Elanus caeruleus", "a small white and grey raptor with black shoulders that hovers over fields", ["black-shouldered kite"]),
 ("egyptian vulture", "Neophron percnopterus", "a small white vulture with a bare yellow face and black flight feathers", []),
 ("white-rumped vulture", "Gyps bengalensis", "a large dark vulture with a white rump patch, now very rare", ["vulture", "indian white-backed vulture"]),
 ("indian pond heron", "Ardeola grayii", "a squat streaked heron that turns startlingly white when it opens its wings", ["pond heron", "paddybird"]),
 ("cattle egret", "Bubulcus ibis", "a small white egret that follows cattle and ploughs, with buff plumes when breeding", ["egret"]),
 ("little egret", "Egretta garzetta", "a slender white egret with a black bill and yellow feet", []),
 ("great egret", "Ardea alba", "the largest white egret, with a yellow bill and a long kinked neck", ["large egret"]),
 ("intermediate egret", "Ardea intermedia", "a medium white egret between the little and the great egret in size", []),
 ("grey heron", "Ardea cinerea", "a tall grey heron with a black eye stripe that stands still in shallow water", ["heron"]),
 ("purple heron", "Ardea purpurea", "a slim chestnut and grey heron of reed beds", []),
 ("black-crowned night heron", "Nycticorax nycticorax", "a stocky grey and black heron that feeds at dusk", ["night heron"]),
 ("little cormorant", "Microcarbo niger", "a small black diving waterbird that perches with its wings spread out to dry", ["cormorant"]),
 ("indian cormorant", "Phalacrocorax fuscicollis", "a slim black cormorant with a narrow bill that fishes in flocks", ["indian shag"]),
 ("oriental darter", "Anhinga melanogaster", "a black waterbird that swims with only its snake-like neck above the surface", ["darter", "snakebird"]),
 ("painted stork", "Mycteria leucocephala", "a white stork with pink flight feathers and a long yellow curved bill", ["stork"]),
 ("asian openbill", "Anastomus oscitans", "a white and black stork whose bill leaves a gap when closed, a snail eater", ["openbill stork"]),
 ("woolly-necked stork", "Ciconia episcopus", "a black stork with a white woolly neck", []),
 ("black-headed ibis", "Threskiornis melanocephalus", "a white ibis with a bare black head and a long curved bill", ["ibis", "white ibis"]),
 ("glossy ibis", "Plegadis falcinellus", "a dark ibis that shines green and purple in sunlight", []),
 ("eurasian spoonbill", "Platalea leucorodia", "a white waterbird with a flat spoon-shaped bill that it sweeps through the water", ["spoonbill"]),
 ("greater flamingo", "Phoenicopterus roseus", "a tall pink and white wading bird with a bent bill, feeding in salt pans", ["flamingo"]),
 ("indian spot-billed duck", "Anas poecilorhyncha", "a large brown duck with a yellow-tipped bill", ["spot-billed duck", "duck"]),
 ("lesser whistling duck", "Dendrocygna javanica", "a small chestnut duck that whistles as it flies", ["whistling teal"]),
 ("knob-billed duck", "Sarkidiornis melanotos", "a black and white duck, the male with a fleshy knob on the bill", ["comb duck"]),
 ("eurasian coot", "Fulica atra", "a sooty black waterbird with a white bill and forehead shield", ["coot"]),
 ("white-breasted waterhen", "Amaurornis phoenicurus", "a slate and white marsh bird that walks with its tail flicking", ["waterhen"]),
 ("grey-headed swamphen", "Porphyrio poliocephalus", "a large purple-blue marsh bird with a red bill and long red legs", ["purple swamphen", "purple moorhen"]),
 ("common moorhen", "Gallinula chloropus", "a dark waterbird with a red and yellow bill", ["moorhen"]),
 ("red-wattled lapwing", "Vanellus indicus", "a black, white and brown plover with red wattles and a ringing alarm call", ["lapwing"]),
 ("yellow-wattled lapwing", "Vanellus malabaricus", "a dry-country lapwing with yellow wattles and a black cap", []),
 ("black-winged stilt", "Himantopus himantopus", "a black and white wader on very long pink legs", ["stilt"]),
 ("little ringed plover", "Charadrius dubius", "a small sandy plover with a yellow ring round the eye", ["plover"]),
 ("common sandpiper", "Actitis hypoleucos", "a small brown wader that bobs its tail on stream edges", ["sandpiper"]),
 ("whiskered tern", "Chlidonias hybrida", "a marsh tern that dips over tanks and paddy fields", ["tern"]),
 ("brown-headed gull", "Chroicocephalus brunnicephalus", "a coastal winter gull that grows a chocolate hood in the breeding season", ["gull", "seagull"]),
 ("common kingfisher", "Alcedo atthis", "a tiny blue and orange kingfisher that dives from a low perch", ["kingfisher", "small blue kingfisher"]),
 ("white-throated kingfisher", "Halcyon smyrnensis", "a brown and turquoise kingfisher with a white throat and a red bill, often far from water", ["white-breasted kingfisher"]),
 ("pied kingfisher", "Ceryle rudis", "a black and white kingfisher that hovers over water before diving", []),
 ("stork-billed kingfisher", "Pelargopsis capensis", "a big kingfisher with a heavy red bill", []),
 ("green bee-eater", "Merops orientalis", "a slim green bird with a curved bill that catches bees in the air", ["bee-eater", "bee eater", "little green bee-eater"]),
 ("blue-tailed bee-eater", "Merops philippinus", "a larger bee-eater with a blue tail and a chestnut throat", []),
 ("indian roller", "Coracias benghalensis", "a stocky bird that flashes bright blue wings in flight", ["roller", "blue jay"]),
 ("eurasian hoopoe", "Upupa epops", "a buff bird with barred black and white wings and a fan-like crest", ["hoopoe"]),
 ("asian koel", "Eudynamys scolopaceus", "a glossy black cuckoo with a red eye, known for its rising call before the rains", ["koel", "cuckoo"]),
 ("greater coucal", "Centropus sinensis", "a heavy black bird with chestnut wings that walks through undergrowth", ["coucal", "crow pheasant"]),
 ("common hawk-cuckoo", "Hierococcyx varius", "a hawk-like cuckoo that calls insistently through the hot weather", ["brainfever bird"]),
 ("rose-ringed parakeet", "Psittacula krameri", "a green parrot with a red bill, the male with a rose and black neck ring", ["parakeet", "parrot", "ring-necked parakeet"]),
 ("plum-headed parakeet", "Psittacula cyanocephala", "a green parakeet, the male with a plum-red head", []),
 ("alexandrine parakeet", "Psittacula eupatria", "a large green parakeet with a red shoulder patch", []),
 ("spotted owlet", "Athene brama", "a small spotted owl that peers out of tree holes and old buildings by day", ["owlet"]),
 ("barn owl", "Tyto alba", "a pale owl with a heart-shaped face that hunts rats at night", ["owl"]),
 ("indian eagle-owl", "Bubo bengalensis", "a large brown owl with ear tufts and orange eyes", ["rock eagle-owl"]),
 ("indian nightjar", "Caprimulgus asiaticus", "a cryptic dusk-flying bird that rests along the ground", ["nightjar"]),
 ("little swift", "Apus affinis", "a small black swift with a white rump that nests in colonies on buildings", ["house swift", "swift"]),
 ("asian palm swift", "Cypsiurus balasiensis", "a slender swift that glues its nest into a palm frond", []),
 ("barn swallow", "Hirundo rustica", "a blue-black swallow with a red throat and a deeply forked tail", ["swallow"]),
 ("red-rumped swallow", "Cecropis daurica", "a swallow with a chestnut rump that builds a mud nest under bridges", []),
 ("common tailorbird", "Orthotomus sutorius", "a small olive warbler that stitches leaves together into a nest", ["tailorbird"]),
 ("purple sunbird", "Cinnyris asiaticus", "a tiny nectar bird, the male glossy purple-black in the breeding season", ["sunbird"]),
 ("purple-rumped sunbird", "Leptocoma zeylonica", "a small sunbird with a yellow belly and a maroon breast band", []),
 ("loten's sunbird", "Cinnyris lotenius", "a long-billed sunbird of gardens in the south", ["long-billed sunbird"]),
 ("indian white-eye", "Zosterops palpebrosus", "a small yellow-green bird with a white ring round the eye", ["oriental white-eye", "white-eye"]),
 ("baya weaver", "Ploceus philippinus", "a yellow and brown weaver that builds a hanging flask-shaped nest", ["weaver bird", "baya"]),
 ("scaly-breasted munia", "Lonchura punctulata", "a small brown finch with scaly markings on the breast", ["munia", "spotted munia"]),
 ("indian silverbill", "Euodice malabarica", "a pale munia with a silvery bill and a pointed tail", ["white-throated munia"]),
 ("red avadavat", "Amandava amandava", "a tiny red and white spotted finch of tall grass", ["red munia", "strawberry finch"]),
 ("black drongo", "Dicrurus macrocercus", "a glossy black bird with a forked tail that perches on wires and on cattle", ["drongo", "king crow"]),
 ("ashy drongo", "Dicrurus leucophaeus", "a grey drongo of wooded country in winter", []),
 ("indian golden oriole", "Oriolus kundoo", "a bright yellow bird with black wings and a pink bill", ["golden oriole", "oriole"]),
 ("black-hooded oriole", "Oriolus xanthornus", "a yellow oriole with a black head", []),
 ("rufous treepie", "Dendrocitta vagabunda", "a long-tailed rust and grey bird of the crow family", ["treepie", "indian treepie"]),
 ("indian robin", "Copsychus fulicatus", "a dark bird with a chestnut vent that cocks its tail on stony ground", ["robin"]),
 ("oriental magpie-robin", "Copsychus saularis", "a black and white songbird of gardens and compounds", ["magpie robin"]),
 ("pied bushchat", "Saxicola caprata", "a small black and white chat of open fields and fence wires", ["bushchat"]),
 ("white-browed wagtail", "Motacilla maderaspatensis", "a large black and white wagtail of river banks and rooftops", ["wagtail", "large pied wagtail"]),
 ("paddyfield pipit", "Anthus rufulus", "a streaked brown bird that runs in short bursts over open ground", ["pipit"]),
 ("indian peafowl", "Pavo cristatus", "the blue-necked peacock, the male carrying a great eyed train", ["peacock", "peahen", "peafowl"]),
 ("grey junglefowl", "Gallus sonneratii", "the wild fowl of the southern forests, the male grey with yellow-tipped neck feathers", ["junglefowl"]),
 ("red junglefowl", "Gallus gallus", "the wild ancestor of the domestic chicken", []),
 ("grey francolin", "Francolinus pondicerianus", "a plump brown game bird of scrub that calls at dawn", ["grey partridge", "francolin", "partridge"]),
 ("indian grey hornbill", "Ocyceros birostris", "a grey hornbill with a casque on the bill that feeds on figs", ["hornbill"]),
 ("coppersmith barbet", "Psilopogon haemacephalus", "a small green barbet with a crimson forehead whose call is a steady metallic knock", ["barbet", "crimson-breasted barbet"]),
]

# ------------------------------------------------------------------ coverage list 2: 100 common Indian plants and trees
# (english name, scientific name, kind, gloss, extra match terms)
PLANTS = [
 ("neem", "Azadirachta indica", "tree", "a bitter-leaved shade tree used in medicine and as a village pesticide", ["margosa", "indian lilac", "neem tree"]),
 ("banyan", "Ficus benghalensis", "tree", "a huge fig tree that drops aerial roots and spreads into a grove", ["banyan tree", "indian banyan"]),
 ("sacred fig", "Ficus religiosa", "tree", "a fig with heart-shaped long-tipped leaves that rustle in the least wind", ["peepal", "pipal", "bodhi tree", "bo tree"]),
 ("coconut palm", "Cocos nucifera", "tree", "the tall palm of the coast that gives coconuts, fronds and toddy", ["coconut tree", "coconut palm tree"]),
 ("mango tree", "Mangifera indica", "tree", "the dense dark-leaved tree that bears mangoes", ["mango tree"]),
 ("tamarind tree", "Tamarindus indica", "tree", "a broad shade tree with feathery leaves and sour brown pods", ["tamarind", "tamarind tree"]),
 ("arabian jasmine", "Jasminum sambac", "flower", "a white jasmine with a heavy scent, strung into garlands", ["jasmine", "mogra", "sambac jasmine", "malli"]),
 ("hibiscus", "Hibiscus rosa-sinensis", "flower", "a shrub with large trumpet flowers and a long central column of stamens", ["shoe flower", "china rose", "rose mallow"]),
 ("holy basil", "Ocimum tenuiflorum", "plant", "a small aromatic basil grown in house courtyards and used in medicine", ["tulsi", "tulasi", "sacred basil"]),
 ("palmyra palm", "Borassus flabellifer", "tree", "a tall fan-leaved palm of the dry plains, giving fruit, sap and leaf", ["toddy palm", "palmyra", "palmyrah"]),
 ("areca palm", "Areca catechu", "tree", "a slender palm whose nut is chewed with betel leaf", ["betel nut palm", "areca nut", "arecanut"]),
 ("jackfruit tree", "Artocarpus heterophyllus", "tree", "a tree that bears the largest of all fruits straight off its trunk", ["jack tree"]),
 ("indian gooseberry tree", "Phyllanthus emblica", "tree", "a small tree with feathery leaves and hard sour green fruit", ["amla tree", "emblic", "nelli tree"]),
 ("sandalwood", "Santalum album", "tree", "a small semi-parasitic tree whose heartwood is fragrant", ["sandal tree", "white sandalwood", "sandal"]),
 ("teak", "Tectona grandis", "tree", "a tall timber tree with very large rough leaves", ["teak tree"]),
 ("indian rosewood", "Dalbergia latifolia", "tree", "a timber tree with dark streaked heartwood", ["rosewood", "blackwood"]),
 ("chinese banyan", "Ficus microcarpa", "tree", "a small-leaved fig often clipped as an avenue tree", ["indian laurel fig", "curtain fig"]),
 ("cluster fig", "Ficus racemosa", "tree", "a fig that carries its fruit in bunches directly on the trunk", ["gular fig", "country fig"]),
 ("portia tree", "Thespesia populnea", "tree", "a coastal tree with heart-shaped leaves and yellow cup flowers", ["indian tulip tree"]),
 ("indian beech", "Millettia pinnata", "tree", "a glossy-leaved shade tree whose seed gives lamp oil", ["pongamia", "pongam", "karanja"]),
 ("rain tree", "Samanea saman", "tree", "a wide umbrella-crowned tree whose leaflets fold at dusk", ["monkey pod"]),
 ("flamboyant", "Delonix regia", "tree", "a tree that turns scarlet with flowers just before the rains", ["gulmohar", "flame tree", "royal poinciana"]),
 ("copperpod", "Peltophorum pterocarpum", "tree", "an avenue tree with yellow flower sprays and copper-coloured pods", ["yellow flame tree", "copper pod"]),
 ("indian cork tree", "Millingtonia hortensis", "tree", "a tall slim tree with long white night-scented flowers", ["tree jasmine", "akash neem"]),
 ("bael", "Aegle marmelos", "tree", "a thorny tree with three-part leaves and a hard-shelled fruit", ["bael tree", "stone apple", "bilva"]),
 ("wood apple", "Limonia acidissima", "tree", "a tree with a hard grey fruit whose sour pulp goes into chutneys", ["elephant apple", "curd fruit"]),
 ("curry leaf tree", "Murraya koenigii", "plant", "a small tree whose aromatic leaves flavour south Indian cooking", ["curry tree", "curry leaf"]),
 ("drumstick tree", "Moringa oleifera", "tree", "a soft-wooded tree with long ribbed pods and edible leaves", ["moringa", "horseradish tree", "moringa tree"]),
 ("custard apple tree", "Annona squamosa", "tree", "a small tree with a knobbly green fruit full of sweet white pulp", ["sugar apple tree", "sitaphal tree"]),
 ("guava tree", "Psidium guajava", "tree", "a small tree with peeling bark and round fruit with pink or white flesh", []),
 ("sapodilla", "Manilkara zapota", "tree", "an evergreen tree with a brown sweet grainy fruit", ["sapota tree", "chikoo tree"]),
 ("papaya tree", "Carica papaya", "tree", "a soft-stemmed tree with a crown of lobed leaves and orange fruit", ["pawpaw tree"]),
 ("pomegranate tree", "Punica granatum", "tree", "a shrubby tree with red flowers and a fruit full of juicy seeds", []),
 ("indian jujube tree", "Ziziphus mauritiana", "tree", "a thorny tree with small round sweet-sour fruit", ["ber tree", "indian plum tree"]),
 ("cashew tree", "Anacardium occidentale", "tree", "a spreading tree whose nut hangs below a fleshy false fruit", ["cashew"]),
 ("red silk cotton tree", "Bombax ceiba", "tree", "a thorny tree with big red cup flowers and pods full of white floss", ["silk cotton tree", "cotton tree", "semal"]),
 ("kapok", "Ceiba pentandra", "tree", "a tall buttressed tree whose pods give white silk cotton", ["white silk cotton tree", "java cotton"]),
 ("flame of the forest", "Butea monosperma", "tree", "a tree that carries orange parrot-beak flowers on bare branches", ["palash", "dhak", "bastard teak"]),
 ("indian coral tree", "Erythrina variegata", "tree", "a thorny tree with bright scarlet flowers", ["coral tree", "tiger claw"]),
 ("indian almond", "Terminalia catappa", "tree", "a tree with tiers of branches and large leaves that turn red before falling", ["sea almond", "tropical almond"]),
 ("arjuna", "Terminalia arjuna", "tree", "a large riverside tree with smooth pale bark used in medicine", ["arjun tree", "white murdah"]),
 ("beleric", "Terminalia bellirica", "tree", "a forest tree whose fruit is one of the three myrobalans", ["bahera", "bedda nut"]),
 ("chebulic myrobalan", "Terminalia chebula", "tree", "a tree whose ribbed fruit is the chief myrobalan of Indian medicine", ["haritaki", "black myrobalan"]),
 ("ashoka tree", "Saraca asoca", "tree", "a small tree with drooping young leaves and dense orange flower heads", ["asoka", "sita ashok"]),
 ("false ashoka", "Polyalthia longifolia", "tree", "a tall narrow tree with wavy hanging leaves, planted along drives", ["mast tree", "indian mast tree"]),
 ("champak", "Magnolia champaca", "tree", "a tree with strongly fragrant orange-yellow flowers", ["champa", "golden champa", "chempaka"]),
 ("frangipani", "Plumeria rubra", "tree", "a small tree with thick bare branches and waxy scented flowers", ["temple tree", "plumeria", "pagoda tree"]),
 ("night-flowering jasmine", "Nyctanthes arbor-tristis", "tree", "a shrub whose orange-stalked white flowers open at night and carpet the ground by morning", ["parijat", "coral jasmine", "parijatham"]),
 ("crepe jasmine", "Tabernaemontana divaricata", "flower", "a shrub with milky sap and flat white pinwheel flowers", ["pinwheel flower", "nandiyavattai", "east india rosebay"]),
 ("oleander", "Nerium oleander", "flower", "a poisonous shrub with narrow leaves and pink or white flowers", ["nerium", "rose bay"]),
 ("yellow oleander", "Cascabela thevetia", "flower", "a shrub with yellow bell flowers and a poisonous seed", ["lucky nut", "thevetia"]),
 ("marigold", "Tagetes erecta", "flower", "a garden flower with dense orange or yellow heads, made into garlands", ["african marigold", "genda"]),
 ("rose", "Rosa indica", "flower", "a thorny shrub grown for its scented layered flowers", ["roses", "garden rose"]),
 ("sacred lotus", "Nelumbo nucifera", "flower", "a water plant whose round leaves stand above the water and whose large flowers are pink or white", ["lotus", "indian lotus"]),
 ("water lily", "Nymphaea nouchali", "flower", "a water plant with notched floating leaves and cup-shaped flowers", ["waterlily", "blue lotus", "lily"]),
 ("chrysanthemum", "Chrysanthemum indicum", "flower", "a garden daisy with crowded petals, grown for garlands", ["mum", "samanthi"]),
 ("sunflower", "Helianthus annuus", "flower", "a tall annual with one large yellow head that turns with the sun", []),
 ("bougainvillea", "Bougainvillea glabra", "flower", "a thorny climber whose colour comes from papery bracts rather than petals", ["paper flower"]),
 ("jungle geranium", "Ixora coccinea", "flower", "a shrub with dense heads of small red tube flowers", ["ixora", "flame of the woods"]),
 ("screwpine", "Pandanus odorifer", "plant", "a coastal shrub with spiny strap leaves and a strongly scented flower", ["kewda", "pandanus", "umbrella tree"]),
 ("lantana", "Lantana camara", "plant", "a rough-leaved shrub with small clustered flowers that change colour as they age", ["wild sage"]),
 ("madagascar periwinkle", "Catharanthus roseus", "flower", "a small garden plant with pink or white five-petalled flowers, used in medicine", ["periwinkle", "sadabahar"]),
 ("garden balsam", "Impatiens balsamina", "flower", "a soft annual whose ripe pods burst at a touch", ["balsam", "rose balsam"]),
 ("spanish jasmine", "Jasminum grandiflorum", "flower", "a jasmine with larger flowers, grown for perfume and for garlands", ["royal jasmine", "jathi malli"]),
 ("aloe vera", "Aloe vera", "plant", "a stemless succulent with thick spiny-edged leaves full of clear gel", ["aloe"]),
 ("malabar nut", "Justicia adhatoda", "plant", "a shrub whose leaves are used against coughs", ["adhatoda", "vasaka", "adathodai"]),
 ("chaste tree", "Vitex negundo", "plant", "an aromatic shrub with five-fingered leaves used in medicine", ["five-leaved chaste tree", "nochi", "nirgundi"]),
 ("king of bitters", "Andrographis paniculata", "plant", "a very bitter herb taken against fever", ["nilavembu", "kalmegh", "creat"]),
 ("gale of the wind", "Phyllanthus niruri", "plant", "a small herb that carries its seed under the leaf, used for liver complaints", ["stonebreaker", "keezhanelli"]),
 ("asiatic pennywort", "Centella asiatica", "plant", "a creeping herb with round scalloped leaves, taken for memory", ["gotu kola", "vallarai", "brahmi"]),
 ("false daisy", "Eclipta prostrata", "plant", "a low herb with small white heads, used in hair oils", ["bhringraj", "karisalankanni"]),
 ("climbing brinjal", "Solanum trilobatum", "plant", "a thorny climber whose leaves are cooked for coughs", ["thoothuvalai", "purple fruited pea eggplant"]),
 ("mountain knotgrass", "Aerva lanata", "plant", "a woolly roadside herb used for urinary complaints", ["poolai", "sirupeelai"]),
 ("balloon vine", "Cardiospermum halicacabum", "plant", "a slender climber with papery three-cornered fruit, used for joint pain", ["mudakathan", "love in a puff"]),
 ("indian thorny bamboo", "Bambusa bambos", "plant", "a giant clumping grass with hollow woody stems", ["bamboo", "giant thorny bamboo"]),
 ("sugarcane", "Saccharum officinarum", "plant", "a tall grass with thick sweet juicy stems", ["sugar cane"]),
 ("rice", "Oryza sativa", "plant", "the grass grown in flooded fields whose grain is the staple food", ["paddy", "rice plant"]),
 ("wheat", "Triticum aestivum", "plant", "the winter cereal grass whose grain is ground into flour", []),
 ("maize", "Zea mays", "plant", "a tall cereal grass that carries its grain on a cob", ["corn", "sweet corn"]),
 ("finger millet", "Eleusine coracana", "plant", "a millet with finger-like spikes, ground into a dark flour", ["ragi", "kezhvaragu"]),
 ("pearl millet", "Pennisetum glaucum", "plant", "a dry-land millet with a thick cylindrical head", ["bajra", "kambu"]),
 ("sorghum", "Sorghum bicolor", "plant", "a tall millet with a loose head of round grain", ["jowar", "cholam", "great millet"]),
 ("cotton", "Gossypium herbaceum", "plant", "a shrub whose seed pods burst into white fibre", ["cotton plant"]),
 ("groundnut", "Arachis hypogaea", "plant", "a low legume that ripens its pods underground", ["peanut", "monkey nut"]),
 ("sesame", "Sesamum indicum", "plant", "an erect annual whose small seeds are pressed for oil", ["gingelly", "til", "sesamum"]),
 ("castor", "Ricinus communis", "plant", "a fast-growing plant with large hand-shaped leaves and spiny seed capsules", ["castor oil plant"]),
 ("blue gum", "Eucalyptus globulus", "tree", "a tall aromatic plantation tree with peeling bark", ["eucalyptus", "gum tree"]),
 ("beach she-oak", "Casuarina equisetifolia", "tree", "a coastal tree with needle-like drooping branchlets", ["casuarina", "australian pine"]),
 ("gum arabic tree", "Vachellia nilotica", "tree", "a thorny acacia of dry country with yellow ball flowers", ["babul", "acacia nilotica", "karuvelam"]),
 ("mesquite", "Prosopis juliflora", "tree", "a hardy thorny invader of dry waste ground", ["prosopis", "seemai karuvelam"]),
 ("crown flower", "Calotropis gigantea", "plant", "a milky shrub of waste ground with crown-shaped mauve or white flowers", ["giant milkweed", "erukku", "calotropis"]),
 ("coffee", "Coffea arabica", "plant", "a hill shrub with glossy leaves and red cherries that hold the coffee bean", ["coffee plant", "arabica"]),
 ("tea", "Camellia sinensis", "plant", "a clipped evergreen bush whose young leaves are made into tea", ["tea plant", "tea bush"]),
 ("rubber tree", "Hevea brasiliensis", "tree", "a plantation tree tapped for white latex", ["para rubber tree"]),
 ("black pepper", "Piper nigrum", "plant", "a woody climber whose green berry spikes dry into peppercorns", ["pepper vine", "pepper"]),
 ("betel", "Piper betle", "plant", "a climbing vine whose heart-shaped leaf is chewed with areca nut", ["betel leaf", "paan", "vetrilai"]),
 ("cardamom", "Elettaria cardamomum", "plant", "a shade-grown herb of the hills whose green pods are a spice", ["green cardamom", "elaichi"]),
 ("turmeric", "Curcuma longa", "plant", "a rhizome herb whose boiled and dried root gives a yellow spice", ["haldi", "manjal"]),
 ("ginger", "Zingiber officinale", "plant", "a herb grown for its pungent underground stem", ["ginger root"]),
 ("kadamba", "Neolamarckia cadamba", "tree", "a fast-growing tree with orange ball-shaped flower heads", ["kadam", "burflower tree"]),
]

# ------------------------------------------------------------------ coverage list 3: common fruits and vegetables
FOODS = [
 ("mango", "Mangifera indica", "fruit", "the king of Indian fruits, yellow or red-cheeked with one flat stone", ["mangoes"]),
 ("banana", "Musa acuminata", "fruit", "a soft sweet fruit that grows in hands on a large herb", ["bananas", "plantain"]),
 ("jackfruit", "Artocarpus heterophyllus", "fruit", "a very large green fruit with sweet yellow bulbs inside", ["jack fruit"]),
 ("guava", "Psidium guajava", "fruit", "a round green fruit with white or pink seedy flesh", ["guavas"]),
 ("papaya", "Carica papaya", "fruit", "an orange-fleshed fruit with a hollow full of black seeds", ["pawpaw"]),
 ("pomegranate", "Punica granatum", "fruit", "a leathery red fruit packed with juicy seeds", ["anar"]),
 ("sapota", "Manilkara zapota", "fruit", "a brown fruit with grainy sweet flesh", ["chikoo", "chiku", "sapodilla"]),
 ("custard apple", "Annona squamosa", "fruit", "a knobbly green fruit with sweet white pulp", ["sugar apple", "sitaphal"]),
 ("watermelon", "Citrullus lanatus", "fruit", "a large green-skinned melon with red watery flesh", ["water melon"]),
 ("muskmelon", "Cucumis melo", "fruit", "a netted melon with sweet orange or green flesh", ["cantaloupe", "melon"]),
 ("grape", "Vitis vinifera", "fruit", "small round fruit carried in bunches on a climbing vine", ["grapes"]),
 ("mandarin orange", "Citrus reticulata", "fruit", "a loose-skinned orange citrus that peels easily", ["orange", "tangerine"]),
 ("sweet lime", "Citrus limetta", "fruit", "a pale green-yellow citrus with mild sweet juice", ["mosambi", "musambi"]),
 ("lemon", "Citrus limon", "fruit", "a yellow sour citrus", ["lemons"]),
 ("key lime", "Citrus aurantiifolia", "fruit", "a small green very sour lime", ["lime", "indian lime"]),
 ("pineapple", "Ananas comosus", "fruit", "a spiny-skinned fruit with a crown of leaves and sweet yellow flesh", ["pine apple"]),
 ("apple", "Malus domestica", "fruit", "a crisp red or green temperate fruit", ["apples"]),
 ("pear", "Pyrus communis", "fruit", "a sweet grainy temperate fruit, narrow at the stalk", ["pears"]),
 ("date", "Phoenix dactylifera", "fruit", "a sweet sticky palm fruit", ["dates", "date palm"]),
 ("fig", "Ficus carica", "fruit", "a soft purple or green fruit full of tiny seeds", ["figs", "common fig", "anjeer"]),
 ("tamarind", "Tamarindus indica", "fruit", "a brown pod with sour sticky pulp used to sour a curry", ["tamarind pod"]),
 ("indian gooseberry", "Phyllanthus emblica", "fruit", "a hard pale green fruit, very sour and astringent", ["amla", "nellikai", "gooseberry"]),
 ("indian jujube", "Ziziphus mauritiana", "fruit", "a small round sweet-sour fruit off a thorny tree", ["ber", "elandhai", "jujube"]),
 ("rose apple", "Syzygium jambos", "fruit", "a pale watery fruit that smells of roses", ["water apple", "jambu"]),
 ("java plum", "Syzygium cumini", "fruit", "a dark purple astringent fruit that stains the tongue", ["jamun", "black plum", "naval"]),
 ("star fruit", "Averrhoa carambola", "fruit", "a ribbed yellow fruit that cuts into stars", ["carambola", "starfruit"]),
 ("passion fruit", "Passiflora edulis", "fruit", "a wrinkled purple fruit with tart aromatic pulp", ["passionfruit"]),
 ("coconut", "Cocos nucifera", "fruit", "a hard-shelled palm fruit with a white kernel and sweet water", ["coconuts", "tender coconut"]),
 ("palmyra fruit", "Borassus flabellifer", "fruit", "a black palm fruit holding jelly-like kernels", ["ice apple", "nungu", "palmyra palm fruit"]),
 ("cashew apple", "Anacardium occidentale", "fruit", "the fleshy red or yellow false fruit that carries the cashew nut", ["cashew fruit"]),
 ("mulberry", "Morus alba", "fruit", "a small soft fruit of the mulberry tree whose leaves feed silkworms", ["mulberries"]),
 ("lychee", "Litchi chinensis", "fruit", "a rough pink-skinned fruit with translucent sweet flesh", ["litchi", "lichee"]),
 ("pomelo", "Citrus maxima", "fruit", "the largest citrus, thick-rinded with pale sweet segments", ["shaddock"]),
 ("sweet orange", "Citrus sinensis", "fruit", "a round orange citrus with a tight skin", []),
 ("bael fruit", "Aegle marmelos", "fruit", "a hard-shelled fruit whose pulp is made into a cooling drink", ["bael", "wood apple (bael)"]),
 ("brinjal", "Solanum melongena", "vegetable", "a purple or green fruit vegetable of the nightshade family", ["eggplant", "aubergine", "brinjals", "baingan"]),
 ("tomato", "Solanum lycopersicum", "vegetable", "a round red juicy fruit used as a vegetable", ["tomatoes"]),
 ("okra", "Abelmoschus esculentus", "vegetable", "a ridged green pod that turns slippery when it is cooked", ["lady's finger", "ladies finger", "bhindi", "vendakkai"]),
 ("onion", "Allium cepa", "vegetable", "a layered bulb with a pungent smell", ["onions", "big onion"]),
 ("shallot", "Allium cepa var. aggregatum", "vegetable", "the small pink onion of south Indian cooking", ["small onion", "sambar onion", "shallots"]),
 ("garlic", "Allium sativum", "vegetable", "a bulb of pungent cloves inside a papery skin", []),
 ("potato", "Solanum tuberosum", "vegetable", "a starchy underground tuber", ["potatoes"]),
 ("carrot", "Daucus carota", "vegetable", "an orange tapering root eaten raw or cooked", ["carrots"]),
 ("radish", "Raphanus sativus", "vegetable", "a long white pungent root", ["white radish", "mooli", "daikon"]),
 ("beetroot", "Beta vulgaris", "vegetable", "a deep red sweet root", ["beet", "beets"]),
 ("cabbage", "Brassica oleracea", "vegetable", "a tight ball of pale green leaves", ["cabbages"]),
 ("cauliflower", "Brassica oleracea var. botrytis", "vegetable", "a white curd head wrapped in green leaves", []),
 ("pumpkin", "Cucurbita maxima", "vegetable", "a large orange-fleshed gourd", ["red pumpkin", "pumpkins"]),
 ("ash gourd", "Benincasa hispida", "vegetable", "a big pale gourd with a waxy bloom", ["winter melon", "white pumpkin", "poosanikai"]),
 ("bottle gourd", "Lagenaria siceraria", "vegetable", "a long pale green gourd with soft white flesh", ["calabash", "lauki", "sorakkai"]),
 ("ridge gourd", "Luffa acutangula", "vegetable", "a ridged dark green gourd", ["angled luffa", "peerkangai", "turai"]),
 ("snake gourd", "Trichosanthes cucumerina", "vegetable", "a very long thin curling gourd", ["pudalangai"]),
 ("bitter gourd", "Momordica charantia", "vegetable", "a warty green gourd with a strong bitter taste", ["bitter melon", "karela", "pavakkai"]),
 ("cucumber", "Cucumis sativus", "vegetable", "a cool watery green fruit eaten raw", ["cucumbers"]),
 ("chayote", "Sechium edule", "vegetable", "a pale pear-shaped gourd of the hills", ["chow chow", "chayote squash"]),
 ("cluster bean", "Cyamopsis tetragonoloba", "vegetable", "a slim slightly bitter bean pod", ["guar", "kothavarai"]),
 ("french bean", "Phaseolus vulgaris", "vegetable", "a tender green pod eaten whole", ["green bean", "beans", "french beans"]),
 ("field bean", "Lablab purpureus", "vegetable", "a flat pod eaten green or dried as a pulse", ["hyacinth bean", "avarai"]),
 ("green pea", "Pisum sativum", "vegetable", "round green seeds inside a pod", ["peas", "garden pea"]),
 ("sweet potato", "Ipomoea batatas", "vegetable", "a sweet orange or white starchy tuber", ["sweet potatoes"]),
 ("cassava", "Manihot esculenta", "vegetable", "a long starchy root that has to be cooked", ["tapioca", "maravalli"]),
 ("greater yam", "Dioscorea alata", "vegetable", "a large rough-skinned tuber", ["yam", "purple yam"]),
 ("elephant foot yam", "Amorphophallus paeoniifolius", "vegetable", "a big rough corm eaten as a vegetable", ["suran", "karunai"]),
 ("taro", "Colocasia esculenta", "vegetable", "a small hairy corm under large arrow-shaped leaves", ["colocasia", "arbi", "seppankizhangu"]),
 ("malabar spinach", "Basella alba", "vegetable", "a thick-leaved climbing spinach that thickens a curry", ["vine spinach", "pasalai keerai"]),
 ("amaranth", "Amaranthus tricolor", "vegetable", "a leafy green with red or green leaves", ["amaranth leaves", "thandu keerai"]),
 ("spinach", "Spinacia oleracea", "vegetable", "a soft dark leafy green", ["palak"]),
 ("coriander", "Coriandrum sativum", "vegetable", "a herb whose leaves and seeds both flavour food", ["cilantro", "coriander leaves", "kothamalli"]),
 ("mint", "Mentha spicata", "vegetable", "a cool-tasting herb used in chutneys", ["spearmint", "pudina"]),
 ("fenugreek", "Trigonella foenum-graecum", "vegetable", "a herb whose bitter leaves and seeds are both used in cooking", ["methi", "venthayam"]),
 ("chilli pepper", "Capsicum annuum", "vegetable", "a hot green or red pod used fresh and dried", ["chilli", "chili", "green chilli", "red chilli", "capsicum", "bell pepper"]),
 ("drumstick", "Moringa oleifera", "vegetable", "a long ribbed pod cooked in sambar", ["drumstick pod", "murungakkai", "moringa pod"]),
 ("banana flower", "Musa acuminata", "vegetable", "the purple flower head of the banana, cooked as a vegetable", ["banana blossom", "vazhaipoo"]),
 ("button mushroom", "Agaricus bisporus", "vegetable", "a soft white edible fungus", ["mushroom", "mushrooms"]),
 ("curry leaf", "Murraya koenigii", "vegetable", "an aromatic leaf tempered in oil at the start of a dish", ["curry leaves", "karuveppilai"]),
 ("black nightshade", "Solanum nigrum", "vegetable", "a small leafy green with tiny berries, cooked as a keerai", ["manathakkali", "sunberry"]),
 ("agathi", "Sesbania grandiflora", "vegetable", "a soft leaf and large white flower eaten as a green", ["hummingbird tree", "agathi keerai", "august tree"]),
 ("sessile joyweed", "Alternanthera sessilis", "vegetable", "a creeping green cooked as a leafy vegetable", ["ponnanganni", "dwarf copperleaf"]),
]

# ------------------------------------------------------------------ text helpers

TA = r"஀-௿"
TA_TOK = re.compile("[" + TA + "]+")
FIELD_LINE = re.compile(r"^\|\s*[\w_ ]{1,30}\s*=")

def strip_wikitext(text):
    """A few hundred dump articles still carry a raw {{Taxobox ...}} block; drop template blocks and
    stray '| field = value' lines so the lead sentence is the first thing in the text."""
    out, depth = [], 0
    for ln in text.split("\n"):
        s = ln.strip()
        if depth > 0:
            depth += s.count("{{") - s.count("}}")
            if depth < 0:
                depth = 0
            continue
        if s.startswith("{{"):
            depth = max(0, s.count("{{") - s.count("}}"))
            continue
        if FIELD_LINE.match(s):
            continue
        out.append(ln)
    return CK.normalise_dashes("\n".join(out)).strip()

SENT_END = re.compile(r"(?<![A-Z])\.(?:\s|$)")

def sentences(text, n=2):
    """The first n sentences of the lead, as single lines."""
    lead = text.strip().split("\n\n")[0].replace("\n", " ")
    lead = re.sub(r"\s+", " ", lead)
    out, start = [], 0
    for m in SENT_END.finditer(lead):
        piece = lead[start:m.start()].strip()
        if len(piece) >= 15:
            out.append(piece + ".")
            start = m.end()
        if len(out) >= n:
            break
    if not out:
        out = [lead[:300].strip()]
    return out

# a Latin binomial: the epithet has to look like Latin, otherwise "Douglas fir" and "Garden strawberry"
# read as scientific names.
EPITHET = re.compile(r"(?:us|um|a|is|i|ii|ae|e|ense|ensis|oides|ifera|iflora|ifolia|folia|ana|ata|atum|"
                     r"osa|osus|ina|inus|alis|aris|icus|ica|icum|ans|ens|ops|oma|ora|ula|ulus|escens)$")
GENUS_BAD = {"The", "This", "It", "In", "A", "An", "Of", "And", "But", "For", "From", "With", "Also",
             "There", "They", "English", "Tamil", "India", "Indian", "See", "New", "South", "North",
             "East", "West", "Sri", "Common", "Great", "Little", "Black", "White", "Red", "Green",
             "Blue", "Grey", "Gray", "Yellow", "Brown", "Asian", "Database", "Garden", "Marine",
             "Giant", "Wild", "Lesser", "Greater", "Northern", "Southern", "Eastern", "Western"}
BINOMIAL = re.compile(r"\b([A-Z][a-z]{2,})\s+([a-z][a-z\-]{2,})\b")
SCI_MARK = re.compile(r"(?:உயிரியல்|அறிவியல்|தாவரவியல்|தாவரப்|விலங்கியல்)\s*(?:பெயர்|வகைப்பாடு)?\s*[:\-]?\s*"
                      r"|தாவர\s*வகைப்பாட்டியல்\s*[:\-]?\s*")

def sci_of(lead):
    """Scientific name from the Tamil lead. A name that follows an explicit 'அறிவியல் பெயர்:' marker wins;
    otherwise the first binomial whose epithet has a Latin ending."""
    for m in SCI_MARK.finditer(lead):
        b = BINOMIAL.match(lead[m.end():m.end() + 80].lstrip())
        if b and b.group(1) not in GENUS_BAD:
            return b.group(1) + " " + b.group(2)
    for b in BINOMIAL.finditer(lead):
        g, s = b.group(1), b.group(2)
        if g in GENUS_BAD or not EPITHET.search(s):
            continue
        return g + " " + s
    return None

PAREN = re.compile(r"\(([^()]{2,160})\)")
EN_BAD = re.compile(r"^(?:ஆங்கிலம்|english|உயிரியல்|அறிவியல்|தாவரவியல்|இலத்தீன்)", re.I)

def en_of(lead, sci):
    """English common name from the brackets in the lead: 'சிட்டுக்குருவி (house sparrow, உயிரியல் பெயர்:
    Passer domesticus)' gives 'house sparrow'."""
    best = None
    for m in PAREN.finditer(lead[:600]):
        inner = m.group(1)
        for part in re.split(r"[,;]|\bஅல்லது\b|\bor\b", inner):
            p = part.strip(" .:-")
            p = SCI_MARK.sub("", p).strip(" .:-")
            if not p or TA_TOK.search(p) or EN_BAD.match(p):
                continue
            if not re.fullmatch(r"[A-Za-z][A-Za-z '\-]{2,44}", p):
                continue
            if sci and p.lower() == sci.lower():
                continue
            if BINOMIAL.fullmatch(p) and EPITHET.search(p.split()[-1]):
                continue
            if p.lower() in ("english", "tamil", "syn", "sp", "spp"):
                continue
            if best is None or len(p) < len(best):
                best = p
    return best

ALT_HEAD = re.compile(r"^([" + TA + r" ]{2,40}?)(?:\s*,\s*|\s*அல்லது\s*)([" + TA + r" ]{2,40}?)"
                      r"(?:\s*,\s*|\s*அல்லது\s*|\s*\(|\s*என)")
ALT_SECTION = re.compile(r"\n\s*(?:வேறு\s*பெயர்கள்|மற்ற\s*பெயர்கள்|பெயர்கள்|வேறு\s*பெயர்|பிற\s*பெயர்கள்)\s*\n+([^\n]{3,300})")

def alt_ta_of(title, body):
    """Alternative Tamil names from the lead ('வேம்பு அல்லது வேப்பை (...)') and from a 'வேறு பெயர்கள்'
    line if the article has one."""
    out = []
    lead = sentences(body, 1)[0]
    head = lead.split("(")[0]
    for part in re.split(r"\s*,\s*|\s*அல்லது\s*", head):
        p = part.strip()
        if 2 <= len(p) <= 40 and TA_TOK.search(p) and not re.search(r"[A-Za-z0-9]", p) and p != title:
            if p.endswith("என்பது") or "என்பது" in p:
                continue
            out.append(p)
    m = ALT_SECTION.search(body[:4000])
    if m:
        for part in re.split(r"\s*,\s*|\s*அல்லது\s*", m.group(1)):
            p = part.strip(" .")
            if 2 <= len(p) <= 40 and TA_TOK.search(p) and not re.search(r"[A-Za-z0-9]", p) and p != title:
                out.append(p)
    seen, uniq = set(), []
    for p in out:
        if p not in seen:
            seen.add(p); uniq.append(p)
    return uniq[:8]

# ------------------------------------------------------------------ romanisation (for match_terms)

VOWELS = {"அ": "a", "ஆ": "aa", "இ": "i", "ஈ": "ee", "உ": "u", "ஊ": "oo",
          "எ": "e", "ஏ": "ae", "ஐ": "ai", "ஒ": "o", "ஓ": "oa", "ஔ": "au"}
SIGNS = {"ா": "aa", "ி": "i", "ீ": "ee", "ு": "u", "ூ": "oo", "ெ": "e",
         "ே": "ae", "ை": "ai", "ொ": "o", "ோ": "oa", "ௌ": "au"}
CONS = {"க": "k", "ங": "ng", "ச": "s", "ஞ": "nj", "ட": "t", "ண": "n",
        "த": "th", "ந": "n", "ப": "p", "ம": "m", "ய": "y", "ர": "r",
        "ல": "l", "வ": "v", "ழ": "zh", "ள": "l", "ற": "r", "ன": "n",
        "ஜ": "j", "ஷ": "sh", "ஸ": "s", "ஹ": "h"}
PULLI = "்"

def romanise(s):
    out, i = [], 0
    while i < len(s):
        c = s[i]
        if c in CONS:
            nxt = s[i + 1] if i + 1 < len(s) else ""
            if nxt == PULLI:
                out.append(CONS[c]); i += 2; continue
            if nxt in SIGNS:
                out.append(CONS[c] + SIGNS[nxt]); i += 2; continue
            out.append(CONS[c] + "a"); i += 1; continue
        if c in VOWELS:
            out.append(VOWELS[c]); i += 1; continue
        if c == " ":
            out.append(" "); i += 1; continue
        i += 1
    return re.sub(r"\s+", " ", "".join(out)).strip()

def plural(w):
    """A plural for a match term. A term that is already plural ("tomatoes", "grapes") is left alone."""
    if not w or w.endswith("s"):
        return None
    if w.endswith(("x", "z", "ch", "sh")):
        return w + "es"
    if len(w) > 2 and w.endswith("y") and w[-2] not in "aeiou":
        return w[:-1] + "ies"
    return w + "s"

def article(word):
    return "an" if word[:1].lower() in "aeiou" else "a"

# ------------------------------------------------------------------ what counts as a nature article

KIND_RULES = [
 ("bird",      r"பறவை(?:யாகும்|கள்|\s*சிற்றின|\s*இன|யாக|யின|க்\s*குடும்ப|\s*வகை)|ஒரு\s*பறவை|பறவையினம்"),
 ("insect",    r"பூச்சி(?:யாகும்|கள்|\s*இன|யின|\s*சிற்றின)|ஒரு\s*பூச்சி|வண்ணத்துப்பூச்சி|வண்டு\s*இன|"
               r"எறும்பு|தும்பி(?:யின|கள்)|அந்துப்பூச்சி|சிலந்தி(?!ப்பிடி|பிடி)"),
 ("animal",    r"பாலூட்டி|ஊர்வன|நீர்நில\s*வாழ்|விலங்கினமாகும்|விலங்காகும்|விலங்கு\s*இன|பாம்பாகும்|"
               r"பாம்பு\s*இன|தவளை|ஆமையாகும்|முதலை|பல்லி|கொறி(?:ணி|ய)|மீன்\s*சிற்றின"),
 ("tree",      r"மரமாகும்|மரம்\s*ஆகும்|ஒரு\s*மரம்|மரவகை|மர\s*இன|மரங்களில்\s*ஒன்று"),
 ("flower",    r"மலர்ச்செடி|மலரினமாகும்|பூவாகும்"),
 ("plant",     r"தாவரமாகும்|தாவரம்\s*ஆகும்|தாவர\s*இன|தாவர\s*வகை|செடியாகும்|செடியினமாகும்|செடி\s*இன|"
               r"கொடியாகும்|மூலிகை|புல்\s*இன|பூக்கும்\s*தாவர"),
 ("fruit",     r"பழமாகும்|பழம்\s*ஆகும்|கனியாகும்|பழ\s*வகை|பழவகை"),
 ("vegetable", r"காய்கறிச்\s*செடி|காய்கறி\s*வகை|கீரையாகும்|கீரை\s*வகை|கீரையினம்"),
]
KIND_RULES = [(k, re.compile(p)) for k, p in KIND_RULES]
PLANT_KINDS = ("tree", "flower", "plant", "fruit", "vegetable")
PLANT_MARK = re.compile(r"தாவரவியல்|தாவர\s*வகைப்பாட|தாவரப்\s*பெயர்")
SPECIES_MARK = re.compile(r"சிற்றின|இனமாகும்|குடும்பத்த|பேரின|வகைப்பாட்ட|உயிரியல்\s*பெயர|அறிவியல்\s*பெயர|"
                          r"தாவரவியல்\s*பெயர|தாவர\s*வகைப்பாட")
BAD_TITLE = re.compile(r"திரைப்படம்|பாடல்|நாவல்(?!\s*(?:\(மரம்\)|மரம்))|கோயில்|கோவில்|ஊராட்சி|கிராமம்|மாவட்டம|சட்டமன்ற|தொகுதி|"
                       r"பட்டியல்|நிறுவனம்|கழகம்|விளையாட்டு|பல்கலைக்கழக|இதழ்|நகரம்|\(நிறம்\)|தேசிய|"
                       r"வரலாறு|பண்பாடு|மருத்துவம்|உணவு|சந்தை|தோட்டக்கலை|காப்பகம்|சரணாலயம்|பூங்கா|"
                       r"ஆய்வ|இலக்கிய|போர்|கோட்பாடு|தேற்றம்")
BAD_LEAD = re.compile(r"பிறந்தார்|இறந்தார்|நடிகர்|எழுத்தாளர்|அரசியல்வாதி|திரைப்படம்|ஊராட்சி|ஆய்விதழ்|"
                      r"கிராமம்\s*ஆகும்|ஒரு\s*நகரம்|மாவட்டத்தில்\s*உள்ள|நாவல்(?!\s*மரம்)|சிறுகதை|காப்பகம்|சரணாலயம்|"
                      r"பழமை|பழைய|பழங்கால|பழம்பெரும்|வெளியீட|சங்கத்தின|விழா\s*மலர|முனிவர்|கடவுள|"
                      r"கோயில|கோவில|உணவு\s*வகை|பதார்த்த|விருது|கட்சி|மொழி(?:யாகும்|கள)|நோயாகும்|"
                      r"ஆவார்|ஆவர்|தொகுதி|அரசர|மன்னர|தேற்றம")

def probe_of(body):
    s1 = sentences(body, 1)[0]
    return s1 if len(s1) > 60 else re.sub(r"\s+", " ", body[:320])

def kind_of(probe):
    rules = KIND_RULES
    if PLANT_MARK.search(probe):
        rules = [(k, r) for k, r in KIND_RULES if k in PLANT_KINDS]
    for k, r in rules:
        if r.search(probe):
            return k
    return None

# ------------------------------------------------------------------ the three coverage lists as one seed table

def seeds():
    out = []
    for en, sci, gloss, syn in BIRDS:
        out.append({"list": "birds_100", "en": en, "sci": sci, "kind": "bird", "gloss": gloss, "syn": syn})
    for en, sci, kind, gloss, syn in PLANTS:
        out.append({"list": "plants_trees_100", "en": en, "sci": sci, "kind": kind, "gloss": gloss, "syn": syn})
    for en, sci, kind, gloss, syn in FOODS:
        out.append({"list": "fruits_vegetables_78", "en": en, "sci": sci, "kind": kind, "gloss": gloss, "syn": syn})
    return out

SEEDS = seeds()
FAMILY = {"bird": "b", "animal": "z", "insect": "z",
          "tree": "p", "plant": "p", "flower": "p", "fruit": "p", "vegetable": "p"}

# Seed lookup is by set membership, not by one huge alternation: an alternation of 278 literals over
# 186,741 leads costs minutes, a set lookup over the binomials the lead actually contains costs seconds.
SCI_TO_SEEDS = {}
for _i, _s in enumerate(SEEDS):
    _s["sci_key"] = " ".join(_s["sci"].lower().split()[:2])          # "var." and "subsp." are not matched on
    SCI_TO_SEEDS.setdefault(_s["sci_key"], []).append(_i)
SCI_SET = set(SCI_TO_SEEDS)

EN_TERMS = {}
for _i, _s in enumerate(SEEDS):
    for _t in [_s["en"]] + _s["syn"]:
        if len(_t) >= 6:            # short names (rose, mint, myna, mango) match far too much to be useful
            EN_TERMS.setdefault(_t.lower(), []).append(_i)
EN_FIRST = {}
for _t in EN_TERMS:
    EN_FIRST.setdefault(_t.split()[0], []).append(_t)
WORD = re.compile(r"[a-z][a-z'\-]+")

# ------------------------------------------------------------------ one pass over the offline dump

def scan_dump(path=TAWIKI):
    """One pass. Keeps an article when it declares itself a bird, animal, insect, tree, plant, flower,
    fruit or vegetable AND carries a scientific name or a species declaration (auto), or when its lead
    names one of the seed species (candidate for a coverage list)."""
    keep, scanned = {}, 0
    with open(path, encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            scanned += 1
            title = d["title"]
            body = strip_wikitext(d["text"])
            if len(body.split()) < 40:
                continue
            lead = body[:1500]
            sci_hits = []
            for m in BINOMIAL.finditer(lead):
                b = (m.group(1) + " " + m.group(2)).lower()
                if b in SCI_SET:
                    sci_hits.append((b, m.start()))
            head = lead[:700].lower()
            words = set(WORD.findall(head))
            en_hits = []
            for w in words & EN_FIRST.keys():
                for t in EN_FIRST[w]:
                    if t in head:
                        en_hits.append(t)
            probe = probe_of(body)
            bad = bool(BAD_TITLE.search(title)) or bool(BAD_LEAD.search(probe))
            kind = None if bad else kind_of(probe)
            sci = sci_of(lead)
            auto = bool(kind) and (bool(sci) or bool(SPECIES_MARK.search(probe)))
            if not auto and not (sci_hits and not bad) and not (en_hits and not bad):
                continue
            keep[title] = {"title": title, "body": body, "kind": kind, "sci": sci, "auto": auto,
                           "sci_hits": sci_hits, "en_hits": en_hits, "words": len(body.split())}
    return keep, scanned

def score_candidate(seed, rec):
    s = 0.0
    low = seed["sci_key"]
    pos = next((p for h, p in rec["sci_hits"] if h == low), None)
    if pos is not None:
        s += 100
        if pos < 400:
            s += 20
    if rec["sci"] and " ".join(rec["sci"].lower().split()[:2]) == low:
        s += 60
    for t in [seed["en"]] + seed["syn"]:
        if t.lower() in rec["en_hits"]:
            s += 30
            break
    if rec["kind"] == seed["kind"]:
        s += 40
    elif rec["kind"] and FAMILY.get(rec["kind"]) == FAMILY.get(seed["kind"]):
        s += 15
    elif rec["kind"]:
        s -= 25
    if rec["auto"]:
        s += 10
    s -= 0.15 * len(rec["title"])
    return s

def resolve_seeds(keep, only=None):
    """Best article per seed, offline. Returns {seed index: title} and the list of unresolved seeds."""
    only = set(range(len(SEEDS))) if only is None else set(only)
    by_sci, by_en = {}, {}
    for title, rec in keep.items():
        for h, _p in rec["sci_hits"]:
            for i in SCI_TO_SEEDS.get(h, []):
                by_sci.setdefault(i, []).append(rec)
        for h in rec["en_hits"]:
            for i in EN_TERMS.get(h, []):
                by_en.setdefault(i, []).append(rec)
    res, missing = {}, []
    for i, seed in enumerate(SEEDS):
        if i not in only:
            continue
        cands = by_sci.get(i) or by_en.get(i) or []
        if not cands:
            missing.append(i); continue
        best = max(cands, key=lambda r: score_candidate(seed, r))
        if score_candidate(seed, best) < 20:
            missing.append(i); continue
        res[i] = best["title"]
    return res, missing

# ------------------------------------------------------------------ live ta.wikipedia, gap fill only

def cache_json(name, fn):
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, name)
    if os.path.exists(path):
        return json.load(open(path, encoding="utf-8"))
    d = fn()
    json.dump(d, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return d

def api_post(params, host=HOST):
    """Same rate limit and User-Agent as CK.api, but POST: 50 Tamil titles in a query string encode to
    more than the API will accept on a GET (HTTP 414)."""
    gap = CK.MIN_GAP - (time.time() - CK._last[0])
    if gap > 0:
        time.sleep(gap)
    p = dict(params); p["format"] = "json"
    req = urllib.request.Request("https://%s/w/api.php" % host,
                                 data=urllib.parse.urlencode(p).encode("utf-8"),
                                 headers={"User-Agent": CK.UA,
                                          "Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=90) as r:
        body = r.read().decode("utf-8", "replace")
    CK._last[0] = time.time()
    return json.loads(body)

def api_search(term, limit=5):
    r = CK.api(HOST, {"action": "query", "list": "search", "srsearch": term,
                      "srnamespace": "0", "srlimit": str(limit)})
    return [h["title"] for h in r.get("query", {}).get("search", [])]

def langlinks_batch(titles, host="en.wikipedia.org"):
    """{English title: Tamil title} for up to 50 titles a request. Redirects are followed, so the
    scientific name ('Cocos nucifera') reaches the article it redirects to ('Coconut') and returns its
    Tamil interlanguage link ('தென்னை'). Only the title crosses over; no English text does."""
    out = {}
    titles = list(titles)
    for i in range(0, len(titles), 50):
        batch = titles[i:i + 50]
        r = api_post({"action": "query", "titles": "|".join(batch), "prop": "langlinks",
                      "lllang": "ta", "lllimit": "max", "redirects": "1"}, host=host)
        q = r.get("query", {})
        chain = {}
        for m in q.get("normalized", []) + q.get("redirects", []):
            chain[m["from"]] = m["to"]
        final = {}
        for pg in q.get("pages", {}).values():
            lls = pg.get("langlinks", [])
            if lls:
                final[pg["title"]] = lls[0].get("*") or lls[0].get("title")
        for t in batch:
            cur, seen = t, set()
            while cur in chain and cur not in seen:
                seen.add(cur); cur = chain[cur]
            if cur in final:
                out[t] = final[cur]
    return out

def resolve_by_langlink(no_fetch=False):
    """Tamil article title for every coverage-list species, from the English Wikipedia interlanguage link
    on its scientific name (and on its English common name where the scientific name has no article).
    Six requests for 278 species. The article text is then read from the offline dump."""
    def go():
        m = langlinks_batch(sorted({s["sci"] for s in SEEDS}))
        left = sorted({s["en"] for s in SEEDS if s["sci"] not in m})
        m.update({k: v for k, v in langlinks_batch(left).items()})
        return m
    path = os.path.join(CACHE, "langlinks.json")
    if no_fetch:
        m = json.load(open(path, encoding="utf-8")) if os.path.exists(path) else {}
    else:
        m = cache_json("langlinks.json", go)
    per_seed = {}
    for i, s in enumerate(SEEDS):
        t = m.get(s["sci"]) or m.get(s["en"])
        if t and not BAD_TITLE.search(t):
            per_seed[i] = t
    bodies = _bodies_for(set(per_seed.values()), no_fetch)
    out = {}
    for i, t in per_seed.items():
        b = bodies.get(t)
        if b and len(b.split()) >= MIN_GAP_WORDS:
            out[i] = (t, b)
    return out

def langlink_ta(title, host="en.wikipedia.org"):
    """Which Tamil article is the same subject as this English one. en.wikipedia is used here only as a
    name index: no English text enters the pack."""
    r = api_post({"action": "query", "titles": title, "prop": "langlinks", "lllang": "ta",
                  "lllimit": "max", "redirects": "1"}, host=host)
    for pg in r.get("query", {}).get("pages", {}).values():
        for ll in pg.get("langlinks", []):
            return ll.get("*") or ll.get("title")
    return None

def api_extracts(titles):
    """Plain text of pages that are not in the offline dump (new or renamed since 2026-08-01)."""
    out = {}
    for i in range(0, len(titles), 10):
        batch = titles[i:i + 10]
        r = api_post({"action": "query", "prop": "extracts", "explaintext": "1",
                      "exsectionformat": "plain", "titles": "|".join(batch), "redirects": "1"})
        for pg in r.get("query", {}).get("pages", {}).values():
            if "extract" in pg and pg["extract"].strip():
                out[pg["title"]] = pg["extract"]
    return out

def api_redirects(titles):
    """Alternative Tamil names: every redirect that points at the entity's article, 50 titles a request."""
    out = {}
    for i in range(0, len(titles), 50):
        batch = titles[i:i + 50]
        params = {"action": "query", "prop": "redirects", "rdlimit": "max", "titles": "|".join(batch)}
        while True:
            r = api_post(params)
            for pg in r.get("query", {}).get("pages", {}).values():
                for rd in pg.get("redirects", []):
                    out.setdefault(pg["title"], []).append(rd["title"])
            if "continue" in r:
                params = dict(params); params.update(r["continue"])
            else:
                break
    return out

def cached_redirects(titles, no_fetch=False):
    """Incremental cache: a title already asked about is never asked again, and a title with no redirects
    is remembered as such rather than refetched."""
    path = os.path.join(CACHE, "redirects.json")
    d = json.load(open(path, encoding="utf-8")) if os.path.exists(path) else {"seen": [], "map": {}}
    seen = set(d["seen"])
    todo = [t for t in titles if t not in seen]
    if todo and not no_fetch:
        d["map"].update(api_redirects(todo))
        d["seen"] = sorted(seen | set(todo))
        os.makedirs(CACHE, exist_ok=True)
        json.dump(d, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return d["map"]

def fetch_dump_titles(wanted, path=TAWIKI):
    """Second pass over the offline dump for a named set of titles (cheaper than refetching them)."""
    got = {}
    if not wanted:
        return got
    with open(path, encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            if d["title"] in wanted:
                got[d["title"]] = strip_wikitext(d["text"])
                if len(got) == len(wanted):
                    break
    return got

ORGANISM = re.compile(r"தாவர|மரம்|மரத்|செடி|கொடி|கீரை|காய்|பழ|கிழங்க|மலர்|பூக்க|பறவை|விலங்க|பூச்சி|"
                      r"மீன்|இலை|வேர்|விதை|பயிர்|கொக்கு|குருவி|நாரை|கழுகு|ஆந்தை|பாம்பு|இனமாகும்")

def plausible(seed, title, body, top_of_sci_search=False):
    """A gap-fill candidate is taken when the article names the species, or when it is the first hit of a
    quoted scientific-name search and reads like an article about a living thing. The second rule matters
    because the dump strips the taxobox, so the binomial the search matched is often not in the text left
    behind."""
    lead = body[:1500]
    low = lead.lower()
    if seed["sci_key"] in low:
        return True
    for t in [seed["en"]] + seed["syn"]:
        if len(t) >= 5 and t.lower() in low[:800]:
            return True
    k = kind_of(probe_of(body))
    if k and FAMILY.get(k) == FAMILY.get(seed["kind"]):
        return True
    return top_of_sci_search and bool(ORGANISM.search(body[:700]))

MIN_GAP_WORDS = 20      # a correct short article (புதினா is 20 words) is still the right answer

def _bodies_for(titles, no_fetch):
    """Article text for a set of Tamil titles: from the offline dump where possible, from the API only for
    the titles the dump does not have. The extracts cache is incremental, so changing the seed lists never
    silently reuses an older, smaller set."""
    titles = set(titles)
    bodies = fetch_dump_titles(titles)
    path = os.path.join(CACHE, "gapfill_extracts.json")
    extra = json.load(open(path, encoding="utf-8")) if os.path.exists(path) else {}
    todo = [t for t in sorted(titles - set(bodies)) if t not in extra]
    if todo and not no_fetch:
        extra.update(api_extracts(todo))
        os.makedirs(CACHE, exist_ok=True)
        json.dump(extra, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    for t in titles:
        if t not in bodies and t in extra:
            bodies[t] = strip_wikitext(extra[t])
    return bodies

def gap_fill(missing, no_fetch=False):
    """Two phases for a coverage-list species the dump did not resolve.

    1. ta.wikipedia list=search on the quoted scientific name: which Tamil article carries it.
    2. whatever is still missing: ask en.wikipedia which Tamil article is the same subject (langlinks).
       en.wikipedia is a name index here, nothing more; no English text goes into the pack.
    The article itself is then read from the offline dump where it is there, from prop=extracts if not."""
    def search_all():
        out = {}
        for i in missing:
            s = SEEDS[i]
            res = api_search('"%s"' % s["sci"])
            how = "sci_quoted"
            if not res:
                res, how = api_search(s["sci"]), "sci"
            if not res:
                res, how = api_search(s["en"]), "en"
            out[str(i)] = {"how": how, "titles": res}
        return out
    if no_fetch:
        hits = json.load(open(os.path.join(CACHE, "gapfill_search.json"), encoding="utf-8"))
    else:
        hits = cache_json("gapfill_search.json", search_all)

    wanted = set()
    for i in missing:
        wanted.update(t for t in hits.get(str(i), {}).get("titles", [])[:5] if not BAD_TITLE.search(t))
    bodies = _bodies_for(wanted, no_fetch)

    filled, still, how = {}, [], {}
    for i in missing:
        h = hits.get(str(i), {})
        chosen = None
        for rank, t in enumerate(h.get("titles", [])[:5]):
            b = bodies.get(t)
            if not b or len(b.split()) < MIN_GAP_WORDS or BAD_TITLE.search(t):
                continue
            if plausible(SEEDS[i], t, b, top_of_sci_search=(rank == 0 and h.get("how") != "en")):
                chosen = (t, b); break
        if chosen:
            filled[i] = chosen
            how[i] = "ta_search"
        else:
            still.append(i)

    if still:
        def langlinks():
            return {str(i): langlink_ta(SEEDS[i]["sci"]) or langlink_ta(SEEDS[i]["en"]) for i in still}
        if no_fetch:
            path = os.path.join(CACHE, "gapfill_langlinks.json")
            ll = json.load(open(path, encoding="utf-8")) if os.path.exists(path) else {}
        else:
            ll = cache_json("gapfill_langlinks.json", langlinks)
        want2 = {t for t in (ll.get(str(i)) for i in still) if t and not BAD_TITLE.search(t)}
        bodies2 = _bodies_for(want2, no_fetch)
        left = []
        for i in still:
            t = ll.get(str(i))
            b = bodies2.get(t) if t else None
            if b and len(b.split()) >= MIN_GAP_WORDS:
                filled[i] = (t, b)
                how[i] = "en_langlink"
            else:
                left.append(i)
        still = left
    return filled, still, how

# ------------------------------------------------------------------ entities

KIND_TA = {"bird": "பறவை", "animal": "விலங்கு", "insect": "பூச்சி", "flower": "மலர்",
           "tree": "மரம்", "plant": "தாவரம்", "fruit": "பழம்", "vegetable": "காய்கறி",
           "other": "உயிரினம்"}
KIND_EN = {"bird": "bird", "animal": "animal", "insect": "insect", "flower": "flowering plant",
           "tree": "tree", "plant": "plant", "fruit": "fruit", "vegetable": "vegetable",
           "other": "living thing"}
TITLE_QUAL = re.compile(r"\s*\([^)]*\)\s*$")

def clean_title(t):
    """'புளி (மரம்)' is the article title; 'புளி' is the name a person would say. A trailing rank word
    ('பீர்க்கு பேரினம்') goes the same way."""
    t = TITLE_QUAL.sub("", t).strip() or t
    return re.sub(r"\s+(?:பேரினம்|பேரினங்கள்|இனம்|குடும்பம்)$", "", t).strip() or t

def describe_ta(body, kind, sci):
    lines = sentences(body, 2)
    l1 = lines[0][:400]
    if len(lines) > 1 and len(lines[1]) > 20:
        l2 = lines[1][:400]
    else:
        l2 = "இது ஒரு %s." % KIND_TA.get(kind, KIND_TA["other"])
        if sci:
            l2 += " அறிவியல் பெயர்: %s." % sci
    return l1 + "\n" + l2

def describe_en(seed, name_en, name_ta, roman, kind, sci, alts):
    tail = " (%s)" % sci if sci else ""
    kw = KIND_EN.get(kind, KIND_EN["other"])
    if seed:
        l1 = "%s%s is %s." % (seed["en"][0].upper() + seed["en"][1:], tail, seed["gloss"])
    elif name_en:
        l1 = "%s%s is %s %s." % (name_en[0].upper() + name_en[1:], tail, article(kw), kw)
    elif sci:
        l1 = "%s is %s %s." % (sci, article(kw), kw)
    else:
        head = roman.title() if roman else name_ta
        l1 = "%s is %s %s." % (head, article(kw), kw)
    l2 = "In Tamil it is called %s%s." % (name_ta, " (%s)" % roman if roman else "")
    if alts:
        l2 = l2[:-1] + ", also written %s." % ", ".join(alts[:2])
    return l1 + "\n" + l2

def match_terms(seed, name_en, name_ta, alts, sci, kind):
    out = []
    def add(t):
        t = re.sub(r"\s+", " ", (t or "")).strip().lower()
        if t and t not in out:
            out.append(t)
    en_terms = []
    if seed:
        en_terms = [seed["en"]] + list(seed["syn"])
        head = seed["en"].split()[-1]
        if len(head) > 3:
            en_terms.append(head)
    if name_en:
        en_terms.append(name_en)
        h = name_en.split()[-1]
        if len(h) > 3 and seed:
            en_terms.append(h)
    for t in en_terms:
        add(t)
        p = plural(t)
        if p:
            add(p)
        if "-" in t:
            add(t.replace("-", " "))
            add(t.replace("-", ""))
    for t in [name_ta] + list(alts):
        add(t)
        r = romanise(t)
        if len(r) >= 3:
            add(r)
            add(r.replace(" ", ""))
    if sci:
        add(sci)
    return [t for t in out if t]

# ------------------------------------------------------------------ build

SEED_CHUNKS, AUTO_CHUNKS = 3, 1

def build_entities(keep, resolved, filled, api_titles=()):
    """One entity per Tamil Wikipedia article. A seed that resolves onto the same article as another seed
    (mango tree and mango, coconut palm and coconut) merges into one entity carrying both list slots."""
    ent = OrderedDict()
    def slot(title, body, source):
        e = ent.get(title)
        if e is None:
            e = ent[title] = {"title": title, "body": body, "seeds": [], "source": source}
        return e
    for i, title in sorted(resolved.items()):
        slot(title, keep[title]["body"], "dump")["seeds"].append(i)
    api_titles = set(api_titles)
    for i, (title, body) in sorted(filled.items()):
        slot(title, body, "api" if title in api_titles else "dump")["seeds"].append(i)
    for title, rec in keep.items():
        if rec["auto"]:
            slot(title, rec["body"], "dump")
    return ent

def finish_entity(e, redirects):
    title, body = e["title"], e["body"]
    lead = body[:1500]
    seeds_here = [SEEDS[i] for i in e["seeds"]]
    seed = seeds_here[0] if seeds_here else None
    kind = seed["kind"] if seed else (kind_of(probe_of(body)) or "other")
    sci = seed["sci"] if seed else sci_of(lead)
    name_ta = clean_title(title)
    alts = alt_ta_of(title, body)
    if title != name_ta:
        alts.insert(0, title)
    for rd in redirects.get(title, []):
        if TA_TOK.search(rd) and not re.search(r"[A-Za-z0-9]", rd) and rd not in alts and rd != name_ta:
            alts.append(rd)
    latin_redirects = [rd for rd in redirects.get(title, []) if not TA_TOK.search(rd)]
    alts = alts[:10]
    name_en = seed["en"] if seed else en_of(lead, sci)
    terms = match_terms(seed, name_en, name_ta, alts, sci, kind)
    for s2 in seeds_here[1:]:
        for t in [s2["en"]] + s2["syn"]:
            if t.lower() not in terms:
                terms.append(t.lower())
    for rd in latin_redirects[:6]:
        if rd.lower() not in terms:
            terms.append(rd.lower())
    return {
        "kind": kind,
        "name_ta": name_ta,
        "names_ta_alt": alts,
        "name_en": name_en,
        "name_sci": sci,
        "description_ta": describe_ta(body, kind, sci),
        "description_en": describe_en(seed, name_en, name_ta, romanise(name_ta), kind, sci, alts),
        "source_title": title,
        "source_url": CK.wiki_url(HOST, title),
        "license": LICENSE,
        "match_terms": terms,
        "lists": sorted({SEEDS[i]["list"] for i in e["seeds"]}),
        "description_en_written": bool(seed),
        "text_from": e["source"],
    }

def make_chunks(ent_rows, counter):
    out = []
    for e in ent_rows:
        cap = SEED_CHUNKS if e["_seed"] else AUTO_CHUNKS
        blocks = CK.blocks_from_plain(e["_body"])
        made = 0
        for sections, cbody in CK.chunk_blocks(blocks):
            if made >= cap:
                break
            counter[0] += 1
            section = " | ".join(sections)
            row = {"id": "nature-%05d" % counter[0], "entity_id": e["id"], "title": e["source_title"],
                   "text": CK.chunk_text(e["source_title"], section, cbody),
                   "lang": CK.lang_of(cbody), "source": "ta.wikipedia", "url": e["source_url"],
                   "license": LICENSE, "machine_translated": False, "kind": e["kind"]}
            if section:
                row["section"] = section
            out.append(row)
            made += 1
        if made == 0:                      # never leave an entity without a chunk
            counter[0] += 1
            out.append({"id": "nature-%05d" % counter[0], "entity_id": e["id"], "title": e["source_title"],
                        "text": CK.chunk_text(e["source_title"], "", " ".join(e["_body"].split()[:400])),
                        "lang": CK.lang_of(e["_body"]), "source": "ta.wikipedia", "url": e["source_url"],
                        "license": LICENSE, "machine_translated": False, "kind": e["kind"]})
    return out

def severe(hits):
    return [h for h in hits if (h.get("severity") in FS.SEVERE or h.get("severity") == "profanity")]

def coverage_table(entities, list_name, reasons):
    rows = []
    for i, s in enumerate(SEEDS):
        if s["list"] != list_name:
            continue
        e = next((x for x in entities if i in x["_seeds"]), None)
        rows.append(OrderedDict([
            ("english", s["en"]),
            ("scientific", s["sci"]),
            ("kind", s["kind"]),
            ("entity", bool(e)),
            ("name_ta", (e or {}).get("name_ta")),
            ("name_sci", (e or {}).get("name_sci")),
            ("description", bool(e and e.get("description_ta"))),
            ("source_title", (e or {}).get("source_title")),
            ("entity_id", (e or {}).get("id")),
            ("gap", None if e else reasons.get(i, "no Tamil article found")),
        ]))
    return rows

def summarise(rows):
    return OrderedDict([
        ("items", len(rows)),
        ("entity", sum(1 for r in rows if r["entity"])),
        ("name_ta", sum(1 for r in rows if r["name_ta"])),
        ("name_sci", sum(1 for r in rows if r["name_sci"])),
        ("description", sum(1 for r in rows if r["description"])),
        ("missing", [r["english"] for r in rows if not r["entity"]]),
        ("missing_reason", {r["english"]: r["gap"] for r in rows if not r["entity"]}),
    ])

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-fetch", action="store_true", help="build from data/raw/packs/nature only")
    ap.add_argument("--titles", action="store_true", help="print the selected Tamil Wikipedia titles and stop")
    a = ap.parse_args()

    keep, scanned = scan_dump()
    if a.titles:
        for t, r in sorted(keep.items()):
            if r["auto"]:
                print(r["kind"], "\t", r["sci"] or "-", "\t", t)
        print("scanned %d, kept %d, auto %d" % (scanned, len(keep), sum(1 for r in keep.values() if r["auto"])))
        return
    os.makedirs(PACK, exist_ok=True)
    os.makedirs(CACHE, exist_ok=True)

    # --- licence, read from the wiki itself on the build date
    if a.no_fetch:
        rights = json.load(open(os.path.join(CACHE, "rightsinfo.json"), encoding="utf-8"))
    else:
        rights = cache_json("rightsinfo.json",
                            lambda: {h: CK.rightsinfo(h) for h in (HOST, "en.wikipedia.org")})
    print("licence:", json.dumps(rights, ensure_ascii=False))

    ll_res = resolve_by_langlink(no_fetch=a.no_fetch)
    print("seeds: %d of %d named by the English Wikipedia interlanguage link" % (len(ll_res), len(SEEDS)))
    resolved, missing = resolve_seeds(keep, only=[i for i in range(len(SEEDS)) if i not in ll_res])
    print("seeds: %d more resolved offline from the dump" % len(resolved))
    filled, still_missing, how = gap_fill(missing, no_fetch=a.no_fetch)
    for i in ll_res:
        how[i] = "en_langlink"
    filled.update(ll_res)
    print("gap fill: %d seeds have text (%d by ta search, %d by en langlink), "
          "%d still missing" % (len(filled),
                                sum(1 for v in how.values() if v == "ta_search"),
                                sum(1 for v in how.values() if v == "en_langlink"), len(still_missing)))

    ex_path = os.path.join(CACHE, "gapfill_extracts.json")
    api_titles = json.load(open(ex_path, encoding="utf-8")).keys() if os.path.exists(ex_path) else []
    ent = build_entities(keep, resolved, filled, api_titles=api_titles)
    titles = sorted(ent)
    redirects = cached_redirects(titles, no_fetch=a.no_fetch)
    print("redirects: %d articles carry at least one" % len(redirects))

    rows = []
    for title in titles:
        e = ent[title]
        r = finish_entity(e, redirects)
        r["_body"], r["_seed"], r["_seeds"] = e["body"], bool(e["seeds"]), list(e["seeds"])
        rows.append(r)
    rows.sort(key=lambda r: (0 if r["_seed"] else 1, r["kind"], r["source_title"]))

    # --- family safe over every description, before ids are handed out
    dropped_entities, kept_rows, ent_hits = [], [], Counter()
    for r in rows:
        hits = FS.check(r["description_ta"]) + FS.check(r["description_en"]) + FS.check(r["name_ta"])
        for h in hits:
            ent_hits[h.get("severity") or "profanity"] += 1
        if severe(hits):
            dropped_entities.append({"title": r["source_title"], "kind": r["kind"], "seeds": r["_seeds"],
                                     "severities": sorted({h.get("severity") or "profanity" for h in hits})})
        else:
            kept_rows.append(r)
    for i, r in enumerate(kept_rows, 1):
        r["id"] = "nature-e%05d" % i

    counter = [0]
    chunks = make_chunks(kept_rows, counter)

    by_sev, dropped_chunks, kept_chunks, examples = Counter(), 0, [], []
    for c in chunks:
        hits = FS.check(c["text"])
        for h in hits:
            by_sev[h.get("severity") or "profanity"] += 1
        if severe(hits):
            dropped_chunks += 1
            if len(examples) < 20:
                examples.append({"id": c["id"], "title": c["title"],
                                 "severities": sorted({h.get("severity") or "profanity" for h in hits})})
        else:
            kept_chunks.append(c)
    have = {c["entity_id"] for c in kept_chunks}
    lost = [r for r in kept_rows if r["id"] not in have]
    kept_rows = [r for r in kept_rows if r["id"] in have]
    for r in lost:
        dropped_entities.append({"title": r["source_title"], "kind": r["kind"], "seeds": r["_seeds"],
                                 "severities": ["chunk dropped, entity left without text"]})
    for i, c in enumerate(kept_chunks, 1):
        c["id"] = "nature-%05d" % i
    print("family safe: %d entities scanned, %d dropped; %d chunks scanned, %d dropped"
          % (len(rows), len(dropped_entities), len(chunks), dropped_chunks))

    reasons = {}
    for r in dropped_entities:
        for i in r.get("seeds", []):
            reasons[i] = "article found (%s) but dropped by the family-safe lexicon" % r["title"]
    cov = OrderedDict()
    for name in ("birds_100", "plants_trees_100", "fruits_vegetables_78"):
        table = coverage_table(kept_rows, name, reasons)
        cov[name] = OrderedDict([("summary", summarise(table)), ("items", table)])

    # --- write entities.jsonl
    with open(os.path.join(PACK, "entities.jsonl"), "w", encoding="utf-8") as f:
        for r in kept_rows:
            out = OrderedDict([(k, r[k]) for k in
                               ("id", "kind", "name_ta", "names_ta_alt", "name_en", "name_sci",
                                "description_ta", "description_en", "source_title", "source_url",
                                "license", "match_terms", "lists", "description_en_written", "text_from")])
            out["chunk_ids"] = [c["id"] for c in kept_chunks if c["entity_id"] == r["id"]]
            f.write(json.dumps(out, ensure_ascii=False) + "\n")

    with open(os.path.join(PACK, "chunks.jsonl"), "w", encoding="utf-8") as f:
        for c in kept_chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")

    by_kind = Counter(r["kind"] for r in kept_rows)
    words = [len(c["text"].split()) for c in kept_chunks]
    terms = sum(len(r["match_terms"]) for r in kept_rows)

    sources = [
        OrderedDict([
            ("name", "Tamil Wikipedia, dump tawiki-20260801 (offline family-safe copy)"),
            ("url", "https://ta.wikipedia.org"),
            ("license", LICENSE),
            ("license_verified_on", VERSION),
            ("how_obtained", "read OFFLINE from data/index/tawiki_20260801_fs/articles.jsonl; an article is "
                             "kept when its lead declares it a bird, animal, insect, tree, plant, flower, "
                             "fruit or vegetable and carries a scientific name or a species declaration, or "
                             "when its lead names one of the 278 coverage-list species"),
            ("articles_scanned", scanned),
            ("articles_kept", sum(1 for r in kept_rows if r["text_from"] == "dump")),
        ]),
        OrderedDict([
            ("name", "Tamil Wikipedia live MediaWiki API (gap fill only)"),
            ("url", "https://ta.wikipedia.org/w/api.php"),
            ("license", LICENSE),
            ("license_verified_on", VERSION),
            ("how_obtained", "siteinfo rightsinfo for the licence; list=search for the coverage-list species "
                             "the dump did not resolve; prop=redirects (50 titles a request) for alternative "
                             "Tamil names; prop=extracts only for pages that are not in the dump. "
                             "User-Agent tamil-lm-research (contact@timegravity.ai), under 2 requests a second"),
            ("articles_kept", sum(1 for r in kept_rows if r["text_from"] == "api")),
            ("redirect_titles_read", sum(len(v) for v in redirects.values())),
        ]),
        OrderedDict([
            ("name", "English Wikipedia MediaWiki API (name index only, no text taken)"),
            ("url", "https://en.wikipedia.org/w/api.php"),
            ("license", LICENSE),
            ("license_verified_on", VERSION),
            ("how_obtained", "prop=langlinks&lllang=ta on the scientific name, to learn which Tamil article "
                             "is the same subject when the Tamil search could not find it. Only the Tamil "
                             "title is taken; no English sentence enters the pack"),
            ("titles_resolved", sum(1 for v in how.values() if v == "en_langlink")),
        ]),
    ]

    manifest = OrderedDict([
        ("pack", "nature"),
        ("version", VERSION),
        ("languages", ["ta", "en"]),
        ("purpose", "knowledge source for the photo-identification feature: the model guesses a category "
                    "label from a photo, the Tamil name and the description are looked up here"),
        ("sources", sources),
        ("entities", len(kept_rows)),
        ("entities_by_kind", dict(by_kind)),
        ("entities_on_a_coverage_list", sum(1 for r in kept_rows if r["lists"])),
        ("entities_with_name_en", sum(1 for r in kept_rows if r["name_en"])),
        ("entities_with_name_sci", sum(1 for r in kept_rows if r["name_sci"])),
        ("entities_with_alt_names", sum(1 for r in kept_rows if r["names_ta_alt"])),
        ("match_terms_total", terms),
        ("match_terms_mean", round(terms / max(1, len(kept_rows)), 1)),
        ("chunks", len(kept_chunks)),
        ("chunks_by_language", dict(Counter(c["lang"] for c in kept_chunks))),
        ("words", {"total": sum(words), "mean": round(sum(words) / max(1, len(words)), 1),
                   "min": min(words) if words else 0, "max": max(words) if words else 0}),
        ("family_safe", {"entities_scanned": len(rows), "entities_dropped": len(dropped_entities),
                         "chunks_scanned": len(chunks), "chunks_dropped": dropped_chunks,
                         "policy": "severe lexicon hits dropped"}),
        ("coverage", OrderedDict([(k, v["summary"]) for k, v in cov.items()])),
        ("coverage_detail", cov),
        ("built_by", "build_pack_nature.py"),
        ("notes", "Text only, nothing translated: machine_translated is false on every chunk and the Tamil "
                  "description is the article's own first two sentences. description_en is written by hand "
                  "for the coverage-list entities (description_en_written true) and templated from the "
                  "record's own fields for the rest; it is never a machine translation of the Tamil. "
                  "Chunks are 200 to 400 words with the title repeated at the top, one for every entity and "
                  "up to three for a coverage-list entity. Em and en dashes in the source text are "
                  "normalised to hyphens (project house rule)."),
    ])
    json.dump(manifest, open(os.path.join(PACK, "manifest.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    report = OrderedDict([
        ("entities_scanned", len(rows)),
        ("entities_dropped", len(dropped_entities)),
        ("chunks_scanned", len(chunks)),
        ("chunks_dropped", dropped_chunks),
        ("policy", "severe lexicon hits dropped"),
        ("severe_severities", ["slur", "sexual", "profanity"]),
        ("hits_by_severity_entities", dict(ent_hits)),
        ("hits_by_severity_chunks", dict(by_sev)),
        ("kept_entities", len(kept_rows)),
        ("kept_chunks", len(kept_chunks)),
        ("lexicon", {"file": "data/lexicon.hashed", "single_word_entries": len(FS._SET),
                     "two_word_entries": len(FS._SET2)}),
        ("dropped_entity_examples", dropped_entities[:20]),
        ("dropped_chunk_examples", examples),
        ("note", "family_safe.check() over every chunk (title, section and body), over both descriptions and "
                 "over the Tamil name of every entity. A severity of slur, sexual or profanity drops the "
                 "row; a mild hit is kept and counted. An entity that loses all of its chunks is dropped "
                 "too, so no entity is left without text. The Tamil Wikipedia source was already filtered "
                 "once at index build time (data/index/tawiki_20260801_fs/family_safe_report.json), so few "
                 "hits are expected; the live-API gap-fill pages were not, and are scanned here for the "
                 "first time."),
    ])
    json.dump(report, open(os.path.join(PACK, "family_safe_report.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    json.dump({"still_missing": [{"list": SEEDS[i]["list"], "english": SEEDS[i]["en"],
                                  "scientific": SEEDS[i]["sci"]} for i in still_missing]},
              open(os.path.join(CACHE, "unresolved.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    print("wrote %s: %d entities, %d chunks" % (PACK, len(kept_rows), len(kept_chunks)))
    for k, v in cov.items():
        s = v["summary"]
        print("  %-22s entity %d/%d, tamil name %d, scientific %d, description %d"
              % (k, s["entity"], s["items"], s["name_ta"], s["name_sci"], s["description"]))

if __name__ == "__main__":
    main()
