/**
 * The interface wording of every app-authored string in English and Finnish.
 *
 * Each entry is keyed by its English literal and holds both translations. A context suffix such as
 * `Completed (basis)` gives one English word a second Finnish form. A template keeps its
 * placeholders by name. The module imports only types.
 */
import type { SearchMethod } from "../api/types";
import type { DisplayLanguage } from "../state/types";

/** Every app-authored interface string in Finnish and English, keyed by its English source. */
const UI_TEXT = {
  "course-explorer": { en: "course-explorer", fi: "course-explorer" },
  tuni: { en: "tuni", fi: "tuni" },
  Search: { en: "Search", fi: "Haku" },
  Compare: { en: "Compare", fi: "Vertailu" },
  Prerequisites: { en: "Prerequisites", fi: "Esitiedot" },
  Discover: { en: "Discover", fi: "Ehdotukset" },
  "Structure of studies": {
    en: "Structure of studies",
    fi: "Opintojen rakenne",
  },
  Prereqs: { en: "Prereqs", fi: "Esitiedot" },
  Structure: { en: "Structure", fi: "Rakenne" },
  "Discover (phone)": { en: "Discover", fi: "Ehdotukset" },
  Docs: { en: "Docs", fi: "Ohjeet" },
  Feedback: { en: "Feedback", fi: "Palaute" },
  "Return to app": { en: "Return to app", fi: "Takaisin sovellukseen" },
  "Main navigation": { en: "Main navigation", fi: "Päävalikko" },
  "Loading feedback form…": {
    en: "Loading feedback form…",
    fi: "Ladataan palautelomaketta…",
  },
  "Could not load feedback form. Reload the page to try again.": {
    en: "Could not load feedback form. Reload the page to try again.",
    fi: "Palautelomakkeen lataus epäonnistui. Yritä uudelleen lataamalla sivu.",
  },
  "Submit feedback": { en: "Submit feedback", fi: "Lähetä palaute" },
  "Submitting feedback…": {
    en: "Submitting feedback…",
    fi: "Palautetta lähetetään…",
  },
  "Choose images": { en: "Choose images", fi: "Valitse kuvat" },
  "or drop images here": {
    en: "or drop images here",
    fi: "tai pudota kuvat tähän",
  },
  "Remove {name}": { en: "Remove {name}", fi: "Poista {name}" },
  "Answer this required question.": {
    en: "Answer this required question.",
    fi: "Vastaa tähän pakolliseen kysymykseen.",
  },
  "Add an image for this required question.": {
    en: "Add an image for this required question.",
    fi: "Lisää kuva tähän pakolliseen kysymykseen.",
  },
  "The answer is too long. Maximum length: {limit} characters.": {
    en: "The answer is too long. Maximum length: {limit} characters.",
    fi: "Vastaus on liian pitkä. Enimmäispituus: {limit} merkkiä.",
  },
  "Too many images for {field}. Limit: {limit}.": {
    en: "Too many images for {field}. Limit: {limit}.",
    fi: "{field}: liian monta kuvaa. Enimmäismäärä: {limit}.",
  },
  "An image for {field} exceeds the size limit of {limit} bytes.": {
    en: "An image for {field} exceeds the size limit of {limit} bytes.",
    fi: "{field}: kuva ylittää kokorajoituksen {limit} tavua.",
  },
  "Choose a PNG or JPEG image for {field}.": {
    en: "Choose a PNG or JPEG image for {field}.",
    fi: "{field}: valitse PNG- tai JPEG-kuva.",
  },
  "Feedback is too large. Remove images or shorten the answers.": {
    en: "Feedback is too large. Remove images or shorten the answers.",
    fi: "Palaute on liian suuri. Poista kuvia tai lyhennä vastauksia.",
  },
  "Too many feedback submissions. Try again later.": {
    en: "Too many feedback submissions. Try again later.",
    fi: "Liian monta palautelähetystä. Yritä myöhemmin uudelleen.",
  },
  "Could not submit feedback. Your answers are still in the form.": {
    en: "Could not submit feedback. Your answers are still in the form.",
    fi: "Palautteen lähettäminen epäonnistui. Vastauksesi ovat yhä lomakkeessa.",
  },
  "The GitHub issue includes {fields} and any images in {attachment}. Other answers stay private.":
    {
      en: "The GitHub issue includes {fields} and any images in {attachment}. Other answers stay private.",
      fi: "GitHub-issue sisältää kentät {fields} sekä kuvat kentästä {attachment}. Muut vastaukset pysyvät yksityisinä.",
    },
  "Create public GitHub issue": {
    en: "Create public GitHub issue",
    fi: "Luo julkinen GitHub-issue",
  },
  "Create GitHub issue in a private repository": {
    en: "Create GitHub issue in a private repository",
    fi: "Luo GitHub-issue yksityiseen repositorioon",
  },
  "Create public GitHub issue?": {
    en: "Create public GitHub issue?",
    fi: "Luodaanko julkinen GitHub-issue?",
  },
  "Create a public GitHub issue in {repository} with {fields} and any images in {attachment}? Other answers stay private. Turn off the GitHub issue toggle to save private feedback without creating an issue.":
    {
      en: "Create a public GitHub issue in {repository} with {fields} and any images in {attachment}? Other answers stay private. Turn off the GitHub issue toggle to save private feedback without creating an issue.",
      fi: "Luodaanko julkinen GitHub-issue repositorioon {repository}, joka sisältää kentät {fields} sekä kuvat kentästä {attachment}? Muut vastaukset pysyvät yksityisinä. Poista GitHub-issue käytöstä, jos haluat tallentaa palautteen yksityisenä ilman issuea.",
    },
  "Create GitHub issue in a private repository?": {
    en: "Create GitHub issue in a private repository?",
    fi: "Luodaanko GitHub-issue yksityiseen repositorioon?",
  },
  "Create a GitHub issue in the private repository {repository} with {fields} and any images in {attachment}? Other answers stay private. Turn off the GitHub issue toggle to save private feedback without creating an issue.":
    {
      en: "Create a GitHub issue in the private repository {repository} with {fields} and any images in {attachment}? Other answers stay private. Turn off the GitHub issue toggle to save private feedback without creating an issue.",
      fi: "Luodaanko yksityiseen repositorioon {repository} GitHub-issue, joka sisältää kentät {fields} sekä kuvat kentästä {attachment}? Muut vastaukset pysyvät yksityisinä. Poista GitHub-issue käytöstä, jos haluat tallentaa palautteen yksityisenä ilman issuea.",
    },
  "Submit and create issue": {
    en: "Submit and create issue",
    fi: "Lähetä ja luo issue",
  },
  "Submit feedback?": { en: "Submit feedback?", fi: "Lähetä palaute?" },
  "Save this feedback privately? No GitHub issue is created and the feedback is saved on this site.":
    {
      en: "Save this feedback privately? No GitHub issue is created and the feedback is saved on this site.",
      fi: "Tallennetaanko palaute yksityisenä? GitHub-issuea ei luoda, ja palaute tallennetaan tälle sivustolle.",
    },
  "Feedback saved": { en: "Feedback saved", fi: "Palaute tallennettu" },
  "GitHub publication pending": {
    en: "GitHub publication pending",
    fi: "GitHub-julkaisu odottaa",
  },
  "Saved as private feedback": {
    en: "Saved as private feedback",
    fi: "Tallennettu yksityisenä palautteena",
  },
  More: { en: "More", fi: "Lisää" },
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
      fi: "Tämä on itsenäinen projekti, joka ei ole sidoksissa Tampereen yliopistoon.",
    },
  "Source code on GitHub.": {
    en: "Source code on GitHub.",
    fi: "Lähdekoodi GitHubissa.",
  },

  active: { en: "active", fi: "aktiivinen" },
  inactive: { en: "inactive", fi: "ei-aktiivinen" },
  completed: { en: "completed", fi: "suoritettu" },
  selected: { en: "selected", fi: "valittu" },
  "not selected": { en: "not selected", fi: "ei valittu" },
  "{code} {name}": { en: "{code} {name}", fi: "{code} {name}" },
  "{action} {name}": { en: "{action} {name}", fi: "{action} {name}" },
  "comparison slot {slot}": {
    en: "comparison slot {slot}",
    fi: "vertailupaikka {slot}",
  },
  "Completed (basis)": { en: "Completed", fi: "Suoritetut" },
  "Selected (basis)": { en: "Selected", fi: "Valitut" },
  "Completed (course)": { en: "Completed", fi: "Suoritettu" },
  "Complete (course)": { en: "Complete", fi: "Suorita" },
  Excluded: { en: "Excluded", fi: "Suljettu pois" },
  Exclude: { en: "Exclude", fi: "Sulje pois" },
  inferred: { en: "inferred", fi: "päätelty" },
  Inferred: { en: "Inferred", fi: "Päätellyt" },
  "Active only": { en: "Active only", fi: "Vain aktiiviset" },
  added: { en: "added", fi: "lisätty" },
  "not available": { en: "not available", fi: "ei saatavilla" },
  "{value}%": { en: "{value}%", fi: "{value} %" },
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
  Pull: { en: "Pull", fi: "Siirrä tänne" },
  Reset: { en: "Reset", fi: "Nollaa" },
  Replace: { en: "Replace", fi: "Vaihda" },
  Remove: { en: "Remove", fi: "Poista" },
  Change: { en: "Change", fi: "Vaihda" },
  Recenter: { en: "Recenter", fi: "Keskitä" },
  "Zoom in": { en: "Zoom in", fi: "Lähennä" },
  "Zoom out": { en: "Zoom out", fi: "Loitonna" },
  "Graph options": {
    en: "Graph options",
    fi: "Esitietograafin asetukset",
  },
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
  "Added {code} to comparison": {
    en: "Added {code} to comparison",
    fi: "Lisätty {code} vertailuun",
  },
  "comparison (notice)": { en: "comparison", fi: "vertailuun" },
  "Open prerequisite graph": {
    en: "Open prerequisite graph",
    fi: "Avaa esitietograafi",
  },
  "Add to Unplaced studies": {
    en: "Add to Unplaced studies",
    fi: "Lisää sijoittamattomiin opintoihin",
  },
  "Move to Unplaced studies": {
    en: "Move to Unplaced studies",
    fi: "Siirrä sijoittamattomiin opintoihin",
  },
  "Remove from Unplaced studies": {
    en: "Remove from Unplaced studies",
    fi: "Poista sijoittamattomista opinnoista",
  },
  "Remove from {name}": {
    en: "Remove from {name}",
    fi: "Poista kohteesta {name}",
  },
  "Added {code} to Unplaced studies": {
    en: "Added {code} to Unplaced studies",
    fi: "Lisätty {code} sijoittamattomiin opintoihin",
  },
  "Unplaced studies (notice)": {
    en: "Unplaced studies",
    fi: "sijoittamattomiin opintoihin",
  },
  "Unplaced studies (removal notice)": {
    en: "Unplaced studies",
    fi: "sijoittamattomista opinnoista",
  },
  "Added {code} to Unplaced studies and marked it completed": {
    en: "Added {code} to Unplaced studies and marked it completed",
    fi: "Lisätty {code} sijoittamattomiin opintoihin ja merkitty suoritetuksi",
  },
  "Moved {code} from {name} to Unplaced studies": {
    en: "Moved {code} from {name} to Unplaced studies",
    fi: "Siirretty {code} kohteesta {name} sijoittamattomiin opintoihin",
  },
  "Moved {code} to Unplaced studies": {
    en: "Moved {code} to Unplaced studies",
    fi: "Siirretty {code} sijoittamattomiin opintoihin",
  },
  "Removed {code} from Unplaced studies": {
    en: "Removed {code} from Unplaced studies",
    fi: "Poistettu {code} sijoittamattomista opinnoista",
  },
  "Removed {code} from {name}": {
    en: "Removed {code} from {name}",
    fi: "Poistettu {code} kohteesta {name}",
  },
  "Move to Unplaced studies?": {
    en: "Move to Unplaced studies?",
    fi: "Siirretäänkö sijoittamattomiin opintoihin?",
  },
  "{code} is already in your plan. Move it to Unplaced studies?": {
    en: "{code} is already in your plan. Move it to Unplaced studies?",
    fi: "{code} on jo suunnitelmassasi. Siirretäänkö se sijoittamattomiin opintoihin?",
  },
  "Added {count} course to Unplaced studies": {
    en: "Added {count} course to Unplaced studies",
    fi: "Lisättiin {count} kurssi sijoittamattomiin opintoihin",
  },
  "Added {count} courses to Unplaced studies": {
    en: "Added {count} courses to Unplaced studies",
    fi: "Lisättiin {count} kurssia sijoittamattomiin opintoihin",
  },
  "No courses added. Selection unchanged.": {
    en: "No courses added. Selection unchanged.",
    fi: "Kursseja ei lisätty. Valinta ei muuttunut.",
  },
  structure: { en: "structure", fi: "rakenne" },
  "Mark completed": { en: "Mark completed", fi: "Merkitse suoritetuksi" },
  "Marked course {code} as completed": {
    en: "Marked course {code} as completed",
    fi: "Kurssi {code} merkitty suoritetuksi",
  },
  "Remove completion": {
    en: "Remove completion",
    fi: "Poista suoritusmerkintä",
  },
  "Removed completion of course {code}": {
    en: "Removed completion of course {code}",
    fi: "Poistettu kurssin {code} suoritusmerkintä",
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
  "No active courses matched. Consider turning Active only off.": {
    en: "No active courses matched. Consider turning Active only off.",
    fi: "Mikään aktiivinen kurssi ei vastaa tätä hakua. Kokeile poistaa Vain aktiiviset käytöstä.",
  },
  "Type to search courses by name or code.": {
    en: "Type to search courses by name or code.",
    fi: "Hae kursseja kirjoittamalla nimi tai koodi.",
  },
  "Semantic search is unavailable. Showing matches by code and name only.": {
    en: "Semantic search is unavailable. Showing matches by code and name only.",
    fi: "Semanttinen haku ei ole käytettävissä. Näytetään vain koodin ja nimen perusteella löytyneet kurssit.",
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
    fi: "Tietoa valinnoista",
  },
  "Explain comparison": {
    en: "Explain comparison",
    fi: "Tietoa vertailusta",
  },
  "Explain structure of studies": {
    en: "Explain structure of studies",
    fi: "Tietoa opintojen rakenteesta",
  },
  "Explain profiles and import": {
    en: "Explain profiles and import",
    fi: "Tietoa profiileista ja tuonnista",
  },
  "Explain import": {
    en: "Explain import",
    fi: "Tietoa tuonnista",
  },
  "No prerequisites with these options.": {
    en: "No prerequisites with these options.",
    fi: "Ei esitietoja näillä valinnoilla.",
  },
  "No prerequisites with these options. Consider turning Recommended on.": {
    en: "No prerequisites with these options. Consider turning Recommended on.",
    fi: "Ei esitietoja näillä valinnoilla. Kokeile ottaa Suositellut käyttöön.",
  },
  "No prerequisites with these options. Consider turning Active only off.": {
    en: "No prerequisites with these options. Consider turning Active only off.",
    fi: "Ei esitietoja näillä valinnoilla. Kokeile poistaa Vain aktiiviset käytöstä.",
  },
  "No prerequisites with these options. Consider turning Inferred on.": {
    en: "No prerequisites with these options. Consider turning Inferred on.",
    fi: "Ei esitietoja näillä valinnoilla. Kokeile ottaa Päätellyt käyttöön.",
  },
  "No prerequisites with these options. Consider turning Recommended on or Active only off.":
    {
      en: "No prerequisites with these options. Consider turning Recommended on or Active only off.",
      fi: "Ei esitietoja näillä valinnoilla. Kokeile ottaa Suositellut käyttöön tai poistaa Vain aktiiviset käytöstä.",
    },
  "No prerequisites with these options. Consider turning Recommended on or Inferred on.":
    {
      en: "No prerequisites with these options. Consider turning Recommended on or Inferred on.",
      fi: "Ei esitietoja näillä valinnoilla. Kokeile ottaa Suositellut tai Päätellyt käyttöön.",
    },
  "No prerequisites with these options. Consider turning Active only off or Inferred on.":
    {
      en: "No prerequisites with these options. Consider turning Active only off or Inferred on.",
      fi: "Ei esitietoja näillä valinnoilla. Kokeile poistaa Vain aktiiviset käytöstä tai ottaa Päätellyt käyttöön.",
    },
  "No prerequisites with these options. Consider turning Recommended on, Active only off or Inferred on.":
    {
      en: "No prerequisites with these options. Consider turning Recommended on, Active only off or Inferred on.",
      fi: "Ei esitietoja näillä valinnoilla. Kokeile ottaa Suositellut käyttöön, poistaa Vain aktiiviset käytöstä tai ottaa Päätellyt käyttöön.",
    },
  "Exploring prerequisites": {
    en: "Exploring prerequisites",
    fi: "Esitietojen tarkastelu",
  },
  options: { en: "options", fi: "valinnat" },
  results: { en: "results", fi: "tulokset" },
  graph: { en: "graph", fi: "graafi" },

  "Search by code, name or topic": {
    en: "Search by code, name or topic",
    fi: "Hae koodin, nimen tai aiheen mukaan",
  },
  "Search by code or name": {
    en: "Search by code or name",
    fi: "Hae koodilla tai nimellä",
  },
  "Search results": { en: "Search results", fi: "Hakutulokset" },
  "Shows only courses that are currently active. Turn it off to include inactive courses.":
    {
      en: "Shows only courses that are currently active. Turn it off to include inactive courses.",
      fi: "Näyttää vain tällä hetkellä aktiiviset kurssit. Poista valinta, jos haluat mukaan myös ei-aktiiviset kurssit.",
    },
  "search methods": { en: "search methods", fi: "hakumenetelmät" },
  "Exact code": { en: "Exact code", fi: "Tarkka koodi" },
  Substring: { en: "Substring", fi: "Osamerkkijono" },
  "Fuzzy search": { en: "Fuzzy search", fi: "Likimääräinen haku" },
  Semantic: { en: "Semantic", fi: "Semanttinen" },
  "Finds courses whose full code is a word in the query. Separate several codes with spaces or commas to find them together.":
    {
      en: "Finds courses whose full code is a word in the query. Separate several codes with spaces or commas to find them together.",
      fi: "Löytää kurssit, joiden koko koodi on hakutekstissä omana sananaan. Erota useat koodit välilyönnein tai pilkuin, niin löydät ne yhdellä haulla.",
    },
  "Finds the text inside a course name or code, ignoring case. A code fragment such as COMP.CS finds codes containing that fragment.":
    {
      en: "Finds the text inside a course name or code, ignoring case. A code fragment such as COMP.CS finds codes containing that fragment.",
      fi: "Etsii tekstiä kurssin nimestä tai koodista kirjainkoosta riippumatta. Esimerkiksi koodin osa COMP.CS löytää koodit, joissa se esiintyy.",
    },
  "Finds course names close to the query. A small typo or a different word order can still match.":
    {
      en: "Finds course names close to the query. A small typo or a different word order can still match.",
      fi: "Löytää hakutekstiä muistuttavat kurssien nimet. Pieni kirjoitusvirhe tai erilainen sanajärjestys ei välttämättä estä löytymistä.",
    },
  "Matches the meaning of your query against course names, content and learning outcomes. A course can match without using the same words. Prerequisite text does not drive this match.":
    {
      en: "Matches the meaning of your query against course names, content and learning outcomes. A course can match without using the same words. Prerequisite text does not drive this match.",
      fi: "Vertaa hakusi merkitystä kurssien nimiin, sisältöihin ja osaamistavoitteisiin. Kurssi voi löytyä, vaikka siinä käytetään eri sanoja. Esitietoteksti ei vaikuta tähän hakuun.",
    },
  "A course appears once with every method that matched it. Results are grouped by their first matching method. Run the search with Enter or the magnifier. Editing the text alone does not run it.":
    {
      en: "A course appears once with every method that matched it. Results are grouped by their first matching method. Run the search with Enter or the magnifier. Editing the text alone does not run it.",
      fi: "Kurssi näkyy kerran, ja sen merkinnät kertovat, millä hakumenetelmillä se löytyi. Tulokset ryhmitellään ensimmäisen osuneen hakumenetelmän mukaan. Käynnistä haku Enter-näppäimellä tai suurennuslasista. Pelkkä tekstin muokkaaminen ei käynnistä hakua.",
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
    fi: "Korvaa paikka {slot}: {name}",
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
    fi: "Sama aihealue, eri sisältö",
  },
  "Loosely related": { en: "Loosely related", fi: "Löyhästi liittyvät" },
  Unrelated: { en: "Unrelated", fi: "Eivät liity toisiinsa" },
  "Overall relatedness": {
    en: "Overall relatedness",
    fi: "Yleinen samankaltaisuus",
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
    fi: "Päällekkäisyys: {a} suhteessa kurssiin {b}",
  },
  "how much of A has a match in B": {
    en: "how much of A has a match in B",
    fi: "kuinka suurelle osalle A:sta löytyy vastine B:stä",
  },
  "Overlap: {b} in {a}": {
    en: "Overlap: {b} in {a}",
    fi: "Päällekkäisyys: {b} suhteessa kurssiin {a}",
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
  Overlap: { en: "Overlap", fi: "Päällekkäisyys" },
  Verdict: { en: "Verdict", fi: "Vertailun tulos" },
  analysis: { en: "analysis", fi: "analyysi" },
  "Choose a course for A and B by name or code. You can also use Add to comparison in a course menu. Replace changes one slot and Remove empties it. The picker has its own Active only setting.":
    {
      en: "Choose a course for A and B by name or code. You can also use Add to comparison in a course menu. Replace changes one slot and Remove empties it. The picker has its own Active only setting.",
      fi: "Valitse A- ja B-paikkoihin kurssit nimen tai koodin perusteella. Voit käyttää myös kurssivalikon Lisää vertailuun -toimintoa. Vaihda vaihtaa yhden paikan kurssin ja Poista tyhjentää paikan. Kurssivalitsimella on oma Vain aktiiviset -asetus.",
    },
  "Compares the courses as a whole using their names, content and learning outcomes.":
    {
      en: "Compares the courses as a whole using their names, content and learning outcomes.",
      fi: "Vertaa kursseja kokonaisuutena nimien, sisältöjen ja osaamistavoitteiden perusteella.",
    },
  "Compares content text with content text.": {
    en: "Compares content text with content text.",
    fi: "Vertaa kurssien sisältötekstejä keskenään.",
  },
  "Compares learning outcomes with learning outcomes.": {
    en: "Compares learning outcomes with learning outcomes.",
    fi: "Vertaa kurssien osaamistavoitteita keskenään.",
  },
  "Estimates how much of one course's content and learning outcomes has a match in the other. The two directions can differ. A high A-to-B value does not imply the same B-to-A value.":
    {
      en: "Estimates how much of one course's content and learning outcomes has a match in the other. The two directions can differ. A high A-to-B value does not imply the same B-to-A value.",
      fi: "Arvioi, kuinka suuri osa yhden kurssin sisällöstä ja osaamistavoitteista vastaa toisen kurssin tekstiä. Suunnat voivat erota toisistaan. Suuri arvo suunnassa A:sta B:hen ei tarkoita yhtä suurta arvoa suunnassa B:stä A:han.",
    },
  "The stronger overlap decides the overlap labels first. Otherwise overall relatedness decides the label. These are estimates from teaching text, not official equivalence or a credit-transfer decision.":
    {
      en: "The stronger overlap decides the overlap labels first. Otherwise overall relatedness decides the label. These are estimates from teaching text, not official equivalence or a credit-transfer decision.",
      fi: "Voimakkaampi päällekkäisyys ratkaisee ensin päällekkäisyysmerkinnän. Muissa tapauksissa merkinnän ratkaisee yleinen samankaltaisuus. Arviot perustuvat opetustekstiin, eivät viralliseen vastaavuuteen tai hyväksilukupäätökseen.",
    },
  "The meter lacks the text or shared language needed for the comparison. A measured 0% is a result, not missing data. Includes derived text means a translation contributed on either side.":
    {
      en: "The meter lacks the text or shared language needed for the comparison. A measured 0% is a result, not missing data. Includes derived text means a translation contributed on either side.",
      fi: "Mittarilta puuttuu vertailuun tarvittava teksti tai yhteinen kieli. Mitattu 0 % on tulos, ei puuttuva tieto. Sisältää johdettua tekstiä tarkoittaa, että jommankumman kurssin vertailussa käytettiin käännöstä.",
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
  "Discover options": {
    en: "Discover options",
    fi: "Ehdotusten asetukset",
  },
  "Next courses": { en: "Next courses", fi: "Seuraavat kurssit" },
  Recommended: { en: "Recommended", fi: "Suositellut" },
  All: { en: "All", fi: "Kaikki" },
  "Partially covered": { en: "Partially covered", fi: "Osittain katettu" },
  "Prerequisite mode": {
    en: "Prerequisite mode",
    fi: "Esitietojen kattavuus",
  },
  "Discovery basis": { en: "Discovery basis", fi: "Ehdotuksissa huomioidaan" },
  "All / Partially covered": {
    en: "All / Partially covered",
    fi: "Kaikki / Osittain katettu",
  },
  "All lists courses whose prerequisite requirements your basis satisfies. Partially covered lists courses with at least one covered prerequisite, including fully covered courses. It orders them by required coverage, then recommended coverage. Recommended prerequisites also take part in eligibility.":
    {
      en: "All lists courses whose prerequisite requirements your basis satisfies. Partially covered lists courses with at least one covered prerequisite, including fully covered courses. It orders them by required coverage, then recommended coverage. Recommended prerequisites also take part in eligibility.",
      fi: "Kaikki näyttää kurssit, joiden esitietovaatimukset huomioitavat kurssisi täyttävät. Osittain katettu näyttää kurssit, joilla on vähintään yksi katettu esitieto, myös kokonaan katetut. Järjestys määräytyy ensin pakollisten ja sitten suositeltujen esitietojen kattavuuden mukaan. Myös suositellut esitiedot vaikuttavat siihen, pääseekö kurssi listalle.",
    },
  "Completed / Selected": {
    en: "Completed / Selected",
    fi: "Suoritetut / Valitut",
  },
  "Choose the courses used as the basis for suggestions: only completed courses, or every selected course, including completed ones. Select or complete courses in any tab to build the basis.":
    {
      en: "Choose the courses used as the basis for suggestions: only completed courses, or every selected course, including completed ones. Select or complete courses in any tab to build the basis.",
      fi: "Valitse ehdotuksissa huomioitavat kurssit: vain suoritetut tai kaikki valitut kurssit, joihin myös suoritetut kuuluvat. Voit lisätä niitä valitsemalla kursseja tai merkitsemällä niitä suoritetuiksi millä tahansa välilehdellä.",
    },
  "Proposes only active courses. Turn it off to include inactive courses. Inactive courses in your basis still contribute to suggestions.":
    {
      en: "Proposes only active courses. Turn it off to include inactive courses. Inactive courses in your basis still contribute to suggestions.",
      fi: "Ehdottaa vain aktiivisia kursseja. Poista valinta, jos haluat mukaan myös ei-aktiiviset kurssit. Ehdotuksiin vaikuttavat myös ne ei-aktiiviset kurssit, jotka kuuluvat huomioitaviin kursseihin.",
    },
  "Select or complete courses in any tab to get suggestions.": {
    en: "Select or complete courses in any tab to get suggestions.",
    fi: "Saat ehdotuksia, kun valitset tai merkitset kursseja suoritetuiksi missä tahansa välilehdessä.",
  },
  "basis · {basis} · empty": {
    en: "basis · {basis} · empty",
    fi: "mukana: {basis} · tyhjä",
  },
  "Basis · {basis}": { en: "Basis · {basis}", fi: "mukana: {basis}" },
  "Basis: {basis}": {
    en: "Basis: {basis}",
    fi: "Mukana: {basis}",
  },
  "basis · {basis} · {count} courses": {
    en: "basis · {basis} · {count} courses",
    fi: "mukana: {basis} · {count} kurssia",
  },
  "basis · {basis} · {count} course": {
    en: "basis · {basis} · {count} course",
    fi: "mukana: {basis} · {count} kurssi",
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
  "No active course matches these options. Consider turning Active only off.": {
    en: "No active course matches these options. Consider turning Active only off.",
    fi: "Mikään aktiivinen kurssi ei vastaa näitä valintoja. Kokeile poistaa Vain aktiiviset käytöstä.",
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
  "Each percentage shows how much of the best-covered prerequisite option your basis covers in that category. A category without course prerequisites has no meter. All shows no meters, because satisfying a choice can require fewer than all its alternatives.":
    {
      en: "Each percentage shows how much of the best-covered prerequisite option your basis covers in that category. A category without course prerequisites has no meter. All shows no meters, because satisfying a choice can require fewer than all its alternatives.",
      fi: "Prosentti kertoo, kuinka suuren osan parhaiten katetusta esitietovaihtoehdosta huomioitavat kurssisi kattavat kyseisessä luokassa. Jos luokassa ei ole kurssiesitietoja, mittaria ei näytetä. Kaikki-tilassa mittareita ei näytetä, koska valintavaatimuksen täyttämiseen voi riittää vain osa vaihtoehdoista.",
    },
  "Official and inferred prerequisites both count.": {
    en: "Official and inferred prerequisites both count.",
    fi: "Sekä viralliset että päätellyt esitiedot lasketaan mukaan.",
  },
  "Only official prerequisites count.": {
    en: "Only official prerequisites count.",
    fi: "Vain viralliset esitiedot lasketaan mukaan.",
  },
  marks: { en: "marks", fi: "merkinnät" },
  "Inferred prerequisites or equivalence groups are what bring this course onto the list. They are analysis, not official requirements. The linked experiments explain the evidence and its limits.":
    {
      en: "Inferred prerequisites or equivalence groups are what bring this course onto the list. They are analysis, not official requirements. The linked experiments explain the evidence and its limits.",
      fi: "Kurssi pääsee listalle pääteltyjen esitietojen tai vastaavuusryhmien perusteella. Ne ovat analyysin tuloksia, eivät virallisia vaatimuksia. Linkitetyt kokeet kuvaavat näyttöä ja sen rajoituksia.",
    },
  "In the profile's selection, not completed.": {
    en: "In the profile's selection, not completed.",
    fi: "Profiilin valinnoissa, ei suoritettu.",
  },
  "Marked completed and also selected.": {
    en: "Marked completed and also selected.",
    fi: "Merkitty suoritetuksi ja myös valittu.",
  },
  "Measures how close the course's content and learning outcomes are to the subject profile formed from your basis. It is a similarity score, not prerequisite coverage or official equivalence. The list leaves out courses that closely duplicate a basis course. A note identifies derived translations used in the comparison.":
    {
      en: "Measures how close the course's content and learning outcomes are to the subject profile formed from your basis. It is a similarity score, not prerequisite coverage or official equivalence. The list leaves out courses that closely duplicate a basis course. A note identifies derived translations used in the comparison.",
      fi: "Mittaa, kuinka lähellä kurssin sisältö ja osaamistavoitteet ovat huomioitavista kursseistasi muodostettua aiheprofiilia. Luku kuvaa samankaltaisuutta, ei esitietojen kattavuutta tai virallista vastaavuutta. Listalta jätetään pois kurssit, jotka toistavat liian läheisesti jonkin huomioitavan kurssin sisältöä. Huomautus kertoo vertailussa käytetyistä johdetuista käännöksistä.",
    },
  "Teaching text includes derived translations": {
    en: "Teaching text includes derived translations",
    fi: "Opetusteksti sisältää johdettuja käännöksiä",
  },

  "Counts as covered": { en: "Counts as covered", fi: "Lasketaan katetuksi" },
  "Route basis": { en: "Route basis", fi: "Reitissä huomioidaan" },
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
  "Calculates a temporary route with the fewest new credits beyond your basis. A shared course counts once. The result states whether it is exact, approximate or unresolved, or whether a route cannot be found. Changing the root, options, courses or graph marks, or leaving this tab, clears the shown route. Use Clear minimum route to return to the plain graph.":
    {
      en: "Calculates a temporary route with the fewest new credits beyond your basis. A shared course counts once. The result states whether it is exact, approximate or unresolved, or whether a route cannot be found. Changing the root, options, courses or graph marks, or leaving this tab, clears the shown route. Use Clear minimum route to return to the plain graph.",
      fi: "Laskee tilapäisen reitin, joka vaatii huomioitavien kurssien lisäksi vähiten uusia opintopisteitä. Usean haaran tarvitsema kurssi lasketaan kerran. Tulos kertoo, onko reitti tarkka, likimääräinen vai ratkaisematon, tai löytyykö reittiä lainkaan. Näytetty reitti poistuu, kun vaihdat juurikurssia, valintoja, kursseja tai graafin merkintöjä tai poistut välilehdestä. Palaa tavalliseen graafiin toiminnolla Tyhjennä lyhin reitti.",
    },
  "Also shows recommended prerequisites and includes them in the minimum route.":
    {
      en: "Also shows recommended prerequisites and includes them in the minimum route.",
      fi: "Näyttää myös suositellut esitiedot ja ottaa ne mukaan lyhimpään reittiin.",
    },
  "Leaves inactive courses out of the graph and the route. Selected or completed inactive courses and the opened root are shown. Turn it off to include other inactive courses. The course picker uses this same setting.":
    {
      en: "Leaves inactive courses out of the graph and the route. Selected or completed inactive courses and the opened root are shown. Turn it off to include other inactive courses. The course picker uses this same setting.",
      fi: "Jättää ei-aktiiviset kurssit pois graafista ja reitistä. Valitut tai suoritetut ei-aktiiviset kurssit ja avattu juurikurssi näytetään silti. Poista valinta, jos haluat mukaan muutkin ei-aktiiviset kurssit. Kurssivalitsin käyttää samaa asetusta.",
    },
  "Adds prerequisites found by analysis of teaching text, separately from the university's official requirements. A course is marked inferred only when no official occurrence reaches it. A connection is dashed only when all its relationships are inferred.":
    {
      en: "Adds prerequisites found by analysis of teaching text, separately from the university's official requirements. A course is marked inferred only when no official occurrence reaches it. A connection is dashed only when all its relationships are inferred.",
      fi: "Lisää opetustekstistä päätellyt esitiedot yliopiston virallisten vaatimusten rinnalle. Kurssi merkitään päätellyksi vain, jos siihen ei johda yhtään virallista esiintymää. Yhteys on katkoviiva vain, jos kaikki sen esitietosuhteet ovat pääteltyjä.",
    },
  "inference experiments": {
    en: "inference experiments",
    fi: "Esitietojen päättelyn kokeet",
  },
  "describe the evidence and its limits.": {
    en: "describe the evidence and its limits.",
    fi: "kuvaavat näyttöä ja sen rajoituksia.",
  },
  "Choose which courses count as covered: only completed courses, or every selected course, including completed ones. Covered courses add no new credits to the route.":
    {
      en: "Choose which courses count as covered: only completed courses, or every selected course, including completed ones. Covered courses add no new credits to the route.",
      fi: "Valitse, mitkä kurssit lasketaan katetuiksi: vain suoritetut vai kaikki valitut kurssit, joihin myös suoritetut kuuluvat. Katetut kurssit eivät lisää reitin uusia opintopisteitä.",
    },
  "AND requires every branch. OR requires one alternative. Other requirement boxes state how many courses or credits are needed. Complete marks a course completed across the app. A completion mark on a module or requirement box applies to that graph requirement instead. Exclude blocks routes through the marked course or requirement.":
    {
      en: "AND requires every branch. OR requires one alternative. Other requirement boxes state how many courses or credits are needed. Complete marks a course completed across the app. A completion mark on a module or requirement box applies to that graph requirement instead. Exclude blocks routes through the marked course or requirement.",
      fi: "AND vaatii kaikki haarat ja OR yhden vaihtoehdon. Muut vaatimuslaatikot kertovat tarvittavan kurssi- tai opintopistemäärän. Suoritusmerkintä kurssille vaikuttaa koko sovellukseen. Moduulin tai vaatimuslaatikon suoritusmerkintä koskee sen sijaan kyseistä graafin vaatimusta. Poissulkeminen estää reitit merkityn kurssin tai vaatimuksen kautta.",
    },
  "Minimum route": { en: "Minimum route", fi: "Lyhin reitti" },
  "Calculating…": { en: "Calculating…", fi: "Lasketaan…" },
  "Clear minimum route": {
    en: "Clear minimum route",
    fi: "Tyhjennä lyhin reitti",
  },
  Clear: { en: "Clear", fi: "Tyhjennä" },
  "cheapest route to the selected course": {
    en: "cheapest route to the selected course",
    fi: "lyhin reitti valitulle kurssille",
  },
  "click to clear": { en: "click to clear", fi: "tyhjennä painamalla" },
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
    fi: "Ei välttämättä ole lyhin reitti.",
  },
  "The exact search was too large and the approximation gave up.": {
    en: "The exact search was too large and the approximation gave up.",
    fi: "Tarkka haku oli liian suuri, eikä likimääräinen haku onnistunut.",
  },
  "No route or total is available.": {
    en: "No route or total is available.",
    fi: "Reittiä tai kokonaismäärää ei ole saatavilla.",
  },
  "No route meets every requirement.": {
    en: "No route meets every requirement.",
    fi: "Mikään reitti ei täytä kaikkia vaatimuksia.",
  },
  "Blocked requirements:": {
    en: "Blocked requirements:",
    fi: "Estetyt vaatimukset:",
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
  "This prerequisite graph is too large to draw.": {
    en: "This prerequisite graph is too large to draw.",
    fi: "Tämä esitietograafi on liian suuri piirrettäväksi.",
  },
  "{elements} elements, limit {limit}.": {
    en: "{elements} elements, limit {limit}.",
    fi: "{elements} elementtiä, raja {limit}.",
  },
  "Tip: turn off Recommended or Inferred, or turn on Active only, to shrink the graph.":
    {
      en: "Tip: turn off Recommended or Inferred, or turn on Active only, to shrink the graph.",
      fi: "Vinkki: pienennä graafia poistamalla Suositellut tai Päätellyt käytöstä tai ottamalla Vain aktiiviset käyttöön.",
    },
  "Tip: turn off Recommended, or turn on Active only, to shrink the graph.": {
    en: "Tip: turn off Recommended, or turn on Active only, to shrink the graph.",
    fi: "Vinkki: poista Suositellut käytöstä tai ota Vain aktiiviset käyttöön, niin graafi pienenee.",
  },

  "Dragging courses": {
    en: "Dragging courses",
    fi: "Kurssien raahaaminen",
  },
  "Profiles and import": {
    en: "Profiles and import",
    fi: "Profiilit ja tuonti",
  },
  editing: { en: "editing", fi: "muokkaaminen" },
  "Add programme": { en: "Add programme", fi: "Lisää ohjelma" },
  "Replace programme": { en: "Replace programme", fi: "Vaihda ohjelma" },
  "Reset programme": { en: "Reset programme", fi: "Nollaa ohjelma" },
  "Delete programme": { en: "Delete programme", fi: "Poista ohjelma" },
  "Choose programme": { en: "Choose programme", fi: "Valitse ohjelma" },
  "Choose module version": {
    en: "Choose module version",
    fi: "Valitse moduulin versio",
  },
  "module versions": { en: "module versions", fi: "moduulin versiot" },
  "{name} has more than one version in the curriculum. Choose the version to add.":
    {
      en: "{name} has more than one version in the curriculum. Choose the version to add.",
      fi: "Moduulilla {name} on useampi kuin yksi versio opetussuunnitelmassa. Valitse lisättävä versio.",
    },
  "Add {code} {name} to the structure": {
    en: "Add {code} {name} to the structure",
    fi: "Lisää {code} {name} rakenteeseen",
  },
  Select: { en: "Select", fi: "Valitse" },
  "Valid {start} – {end}": {
    en: "Valid {start} – {end}",
    fi: "Voimassa {start} – {end}",
  },
  "Valid from {start}": {
    en: "Valid from {start}",
    fi: "Voimassa {start} alkaen",
  },
  "Valid until {end}": {
    en: "Valid until {end}",
    fi: "Voimassa {end} asti",
  },
  "Validity not stated": {
    en: "Validity not stated",
    fi: "Voimassaoloaikaa ei ole ilmoitettu",
  },
  "Periods: {periods}": {
    en: "Periods: {periods}",
    fi: "Opetussuunnitelmakaudet: {periods}",
  },
  "Version {id}": { en: "Version {id}", fi: "Versio {id}" },
  "No versions available.": {
    en: "No versions available.",
    fi: "Versioita ei ole saatavilla.",
  },
  "Another version of this module is already selected": {
    en: "Another version of this module is already selected",
    fi: "Tästä moduulista on jo valittu toinen versio",
  },
  "Sisu plan selects two versions of a module": {
    en: "Sisu plan selects two versions of a module",
    fi: "Sisu-suunnitelma valitsee moduulista kaksi versiota",
  },
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
    fi: "{name} on jo sijoitettu. Paikka: {place}. Se siirtyy tänne sisältöineen.",
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
  "Add a degree programme or module by name or code. Choose an exact version when several are offered. Open a module row to choose alternatives or add courses through its drawer.":
    {
      en: "Add a degree programme or module by name or code. Choose an exact version when several are offered. Open a module row to choose alternatives or add courses through its drawer.",
      fi: "Lisää tutkinto-ohjelma tai moduuli nimen tai koodin perusteella. Valitse tarkka versio, jos tarjolla on useita. Avaa moduulin rivi, kun haluat valita vaihtoehtoja tai lisätä kursseja sen paneelissa.",
    },
  "Holds selected courses with no place in a programme or module. Add a course here from its course menu, then place it where you want it. A course appears in one place and its completion is shared across tabs.":
    {
      en: "Holds selected courses with no place in a programme or module. Add a course here from its course menu, then place it where you want it. A course appears in one place and its completion is shared across tabs.",
      fi: "Sisältää valitut kurssit, joita ei ole sijoitettu ohjelmaan tai moduuliin. Lisää kurssi tänne kurssivalikosta ja sijoita se haluamaasi paikkaan. Kurssi näkyy yhdessä paikassa, ja sen suoritusmerkintä on yhteinen kaikille välilehdille.",
    },
  "On desktop, drag a course card to move or reorder it. On a touch screen, hold until the card lifts, then drag. The outline marks the drop position. Hold near the top or bottom to scroll. Dropping asks no confirmation, and a completed course keeps its completion.":
    {
      en: "On desktop, drag a course card to move or reorder it. On a touch screen, hold until the card lifts, then drag. The outline marks the drop position. Hold near the top or bottom to scroll. Dropping asks no confirmation, and a completed course keeps its completion.",
      fi: "Siirrä kurssikorttia tai muuta korttien järjestystä raahaamalla. Kosketusnäytöllä paina korttia, kunnes se nousee, ja raahaa sitten. Ääriviiva näyttää pudotuspaikan. Vieritä pitämällä korttia ylä- tai alareunan lähellä. Pudotus ei kysy vahvistusta, ja suoritetun kurssin suoritusmerkintä säilyy.",
    },
  "The programme menu and the module drawer restore official content through a confirmation. Reset preserves completed courses. Reset all also clears completions held by the affected part. Read the confirmation before resetting, replacing or deleting a part.":
    {
      en: "The programme menu and the module drawer restore official content through a confirmation. Reset preserves completed courses. Reset all also clears completions held by the affected part. Read the confirmation before resetting, replacing or deleting a part.",
      fi: "Ohjelmavalikosta ja moduulin paneelista voit palauttaa virallisen sisällön vahvistamalla. Nollaa säilyttää suoritetut kurssit. Nollaa kaikki poistaa myös kyseisen osan suoritusmerkinnät. Lue vahvistus ennen osan nollaamista, vaihtamista tai poistamista.",
    },
  "Your programmes, choices, placements and card order are saved in this browser's profile. Use the profile panel to export or import a plan. With no programme added, the import area is also shown below Add programme.":
    {
      en: "Your programmes, choices, placements and card order are saved in this browser's profile. Use the profile panel to export or import a plan. With no programme added, the import area is also shown below Add programme.",
      fi: "Ohjelmat, valinnat, sijoittelut ja korttien järjestys tallentuvat tämän selaimen profiiliin. Voit viedä tai tuoda suunnitelman profiilipaneelista. Kun yhtään ohjelmaa ei ole lisätty, tuontialue näkyy myös Lisää ohjelma -rivin alla.",
    },
  "any studies": { en: "any studies", fi: "mitkä tahansa opinnot" },
  "Nothing here yet.": {
    en: "Nothing here yet.",
    fi: "Täällä ei ole vielä mitään.",
  },
  programme: { en: "programme", fi: "tutkinto-ohjelma" },
  choice: { en: "choice", fi: "valintakohde" },
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
  "This module has changes to its official content. Removing it discards them.":
    {
      en: "This module has changes to its official content. Removing it discards them.",
      fi: "Tämän moduulin virallista sisältöä on muutettu. Sen poistaminen hylkää muutokset.",
    },
  "This module has changes to its official content. Removing it discards them. Keep completed courses under Unplaced studies, or remove them with their completions.":
    {
      en: "This module has changes to its official content. Removing it discards them. Keep completed courses under Unplaced studies, or remove them with their completions.",
      fi: "Tämän moduulin virallista sisältöä on muutettu. Sen poistaminen hylkää muutokset. Säilytä suoritetut kurssit sijoittamattomissa opinnoissa tai poista ne suoritusmerkintöineen.",
    },
  "This module holds completed courses. Keep them under Unplaced studies, or remove them with their completions.":
    {
      en: "This module holds completed courses. Keep them under Unplaced studies, or remove them with their completions.",
      fi: "Moduuli sisältää suoritettuja kursseja. Säilytä ne sijoittamattomissa opinnoissa tai poista ne suoritusmerkintöineen.",
    },
  "This programme has changes to its official content. Removing it discards them.":
    {
      en: "This programme has changes to its official content. Removing it discards them.",
      fi: "Tämän ohjelman virallista sisältöä on muutettu. Sen poistaminen hylkää muutokset.",
    },
  "This programme has changes to its official content. Removing it discards them. Keep completed courses under Unplaced studies, or remove them with their completions.":
    {
      en: "This programme has changes to its official content. Removing it discards them. Keep completed courses under Unplaced studies, or remove them with their completions.",
      fi: "Tämän ohjelman virallista sisältöä on muutettu. Sen poistaminen hylkää muutokset. Säilytä suoritetut kurssit sijoittamattomissa opinnoissa tai poista ne suoritusmerkintöineen.",
    },
  "This programme holds completed courses. Keep them under Unplaced studies, or remove them with their completions.":
    {
      en: "This programme holds completed courses. Keep them under Unplaced studies, or remove them with their completions.",
      fi: "Ohjelma sisältää suoritettuja kursseja. Säilytä ne sijoittamattomissa opinnoissa tai poista ne suoritusmerkintöineen.",
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
  "Move keeps the module's current content. Reset restores its official content. Reset all also clears its completions.":
    {
      en: "Move keeps the module's current content. Reset restores its official content. Reset all also clears its completions.",
      fi: "Siirto säilyttää moduulin nykyisen sisällön. Nollaus palauttaa sen virallisen sisällön. Nollaa kaikki poistaa myös sen suoritusmerkinnät.",
    },
  "Move keeps the module's current content. Reset restores its official content.":
    {
      en: "Move keeps the module's current content. Reset restores its official content.",
      fi: "Siirto säilyttää moduulin nykyisen sisällön. Nollaus palauttaa sen virallisen sisällön.",
    },
  "Move keeps the module's current content. Reset all restores its official content and clears its completions.":
    {
      en: "Move keeps the module's current content. Reset all restores its official content and clears its completions.",
      fi: "Siirto säilyttää moduulin nykyisen sisällön. Nollaa kaikki palauttaa sen virallisen sisällön ja poistaa sen suoritusmerkinnät.",
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
  "Filter programmes and modules by name or code": {
    en: "Filter programmes and modules by name or code",
    fi: "Rajaa tutkinto-ohjelmia ja moduuleja nimen tai koodin mukaan",
  },
  "Loading programmes and modules": {
    en: "Loading programmes and modules",
    fi: "Ladataan tutkinto-ohjelmia ja moduuleja",
  },
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
  "Mark completed?": {
    en: "Mark completed?",
    fi: "Merkitäänkö suoritetuksi?",
  },
  "Add {name} to Unplaced studies and mark it completed?": {
    en: "Add {name} to Unplaced studies and mark it completed?",
    fi: "Lisätäänkö {name} sijoittamattomiin opintoihin ja merkitäänkö se suoritetuksi?",
  },
  "Add and complete": {
    en: "Add and complete",
    fi: "Lisää ja merkitse suoritetuksi",
  },
  "Move here?": { en: "Move here?", fi: "Siirretäänkö tänne?" },
  "the programme list": { en: "the programme list", fi: "ohjelmaluettelo" },
  "{name} is already in {place}. Move it here?": {
    en: "{name} is already in {place}. Move it here?",
    fi: "{name} on jo sijoitettu. Paikka: {place}. Siirretäänkö se tänne?",
  },
  "Move this course into {name}?": {
    en: "Move this course into {name}?",
    fi: "Siirretäänkö tämä kurssi kohteeseen {name}?",
  },
  "Move these courses into {name}?": {
    en: "Move these courses into {name}?",
    fi: "Siirretäänkö nämä kurssit kohteeseen {name}?",
  },
  "Move this module into {name}?": {
    en: "Move this module into {name}?",
    fi: "Siirretäänkö tämä moduuli kohteeseen {name}?",
  },
  "Move these modules into {name}?": {
    en: "Move these modules into {name}?",
    fi: "Siirretäänkö nämä moduulit kohteeseen {name}?",
  },
  "Move these courses and modules into {name}?": {
    en: "Move these courses and modules into {name}?",
    fi: "Siirretäänkö nämä kurssit ja moduulit kohteeseen {name}?",
  },
  "Move them here, or keep them where they are now.": {
    en: "Move them here, or keep them where they are now.",
    fi: "Siirrä ne tänne tai säilytä ne nykyisillä paikoillaan.",
  },
  "{course} · {place}": { en: "{course} · {place}", fi: "{course} · {place}" },
  "{module} · {place}": { en: "{module} · {place}", fi: "{module} · {place}" },
  "Selection changed": {
    en: "Selection changed",
    fi: "Valinta muutettu",
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
  Choice: { en: "Choice", fi: "Valintakohde" },

  Profiles: { en: "Profiles", fi: "Profiilit" },
  "New profile": { en: "New profile", fi: "Uusi profiili" },
  Name: { en: "Name", fi: "Nimi" },
  "{selected} selected · {completed} completed": {
    en: "{selected} selected · {completed} completed",
    fi: "valittuja: {selected} · suoritettuja: {completed}",
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
      fi: "Tämä on nykyinen profiilisi. Tilalle valitaan ensimmäinen jäljellä oleva profiili.",
    },
  Export: { en: "Export", fi: "Vie" },
  Import: { en: "Import", fi: "Tuo" },
  Overwrite: { en: "Overwrite", fi: "Korvaa" },
  "All saved data": { en: "All saved data", fi: "Kaikki tallennetut tiedot" },
  "Select which file to export": {
    en: "Select which file to export",
    fi: "Valitse vietävä tiedosto",
  },
  "Choose file": { en: "Choose file", fi: "Valitse tiedosto" },
  Choose: { en: "Choose", fi: "Valitse" },
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
  "This replaces the saved data of the profile “{name}” and makes it current.":
    {
      en: "This replaces the saved data of the profile “{name}” and makes it current.",
      fi: "Tämä korvaa profiilin ”{name}” tallennetut tiedot ja ottaa sen käyttöön.",
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
  "Invalid Sisu PDF plan": {
    en: "Invalid Sisu PDF plan",
    fi: "Sisu-suunnitelman PDF-tiedostoa ei voitu lukea",
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
  "Sisu import paused to preserve saved edits. Your profile is unchanged.": {
    en: "Sisu import paused to preserve saved edits. Your profile is unchanged.",
    fi: "Sisu-tuonti on keskeytetty tallennettujen muutosten säilyttämiseksi. Profiilisi säilyy ennallaan.",
  },
  "or drop a .json or .pdf file": {
    en: "or drop a .json or .pdf file",
    fi: "tai pudota .json- tai .pdf-tiedosto tähän",
  },
  "or drop a PDF print of your Sisu study plan or a JSON profile export": {
    en: "or drop a PDF print of your Sisu study plan or a JSON profile export",
    fi: "tai pudota Sisu-opintosuunnitelmasi PDF-tuloste tai profiilin JSON-tiedosto",
  },
  "This creates a new profile with these programmes: {names}.": {
    en: "This creates a new profile with these programmes: {names}.",
    fi: "Tämä luo uuden profiilin, jossa on nämä ohjelmat: {names}.",
  },
  "This replaces the saved data of the profile “{name}” with these programmes: {names}.":
    {
      en: "This replaces the saved data of the profile “{name}” with these programmes: {names}.",
      fi: "Tämä korvaa profiilin ”{name}” tallennetut tiedot näillä ohjelmilla: {names}.",
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
      fi: "Kurssiluettelossa ei ole tämän moduulin rakennetta, joten moduuli jätettiin pois. Sen kurssit, jotka löytyvät kurssiluettelosta, ovat sijoittamattomissa opinnoissa.",
    },
  "This course is not in the catalogue, so it was left out together with its completion.":
    {
      en: "This course is not in the catalogue, so it was left out together with its completion.",
      fi: "Tätä kurssia ei ole kurssiluettelossa, joten se jätettiin pois suoritusmerkintöineen.",
    },
  "No official match was found, so this item was left out.": {
    en: "No official match was found, so this item was left out.",
    fi: "Kohteelle ei löytynyt virallista vastinetta, joten se jätettiin pois.",
  },
  "Several official items match, so this item was left out.": {
    en: "Several official items match, so this item was left out.",
    fi: "Kohteelle löytyi useampi virallinen vastine, joten se jätettiin pois.",
  },
  "This module is matched by name after you choose the version of the module above it.":
    {
      en: "This module is matched by name after you choose the version of the module above it.",
      fi: "Moduuli tunnistetaan nimen perusteella, kun sen yläpuolisen moduulin versio on valittu.",
    },
  "Matching official items:": {
    en: "Matching official items:",
    fi: "Vastaavat viralliset kohteet:",
  },
  "Open Export and select a profile to download it as a .json file. All saved data downloads every profile and setting together. Exporting changes no profile.":
    {
      en: "Open Export and select a profile to download it as a .json file. All saved data downloads every profile and setting together. Exporting changes no profile.",
      fi: "Avaa Vie ja valitse profiili, niin lataat sen .json-tiedostona. Kun valitset Kaikki tallennetut tiedot, lataat kaikki profiilit ja asetukset yhtenä tiedostona. Vienti ei muuta profiileja.",
    },
  "A profile holds your language, selected and completed courses, and tab settings in this browser. A new profile starts as a copy of the open profile. Switching profiles leaves the open tab in place. Export a file to move your plan to another browser or device.":
    {
      en: "A profile holds your language, selected and completed courses, and tab settings in this browser. A new profile starts as a copy of the open profile. Switching profiles leaves the open tab in place. Export a file to move your plan to another browser or device.",
      fi: "Profiili sisältää kielen, valitut ja suoritetut kurssit sekä välilehtien asetukset tässä selaimessa. Uusi profiili luodaan avoimen profiilin kopiona. Profiilin vaihtaminen ei vaihda avointa välilehteä. Vie suunnitelma tiedostoon, jos haluat siirtää sen toiseen selaimeen tai laitteeseen.",
    },
  "Choose or drop one .json or .pdf file. A profile file creates a separate profile after confirmation, or overwrites the profile that already has its name. All saved data replaces every profile in this browser after confirmation. A Sisu capture or a supported Sisu plan PDF asks for a profile name, then places its choices and completions when Structure of studies loads its programmes. Cancel leaves saved data unchanged.":
    {
      en: "Choose or drop one .json or .pdf file. A profile file creates a separate profile after confirmation, or overwrites the profile that already has its name. All saved data replaces every profile in this browser after confirmation. A Sisu capture or a supported Sisu plan PDF asks for a profile name, then places its choices and completions when Structure of studies loads its programmes. Cancel leaves saved data unchanged.",
      fi: "Valitse tai pudota yksi .json- tai .pdf-tiedosto. Profiilitiedosto luo vahvistuksen jälkeen erillisen profiilin tai korvaa samannimisen profiilin. Kun valitset Kaikki tallennetut tiedot ja vahvistat, kaikki tämän selaimen profiilit korvataan. Sisu-kaappaus ja tuettu Sisu-suunnitelman PDF-tiedosto pyytävät profiilin nimen, ja niiden valinnat ja suoritusmerkinnät sijoitetaan, kun Opintojen rakenne lataa ohjelmat. Peruuta jättää tallennetut tiedot ennalleen.",
    },
  "A supported Sisu plan PDF imports the same way. In Sisu, open Structure of studies, choose ⋯ beside New study plan, choose Print study plan and save as PDF. The PDF is read in this browser. Official catalogue and structure reads use this site. Omitted items and their candidates are listed for you to check. Some modules may ask you to choose a version. The PDF contains personal identity data, so do not share it casually.":
    {
      en: "A supported Sisu plan PDF imports the same way. In Sisu, open Structure of studies, choose ⋯ beside New study plan, choose Print study plan and save as PDF. The PDF is read in this browser. Official catalogue and structure reads use this site. Omitted items and their candidates are listed for you to check. Some modules may ask you to choose a version. The PDF contains personal identity data, so do not share it casually.",
      fi: "Tuetun Sisu-suunnitelman PDF-tiedoston voi tuoda samalla tavalla. Avaa Sisussa Opintojen rakenne, valitse ⋯ Uusi opintosuunnitelma -painikkeen vierestä, valitse Tulosta opintosuunnitelma ja tallenna PDF. PDF luetaan tässä selaimessa. Virallisen kurssiluettelon ja rakenteen haut tehdään tällä sivustolla. Pois jätetyt kohteet ja niiden mahdolliset viralliset vastineet luetellaan tarkistettaviksi. Joidenkin moduulien kohdalla sinua voidaan pyytää valitsemaan versio. PDF sisältää henkilötietoja, joten älä jaa sitä huolettomasti.",
    },
  "Open your plan in Sisu's Structure of studies and expand every module. Copy Sisu import script copies a browser-console script. Read the":
    {
      en: "Open your plan in Sisu's Structure of studies and expand every module. Copy Sisu import script copies a browser-console script. Read the",
      fi: "Avaa suunnitelmasi Sisun Opintojen rakenne -näkymässä ja laajenna kaikki moduulit. Toiminto Kopioi Sisu-tuontiskripti kopioi selaimen konsolissa suoritettavan skriptin. Lue",
    },
  "whole script": { en: "whole script", fi: "koko skripti" },
  "before running it in that Sisu tab. It reads the open page and makes anonymous requests to the public Kori interface without Sisu login cookies. Import the downloaded sisu-plan-capture.json here and name the new profile. The file is read in this browser, not uploaded. Check the import's notices for items it could not place.":
    {
      en: "before running it in that Sisu tab. It reads the open page and makes anonymous requests to the public Kori interface without Sisu login cookies. Import the downloaded sisu-plan-capture.json here and name the new profile. The file is read in this browser, not uploaded. Check the import's notices for items it could not place.",
      fi: "ennen sen suorittamista kyseisellä Sisu-välilehdellä. Se lukee avoimen sivun ja tekee anonyymejä pyyntöjä julkiseen Kori-rajapintaan ilman Sisun kirjautumisevästeitä. Tuo ladattu sisu-plan-capture.json tähän ja nimeä uusi profiili. Tiedosto luetaan tässä selaimessa, eikä sitä lähetetä palvelimelle. Tarkista tuonnin ilmoituksista kohteet, joita ei voitu sijoittaa.",
    },

  "Course not in the catalogue": {
    en: "Course not in the catalogue",
    fi: "Kurssi ei ole kurssiluettelossa",
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
    fi: "Estetty, koska kurssi on suljettu pois",
  },
  "Inactive course": { en: "Inactive course", fi: "Ei-aktiivinen kurssi" },
  "Not enough active courses": {
    en: "Not enough active courses",
    fi: "Ei tarpeeksi aktiivisia kursseja",
  },
  "Too few positions": { en: "Too few positions", fi: "Liian vähän paikkoja" },
  "Unreachable bound": { en: "Unreachable bound", fi: "Saavuttamaton raja" },
  "Search too large": { en: "Search too large", fi: "Liian suuri haku" },
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
    fi: "Moduuliversion varavaihtoehto",
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
  "The serving dataset changed during the read": {
    en: "The serving dataset changed during the read",
    fi: "Palveltava tietoaineisto muuttui lukemisen aikana",
  },
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
  "Notice provider is missing": {
    en: "Notice provider is missing",
    fi: "Ilmoitusten tarjoaja puuttuu",
  },
  "Read cache provider is missing": {
    en: "Read cache provider is missing",
    fi: "Lukuvälimuisti puuttuu",
  },
  "Discovery cache provider is missing": {
    en: "Discovery cache provider is missing",
    fi: "Ehdotusten välimuisti puuttuu",
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
    fi: "Tallennetun selainprofiilin haun osio on virheellinen",
  },
  "Saved browser profile slice compare is invalid": {
    en: "Saved browser profile slice compare is invalid",
    fi: "Tallennetun selainprofiilin vertailun osio on virheellinen",
  },
  "Saved browser profile slice prerequisites is invalid": {
    en: "Saved browser profile slice prerequisites is invalid",
    fi: "Tallennetun selainprofiilin esitietojen osio on virheellinen",
  },
  "Saved browser profile slice discover is invalid": {
    en: "Saved browser profile slice discover is invalid",
    fi: "Tallennetun selainprofiilin ehdotusten osio on virheellinen",
  },
  "Saved browser profile slice structure is invalid": {
    en: "Saved browser profile slice structure is invalid",
    fi: "Tallennetun selainprofiilin rakenteen osio on virheellinen",
  },
  "A module cannot be added inside itself": {
    en: "A module cannot be added inside itself",
    fi: "Moduulia ei voi lisätä itsensä sisään",
  },
  "Structure programmes changed while adding a module": {
    en: "Structure programmes changed while adding a module",
    fi: "Rakenteen ohjelmat muuttuivat moduulia lisättäessä",
  },
  "Structure version selection changed while adding a module": {
    en: "Structure version selection changed while adding a module",
    fi: "Rakenteen versiovalinta muuttui moduulia lisättäessä",
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

/** One key of the wording resource. */
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

/** Return the localized label of one search method. */
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
