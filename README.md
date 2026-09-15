# Uređenje adresa Republike Hrvatske — geoprostorna baza podataka adresa

Praktični dio završnog rada iz kolegija **Geoprostorne baze podataka** (Građevinski fakultet Sveučilišta u Mostaru). Projekt obrađuje službene podatke o adresama Republike Hrvatske, objavljene prema INSPIRE modelu podataka (tema *Addresses*, AD), i priprema ih za analizu na razini ulica kroz niz Python skripti koje grade i pune geoprostornu SpatiaLite bazu podataka.

## Sadržaj

- [O projektu](#o-projektu)
- [Izvor podataka](#izvor-podataka)
- [Tijek obrade (pipeline)](#tijek-obrade-pipeline)
- [Struktura repozitorija](#struktura-repozitorija)
- [Preduvjeti](#preduvjeti)
- [Pokretanje](#pokretanje)
- [Rezultat](#rezultat)
- [Poznata ograničenja i napomene](#poznata-ograničenja-i-napomene)

## O projektu

Izvorni INSPIRE podaci o adresama dolaze de-strukturirani: naziv ulice, kućni broj, naselje i poštanski broj zajedno su zapisani unutar jednog niza znakova (stupac `alternativeIdentifier`, u kodu nazvan `alt_identifier`). Cilj projekta je taj zapis rastaviti natrag u zasebne, semantički jasne atribute adrese, koristeći kućni broj (stupac `designator`) kao referentnu točku za rastavljanje teksta.

Ideja rješenja zadana je od strane predmetnog nastavnika (upotreba `INSTR`/`SUBSTR` nad kućnim brojem), ali je u ovom radu provedena unutar **Python** okruženja umjesto izravno u SQL naredbama — sve operacije nad bazom (izrada sheme, upis, indeksiranje, geoprostorne funkcije) i dalje se izvode SQL naredbama, ali ih Python orkestrira i šalje SpatiaLite/SQLite motoru.

## Izvor podataka

- **Skup podataka:** INSPIRE tema *Addresses* (AD) za Republiku Hrvatsku
- **Format:** GML (Geography Markup Language)
- **Izvor:** Državna geodetska uprava (DGU), geoportal / Nacionalna infrastruktura prostornih podataka (NIPP)
- **Referentni koordinatni sustav izvornih podataka:** ETRS89 / LAEA Europe (EPSG:3035)

Izvorni podaci su podijeljeni u nekoliko odvojenih GML datoteka prema tipu objekta (adrese, nazivi ulica, poštanski brojevi, nazivi upravnih jedinica), koje su međusobno povezane referencama (`xlink:href`), a ne ugniježđivanjem.

## Tijek obrade (pipeline)

Obrada je podijeljena u zasebne, uzastopne korake — svaki s jasno definiranim ulazom i izlazom, što olakšava provjeru, ponovno pokretanje pojedinog koraka u slučaju pogreške i preglednost cjelokupnog rješenja.

| # | Skripta | Ulaz | Izlaz | Namjena |
|---|---|---|---|---|
| 0 | `describe_db.py` | postojeća SpatiaLite baza | ispis strukture/sadržaja baze | preliminarni pregled sheme i sadržaja baze prije daljnje obrade |
| 1 | `load_gml.py` | izvorne INSPIRE GML datoteke | `addresses.sqlite` | protočno (streaming) parsiranje GML-a i učitavanje slojeva (adrese, ulice, poštanski brojevi, upravne jedinice) u strukturiranu geoprostornu bazu |
| 2 | `restructure_addresses.py` | `addresses.sqlite` | `restructured_addresses.sqlite` | rastavljanje spojenog niza `alt_identifier` u zasebne atribute adrese (ulica, kućni broj, naselje, poštanski broj, grad) |
| 3 | `validate_restrucured.py` | `restructured_addresses.sqlite` | ispis izvještaja u konzoli | provjera potpunosti i kvalitete restrukturiranih podataka po atributima |

### Korak 1 — `load_gml.py`

- GML datoteke se protočno parsiraju (`xml.etree.ElementTree.iterparse`) element po element, bez učitavanja cijele datoteke u memoriju, čime se omogućuje obrada slojeva s do gotovo dva milijuna zapisa uz stabilnu potrošnju memorije.
- Iz svakog elementa izdvajaju se samo eksplicitno imenovani atributi (XPath izrazi prilagođeni imenskim prostorima `ad`, `gml`, `gn`, `base`), čime se izbjegava problem booleovih (T/F) atributa koji onemogućuju generičko učitavanje u pojedinim alatima (npr. QGIS DB Manager).
- Podaci se upisuju u serijama (*batch* upis, 10 000 zapisa za sloj adresa) radi brzine.
- Geometrija adresne točke pohranjuje se kao WKT zapis (`POINT(x y)`) i pretvara funkcijom `GeomFromText` uz SRID 3035.
- Na kraju se grade indeksi nad poveznim stupcima te prostorni indeks (`CreateSpatialIndex`) nad stupcem geometrije.

### Korak 2 — `restructure_addresses.py`

Funkcija `parse_address` rastavlja `alt_identifier` po sljedećoj logici:

1. pronalazi se pozicija „razmak + kućni broj" unutar niza → sve prije toga je **naziv ulice**;
2. prvi sljedeći token nakon kućnog broja izdvaja se kao **puni oblik kućnog broja** (`house_number_full`, može uključivati slovne dodatke);
3. u preostalom tekstu traži se peteroznamenkasti token → **poštanski broj**;
4. tekst prije poštanskog broja → **naselje**; tekst nakon njega → **grad** (upravna jedinica).

Ako neka komponenta ne može biti pronađena, funkcija za nju upisuje `None` umjesto da prekine izvođenje — ostale, uspješno prepoznate komponente ipak se zapisuju. Izvorna i ciljna baza povezane su naredbom `ATTACH DATABASE`; podaci se čitaju u serijama od 50 000 zapisa (`LIMIT`/`OFFSET`), a geometrija se prenosi nepromijenjena. Poveznica na izvorni zapis čuva se kroz `gml_id` radi sljedivosti.

### Korak 3 — `validate_restrucured.py`

Za svaki atribut (ulica, kućni broj — puni i osnovni oblik, naselje, poštanski broj, grad, geometrija) broji se udio praznih/`NULL` vrijednosti (nakon `TRIM`), ispisuje se status (`OK` / `MISSING`) te se za atribute s nedostacima ispisuje uzorak (do 10) problematičnih zapisa radi ručne dijagnostike. Na kraju se ispisuje sažetak broja atributa s nedostacima i broj distinct vrijednosti po atributu.

## Struktura repozitorija

```
.
├── describe_db.py                 # pregled strukture/sadržaja postojeće baze
├── load_gml.py                    # korak 1 — učitavanje GML → addresses.sqlite
├── restructure_addresses.py       # korak 2 — rastavljanje adresa → restructured_addresses.sqlite
├── validate_restrucured.py        # korak 3 — validacija restrukturiranih podataka
├── addresses.sqlite               # (generirano) izlaz koraka 1
├── restructured_addresses.sqlite  # (generirano) izlaz koraka 2
└── README.md
```

> Napomena: nazivi i lokacije ulaznih GML datoteka nisu bili navedeni u dostupnoj dokumentaciji projekta — prilagodi putanje u `load_gml.py` prema stvarnom rasporedu preuzetih datoteka.

## Preduvjeti

- Python 3.x
- Python biblioteka `spatialite` (sučelje prema SpatiaLite proširenju za SQLite)
- SpatiaLite proširenje instalirano i dostupno SQLite motoru
- Standardne biblioteke: `xml.etree.ElementTree`, `os`, `time`, `sys`

Instalacija Python ovisnosti (primjer):

```bash
pip install spatialite
```

## Pokretanje

Skripte se pokreću redom, jer svaki korak ovisi o izlazu prethodnog:

```bash
python load_gml.py
python restructure_addresses.py
python validate_restrucured.py
```

Po potrebi, strukturu i sadržaj generirane baze moguće je pregledati alatom:

```bash
python describe_db.py
```

## Rezultat

Krajnji rezultat pipeline-a je `restructured_addresses.sqlite` — geoprostorna baza podataka u kojoj je svaka hrvatska adresa predstavljena jednim zapisom s razdvojenim, čitljivim atributima (ulica, kućni broj, naselje, poštanski broj, grad) i pripadajućom geometrijom, pogodna za pretraživanje, statističku analizu i vizualizaciju (npr. u QGIS-u).

## Poznata ograničenja i napomene

- Rastavljanje adrese oslanja se na pretpostavljeni, ali ne i formalno zajamčen obrazac zapisa unutar `alt_identifier` — otuda i potreba za korakom validacije.
- Zapisi kod kojih rastavljanje ne uspije u potpunosti (npr. nedostaje poštanski broj) ne prekidaju obradu — za tu komponentu jednostavno se upisuje prazna vrijednost.
- Pri izradi i uređivanju koda kao pomoćni alat korišten je Claude AI unutar VS Code okruženja.

---

*Ovaj README opisuje praktični (metodološki) dio završnog rada "Uređenje adresa Republike Hrvatske", kolegij Geoprostorne baze podataka.*
