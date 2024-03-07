let popscore = 0;
// let popstreak = 0;
// let currentHigherPopulationCountry = ""; // To keep track of the correct answer

const countriesData = [
    {"country":"India","2023 population":1428627663,"image_path":"images\/games-images\/country-outlines\/India.png"},
    {"country":"China","2023 population":1425671352,"image_path":"images\/games-images\/country-outlines\/China.png"},
    {"country":"United States","2023 population":339996563,"image_path":"images\/games-images\/country-outlines\/United_States.png"},
    {"country":"Indonesia","2023 population":277534122,"image_path":"images\/games-images\/country-outlines\/Indonesia.png"},
    {"country":"Pakistan","2023 population":240485658,"image_path":"images\/games-images\/country-outlines\/Pakistan.png"},
    {"country":"Nigeria","2023 population":223804632,"image_path":"images\/games-images\/country-outlines\/Nigeria.png"},
    {"country":"Brazil","2023 population":216422446,"image_path":"images\/games-images\/country-outlines\/Brazil.png"},
    {"country":"Bangladesh","2023 population":172954319,"image_path":"images\/games-images\/country-outlines\/Bangladesh.png"},
    {"country":"Russia","2023 population":144444359,"image_path":"images\/games-images\/country-outlines\/Russia.png"},
    {"country":"Mexico","2023 population":128455567,"image_path":"images\/games-images\/country-outlines\/Mexico.png"},
    {"country":"Ethiopia","2023 population":126527060,"image_path":"images\/games-images\/country-outlines\/Ethiopia.png"},
    {"country":"Japan","2023 population":123294513,"image_path":"images\/games-images\/country-outlines\/Japan.png"},
    {"country":"Philippines","2023 population":117337368,"image_path":"images\/games-images\/country-outlines\/Philippines.png"},
    {"country":"Egypt","2023 population":112716598,"image_path":"images\/games-images\/country-outlines\/Egypt.png"},
    {"country":"DR Congo","2023 population":102262808,"image_path":"images\/games-images\/country-outlines\/DR_Congo.png"},
    {"country":"Vietnam","2023 population":98858950,"image_path":"images\/games-images\/country-outlines\/Vietnam.png"},
    {"country":"Iran","2023 population":89172767,"image_path":"images\/games-images\/country-outlines\/Iran.png"},
    {"country":"Turkey","2023 population":85816199,"image_path":"images\/games-images\/country-outlines\/Turkey.png"},
    {"country":"Germany","2023 population":83294633,"image_path":"images\/games-images\/country-outlines\/Germany.png"},
    {"country":"Thailand","2023 population":71801279,"image_path":"images\/games-images\/country-outlines\/Thailand.png"},
    {"country":"United Kingdom","2023 population":67736802,"image_path":"images\/games-images\/country-outlines\/United_Kingdom.png"},
    {"country":"Tanzania","2023 population":67438106,"image_path":"images\/games-images\/country-outlines\/Tanzania.png"},
    {"country":"France","2023 population":64756584,"image_path":"images\/games-images\/country-outlines\/France.png"},
    {"country":"South Africa","2023 population":60414495,"image_path":"images\/games-images\/country-outlines\/South_Africa.png"},
    {"country":"Italy","2023 population":58870762,"image_path":"images\/games-images\/country-outlines\/Italy.png"},
    {"country":"Kenya","2023 population":55100586,"image_path":"images\/games-images\/country-outlines\/Kenya.png"},
    {"country":"Myanmar","2023 population":54577997,"image_path":"images\/games-images\/country-outlines\/Myanmar.png"},
    {"country":"Colombia","2023 population":52085168,"image_path":"images\/games-images\/country-outlines\/Colombia.png"},
    {"country":"South Korea","2023 population":51784059,"image_path":"images\/games-images\/country-outlines\/South_Korea.png"},
    {"country":"Uganda","2023 population":48582334,"image_path":"images\/games-images\/country-outlines\/Uganda.png"},
    {"country":"Sudan","2023 population":48109006,"image_path":"images\/games-images\/country-outlines\/Sudan.png"},
    {"country":"Spain","2023 population":47519628,"image_path":"images\/games-images\/country-outlines\/Spain.png"},
    {"country":"Argentina","2023 population":45773884,"image_path":"images\/games-images\/country-outlines\/Argentina.png"},
    {"country":"Algeria","2023 population":45606480,"image_path":"images\/games-images\/country-outlines\/Algeria.png"},
    {"country":"Iraq","2023 population":45504560,"image_path":"images\/games-images\/country-outlines\/Iraq.png"},
    {"country":"Afghanistan","2023 population":42239854,"image_path":"images\/games-images\/country-outlines\/Afghanistan.png"},
    {"country":"Poland","2023 population":41026067,"image_path":"images\/games-images\/country-outlines\/Poland.png"},
    {"country":"Canada","2023 population":38781291,"image_path":"images\/games-images\/country-outlines\/Canada.png"},
    {"country":"Morocco","2023 population":37840044,"image_path":"images\/games-images\/country-outlines\/Morocco.png"},
    {"country":"Saudi Arabia","2023 population":36947025,"image_path":"images\/games-images\/country-outlines\/Saudi_Arabia.png"},
    {"country":"Ukraine","2023 population":36744634,"image_path":"images\/games-images\/country-outlines\/Ukraine.png"},
    {"country":"Angola","2023 population":36684202,"image_path":"images\/games-images\/country-outlines\/Angola.png"},
    {"country":"Uzbekistan","2023 population":35163944,"image_path":"images\/games-images\/country-outlines\/Uzbekistan.png"},
    {"country":"Yemen","2023 population":34449825,"image_path":"images\/games-images\/country-outlines\/Yemen.png"},
    {"country":"Peru","2023 population":34352719,"image_path":"images\/games-images\/country-outlines\/Peru.png"},
    {"country":"Malaysia","2023 population":34308525,"image_path":"images\/games-images\/country-outlines\/Malaysia.png"},
    {"country":"Ghana","2023 population":34121985,"image_path":"images\/games-images\/country-outlines\/Ghana.png"},
    {"country":"Mozambique","2023 population":33897354,"image_path":"images\/games-images\/country-outlines\/Mozambique.png"},
    {"country":"Nepal","2023 population":30896590,"image_path":"images\/games-images\/country-outlines\/Nepal.png"},
    {"country":"Madagascar","2023 population":30325732,"image_path":"images\/games-images\/country-outlines\/Madagascar.png"},
    {"country":"Ivory Coast","2023 population":28873034,"image_path":"images\/games-images\/country-outlines\/Ivory_Coast.png"},
    {"country":"Venezuela","2023 population":28838499,"image_path":"images\/games-images\/country-outlines\/Venezuela.png"},
    {"country":"Cameroon","2023 population":28647293,"image_path":"images\/games-images\/country-outlines\/Cameroon.png"},
    {"country":"Niger","2023 population":27202843,"image_path":"images\/games-images\/country-outlines\/Niger.png"},
    {"country":"Australia","2023 population":26439111,"image_path":"images\/games-images\/country-outlines\/Australia.png"},
    {"country":"North Korea","2023 population":26160821,"image_path":"images\/games-images\/country-outlines\/North_Korea.png"},
    {"country":"Taiwan","2023 population":23923276,"image_path":"images\/games-images\/country-outlines\/Taiwan.png"},
    {"country":"Mali","2023 population":23293698,"image_path":"images\/games-images\/country-outlines\/Mali.png"},
    {"country":"Burkina Faso","2023 population":23251485,"image_path":"images\/games-images\/country-outlines\/Burkina_Faso.png"},
    {"country":"Syria","2023 population":23227014,"image_path":"images\/games-images\/country-outlines\/Syria.png"},
    {"country":"Sri Lanka","2023 population":21893579,"image_path":"images\/games-images\/country-outlines\/Sri_Lanka.png"},
    {"country":"Malawi","2023 population":20931751,"image_path":"images\/games-images\/country-outlines\/Malawi.png"},
    {"country":"Zambia","2023 population":20569737,"image_path":"images\/games-images\/country-outlines\/Zambia.png"},
    {"country":"Romania","2023 population":19892812,"image_path":"images\/games-images\/country-outlines\/Romania.png"},
    {"country":"Chile","2023 population":19629590,"image_path":"images\/games-images\/country-outlines\/Chile.png"},
    {"country":"Kazakhstan","2023 population":19606633,"image_path":"images\/games-images\/country-outlines\/Kazakhstan.png"},
    {"country":"Chad","2023 population":18278568,"image_path":"images\/games-images\/country-outlines\/Chad.png"},
    {"country":"Ecuador","2023 population":18190484,"image_path":"images\/games-images\/country-outlines\/Ecuador.png"},
    {"country":"Somalia","2023 population":18143378,"image_path":"images\/games-images\/country-outlines\/Somalia.png"},
    {"country":"Guatemala","2023 population":18092026,"image_path":"images\/games-images\/country-outlines\/Guatemala.png"},
    {"country":"Senegal","2023 population":17763163,"image_path":"images\/games-images\/country-outlines\/Senegal.png"},
    {"country":"Netherlands","2023 population":17618299,"image_path":"images\/games-images\/country-outlines\/Netherlands.png"},
    {"country":"Cambodia","2023 population":16944826,"image_path":"images\/games-images\/country-outlines\/Cambodia.png"},
    {"country":"Zimbabwe","2023 population":16665409,"image_path":"images\/games-images\/country-outlines\/Zimbabwe.png"},
    {"country":"Guinea","2023 population":14190612,"image_path":"images\/games-images\/country-outlines\/Guinea.png"},
    {"country":"Rwanda","2023 population":14094683,"image_path":"images\/games-images\/country-outlines\/Rwanda.png"},
    {"country":"Benin","2023 population":13712828,"image_path":"images\/games-images\/country-outlines\/Benin.png"},
    {"country":"Burundi","2023 population":13238559,"image_path":"images\/games-images\/country-outlines\/Burundi.png"},
    {"country":"Tunisia","2023 population":12458223,"image_path":"images\/games-images\/country-outlines\/Tunisia.png"},
    {"country":"Bolivia","2023 population":12388571,"image_path":"images\/games-images\/country-outlines\/Bolivia.png"},
    {"country":"Haiti","2023 population":11724763,"image_path":"images\/games-images\/country-outlines\/Haiti.png"},
    {"country":"Belgium","2023 population":11686140,"image_path":"images\/games-images\/country-outlines\/Belgium.png"},
    {"country":"Jordan","2023 population":11337052,"image_path":"images\/games-images\/country-outlines\/Jordan.png"},
    {"country":"Dominican Republic","2023 population":11332972,"image_path":"images\/games-images\/country-outlines\/Dominican_Republic.png"},
    {"country":"Cuba","2023 population":11194449,"image_path":"images\/games-images\/country-outlines\/Cuba.png"},
    {"country":"South Sudan","2023 population":11088796,"image_path":"images\/games-images\/country-outlines\/South_Sudan.png"},
    {"country":"Sweden","2023 population":10612086,"image_path":"images\/games-images\/country-outlines\/Sweden.png"},
    {"country":"Honduras","2023 population":10593798,"image_path":"images\/games-images\/country-outlines\/Honduras.png"},
    {"country":"Czech Republic","2023 population":10495295,"image_path":"images\/games-images\/country-outlines\/Czech_Republic.png"},
    {"country":"Azerbaijan","2023 population":10412651,"image_path":"images\/games-images\/country-outlines\/Azerbaijan.png"},
    {"country":"Greece","2023 population":10341277,"image_path":"images\/games-images\/country-outlines\/Greece.png"},
    {"country":"Papua New Guinea","2023 population":10329931,"image_path":"images\/games-images\/country-outlines\/Papua_New_Guinea.png"},
    {"country":"Portugal","2023 population":10247605,"image_path":"images\/games-images\/country-outlines\/Portugal.png"},
    {"country":"Hungary","2023 population":10156239,"image_path":"images\/games-images\/country-outlines\/Hungary.png"},
    {"country":"Tajikistan","2023 population":10143543,"image_path":"images\/games-images\/country-outlines\/Tajikistan.png"},
    {"country":"United Arab Emirates","2023 population":9516871,"image_path":"images\/games-images\/country-outlines\/United_Arab_Emirates.png"},{"country":"Belarus","2023 population":9498238,"image_path":"images\/games-images\/country-outlines\/Belarus.png"},{"country":"Israel","2023 population":9174520,"image_path":"images\/games-images\/country-outlines\/Israel.png"},
    {"country":"Togo","2023 population":9053799,"image_path":"images\/games-images\/country-outlines\/Togo.png"},
    {"country":"Austria","2023 population":8958960,"image_path":"images\/games-images\/country-outlines\/Austria.png"},
    {"country":"Switzerland","2023 population":8796669,"image_path":"images\/games-images\/country-outlines\/Switzerland.png"},
    {"country":"Sierra Leone","2023 population":8791092,"image_path":"images\/games-images\/country-outlines\/Sierra_Leone.png"},
    {"country":"Laos","2023 population":7633779,"image_path":"images\/games-images\/country-outlines\/Laos.png"},
    {"country":"Hong Kong","2023 population":7491609,"image_path":"images\/games-images\/country-outlines\/Hong_Kong.png"},
    {"country":"Serbia","2023 population":7149077,"image_path":"images\/games-images\/country-outlines\/Serbia.png"},
    {"country":"Nicaragua","2023 population":7046310,"image_path":"images\/games-images\/country-outlines\/Nicaragua.png"},
    {"country":"Libya","2023 population":6888388,"image_path":"images\/games-images\/country-outlines\/Libya.png"},
    {"country":"Paraguay","2023 population":6861524,"image_path":"images\/games-images\/country-outlines\/Paraguay.png"},
    {"country":"Kyrgyzstan","2023 population":6735347,"image_path":"images\/games-images\/country-outlines\/Kyrgyzstan.png"},
    {"country":"Bulgaria","2023 population":6687717,"image_path":"images\/games-images\/country-outlines\/Bulgaria.png"},
    {"country":"Turkmenistan","2023 population":6516100,"image_path":"images\/games-images\/country-outlines\/Turkmenistan.png"},
    {"country":"El Salvador","2023 population":6364943,"image_path":"images\/games-images\/country-outlines\/El_Salvador.png"},
    {"country":"Republic of the Congo","2023 population":6106869,"image_path":"images\/games-images\/country-outlines\/Republic_of_the_Congo.png"},
    {"country":"Singapore","2023 population":6014723,"image_path":"images\/games-images\/country-outlines\/Singapore.png"},
    {"country":"Denmark","2023 population":5910913,"image_path":"images\/games-images\/country-outlines\/Denmark.png"},
    {"country":"Slovakia","2023 population":5795199,"image_path":"images\/games-images\/country-outlines\/Slovakia.png"},
    {"country":"Central African Republic","2023 population":5742315,"image_path":"images\/games-images\/country-outlines\/Central_African_Republic.png"},
    {"country":"Finland","2023 population":5545475,"image_path":"images\/games-images\/country-outlines\/Finland.png"},
    {"country":"Norway","2023 population":5474360,"image_path":"images\/games-images\/country-outlines\/Norway.png"},
    {"country":"Liberia","2023 population":5418377,"image_path":"images\/games-images\/country-outlines\/Liberia.png"},
    {"country":"Palestine","2023 population":5371230,"image_path":"images\/games-images\/country-outlines\/Palestine.png"},
    {"country":"Lebanon","2023 population":5353930,"image_path":"images\/games-images\/country-outlines\/Lebanon.png"},
    {"country":"New Zealand","2023 population":5228100,"image_path":"images\/games-images\/country-outlines\/New_Zealand.png"},
    {"country":"Costa Rica","2023 population":5212173,"image_path":"images\/games-images\/country-outlines\/Costa_Rica.png"},
    {"country":"Ireland","2023 population":5056935,"image_path":"images\/games-images\/country-outlines\/Ireland.png"},
    {"country":"Mauritania","2023 population":4862989,"image_path":"images\/games-images\/country-outlines\/Mauritania.png"},
    {"country":"Oman","2023 population":4644384,"image_path":"images\/games-images\/country-outlines\/Oman.png"},
    {"country":"Panama","2023 population":4468087,"image_path":"images\/games-images\/country-outlines\/Panama.png"},
    {"country":"Kuwait","2023 population":4310108,"image_path":"images\/games-images\/country-outlines\/Kuwait.png"},
    {"country":"Croatia","2023 population":4008617,"image_path":"images\/games-images\/country-outlines\/Croatia.png"},
    {"country":"Eritrea","2023 population":3748901,"image_path":"images\/games-images\/country-outlines\/Eritrea.png"},
    {"country":"Georgia","2023 population":3728282,"image_path":"images\/games-images\/country-outlines\/Georgia.png"},
    {"country":"Mongolia","2023 population":3447157,"image_path":"images\/games-images\/country-outlines\/Mongolia.png"},
    {"country":"Moldova","2023 population":3435931,"image_path":"images\/games-images\/country-outlines\/Moldova.png"},
    {"country":"Uruguay","2023 population":3423108,"image_path":"images\/games-images\/country-outlines\/Uruguay.png"},
    {"country":"Puerto Rico","2023 population":3260314,"image_path":"images\/games-images\/country-outlines\/Puerto_Rico.png"},
    {"country":"Bosnia and Herzegovina","2023 population":3210847,"image_path":"images\/games-images\/country-outlines\/Bosnia_and_Herzegovina.png"},
    {"country":"Albania","2023 population":2832439,"image_path":"images\/games-images\/country-outlines\/Albania.png"},
    {"country":"Jamaica","2023 population":2825544,"image_path":"images\/games-images\/country-outlines\/Jamaica.png"},
    {"country":"Armenia","2023 population":2777970,"image_path":"images\/games-images\/country-outlines\/Armenia.png"},
    {"country":"Gambia","2023 population":2773168,"image_path":"images\/games-images\/country-outlines\/Gambia.png"},
    {"country":"Lithuania","2023 population":2718352,"image_path":"images\/games-images\/country-outlines\/Lithuania.png"},
    {"country":"Qatar","2023 population":2716391,"image_path":"images\/games-images\/country-outlines\/Qatar.png"},
    {"country":"Botswana","2023 population":2675352,"image_path":"images\/games-images\/country-outlines\/Botswana.png"},
    {"country":"Namibia","2023 population":2604172,"image_path":"images\/games-images\/country-outlines\/Namibia.png"},
    {"country":"Gabon","2023 population":2436566,"image_path":"images\/games-images\/country-outlines\/Gabon.png"},
    {"country":"Lesotho","2023 population":2330318,"image_path":"images\/games-images\/country-outlines\/Lesotho.png"},
    {"country":"Guinea-Bissau","2023 population":2150842,"image_path":"images\/games-images\/country-outlines\/Guinea-Bissau.png"},
    {"country":"Slovenia","2023 population":2119675,"image_path":"images\/games-images\/country-outlines\/Slovenia.png"},
    {"country":"North Macedonia","2023 population":2085679,"image_path":"images\/games-images\/country-outlines\/North_Macedonia.png"},
    {"country":"Latvia","2023 population":1830211,"image_path":"images\/games-images\/country-outlines\/Latvia.png"},
    {"country":"Equatorial Guinea","2023 population":1714671,"image_path":"images\/games-images\/country-outlines\/Equatorial_Guinea.png"},
    {"country":"Trinidad and Tobago","2023 population":1534937,"image_path":"images\/games-images\/country-outlines\/Trinidad_and_Tobago.png"},
    {"country":"Bahrain","2023 population":1485509,"image_path":"images\/games-images\/country-outlines\/Bahrain.png"},
    {"country":"Timor-Leste","2023 population":1360596,"image_path":"images\/games-images\/country-outlines\/Timor-Leste.png"},
    {"country":"Estonia","2023 population":1322765,"image_path":"images\/games-images\/country-outlines\/Estonia.png"},
    {"country":"Mauritius","2023 population":1300557,"image_path":"images\/games-images\/country-outlines\/Mauritius.png"},
    {"country":"Cyprus","2023 population":1260138,"image_path":"images\/games-images\/country-outlines\/Cyprus.png"},
    {"country":"Eswatini","2023 population":1210822,"image_path":"images\/games-images\/country-outlines\/Eswatini.png"},
    {"country":"Djibouti","2023 population":1136455,"image_path":"images\/games-images\/country-outlines\/Djibouti.png"},
    {"country":"Reunion","2023 population":981796,"image_path":"images\/games-images\/country-outlines\/Reunion.png"},
    {"country":"Fiji","2023 population":936375,"image_path":"images\/games-images\/country-outlines\/Fiji.png"},
    {"country":"Comoros","2023 population":852075,"image_path":"images\/games-images\/country-outlines\/Comoros.png"},
    {"country":"Guyana","2023 population":813834,"image_path":"images\/games-images\/country-outlines\/Guyana.png"},
    {"country":"Bhutan","2023 population":787424,"image_path":"images\/games-images\/country-outlines\/Bhutan.png"},
    {"country":"Solomon Islands","2023 population":740424,"image_path":"images\/games-images\/country-outlines\/Solomon_Islands.png"},
    {"country":"Macau","2023 population":704149,"image_path":"images\/games-images\/country-outlines\/Macau.png"},
    {"country":"Luxembourg","2023 population":654768,"image_path":"images\/games-images\/country-outlines\/Luxembourg.png"},
    {"country":"Montenegro","2023 population":626485,"image_path":"images\/games-images\/country-outlines\/Montenegro.png"},
    {"country":"Suriname","2023 population":623236,"image_path":"images\/games-images\/country-outlines\/Suriname.png"},
    {"country":"Cape Verde","2023 population":598682,"image_path":"images\/games-images\/country-outlines\/Cape_Verde.png"},
    {"country":"Western Sahara","2023 population":587259,"image_path":"images\/games-images\/country-outlines\/Western_Sahara.png"},
    {"country":"Malta","2023 population":535064,"image_path":"images\/games-images\/country-outlines\/Malta.png"},
    {"country":"Maldives","2023 population":521021,"image_path":"images\/games-images\/country-outlines\/Maldives.png"},
    {"country":"Brunei","2023 population":452524,"image_path":"images\/games-images\/country-outlines\/Brunei.png"},{"country":"Bahamas","2023 population":412623,"image_path":"images\/games-images\/country-outlines\/Bahamas.png"},
    {"country":"Belize","2023 population":410825,"image_path":"images\/games-images\/country-outlines\/Belize.png"},
    {"country":"Guadeloupe","2023 population":395839,"image_path":"images\/games-images\/country-outlines\/Guadeloupe.png"},
    {"country":"Iceland","2023 population":375318,"image_path":"images\/games-images\/country-outlines\/Iceland.png"},
    {"country":"Martinique","2023 population":366981,"image_path":"images\/games-images\/country-outlines\/Martinique.png"},
    {"country":"Mayotte","2023 population":335995,"image_path":"images\/games-images\/country-outlines\/Mayotte.png"},
    {"country":"Vanuatu","2023 population":334506,"image_path":"images\/games-images\/country-outlines\/Vanuatu.png"},
    {"country":"French Guiana","2023 population":312155,"image_path":"images\/games-images\/country-outlines\/French_Guiana.png"},
    {"country":"French Polynesia","2023 population":308872,"image_path":"images\/games-images\/country-outlines\/French_Polynesia.png"},
    {"country":"New Caledonia","2023 population":292991,"image_path":"images\/games-images\/country-outlines\/New_Caledonia.png"},
    {"country":"Barbados","2023 population":281995,"image_path":"images\/games-images\/country-outlines\/Barbados.png"},
    {"country":"Sao Tome and Principe","2023 population":231856,"image_path":"images\/games-images\/country-outlines\/Sao_Tome_and_Principe.png"},
    {"country":"Samoa","2023 population":225681,"image_path":"images\/games-images\/country-outlines\/Samoa.png"},
    {"country":"Curacao","2023 population":192077,"image_path":"images\/games-images\/country-outlines\/Curacao.png"},
    {"country":"Saint Lucia","2023 population":180251,"image_path":"images\/games-images\/country-outlines\/Saint_Lucia.png"},
    {"country":"Guam","2023 population":172952,"image_path":"images\/games-images\/country-outlines\/Guam.png"},
    {"country":"Kiribati","2023 population":133515,"image_path":"images\/games-images\/country-outlines\/Kiribati.png"},
    {"country":"Grenada","2023 population":126183,"image_path":"images\/games-images\/country-outlines\/Grenada.png"},
    {"country":"Micronesia","2023 population":115224,"image_path":"images\/games-images\/country-outlines\/Micronesia.png"},
    {"country":"Jersey","2023 population":111802,"image_path":"images\/games-images\/country-outlines\/Jersey.png"},
    {"country":"Tonga","2023 population":107773,"image_path":"images\/games-images\/country-outlines\/Tonga.png"},
    {"country":"Seychelles","2023 population":107660,"image_path":"images\/games-images\/country-outlines\/Seychelles.png"},
    {"country":"Aruba","2023 population":106277,"image_path":"images\/games-images\/country-outlines\/Aruba.png"},
    {"country":"Saint Vincent and the Grenadines","2023 population":103698,"image_path":"images\/games-images\/country-outlines\/Saint_Vincent_and_the_Grenadines.png"},
    {"country":"United States Virgin Islands","2023 population":98750,"image_path":"images\/games-images\/country-outlines\/United_States_Virgin_Islands.png"},
    {"country":"Antigua and Barbuda","2023 population":94298,"image_path":"images\/games-images\/country-outlines\/Antigua_and_Barbuda.png"},
    {"country":"Isle of Man","2023 population":84710,"image_path":"images\/games-images\/country-outlines\/Isle_of_Man.png"},
    {"country":"Andorra","2023 population":80088,"image_path":"images\/games-images\/country-outlines\/Andorra.png"},
    {"country":"Dominica","2023 population":73040,"image_path":"images\/games-images\/country-outlines\/Dominica.png"},
    {"country":"Cayman Islands","2023 population":69310,"image_path":"images\/games-images\/country-outlines\/Cayman_Islands.png"},
    {"country":"Bermuda","2023 population":64069,"image_path":"images\/games-images\/country-outlines\/Bermuda.png"},
    {"country":"Guernsey","2023 population":63544,"image_path":"images\/games-images\/country-outlines\/Guernsey.png"},
    {"country":"Greenland","2023 population":56643,"image_path":"images\/games-images\/country-outlines\/Greenland.png"},
    {"country":"Faroe Islands","2023 population":53270,"image_path":"images\/games-images\/country-outlines\/Faroe_Islands.png"},
    {"country":"Northern Mariana Islands","2023 population":49796,"image_path":"images\/games-images\/country-outlines\/Northern_Mariana_Islands.png"},
    {"country":"Saint Kitts and Nevis","2023 population":47755,"image_path":"images\/games-images\/country-outlines\/Saint_Kitts_and_Nevis.png"},
    {"country":"Turks and Caicos Islands","2023 population":46062,"image_path":"images\/games-images\/country-outlines\/Turks_and_Caicos_Islands.png"},
    {"country":"Sint Maarten","2023 population":44222,"image_path":"images\/games-images\/country-outlines\/Sint_Maarten.png"},
    {"country":"American Samoa","2023 population":43914,"image_path":"images\/games-images\/country-outlines\/American_Samoa.png"},
    {"country":"Marshall Islands","2023 population":41996,"image_path":"images\/games-images\/country-outlines\/Marshall_Islands.png"},
    {"country":"Liechtenstein","2023 population":39584,"image_path":"images\/games-images\/country-outlines\/Liechtenstein.png"},
    {"country":"Monaco","2023 population":36297,"image_path":"images\/games-images\/country-outlines\/Monaco.png"},
    {"country":"San Marino","2023 population":33642,"image_path":"images\/games-images\/country-outlines\/San_Marino.png"},
    {"country":"Gibraltar","2023 population":32688,"image_path":"images\/games-images\/country-outlines\/Gibraltar.png"},
    {"country":"Saint Martin","2023 population":32077,"image_path":"images\/games-images\/country-outlines\/Saint_Martin.png"},
    {"country":"British Virgin Islands","2023 population":31538,"image_path":"images\/games-images\/country-outlines\/British_Virgin_Islands.png"},
    {"country":"Palau","2023 population":18058,"image_path":"images\/games-images\/country-outlines\/Palau.png"},
    {"country":"Cook Islands","2023 population":17044,"image_path":"images\/games-images\/country-outlines\/Cook_Islands.png"},
    {"country":"Anguilla","2023 population":15899,"image_path":"images\/games-images\/country-outlines\/Anguilla.png"},
    {"country":"Nauru","2023 population":12780,"image_path":"images\/games-images\/country-outlines\/Nauru.png"},
    {"country":"Wallis and Futuna","2023 population":11502,"image_path":"images\/games-images\/country-outlines\/Wallis_and_Futuna.png"},
    {"country":"Tuvalu","2023 population":11396,"image_path":"images\/games-images\/country-outlines\/Tuvalu.png"},
    {"country":"Saint Barthelemy","2023 population":10994,"image_path":"images\/games-images\/country-outlines\/Saint_Barthelemy.png"},
    {"country":"Saint Pierre and Miquelon","2023 population":5840,"image_path":"images\/games-images\/country-outlines\/Saint_Pierre_and_Miquelon.png"},
    {"country":"Montserrat","2023 population":4386,"image_path":"images\/games-images\/country-outlines\/Montserrat.png"},
    {"country":"Falkland Islands","2023 population":3791,"image_path":"images\/games-images\/country-outlines\/Falkland_Islands.png"},
    {"country":"Niue","2023 population":1935,"image_path":"images\/games-images\/country-outlines\/Niue.png"},
    {"country":"Tokelau","2023 population":1893,"image_path":"images\/games-images\/country-outlines\/Tokelau.png"},
    {"country":"Vatican City","2023 population":518,"image_path":"images\/games-images\/country-outlines\/Vatican_City.png"}
];

function loadNewChallenge() {
  // Pick two random countries
  const indices = [];
  while(indices.length < 2){
    let r = Math.floor(Math.random() * countriesData.length);
    if(indices.indexOf(r) === -1) indices.push(r);
  }

  const country1 = countriesData[indices[0]];
  const country2 = countriesData[indices[1]];

  const img1 = document.getElementById('country1-img');
  console.log(country1.image_path);
  img1.src = country1.image_path;
  img1.onclick = () => submitAnswer(country1, country2);

  const img2 = document.getElementById('country2-img');
  img2.src = country2.image_path;
  img2.onclick = () => submitAnswer(country2, country1);
}

function submitAnswer(selectedCountry, otherCountry) {
  // Use bracket notation to access properties with spaces in their names
  if (parseInt(selectedCountry["2023 population"]) > parseInt(otherCountry["2023 population"])) {
    alert('Correct!');
    popscore++;
  } else {
    alert('Incorrect!');
  }
  // Update score and possibly load a new challenge
  document.getElementById('population-score-value').textContent = popscore; // Make sure this ID matches your HTML

  loadNewChallenge();
}

document.addEventListener('DOMContentLoaded', loadNewChallenge);
