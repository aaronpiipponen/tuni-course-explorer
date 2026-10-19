/**
 * One typed in-bundle FI/EN wording resource for every app-authored interface string.
 *
 * The English source literal is the dictionary key. A context suffix such as
 * `Completed (basis)` resolves Finnish grammar where one English word has two forms.
 * Values hold both translations once, beside a template's named `{placeholder}`s.
 * This module is pure: it imports only types and translates app-authored strings
 * between Finnish and English.
 */
import type { SearchMethod } from "../api/types";
import type { DisplayLanguage } from "../state/types";

export const UI_TEXT = {
  Search: { en: "Search", fi: "Haku" },
  Compare: { en: "Compare", fi: "Vertailu" },
  Prerequisites: { en: "Prerequisites", fi: "Esitiedot" },
  Discover: { en: "Discover", fi: "Ehdotukset" },
  "Structure of studies": {
    en: "Structure of studies",
    fi: "Opintojen rakenne",
  },
  Docs: { en: "Docs", fi: "Ohjeet" },
  "Main navigation": { en: "Main navigation", fi: "Päävalikko" },
  "Course tools": { en: "Course tools", fi: "Kurssityökalut" },
  "Previous tab": { en: "Previous tab", fi: "Edellinen välilehti" },
  "Next tab": { en: "Next tab", fi: "Seuraava välilehti" },
  "App language: {language}": {
    en: "App language: {language}",
    fi: "Käyttöliittymän kieli: {language}",
  },
  "This is an independent project that is not affiliated with Tampere University.":
    {
      en: "This is an independent project that is not affiliated with Tampere University.",
      fi: "Tämä on itsenäinen projekti, jolla ei ole virallista yhteyttä Tampereen yliopistoon.",
    },
  "Source code on GitHub.": {
    en: "Source code on GitHub.",
    fi: "Lähdekoodi GitHubissa.",
  },

  active: { en: "active", fi: "aktiivinen" },
  inactive: { en: "inactive", fi: "ei aktiivinen" },
  completed: { en: "completed", fi: "suoritettu" },
  selected: { en: "selected", fi: "valittu" },
  "not selected": { en: "not selected", fi: "ei valittu" },
  "{code} {name}": { en: "{code} {name}", fi: "{code} {name}" },
  "{action} {name}": { en: "{action} {name}", fi: "{action} {name}" },
  "comparison slot {slot}": {
    en: "comparison slot {slot}",
    fi: "vertailukurssi {slot}",
  },
  "Completed (basis)": { en: "Completed", fi: "Suoritetut" },
  "Selected (basis)": { en: "Selected", fi: "Valitut" },
  "Completed (course)": { en: "Completed", fi: "Suoritettu" },
  "Complete (course)": { en: "Complete", fi: "Suorita" },
  Excluded: { en: "Excluded", fi: "Suljettu pois" },
  Exclude: { en: "Exclude", fi: "Sulje pois" },
  inferred: { en: "inferred", fi: "päätelty" },
  Inferred: { en: "Inferred", fi: "Päätelty" },
  "Active only": { en: "Active only", fi: "Vain aktiiviset" },
  done: { en: "done", fi: "valmis" },
  added: { en: "added", fi: "lisätty" },
  "not available": { en: "not available", fi: "ei saatavilla" },
  "{value} cr": { en: "{value} cr", fi: "{value} op" },
  cr: { en: "cr", fi: "op" },
  "{value} courses": { en: "{value} courses", fi: "{value} kurssia" },
  course: { en: "course", fi: "kurssi" },
  courses: { en: "courses", fi: "kurssia" },
  "courses (heading)": { en: "courses", fi: "kurssit" },
  "1 course": { en: "1 course", fi: "1 kurssi" },
  Close: { en: "Close", fi: "Sulje" },
  Cancel: { en: "Cancel", fi: "Peruuta" },
  Save: { en: "Save", fi: "Tallenna" },
  Delete: { en: "Delete", fi: "Poista" },
  Move: { en: "Move", fi: "Siirrä" },
  Keep: { en: "Keep", fi: "Säilytä" },
  Pull: { en: "Pull", fi: "Siirrä" },
  Reset: { en: "Reset", fi: "Nollaa" },
  Replace: { en: "Replace", fi: "Vaihda" },
  Remove: { en: "Remove", fi: "Poista" },
  Change: { en: "Change", fi: "Vaihda" },
  Recenter: { en: "Recenter", fi: "Keskitä" },
  Expand: { en: "Expand", fi: "Laajenna" },
  Collapse: { en: "Collapse", fi: "Tiivistä" },
  "Original technical detail": {
    en: "Original technical detail",
    fi: "Alkuperäinen tekninen tieto",
  },
  "Unknown reason ({reason})": {
    en: "Unknown reason ({reason})",
    fi: "Tuntematon syy ({reason})",
  },

  "Already in comparison": {
    en: "Already in comparison",
    fi: "Jo vertailussa",
  },
  "Add to comparison": { en: "Add to comparison", fi: "Lisää vertailuun" },
  "Open prerequisite graph": {
    en: "Open prerequisite graph",
    fi: "Avaa esitietograafi",
  },
  "Add to Unplaced studies": {
    en: "Add to Unplaced studies",
    fi: "Lisää sijoittamattomiin opintoihin",
  },
  structure: { en: "structure", fi: "rakenteeseen" },
  "Mark completed": { en: "Mark completed", fi: "Merkitse suoritetuksi" },
  "Mark not completed": {
    en: "Mark not completed",
    fi: "Poista suoritusmerkintä",
  },
  "Open in Sisu": { en: "Open in Sisu", fi: "Avaa Sisussa" },
  "Filter courses by name or code": {
    en: "Filter courses by name or code",
    fi: "Rajaa kursseja nimen tai koodin mukaan",
  },
  "Loading courses": { en: "Loading courses", fi: "Ladataan kursseja" },
  "No courses match this search.": {
    en: "No courses match this search.",
    fi: "Mikään kurssi ei vastaa tätä hakua.",
  },
  "Type to search courses by name or code.": {
    en: "Type to search courses by name or code.",
    fi: "Hae kursseja kirjoittamalla nimi tai koodi.",
  },
  "Semantic search is unavailable. Showing matches by code and name only.": {
    en: "Semantic search is unavailable. Showing matches by code and name only.",
    fi: "Semanttinen haku ei ole käytettävissä. Näytetään vain koodi- ja nimihaun tulokset.",
  },

  "Loading site features": {
    en: "Loading site features",
    fi: "Ladataan sivuston ominaisuuksia",
  },
  "Web features provider is missing": {
    en: "Web features provider is missing",
    fi: "Sivuston ominaisuudet puuttuvat",
  },

  "About these options": {
    en: "About these options",
    fi: "Tietoa valinnoista",
  },
  "Explain these options": {
    en: "Explain these options",
    fi: "Selitä nämä valinnat",
  },
  options: { en: "options", fi: "valinnat" },

  "Search by code, name or topic": {
    en: "Search by code, name or topic",
    fi: "Hae koodin, nimen tai aiheen mukaan",
  },
  "Search results": { en: "Search results", fi: "Hakutulokset" },
  "Shows only courses that are currently active. Turn it off to include inactive courses.":
    {
      en: "Shows only courses that are currently active. Turn it off to include inactive courses.",
      fi: "Näyttää vain tällä hetkellä aktiiviset kurssit. Poista valinta, jos haluat mukaan myös ei-aktiiviset kurssit.",
    },
  "search modes": { en: "search modes", fi: "hakutyypit" },
  "Exact code": { en: "Exact code", fi: "Tarkka koodi" },
  Substring: { en: "Substring", fi: "Osamerkkijono" },
  "Fuzzy search": { en: "Fuzzy search", fi: "Likimääräinen haku" },
  Semantic: { en: "Semantic", fi: "Semanttinen" },
  "The text matches a course code, for example COMP.CS.100.": {
    en: "The text matches a course code, for example COMP.CS.100.",
    fi: "Teksti vastaa kurssikoodia, esimerkiksi COMP.CS.100.",
  },
  "The text appears inside a course name or code, ignoring upper and lower case. A code fragment such as: COMP.CS":
    {
      en: "The text appears inside a course name or code, ignoring upper and lower case. A code fragment such as: COMP.CS",
      fi: "Teksti esiintyy kurssin nimessä tai koodissa kirjainkoosta riippumatta. Koodin osa, esimerkiksi: COMP.CS",
    },
  "A course name that is close to the text, so a small typo still finds it.": {
    en: "A course name that is close to the text, so a small typo still finds it.",
    fi: "Kurssin nimi, joka muistuttaa tekstiä, joten pieni kirjoitusvirhe ei estä löytymistä.",
  },
  "Courses whose content is about the topic you describe, even when they share no words with it.":
    {
      en: "Courses whose content is about the topic you describe, even when they share no words with it.",
      fi: "Kurssit, joiden sisältö käsittelee kuvaamaasi aihetta, vaikka niillä ei olisi yhtään samaa sanaa.",
    },

  "Compare course picker": {
    en: "Compare course picker",
    fi: "Vertailun kurssivalitsin",
  },
  "choose course {slot}": {
    en: "choose course {slot}",
    fi: "valitse kurssi {slot}",
  },
  "+ add": { en: "+ add", fi: "+ lisää" },
  "Add {code} {name} to comparison": {
    en: "Add {code} {name} to comparison",
    fi: "Lisää {code} {name} vertailuun",
  },
  "Course {slot}": { en: "Course {slot}", fi: "Kurssi {slot}" },
  "Loading course {slot}": {
    en: "Loading course {slot}",
    fi: "Ladataan kurssia {slot}",
  },
  "Choose course {slot}": {
    en: "Choose course {slot}",
    fi: "Valitse kurssi {slot}",
  },
  "Course details unavailable": {
    en: "Course details unavailable",
    fi: "Kurssin tiedot eivät ole saatavilla",
  },
  "compare is full": { en: "compare is full", fi: "vertailu on täynnä" },
  "Replace which course?": {
    en: "Replace which course?",
    fi: "Kumpi kurssi korvataan?",
  },
  "Two courses are already in the comparison. Choose the one to replace with {name}.":
    {
      en: "Two courses are already in the comparison. Choose the one to replace with {name}.",
      fi: "Vertailussa on jo kaksi kurssia. Valitse, kumpi korvataan kurssilla {name}.",
    },
  "Loading comparison courses…": {
    en: "Loading comparison courses…",
    fi: "Ladataan vertailun kursseja…",
  },
  "Replace slot {slot}: {name}": {
    en: "Replace slot {slot}: {name}",
    fi: "Korvaa kurssi {slot}: {name}",
  },
  "course details unavailable": {
    en: "course details unavailable",
    fi: "kurssin tiedot eivät ole saatavilla",
  },
  "Heavily overlapping": {
    en: "Heavily overlapping",
    fi: "Voimakkaasti päällekkäiset",
  },
  "Partly overlapping": {
    en: "Partly overlapping",
    fi: "Osittain päällekkäiset",
  },
  "Same area, different content": {
    en: "Same area, different content",
    fi: "Sama alue, eri sisältö",
  },
  "Loosely related": { en: "Loosely related", fi: "Löyhästi liittyvät" },
  Unrelated: { en: "Unrelated", fi: "Eivät liity toisiinsa" },
  "Overall relatedness": {
    en: "Overall relatedness",
    fi: "Yleinen läheisyys",
  },
  "whole course": {
    en: "whole course",
    fi: "koko kurssi",
  },
  "Content similarity": {
    en: "Content similarity",
    fi: "Sisällön samankaltaisuus",
  },
  "content vs content": { en: "content vs content", fi: "sisältö vs. sisältö" },
  "Learning-outcome similarity": {
    en: "Learning-outcome similarity",
    fi: "Osaamistavoitteiden samankaltaisuus",
  },
  "outcomes vs outcomes": {
    en: "outcomes vs outcomes",
    fi: "tavoitteet vs. tavoitteet",
  },
  "Overlap: {a} in {b}": {
    en: "Overlap: {a} in {b}",
    fi: "Päällekkäisyys: {a} kurssissa {b}",
  },
  "how much of A has a match in B": {
    en: "how much of A has a match in B",
    fi: "kuinka suurelle osalle A:sta löytyy vastine B:stä",
  },
  "Overlap: {b} in {a}": {
    en: "Overlap: {b} in {a}",
    fi: "Päällekkäisyys: {b} kurssissa {a}",
  },
  "how much of B has a match in A": {
    en: "how much of B has a match in A",
    fi: "kuinka suurelle osalle B:stä löytyy vastine A:sta",
  },
  "Course information analysis, not official equivalence.": {
    en: "Course information analysis, not official equivalence.",
    fi: "Kurssitietojen analyysi, ei virallinen vastaavuus.",
  },
  "Includes derived text.": {
    en: "Includes derived text.",
    fi: "Sisältää johdettua tekstiä.",
  },
  "Comparing courses…": {
    en: "Comparing courses…",
    fi: "Verrataan kursseja…",
  },
  "Select two courses to compare": {
    en: "Select two courses to compare",
    fi: "Valitse kaksi kurssia vertailtavaksi",
  },

  "Discovery list": { en: "Discovery list", fi: "Ehdotuslista" },
  "Next courses": { en: "Next courses", fi: "Seuraavat kurssit" },
  Recommended: { en: "Recommended", fi: "Suositellut" },
  All: { en: "All", fi: "Kaikki" },
  "At least one": { en: "At least one", fi: "Vähintään yksi" },
  "Prerequisite mode": {
    en: "Prerequisite mode",
    fi: "Esitietojen valintatapa",
  },
  "Discovery basis": { en: "Discovery basis", fi: "Ehdotusten perusta" },
  "All / At least one": {
    en: "All / At least one",
    fi: "Kaikki / Vähintään yksi",
  },
  "All proposes a course only when all of its prerequisites are covered by your courses. At least one proposes a course when any one prerequisite is covered, ranked by how much of it is covered.":
    {
      en: "All proposes a course only when all of its prerequisites are covered by your courses. At least one proposes a course when any one prerequisite is covered, ranked by how much of it is covered.",
      fi: "Kaikki-tilassa ehdotetaan kurssia vain, kun kaikki sen esitiedot on katettu kursseillasi. Vähintään yksi -tilassa ehdotetaan kurssia, kun yksikin esitieto on katettu, ja kurssit järjestetään sen mukaan, kuinka suuri osa esitiedoista on katettu.",
    },
  "Completed / Selected": {
    en: "Completed / Selected",
    fi: "Suoritetut / Valitut",
  },
  "Which of your courses count as done: only the ones you marked completed, or everything you have selected.":
    {
      en: "Which of your courses count as done: only the ones you marked completed, or everything you have selected.",
      fi: "Mitkä kursseistasi lasketaan suoritetuiksi: vain ne, jotka merkitsit suoritetuiksi, vai kaikki valitsemasi.",
    },
  "Proposes only courses that are currently active. Turn it off to include inactive courses. Inactive courses you already have still count as done.":
    {
      en: "Proposes only courses that are currently active. Turn it off to include inactive courses. Inactive courses you already have still count as done.",
      fi: "Ehdottaa vain tällä hetkellä aktiivisia kursseja. Poista valinta, jos haluat mukaan myös ei-aktiiviset kurssit. Kurssit, jotka sinulla jo on, lasketaan silti suoritetuiksi.",
    },
  "Select or complete courses in any tab to get suggestions.": {
    en: "Select or complete courses in any tab to get suggestions.",
    fi: "Saat ehdotuksia, kun valitset tai merkitset kursseja suoritetuiksi missä tahansa välilehdessä.",
  },
  "basis · {basis} · empty": {
    en: "basis · {basis} · empty",
    fi: "perusta · {basis} · tyhjä",
  },
  "basis {basis}": { en: "basis {basis}", fi: "perusta {basis}" },
  "{basis} course basis": {
    en: "{basis} course basis",
    fi: "Kurssiperusta: {basis}",
  },
  "basis · {basis} · {count} courses": {
    en: "basis · {basis} · {count} courses",
    fi: "perusta · {basis} · {count} kurssia",
  },
  "basis · {basis} · {count} course": {
    en: "basis · {basis} · {count} course",
    fi: "perusta · {basis} · {count} kurssi",
  },
  "+{count} more": { en: "+{count} more", fi: "+{count} lisää" },
  "Loading course details…": {
    en: "Loading course details…",
    fi: "Ladataan kurssien tietoja…",
  },
  "{total} cr total · {count} courses": {
    en: "{total} cr total · {count} courses",
    fi: "{total} op yhteensä · {count} kurssia",
  },
  "{total} cr total · {count} course": {
    en: "{total} cr total · {count} course",
    fi: "{total} op yhteensä · {count} kurssi",
  },
  "Calculating recommendations…": {
    en: "Calculating recommendations…",
    fi: "Lasketaan suosituksia…",
  },
  "Calculating next courses…": {
    en: "Calculating next courses…",
    fi: "Lasketaan seuraavia kursseja…",
  },
  "No course matches these options.": {
    en: "No course matches these options.",
    fi: "Mikään kurssi ei vastaa näitä valintoja.",
  },
  "Recommended for you": {
    en: "Recommended for you",
    fi: "Sinulle suositellut",
  },
  "next courses · {count}": {
    en: "next courses · {count}",
    fi: "seuraavat kurssit · {count}",
  },
  "recommended for you · {count}": {
    en: "recommended for you · {count}",
    fi: "sinulle suositellut · {count}",
  },
  Required: { en: "Required", fi: "Pakolliset" },
  Similarity: { en: "Similarity", fi: "Samankaltaisuus" },
  percentages: { en: "percentages", fi: "prosentit" },
  "Required / Recommended": {
    en: "Required / Recommended",
    fi: "Pakolliset / Suositellut",
  },
  "Required and Recommended show how many of the courses in the best-matching prerequisite option of each category your basis covers. A category with no course prerequisites has no meter. The All mode lists only courses whose prerequisite requirements your basis satisfies, and it shows no meters. Official and inferred prerequisites both count. The inferred mark shows a course listed only because of inferred prerequisites.":
    {
      en: "Required and Recommended show how many of the courses in the best-matching prerequisite option of each category your basis covers. A category with no course prerequisites has no meter. The All mode lists only courses whose prerequisite requirements your basis satisfies, and it shows no meters. Official and inferred prerequisites both count. The inferred mark shows a course listed only because of inferred prerequisites.",
      fi: "Pakolliset ja Suositellut näyttävät, kuinka suuren osan kunkin luokan parhaiten täyttyvän esitietovaihtoehdon kursseista perustasi kattaa. Jos luokalla ei ole kurssiesitietoja, mittaria ei näytetä. Kaikki-tilassa on vain kursseja, joiden esitietovaatimukset perustasi täyttää, eikä mittareita näytetä. Sekä viralliset että päätellyt esitiedot lasketaan mukaan. Päätelty-merkintä kertoo, että kurssi on luettelossa vain pääteltyjen esitietojen perusteella.",
    },
  "Required and Recommended show how many of the courses in the best-matching prerequisite option of each category your basis covers. A category with no course prerequisites has no meter. The All mode lists only courses whose prerequisite requirements your basis satisfies, and it shows no meters. Only official prerequisites count.":
    {
      en: "Required and Recommended show how many of the courses in the best-matching prerequisite option of each category your basis covers. A category with no course prerequisites has no meter. The All mode lists only courses whose prerequisite requirements your basis satisfies, and it shows no meters. Only official prerequisites count.",
      fi: "Pakolliset ja Suositellut näyttävät, kuinka suuren osan kunkin luokan parhaiten täyttyvän esitietovaihtoehdon kursseista perustasi kattaa. Jos luokalla ei ole kurssiesitietoja, mittaria ei näytetä. Kaikki-tilassa on vain kursseja, joiden esitietovaatimukset perustasi täyttää, eikä mittareita näytetä. Vain viralliset esitiedot lasketaan mukaan.",
    },
  marks: { en: "marks", fi: "merkinnät" },
  "Listed only because of inferred prerequisites.": {
    en: "Listed only because of inferred prerequisites.",
    fi: "Luettelossa vain pääteltyjen esitietojen perusteella.",
  },
  "In the profile's selection, not completed.": {
    en: "In the profile's selection, not completed.",
    fi: "Profiilin valinnoissa, ei suoritettu.",
  },
  "Marked completed and also selected.": {
    en: "Marked completed and also selected.",
    fi: "Merkitty suoritetuksi ja myös valittu.",
  },
  "Similarity shows how close the course's teaching text is to your whole basis. It is a similarity score, not prerequisite coverage or official equivalence.":
    {
      en: "Similarity shows how close the course's teaching text is to your whole basis. It is a similarity score, not prerequisite coverage or official equivalence.",
      fi: "Samankaltaisuus kertoo, kuinka lähellä kurssin opetusteksti on koko perustaasi. Se on samankaltaisuusluku, ei esitietojen kattavuus eikä virallinen vastaavuus.",
    },
  "Teaching text includes derived translations": {
    en: "Teaching text includes derived translations",
    fi: "Opetusteksti sisältää johdettuja käännöksiä",
  },

  "Counts as covered": { en: "Counts as covered", fi: "Lasketaan katetuksi" },
  "Route basis": { en: "Route basis", fi: "Reitin perusta" },
  "Pick a course to open its prerequisite graph.": {
    en: "Pick a course to open its prerequisite graph.",
    fi: "Avaa esitietograafi valitsemalla kurssi.",
  },
  "Choose course": { en: "Choose course", fi: "Valitse kurssi" },
  "Loading prerequisite graph": {
    en: "Loading prerequisite graph",
    fi: "Ladataan esitietograafia",
  },
  "choose course": { en: "choose course", fi: "valitse kurssi" },
  "open →": { en: "open →", fi: "avaa →" },
  "Open prerequisite graph for {code}": {
    en: "Open prerequisite graph for {code}",
    fi: "Avaa esitietograafi kurssille {code}",
  },
  "minimum route": { en: "minimum route", fi: "lyhin reitti" },
  "Find minimum route": {
    en: "Find minimum route",
    fi: "Etsi lyhin reitti",
  },
  "Click to calculate one temporary cheapest route through your completed or selected courses. It is not saved anywhere, changing the selected course, the basis, the scope or your course sets clears it back to the normal graph, and clicking it again clears it.":
    {
      en: "Click to calculate one temporary cheapest route through your completed or selected courses. It is not saved anywhere, changing the selected course, the basis, the scope or your course sets clears it back to the normal graph, and clicking it again clears it.",
      fi: "Laskee yhden tilapäisen reitin, joka vaatii vähiten uusia opintopisteitä suoritettujen tai valittujen kurssiesi kautta. Reittiä ei tallenneta. Se poistuu, kun muutat valittua kurssia, perustaa, laajuutta tai kurssejasi, tai kun painat painiketta uudelleen.",
    },
  "Also shows recommended prerequisites, drawn apart from the required ones. They count in the minimum route while this is on.":
    {
      en: "Also shows recommended prerequisites, drawn apart from the required ones. They count in the minimum route while this is on.",
      fi: "Näyttää myös suositellut esitiedot erillään pakollisista. Ne lasketaan mukaan lyhimpään reittiin, kun asetus on valittuna.",
    },
  "Leaves inactive courses out of the graph and the route. Selected or completed inactive courses and the opened root are shown. Turn it off to include them.":
    {
      en: "Leaves inactive courses out of the graph and the route. Selected or completed inactive courses and the opened root are shown. Turn it off to include them.",
      fi: "Jättää kurssit, jotka eivät ole aktiivisia, pois graafista ja reitistä. Valitut tai suoritetut kurssit, jotka eivät ole aktiivisia, ja avattu kurssi näkyvät. Poista valinta, jos haluat ne mukaan.",
    },
  "Also shows prerequisites found by analysis rather than listed in the official data. They are marked as inferred.":
    {
      en: "Also shows prerequisites found by analysis rather than listed in the official data. They are marked as inferred.",
      fi: "Näyttää myös esitiedot, jotka analyysi on löytänyt ja joita ei ole lueteltu virallisissa tiedoissa. Ne on merkitty pääteltyiksi.",
    },
  "Which of your courses count as covered when the route is worked out: only the ones you marked completed, or everything you have selected.":
    {
      en: "Which of your courses count as covered when the route is worked out: only the ones you marked completed, or everything you have selected.",
      fi: "Mitkä kursseistasi lasketaan katetuiksi reittiä laskettaessa: vain ne, jotka merkitsit suoritetuiksi, vai kaikki valitsemasi.",
    },
  "Minimum route": { en: "Minimum route", fi: "Lyhin reitti" },
  "Calculating…": { en: "Calculating…", fi: "Lasketaan…" },
  "Clear minimum route": {
    en: "Clear minimum route",
    fi: "Tyhjennä lyhin reitti",
  },
  "cheapest route to the selected course": {
    en: "cheapest route to the selected course",
    fi: "lyhin reitti valitulle kurssille",
  },
  "click to clear": { en: "click to clear", fi: "paina tyhjentääksesi" },
  AND: { en: "AND", fi: "AND" },
  OR: { en: "OR", fi: "OR" },
  "pick {range}": { en: "pick {range}", fi: "valitse {range}" },
  "{value} cr other": {
    en: "{value} cr other",
    fi: "{value} op muuta sisältöä",
  },
  "{count} course": { en: "{count} course", fi: "{count} kurssi" },
  "{count} courses": { en: "{count} courses", fi: "{count} kurssia" },
  timeout: { en: "timeout", fi: "aikakatkaisu" },
  fulfilled: { en: "fulfilled", fi: "täyttynyt" },
  module: { en: "module", fi: "moduuli" },
  members: { en: "members", fi: "jäsenet" },
  "total · {count} course": {
    en: "total · {count} course",
    fi: "yhteensä · {count} kurssi",
  },
  "total · {count} courses": {
    en: "total · {count} courses",
    fi: "yhteensä · {count} kurssia",
  },
  "Add all module courses to structure": {
    en: "Add all module courses to structure",
    fi: "Lisää kaikki moduulin kurssit rakenteeseen",
  },
  "Exact minimum route": {
    en: "Exact minimum route",
    fi: "Tarkka lyhin reitti",
  },
  "Approximate route": { en: "Approximate route", fi: "Likimääräinen reitti" },
  "No route found": { en: "No route found", fi: "Reittiä ei löytynyt" },
  "Route unresolved": {
    en: "Route unresolved",
    fi: "Reittiä ei voi selvittää",
  },
  "No route exists": { en: "No route exists", fi: "Reittiä ei ole" },
  Shortfall: { en: "Shortfall", fi: "Vajaus" },
  exact: { en: "exact", fi: "tarkka" },
  approximate: { en: "approximate", fi: "likimääräinen" },
  unresolved: { en: "unresolved", fi: "selvittämätön" },
  shortfall: { en: "shortfall", fi: "vajaus" },
  "no solution": { en: "no solution", fi: "ei ratkaisua" },
  "{new} new · {full} full route": {
    en: "{new} new · {full} full route",
    fi: "{new} uutta · reitillä yhteensä {full}",
  },
  "Not guaranteed to be the minimum.": {
    en: "Not guaranteed to be the minimum.",
    fi: "Ei ole taatusti lyhin reitti.",
  },
  "The exact search was too large and the approximation gave up. No route or total is available.":
    {
      en: "The exact search was too large and the approximation gave up. No route or total is available.",
      fi: "Tarkka haku oli liian suuri, eikä likimääräinen haku onnistunut. Reittiä tai kokonaismäärää ei ole saatavilla.",
    },
  "No route meets every requirement. Blocked requirements:": {
    en: "No route meets every requirement. Blocked requirements:",
    fi: "Mikään reitti ei täytä kaikkia vaatimuksia. Estetyt vaatimukset:",
  },
  "Some requirements cannot be resolved:": {
    en: "Some requirements cannot be resolved:",
    fi: "Joitakin vaatimuksia ei voi selvittää:",
  },
  "A module rule is only partly met with active courses:": {
    en: "A module rule is only partly met with active courses:",
    fi: "Moduulin sääntö täyttyy vain osittain aktiivisilla kursseilla:",
  },
  "Nothing new": { en: "Nothing new", fi: "Ei uusia kursseja" },
  "Add all missing courses to structure": {
    en: "Add all missing courses to structure",
    fi: "Lisää kaikki puuttuvat kurssit rakenteeseen",
  },
  "{achieved} of {required} courses": {
    en: "{achieved} of {required} courses",
    fi: "{achieved}/{required} kurssia",
  },
  "{achieved} of {required} cr": {
    en: "{achieved} of {required} cr",
    fi: "{achieved}/{required} op",
  },
  "This prerequisite tree is too large to draw.": {
    en: "This prerequisite tree is too large to draw.",
    fi: "Tämä esitietopuu on liian suuri piirrettäväksi.",
  },
  "{elements} elements, limit {limit}.": {
    en: "{elements} elements, limit {limit}.",
    fi: "{elements} elementtiä, raja {limit}.",
  },
  "Tip: turn off Recommended or Inferred, or turn on Active only, to shrink the graph.":
    {
      en: "Tip: turn off Recommended or Inferred, or turn on Active only, to shrink the graph.",
      fi: "Vinkki: pienennä graafia poistamalla Suositellut tai Päätelty käytöstä tai ottamalla Vain aktiiviset käyttöön.",
    },
  "Tip: turn off Recommended, or turn on Active only, to shrink the graph.": {
    en: "Tip: turn off Recommended, or turn on Active only, to shrink the graph.",
    fi: "Vinkki: poista Suositellut käytöstä tai ota Vain aktiiviset käyttöön, niin graafi pienenee.",
  },

  "Add programme": { en: "Add programme", fi: "Lisää ohjelma" },
  "Replace programme": { en: "Replace programme", fi: "Vaihda ohjelma" },
  "Reset programme": { en: "Reset programme", fi: "Nollaa ohjelma" },
  "Delete programme": { en: "Delete programme", fi: "Poista ohjelma" },
  "Choose programme": { en: "Choose programme", fi: "Valitse ohjelma" },
  "Programme actions for {name}": {
    en: "Programme actions for {name}",
    fi: "Ohjelman toiminnot: {name}",
  },
  "Replace programme “{name}”?": {
    en: "Replace programme “{name}”?",
    fi: "Vaihdetaanko ohjelma ”{name}”?",
  },
  "Reset programme “{name}”?": {
    en: "Reset programme “{name}”?",
    fi: "Nollataanko ohjelma ”{name}”?",
  },
  "This replaces this programme with “{name}”.": {
    en: "This replaces this programme with “{name}”.",
    fi: "Tämä korvaa tämän ohjelman ohjelmalla ”{name}”.",
  },
  "{name} is already in {place} and moves here with its contents.": {
    en: "{name} is already in {place} and moves here with its contents.",
    fi: "{name} on jo toisessa paikassa: {place}, ja se siirtyy tänne sisältöineen.",
  },
  "This discards the replaced programme's customisation and removes its uncompleted courses.":
    {
      en: "This discards the replaced programme's customisation and removes its uncompleted courses.",
      fi: "Tämä poistaa korvatun ohjelman mukautukset ja suorittamattomat kurssit.",
    },
  "This discards the replaced programme's customisation, removes its uncompleted courses and keeps its completed courses.":
    {
      en: "This discards the replaced programme's customisation, removes its uncompleted courses and keeps its completed courses.",
      fi: "Tämä poistaa korvatun ohjelman mukautukset ja suorittamattomat kurssit sekä säilyttää sen suoritetut kurssit.",
    },
  "Programme is unavailable": {
    en: "Programme is unavailable",
    fi: "Ohjelma ei ole käytettävissä",
  },
  "Programme is already added": {
    en: "Programme is already added",
    fi: "Ohjelma on jo lisätty",
  },
  "Loading structure": { en: "Loading structure", fi: "Ladataan rakennetta" },
  "Loading structure content": {
    en: "Loading structure content",
    fi: "Ladataan rakenteen sisältöä",
  },
  "all required": { en: "all required", fi: "kaikki pakolliset" },
  "choose {count}": { en: "choose {count}", fi: "valitse {count}" },
  "choose {min}–{max}": { en: "choose {min}–{max}", fi: "valitse {min}–{max}" },
  "choose at least {count}": {
    en: "choose at least {count}",
    fi: "valitse vähintään {count}",
  },
  "choose up to {count}": {
    en: "choose up to {count}",
    fi: "valitse enintään {count}",
  },
  "any course": { en: "any course", fi: "mikä tahansa kurssi" },
  "any module": { en: "any module", fi: "mikä tahansa moduuli" },
  required: { en: "required", fi: "pakollinen" },
  "any cr": { en: "any cr", fi: "mikä tahansa määrä op" },
  "min {value} cr": { en: "min {value} cr", fi: "vähintään {value} op" },
  "up to {value} cr": { en: "up to {value} cr", fi: "enintään {value} op" },
  "{min}–{max} cr": { en: "{min}–{max} cr", fi: "{min}–{max} op" },
  "any courses": { en: "any courses", fi: "mikä tahansa määrä kursseja" },
  "min {value} courses": {
    en: "min {value} courses",
    fi: "vähintään {value} kurssia",
  },
  "min 1 course": { en: "min 1 course", fi: "vähintään 1 kurssi" },
  "up to 1 course": { en: "up to 1 course", fi: "enintään 1 kurssi" },
  "up to {value} courses": {
    en: "up to {value} courses",
    fi: "enintään {value} kurssia",
  },
  "{min}–{max} courses": {
    en: "{min}–{max} courses",
    fi: "{min}–{max} kurssia",
  },
  "Courses to choose from: {count}": {
    en: "Courses to choose from: {count}",
    fi: "Valittavia kursseja: {count}",
  },
  "Modules to choose from: {count}": {
    en: "Modules to choose from: {count}",
    fi: "Valittavia moduuleja: {count}",
  },
  "Programmes to choose from: {count}": {
    en: "Programmes to choose from: {count}",
    fi: "Valittavia ohjelmia: {count}",
  },
  "Options to choose from: {count}": {
    en: "Options to choose from: {count}",
    fi: "Valittavia vaihtoehtoja: {count}",
  },
  modules: { en: "modules", fi: "moduulit" },
  "Unplaced studies": {
    en: "Unplaced studies",
    fi: "Sijoittamattomat opinnot",
  },
  "any studies": { en: "any studies", fi: "mitkä tahansa opinnot" },
  "Nothing here yet.": {
    en: "Nothing here yet.",
    fi: "Täällä ei ole vielä mitään.",
  },
  programme: { en: "programme", fi: "tutkinto-ohjelma" },
  choice: { en: "choice", fi: "valinta" },
  group: { en: "group", fi: "ryhmä" },
  unplaced: { en: "unplaced", fi: "sijoittamaton" },
  "Delete programme “{name}”?": {
    en: "Delete programme “{name}”?",
    fi: "Poistetaanko ohjelma ”{name}”?",
  },
  "Delete module “{name}”?": {
    en: "Delete module “{name}”?",
    fi: "Poistetaanko moduuli ”{name}”?",
  },
  "This removes this module from the structure. Keep completed courses under Unplaced studies, or remove them with their completions.":
    {
      en: "This removes this module from the structure. Keep completed courses under Unplaced studies, or remove them with their completions.",
      fi: "Tämä poistaa moduulin rakenteesta. Säilytä suoritetut kurssit sijoittamattomissa opinnoissa tai poista ne suoritusmerkintöineen.",
    },
  "This removes this programme from the structure. Keep completed courses under Unplaced studies, or remove them with their completions.":
    {
      en: "This removes this programme from the structure. Keep completed courses under Unplaced studies, or remove them with their completions.",
      fi: "Tämä poistaa ohjelman rakenteesta. Säilytä suoritetut kurssit sijoittamattomissa opinnoissa tai poista ne suoritusmerkintöineen.",
    },
  "This removes this programme from the structure.": {
    en: "This removes this programme from the structure.",
    fi: "Tämä poistaa ohjelman rakenteesta.",
  },
  "This removes this module from the structure.": {
    en: "This removes this module from the structure.",
    fi: "Tämä poistaa moduulin rakenteesta.",
  },
  "Delete all": { en: "Delete all", fi: "Poista kaikki" },
  "Reset all": { en: "Reset all", fi: "Nollaa kaikki" },
  "Reset this module": { en: "Reset this module", fi: "Nollaa tämä moduuli" },
  "Reset module “{name}”?": {
    en: "Reset module “{name}”?",
    fi: "Nollataanko moduuli ”{name}”?",
  },
  "This restores this programme's official content.": {
    en: "This restores this programme's official content.",
    fi: "Tämä palauttaa ohjelman virallisen sisällön.",
  },
  "This restores this programme's official content. Keep completed courses, or clear their completions too.":
    {
      en: "This restores this programme's official content. Keep completed courses, or clear their completions too.",
      fi: "Tämä palauttaa ohjelman virallisen sisällön. Säilytä suoritetut kurssit tai poista myös niiden suoritusmerkinnät.",
    },
  "This restores this module's official content.": {
    en: "This restores this module's official content.",
    fi: "Tämä palauttaa moduulin virallisen sisällön.",
  },
  "This restores this module's official content. Keep completed courses, or clear their completions too.":
    {
      en: "This restores this module's official content. Keep completed courses, or clear their completions too.",
      fi: "Tämä palauttaa moduulin virallisen sisällön. Säilytä suoritetut kurssit tai poista myös niiden suoritusmerkinnät.",
    },
  "No option selected yet.": {
    en: "No option selected yet.",
    fi: "Valintaa ei ole vielä tehty.",
  },
  "This module is empty.": {
    en: "This module is empty.",
    fi: "Tämä moduuli on tyhjä.",
  },
  "This programme is empty.": {
    en: "This programme is empty.",
    fi: "Tämä ohjelma on tyhjä.",
  },
  "Close drawer": { en: "Close drawer", fi: "Sulje paneeli" },
  "Add a course, module or programme": {
    en: "Add a course, module or programme",
    fi: "Lisää kurssi, moduuli tai ohjelma",
  },
  Courses: { en: "Courses", fi: "Kurssit" },
  Modules: { en: "Modules", fi: "Moduulit" },
  Programmes: { en: "Programmes", fi: "Tutkinto-ohjelmat" },
  "Type to search courses, modules and programmes.": {
    en: "Type to search courses, modules and programmes.",
    fi: "Hae kursseja, moduuleja ja tutkinto-ohjelmia kirjoittamalla.",
  },
  "Loading modules": { en: "Loading modules", fi: "Ladataan moduuleja" },
  programmes: { en: "programmes", fi: "tutkinto-ohjelmat" },
  "No matches.": { en: "No matches.", fi: "Ei osumia." },
  "adding…": { en: "adding…", fi: "lisätään…" },
  "{count} items": { en: "{count} items", fi: "{count} kohdetta" },
  "Filter programmes and modules by name or code": {
    en: "Filter programmes and modules by name or code",
    fi: "Rajaa tutkinto-ohjelmia ja moduuleja nimen tai koodin mukaan",
  },
  "Loading programmes and modules": {
    en: "Loading programmes and modules",
    fi: "Ladataan tutkinto-ohjelmia ja moduuleja",
  },
  "opening…": { en: "opening…", fi: "avataan…" },
  "No programmes or modules match this search.": {
    en: "No programmes or modules match this search.",
    fi: "Mikään tutkinto-ohjelma tai moduuli ei vastaa tätä hakua.",
  },
  "Type to search programmes and modules by name or code.": {
    en: "Type to search programmes and modules by name or code.",
    fi: "Hae tutkinto-ohjelmia ja moduuleja kirjoittamalla nimi tai koodi.",
  },
  "Completed course": { en: "Completed course", fi: "Suoritettu kurssi" },
  "This moves {code} to Unplaced studies and keeps its completion, or removes it from your selection together with its completion.":
    {
      en: "This moves {code} to Unplaced studies and keeps its completion, or removes it from your selection together with its completion.",
      fi: "Tämä siirtää kurssin {code} sijoittamattomiin opintoihin ja säilyttää sen suoritusmerkinnän, tai poistaa sen valinnoistasi suoritusmerkintöineen.",
    },
  "This removes {code} from your selection together with its completion.": {
    en: "This removes {code} from your selection together with its completion.",
    fi: "Tämä poistaa kurssin {code} valinnoistasi suoritusmerkintöineen.",
  },
  "Move here?": { en: "Move here?", fi: "Siirretäänkö tänne?" },
  "the programme list": { en: "the programme list", fi: "ohjelmaluettelo" },
  "{name} is already in {place}. Move it here?": {
    en: "{name} is already in {place}. Move it here?",
    fi: "{name} on jo toisessa paikassa: {place}. Siirretäänkö se tänne?",
  },
  "Move this course into {name}?": {
    en: "Move this course into {name}?",
    fi: "Siirretäänkö tämä kurssi kohteeseen {name}?",
  },
  "Move these courses into {name}?": {
    en: "Move these courses into {name}?",
    fi: "Siirretäänkö nämä kurssit kohteeseen {name}?",
  },
  "Move them here, or keep them where they are now.": {
    en: "Move them here, or keep them where they are now.",
    fi: "Siirrä ne tänne tai säilytä ne nykyisillä paikoillaan.",
  },
  "{course} · {place}": { en: "{course} · {place}", fi: "{course} · {place}" },
  "Selection changed: completed courses kept, other courses dropped": {
    en: "Selection changed: completed courses kept, other courses dropped",
    fi: "Valinta muutettu: suoritetut kurssit säilytetty, muut poistettu",
  },
  "Selection made": { en: "Selection made", fi: "Valinta tehty" },
  "Already in this module": {
    en: "Already in this module",
    fi: "Jo tässä moduulissa",
  },
  "Already in this programme": {
    en: "Already in this programme",
    fi: "Jo tässä ohjelmassa",
  },
  "Added {name}": { en: "Added {name}", fi: "Lisätty {name}" },
  "{count} course moved here": {
    en: "{count} course moved here",
    fi: "{count} kurssi siirrettiin tänne",
  },
  "{count} courses moved here": {
    en: "{count} courses moved here",
    fi: "{count} kurssia siirrettiin tänne",
  },
  "Unplaced studies reset": {
    en: "Unplaced studies reset",
    fi: "Sijoittamattomat opinnot nollattu",
  },
  "Module reset to its official contents": {
    en: "Module reset to its official contents",
    fi: "Moduuli palautettu viralliseen sisältöönsä",
  },
  "Programme reset to its official contents": {
    en: "Programme reset to its official contents",
    fi: "Ohjelma palautettu viralliseen sisältöönsä",
  },
  Choice: { en: "Choice", fi: "Valinta" },

  Profiles: { en: "Profiles", fi: "Profiilit" },
  "New profile": { en: "New profile", fi: "Uusi profiili" },
  Name: { en: "Name", fi: "Nimi" },
  "{selected} selected · {completed} completed": {
    en: "{selected} selected · {completed} completed",
    fi: "valittu: {selected} · suoritettu: {completed}",
  },
  "Rename {name}": { en: "Rename {name}", fi: "Nimeä {name} uudelleen" },
  "Delete {name}": { en: "Delete {name}", fi: "Poista {name}" },
  "Rename profile": { en: "Rename profile", fi: "Nimeä profiili uudelleen" },
  "Profile name": { en: "Profile name", fi: "Profiilin nimi" },
  "Delete profile “{name}”?": {
    en: "Delete profile “{name}”?",
    fi: "Poistetaanko profiili ”{name}”?",
  },
  "This is your current profile. The first remaining profile will be selected instead.":
    {
      en: "This is your current profile. The first remaining profile will be selected instead.",
      fi: "Tämä on nykyinen profiilisi. Ensimmäinen jäljellä oleva profiili valitaan sen sijaan.",
    },
  Export: { en: "Export", fi: "Vie" },
  Import: { en: "Import", fi: "Tuo" },
  "All saved data": { en: "All saved data", fi: "Kaikki tallennetut tiedot" },
  "Choose file": { en: "Choose file", fi: "Valitse tiedosto" },
  "Replace all saved data?": {
    en: "Replace all saved data?",
    fi: "Korvataanko kaikki tallennetut tiedot?",
  },
  "Import profile “{name}”?": {
    en: "Import profile “{name}”?",
    fi: "Tuodaanko profiili ”{name}”?",
  },
  "This creates a new profile named “{name}” and makes it current.": {
    en: "This creates a new profile named “{name}” and makes it current.",
    fi: "Tämä luo uuden profiilin nimeltä ”{name}” ja ottaa sen käyttöön.",
  },
  "This replaces every profile in this browser with the imported saved data.": {
    en: "This replaces every profile in this browser with the imported saved data.",
    fi: "Tämä korvaa kaikki tämän selaimen profiilit tuoduilla tiedoilla.",
  },
  "Invalid import file": {
    en: "Invalid import file",
    fi: "Virheellinen tuontitiedosto",
  },
  "Unsupported file type": {
    en: "Unsupported file type",
    fi: "Tiedostotyyppiä ei tueta",
  },
  "Choose one file": {
    en: "Choose one file",
    fi: "Valitse yksi tiedosto",
  },
  "There is no saved data to export": {
    en: "There is no saved data to export",
    fi: "Ei tallennettuja tietoja vietäväksi",
  },
  "Copy Sisu import script": {
    en: "Copy Sisu import script",
    fi: "Kopioi Sisu-tuontiskripti",
  },
  "Sisu import script copied": {
    en: "Sisu import script copied",
    fi: "Sisu-tuontiskripti kopioitu",
  },
  "Could not copy Sisu import script": {
    en: "Could not copy Sisu import script",
    fi: "Sisu-tuontiskriptin kopiointi ei onnistunut",
  },
  "Invalid Sisu plan file": {
    en: "Invalid Sisu plan file",
    fi: "Virheellinen Sisu-suunnitelmatiedosto",
  },
  "Sisu choice is ambiguous": {
    en: "Sisu choice is ambiguous",
    fi: "Sisu-valinta on epäselvä",
  },
  "Import Sisu plan": {
    en: "Import Sisu plan",
    fi: "Tuo Sisu-suunnitelma",
  },
  "Sisu plan": { en: "Sisu plan", fi: "Sisu-suunnitelma" },
  "or drop a .json file": {
    en: "or drop a .json file",
    fi: "tai raahaa tiedosto tähän",
  },
  "This creates a new profile with these programmes: {names}.": {
    en: "This creates a new profile with these programmes: {names}.",
    fi: "Tämä luo uuden profiilin, jossa on nämä ohjelmat: {names}.",
  },
  "Left out of the import:": {
    en: "Left out of the import:",
    fi: "Tuonnista jäi pois:",
  },
  "The import skipped some items": {
    en: "The import skipped some items",
    fi: "Tuonnissa jätettiin pois joitakin kohteita",
  },
  "Sisu data did not identify this item uniquely, so it was left out.": {
    en: "Sisu data did not identify this item uniquely, so it was left out.",
    fi: "Tätä kohdetta ei voitu yksilöidä Sisun tiedoista, joten se jätettiin pois.",
  },
  "The catalogue has no structure for this module, so it was left out. Its courses that are in the catalogue are in Unplaced studies.":
    {
      en: "The catalogue has no structure for this module, so it was left out. Its courses that are in the catalogue are in Unplaced studies.",
      fi: "Tämän moduulin rakennetta ei ole oppaassa, joten moduuli jätettiin pois. Sen kurssit, jotka löytyvät oppaasta, ovat sijoittamattomissa opinnoissa.",
    },
  "This course is not in the catalogue, so it was left out together with its completion.":
    {
      en: "This course is not in the catalogue, so it was left out together with its completion.",
      fi: "Tätä kurssia ei ole oppaassa, joten se jätettiin pois suoritusmerkintöineen.",
    },
  "Export any listed profile or all saved data as one file. Select an entry to download it.":
    {
      en: "Export any listed profile or all saved data as one file. Select an entry to download it.",
      fi: "Vie mikä tahansa luetelluista profiileista tai kaikki tallennetut tiedot yhtenä tiedostona. Lataa tiedosto valitsemalla kohde.",
    },
  "Import a profile, all saved data or a Sisu plan from a .json file. A profile becomes a new profile, all saved data replaces everything after you confirm, and a Sisu plan becomes a new profile whose choices are placed when Structure of studies first loads the programmes.":
    {
      en: "Import a profile, all saved data or a Sisu plan from a .json file. A profile becomes a new profile, all saved data replaces everything after you confirm, and a Sisu plan becomes a new profile whose choices are placed when Structure of studies first loads the programmes.",
      fi: "Tuo profiili, kaikki tallennetut tiedot tai Sisu-suunnitelma .json-tiedostosta. Profiilista tulee uusi profiili, tallennetut tiedot korvaavat kaiken vahvistuksen jälkeen ja Sisu-suunnitelmasta tulee uusi profiili, jonka valinnat sijoitetaan, kun Opintojen rakenne lataa ohjelmat ensimmäisen kerran.",
    },
  "Import a Sisu plan: expand every module in Sisu, review the copied script and run it in Sisu's browser console, then import the downloaded sisu-plan-capture.json here under a new profile name. The script reads the open Sisu page and the public Kori interface anonymously. The downloaded file stays in this browser.":
    {
      en: "Import a Sisu plan: expand every module in Sisu, review the copied script and run it in Sisu's browser console, then import the downloaded sisu-plan-capture.json here under a new profile name. The script reads the open Sisu page and the public Kori interface anonymously. The downloaded file stays in this browser.",
      fi: "Sisu-suunnitelman tuonti: laajenna kaikki moduulit Sisussa, tarkista kopioitu skripti ja suorita se Sisun selainkonsolissa. Tuo ladattu sisu-plan-capture.json tähän uudella profiilinimellä. Skripti lukee avoinna olevan Sisu-sivun ja julkisen Kori-rajapinnan tiedot anonyymisti. Ladattu tiedosto pysyy tässä selaimessa.",
    },

  "Course not in the catalogue": {
    en: "Course not in the catalogue",
    fi: "Kurssi ei ole oppaassa",
  },
  "Module not found": { en: "Module not found", fi: "Moduulia ei löytynyt" },
  "No current version of this module": {
    en: "No current version of this module",
    fi: "Tästä moduulista ei ole nykyistä versiota",
  },
  "Several current versions of this module": {
    en: "Several current versions of this module",
    fi: "Tästä moduulista on useita nykyisiä versioita",
  },
  "This module has no rule": {
    en: "This module has no rule",
    fi: "Tällä moduulilla ei ole sääntöä",
  },
  "Module reference cycle": {
    en: "Module reference cycle",
    fi: "Moduuliviittausten silmukka",
  },
  "Course is missing": { en: "Course is missing", fi: "Kurssi puuttuu" },
  "Module is missing": { en: "Module is missing", fi: "Moduuli puuttuu" },
  "Several current module versions": {
    en: "Several current module versions",
    fi: "Useita nykyisiä moduuliversioita",
  },
  "Malformed rule": { en: "Malformed rule", fi: "Virheellinen sääntö" },
  "Course reference cycle": {
    en: "Course reference cycle",
    fi: "Kurssiviittausten silmukka",
  },
  "Unknown course count": {
    en: "Unknown course count",
    fi: "Tuntematon kurssimäärä",
  },
  "Unknown credit extent": {
    en: "Unknown credit extent",
    fi: "Tuntematon opintopistemäärä",
  },
  "Blocked by an excluded course": {
    en: "Blocked by an excluded course",
    fi: "Estetty poissuljetun kurssin takia",
  },
  "Inactive course": { en: "Inactive course", fi: "Ei-aktiivinen kurssi" },
  "Not enough active courses": {
    en: "Not enough active courses",
    fi: "Ei tarpeeksi aktiivisia kursseja",
  },
  "Too few positions": { en: "Too few positions", fi: "Liian vähän paikkoja" },
  "Unreachable bound": { en: "Unreachable bound", fi: "Saavuttamaton raja" },
  "Search too large": { en: "Search too large", fi: "Haku liian suuri" },
  "Content could not be expanded": {
    en: "Content could not be expanded",
    fi: "Sisältöä ei voitu laajentaa",
  },
  "Free-choice content": {
    en: "Free-choice content",
    fi: "Vapaavalintainen sisältö",
  },
  "Empty option": { en: "Empty option", fi: "Tyhjä vaihtoehto" },
  "Missing module alternative": {
    en: "Missing module alternative",
    fi: "Puuttuva moduulivaihtoehto",
  },
  "Substitution course is missing": {
    en: "Substitution course is missing",
    fi: "Korvaava kurssi puuttuu",
  },
  "All-mandatory bounds": {
    en: "All-mandatory bounds",
    fi: "Pakollisten kurssien rajat",
  },
  "Module version fallback": {
    en: "Module version fallback",
    fi: "Moduuliversio valittu varavaihtoehtona",
  },
  "Unresolved requirement": {
    en: "Unresolved requirement",
    fi: "Selvittämätön vaatimus",
  },

  "Invalid request": { en: "Invalid request", fi: "Virheellinen pyyntö" },
  "Request failed ({status})": {
    en: "Request failed ({status})",
    fi: "Pyyntö epäonnistui ({status})",
  },
  "Operation failed": { en: "Operation failed", fi: "Toiminto epäonnistui" },
  "Current browser profile is unavailable": {
    en: "Current browser profile is unavailable",
    fi: "Nykyinen selainprofiili ei ole käytettävissä",
  },
  "Browser profile is unavailable": {
    en: "Browser profile is unavailable",
    fi: "Selainprofiili ei ole käytettävissä",
  },
  "Profile name cannot be empty": {
    en: "Profile name cannot be empty",
    fi: "Profiilin nimi ei voi olla tyhjä",
  },
  "A profile with that name already exists": {
    en: "A profile with that name already exists",
    fi: "Samanniminen profiili on jo olemassa",
  },
  "The last browser profile cannot be deleted": {
    en: "The last browser profile cannot be deleted",
    fi: "Viimeistä selainprofiilia ei voi poistaa",
  },
  "Browser store provider is missing": {
    en: "Browser store provider is missing",
    fi: "Selaimen tallennustila puuttuu",
  },
  "Search session provider is missing": {
    en: "Search session provider is missing",
    fi: "Haun istunto puuttuu",
  },
  "Saved browser state is invalid": {
    en: "Saved browser state is invalid",
    fi: "Tallennettu selaintila on virheellinen",
  },
  "Unsupported saved browser state schema": {
    en: "Unsupported saved browser state schema",
    fi: "Tallennetun selaintilan versiota ei tueta",
  },
  "Saved browser state has no current profile": {
    en: "Saved browser state has no current profile",
    fi: "Tallennetussa selaintilassa ei ole nykyistä profiilia",
  },
  "Saved browser profile is invalid": {
    en: "Saved browser profile is invalid",
    fi: "Tallennettu selainprofiili on virheellinen",
  },
  "Saved browser profile state is invalid": {
    en: "Saved browser profile state is invalid",
    fi: "Tallennettu selainprofiilin tila on virheellinen",
  },
  "Saved browser profile slice search is invalid": {
    en: "Saved browser profile slice search is invalid",
    fi: "Tallennetun selainprofiilin hakuosio on virheellinen",
  },
  "Saved browser profile slice compare is invalid": {
    en: "Saved browser profile slice compare is invalid",
    fi: "Tallennetun selainprofiilin vertailuosio on virheellinen",
  },
  "Saved browser profile slice prerequisites is invalid": {
    en: "Saved browser profile slice prerequisites is invalid",
    fi: "Tallennetun selainprofiilin esitieto-osio on virheellinen",
  },
  "Saved browser profile slice discover is invalid": {
    en: "Saved browser profile slice discover is invalid",
    fi: "Tallennetun selainprofiilin ehdotusten osio on virheellinen",
  },
  "Saved browser profile slice structure is invalid": {
    en: "Saved browser profile slice structure is invalid",
    fi: "Tallennetun selainprofiilin opintojen rakenteen osio on virheellinen",
  },
  "A module cannot be added inside itself": {
    en: "A module cannot be added inside itself",
    fi: "Moduulia ei voi lisätä itsensä sisään",
  },
  "Structure programmes changed while adding a module": {
    en: "Structure programmes changed while adding a module",
    fi: "Rakenteen ohjelmat muuttuivat moduulia lisättäessä",
  },
  "Structure moves changed while confirming a module": {
    en: "Structure moves changed while confirming a module",
    fi: "Rakenteen siirrot muuttuivat moduulin vahvistamisen aikana",
  },
  "Structure target is unavailable": {
    en: "Structure target is unavailable",
    fi: "Rakenteen kohde ei ole käytettävissä",
  },
  "Unsupported structure rule type": {
    en: "Unsupported structure rule type",
    fi: "Rakenteen sääntötyyppiä ei tueta",
  },
  "Structure rule entry is missing its source origin": {
    en: "Structure rule entry is missing its source origin",
    fi: "Rakenteen sääntökohdalta puuttuu lähde",
  },
  "Missing placed course summary": {
    en: "Missing placed course summary",
    fi: "Sijoitetun kurssin yhteenveto puuttuu",
  },
  "Missing placed module report": {
    en: "Missing placed module report",
    fi: "Sijoitetun moduulin raportti puuttuu",
  },
  "Placed module is missing from the resolved structure": {
    en: "Placed module is missing from the resolved structure",
    fi: "Sijoitettu moduuli puuttuu selvitetystä rakenteesta",
  },
  "Requested course summary is missing": {
    en: "Requested course summary is missing",
    fi: "Pyydetty kurssin yhteenveto puuttuu",
  },
} as const;

export type UiTextKey = keyof typeof UI_TEXT;

/**
 * Select the exact language entry and substitute named `{placeholder}` values.
 * A placeholder with no supplied value fails instead of fabricating fallback text.
 */
export function uiText(
  language: DisplayLanguage,
  key: UiTextKey,
  values?: Readonly<Record<string, string | number>>,
): string {
  const entry = UI_TEXT[key];
  if (!entry) throw new Error(`Unknown wording key: ${String(key)}`);
  return entry[language].replace(/\{(\w+)\}/g, (_match, name: string) => {
    const value = values?.[name];
    if (value === undefined)
      throw new Error(`Missing wording value for ${name} in ${String(key)}`);
    return String(value);
  });
}

const SEARCH_METHOD_KEYS: Record<SearchMethod, UiTextKey> = {
  exact_code: "Exact code",
  substring: "Substring",
  fuzzy_name: "Fuzzy search",
  semantic: "Semantic",
};

export function searchMethodLabel(
  method: SearchMethod,
  language: DisplayLanguage,
): string {
  return uiText(language, SEARCH_METHOD_KEYS[method]);
}

/**
 * Backend/graph reason and kind tokens, including the Structure unresolved values and
 * the ignored-part vocabulary. An unknown token is shown in its raw form, visibly identified.
 */
const REASON_KEYS: Record<string, UiTextKey> = {
  course_not_represented: "Course not in the catalogue",
  module_not_found: "Module not found",
  no_current_version: "No current version of this module",
  ambiguous_version: "Several current versions of this module",
  missing_rule: "This module has no rule",
  module_cycle: "Module reference cycle",
  missing_course: "Course is missing",
  missing_module: "Module is missing",
  ambiguous_module_version: "Several current module versions",
  malformed_rule: "Malformed rule",
  course_cycle: "Course reference cycle",
  unknown_course_count: "Unknown course count",
  unknown_credit_extent: "Unknown credit extent",
  excluded_node: "Blocked by an excluded course",
  inactive_course: "Inactive course",
  activity_shortfall: "Not enough active courses",
  too_few_positions: "Too few positions",
  unreachable_bound: "Unreachable bound",
  search_too_large: "Search too large",
  unexpandable_content: "Content could not be expanded",
  free_choice: "Free-choice content",
  empty_option: "Empty option",
  missing_module_alternative: "Missing module alternative",
  missing_substitution_course: "Substitution course is missing",
  all_mandatory_bounds: "All-mandatory bounds",
  module_version_fallback: "Module version fallback",
  unresolved: "Unresolved requirement",
};

/** Localize a reason/kind token. An unknown token is visible in raw form. */
export function reasonText(reason: string, language: DisplayLanguage): string {
  const key = REASON_KEYS[reason];
  return key
    ? uiText(language, key)
    : uiText(language, "Unknown reason ({reason})", { reason });
}

/**
 * Localized reason plus any unstructured detail, preserved verbatim under a translated
 * "Original technical detail" label. Free-form detail is diagnostic data shown as supplied.
 */
export function diagnosticText(
  reason: string,
  detail: string | null,
  language: DisplayLanguage,
): string {
  const base = reasonText(reason, language);
  return detail === null
    ? base
    : `${base} — ${uiText(language, "Original technical detail")}: ${detail}`;
}
