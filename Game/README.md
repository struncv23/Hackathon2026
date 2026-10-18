# Struktura hry

Spusteni z korenove slozky projektu:

```powershell
.\.venv\Scripts\python.exe main.py
```

Zavislosti jsou uvedene v `requirements.txt`.

## Komponenty

- `constants.py` — rozmery sachovnice a sdilene konstanty.
- `models.py` — datove modely `Piece` a `Move`.
- `rules.py` — stav hry, legalni tahy a sachova pravidla bez zavislosti na Pygame.
- `app.py` — hlavni smycka, vstup z klavesnice/mysi a herni panel.
- `renderer.py` — vykresleni sachovnice a figurek.
- `effects.py` — rozhrani a vychozi efekt pro oznacene pole a sach.
- `constants.py` — rozmery, ceny a hodnoty figurek.
- `campaign.py` — ekonomika, mesta, farmy, armady a ulozeni kralovstvi.

Po spusteni se zobrazi hlavni menu. Z nej lze spustit/pokracovat ve hre,
zacit novou hru nebo aplikaci ukoncit. Behem partie otevre tlacitko **Pauza**
nebo klavesa **Esc** pauzu; pokud je vybrana figurka, prvni Esc vyber jen
zrusi. V pauze lze pokracovat, vratit se do hlavniho menu a nastavit hlasitost
hudby na pozadi i zvuku menu; obe hlasitosti se ulozi pro dalsi spusteni.

## Kampan

- Hra zacina uvodni valkou na sachovnici 8 x 8. Vyhrat lze pouze zabitim
  souperova krale; snizeni tymoveho zdravi ani zajeti damy samo o sobe hru
  neukonci. Figurky v teto uvodni casti maji polovinu bezneho maxima HP,
  aby byly souboje rychlejsi. V uvodni casti nelze kupovat ani obetovat
  figurky; bot se nejvice soustredi na utoky na hracova krale. Kralovstvi lze
  spustit primo z menu; tlacitko
  **Restartovat kralovstvi** zalozi a hned spusti novou kampan. Tlacitko
  **Nova hra** spusti vybranou cast i behem rozehrane partie.
- Po vitezstvi v uvodni valce sachove figurky okamzite zmizi a spusti se
  standardni zacatek kampane jako pri vyberu kralovstvi v menu; kral se tedy
  objevi na vychozim poli kampane a zustava pocatecni rozpocet i mapa.
  Zobrazeni zacne priblizenim na bileho krale a behem 4,5 sekundy se plynule
  oddali. Bila kralovska postava pod sachovnici zmizi, cerna postava nahore
  zustane.
- V kampani si kralove vymenuji kratke hlasky.
  Behem hry je kazda replika videt ctyri sekundy a potom na ctyri sekundy zmizi.
  Uvodni dialogy drzi dej jako zvrat a neprozrazuji kralovstvi pred prechodem.
  Figurky i sachovnice maji retro pixelovy styl a dialogy funguji cesky i
  anglicky podle zvoleneho jazyka. V uvodni bitve bot utoci hlavne na bileho
  krale, ale zaroven hleda bezpecne tahy pro sve figurky a chrani cerneho
  krale pred okamzitym zajetim.
- Kralovstvi je pruzkumna mapa 20 x 20 s hracovym kralem, plnym tymovym zdravim
  30 000 HP a 450 mincemi; souperuv kral na mape neni, ale souper penize nema
  a stavby i armadu
  porizuje zdarma. Klasicka cast zustava oddelena.
- Na mape jsou standardne tri bezne mince; kazda ma 60 % puvodni hodnoty
  (36 minci pred nasobenim poctem farem) a kazda se po sebrani samostatne doplni
  za jednu sekundu na nahodnem volnem policku. Lektvary se objevi az spolu
  se zombiky, drzi se jich az tri
  a kazdy se po sebrani samostatne doplni za jednu sekundu; kral kazdym obnovi
  az 150 HP, nejvyse do maxima.
  Truhla pres 4 pole se objevi az po naverbovani alespon dvou figurek do armady;
  pak se nahodne objevi v prostrednim pasmu (radky 7-14) a zustane tam i po
  ulozeni hry.
  Bezna mince se znovu objevi na nahodnem volnem poli v radcich 7-14.
  Hlida ji sestava bossu, ktera se meni podle obtiznosti a velikosti tve armady;
  na zacatku jich je mene a pri postupu kampani jich muze byt az ctyri.
- Pokus kralem vstoupit na truhlu otevre vyber armady. Nasadis nejvyse 4 sve
  figurky a nepratele uvidis az po stisku **Hrat**; pak bojujete na sachovnici
  6 x 6 proti botovi. Vitez ziska 3 minuty prijmu z vlastnich farem a prezivsi
  jednotky; pri prohre prijde o vsechny nasazene figurky. Truhla se po vyhre
  uz znovu neobjevi.
- Mapa kralovstvi vyplnuje obrazovku bez praveho panelu. Kral, farmy, mesto i
  zbrojnice jsou na jedne mape; kazda budova ma pudorys 3 x 4 pole.
- Kazda postavena farma se zobrazi jako pestovany pozemek v jednom z 12 poli
  farmy; kazda druha prida sklad. V meste se zobrazuji jednotky a po kazdych
  dvou pribyva veze a dalsi uroven mesta.
- Pokus krale vstoupit do pudorysu budovy rovnou otevre celou obrazovku obchodu;
  kral zustane stat pred budovou. Farmu lze koupit rovnou kliknutim.
- Prvni farma stoji 250 minci; cena kazde dalsi roste o 400 minci
  (250, 650, 1 050 ... az 4 650). Lze postavit maximalne 12 farem.
  Mesto lze koupit az po trech farmach; zbrojnice az po meste a trech vojaccich.
- Kazda farma prubezne generuje 3 mince za sekundu realneho casu.
  Prijem dostava pouze hrac.
- Figuru lze vybrat kliknutim, pretahnout mysi nebo posouvat kralem pomoci WASD.
  Mesto najima armadu; pesec stoji 16 000 minci.
  Tahem prazdneho mista se posouva cela mapa; koleckem mysi se meni zoom.
- Mesto stoji ctyrnasobek puvodni ceny (3 600 minci) po splneni podminky tri
  farem a odemyka najem armady za vyssi ceny; zakladni ceny najmu jsou navysene
  20x. Vylepseni musi jit po
  rade pesec, kun, strelec, vez, dama a stoji 100x puvodni cenu.
  Armada ma limit 16 jednotek; pesce lze vylepsit na silnejsi figuru.
- Zbrojnice stoji 3 000 minci. Bitva probiha na sachovnici 8 x 8 proti tahu
  cerneho bota; vybere se velikost oddilu (1-8) a nasadi nejsilnejsi jednotky.
  Padem armady souper prijde o jednotky,
  prezivsi se vraci a vitez ziska 250 minci navic pro hrace.
- Hrac i bot rozvijeji kralovstvi soucasne. Bot postupne bez placeni stavi farmy,
  mesto, zbrojnici a buduje i vylepsuje armadu; jeho kral poklady nesleduje.
  Po vystaveni mesta se objevi dva pesaci, pozdeji az tri. Zustanou stat;
  kralem lze porazit jednoho za sekundu. Porazeny pesec se po jedne sekunde
  znovu objevi na nahodnem volnem poli, ostatni pesaci zustanou na svych mistech.
  Po smrti krale se zobrazi duvod porazky a volby pro restart
  kampane nebo navrat do hlavniho menu; automaticky se neoživí.
  Rozvoj bota je casove zpomaleny.
  Hrac nema pristup do obchodu ani na brany nepratelskych budov.
- Bot zacne s rozvojem az po 10 sekundach realneho casu; dalsi farmu stavi
  nejdrive za 12 sekund, mesto az po trech farmach a s dalsi prodlevou.
  Stara ulozena kralovstvi se pri prechodu na novy system vrati se souperem
  bez rozvinutych budov a armady, aby se zpomaleni projevilo hned.
- Po kralovstvi pronasleduji kralovy dve az tri pohyblive hlidky. Pohybuji se
  primo za kralem, pri prvnim dosahu hned zautoci za 200 HP a dalsi utok
  provedou po trech sekundach. Kral je muze porazit jednim zasahem; po porazce
  se po jedne sekunde znovu objevi u mesta.
  Mince a prijem z farem patri pouze hraci. Obtiznost ridi i hloubku tahu bota.
- Ekonomicke tahy nelze vratit.
- Behem obou casti se v pravem dolnim rohu postupne zobrazuji kratke napovedy
  k ovladani, utokum, nakupum, vylepsenim, farme, mestu, lektvarum, zombikum
  a bitvam. Pri vstupu do kralovstvi navod doporuci koupit prvni farmu za
  250 minci; dalsi vysvetleni se zobrazi pred otevrenim jejiho nakupu.
  Tlacitkem **Navody: zapnuto/vypnuto** v hlavnim menu lze vsechny navody
  vypnout nebo znovu zapnout. Volba zustava ulozena i po restartu hry.
  Zavri jednotlive navody tlacitkem X. V hlavnim menu lze prepinat cestinu a
  anglictinu; zvoleny jazyk se uklada pro dalsi spusteni.
- Rezim **Hardcore** lze zapnout v hlavnim menu. Tahy v nem nelze vracet;
  pokud zombici zabiji krale, neni dostupne tlacitko pro opakovani a ulozene
  kralovstvi nelze z menu restartovat. Hardcore lze vypnout, ale vypnuti
  smaze dosavadni kampan a druhou cast hry zacne od zacatku.
- V uvodni valce neni tlacitko **Vratit tah** ani moznost kupovat schopnosti
  figurek. Vylepseni figurek se porizuji az ve meste kralovstvi.
- Pri priblizeni mapy se kamera drzi krale uprostred, dokud to dovoluje okraj
  sachovnice. U okraje se kamera zastavi tak, aby kral zustal viditelny a zaroven
  zustala v zaberu sachovnice; pohyb kamery je plynuly i pri rychlych tazich
  krale a rucni posun kamery krale neschova.

## Vymena textur

Deska a pozadi se vykresluji oddelene a stejne textury se pouzivaji v obou
levelech. Pro vlastni obrazky vytvor slozku `assets/textures/` v korenove
slozce projektu a vloz do ni:

- `board.png` — textura jednotlivych poli sachovnice; svetla a tmava pole se
  automaticky barevne odlisi.
- `background.png` — textura pozadi kolem sachovnice.

Obrazky se nactou pri spusteni hry. Pokud soubory chybi, pouziji se generovane
textury; pro vymenu staci nahradit PNG soubory a hru znovu spustit.

## RPG pravidla

- Bily hrac hraje proti botovi za cerne. Bot ma tri orientacni obtiznosti:
  lehka (~100 Elo), stredni (~200 Elo) a tezka+. Uvedene hodnoty jsou pouze
  orientacni, nejde o oficialni ekvivalenci s ratingem chess.com. Tezka obtiznost
  prohledava sirsim stromem do vetsi hloubky a prodluzuje takticky vynucene
  vymeny. Pred tahem premysli nahodne 1 az 3
  sekundy; behem cekani se zobrazuje stav premysleni a hra zustava ovladatelna.
- Maximalni HP a odmena za vyrazeni: pesec 50, kun/strelec 150,
  vez 250, kral 600, dama 300.
- Bezny utok dava polovinu hodnoty utocici figury: pesec 25, kun/strelec
  75, vez 125 a kral 300 poskozeni; oslabena dama dava jen 100. Jeji
  vlastnosti jsou stejne v uvodni hre i v bitvach a krale porazi na sest zasahu.
  Hra konci ihned po porazce krale, neni nutne dobirat zbytek armady.
  Pri vyrazeni figury klesne
  tymove zdravi o jeji zbyvajici HP a utocnik ziska coiny podle jeji hodnoty.
- Upgrady muze kupovat a pouzivat pouze bily hrac. Kupuje se pro vybranou
  figuru za 100x puvodni cenu; nakup dalsi figurky stoji 20x puvodni cenu.
  Upgrade se aktivuje pri kazdem tahu figury. Mina dava 200 HP poskozeni,
  odrazeny strelec
  ubere prvni dalsi figure na diagonale 99 HP a rentgen veze ubere vsem
  figuram v rade/sloupci 199 HP. Schopnosti poskozuji i vlastni figury.
- Upgradovana dama doplni vlastnimu kralovi HP na maximum pri utoku na
  souperova krale. Upgradovany kral vytvori pesce na volnem poli pred sebou.
- Vybrana bila dama muze byt obetovana; jeji zbyvajici HP se prida do
  tymoveho zdravi bileho hrace. Bot nepouziva upgrady ani schopnosti.
- V uvodni valce rozhoduje ztrata alespon poloviny pocatecniho tymoveho HP;
  v bitve kralovstvi je potreba porazit souperova krale. Sach a pat se
  nepouzivaji a pesec se nepromenuje.
- `Ctrl+Z` nebo tlacitko **Vratit tah** vrati bojovy tah vcetne HP, min,
  penez a figurek. Ekonomicke tahy kampane vratit nelze.
- Pokud hrac nema zadny dostupny tah, muze stisknout `P` a tah preskocit.
- Zasahy kratce animuji ubytek HP, tymovy ukazatel zdravi a cislo poskozeni
  nad zasazenym polem. Tahy figurek se plynule presouvaji a hra obnovuje obraz
  az 90krat za sekundu.

Vlastni efekt lze dodat rendereru pres rozhrani `Effects`:

```python
from Game.app import ChessApp

app = ChessApp(effects=MyEffects())
app.run()
```

`MyEffects` ma implementovat metodu `draw(surface, rect, *, selected, checked, time_seconds)`.
Pro GPU shadery bude potreba nahradit nebo rozsirit renderer; aktualni vykreslovani
je zamerne zalozene na Pygame 2D kresleni.
