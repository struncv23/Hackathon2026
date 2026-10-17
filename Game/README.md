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
zacit novou hru nebo aplikaci ukoncit. Behem partie vede tlacitko **Menu**
nebo klavesa **Esc** zpet do menu; pokud je vybrana figurka, prvni Esc vyber
jen zrusi.

## Kampan

- Hra zacina uvodni valkou na sachovnici 8 x 8. Vyhrat lze porazenim krale
  nebo ztratou ctvrtiny tymoveho zdravi soupere. Kralovstvi lze spustit primo
  z menu; tlacitko **Restartovat kralovstvi** zalozi novou kampan.
- Kralovstvi je pruzkumna mapa 20 x 20 se dvema kraly, plnym tymovym zdravim
  30 000 HP a 350 mincemi na kazde strane. Klasicka cast zustava oddelena.
- Poklady s hodnotou 300 az 1500 minci se objevuji na mape. Vzdy je aktivni
  jen jeden; kazdy dalsi nalezeny ma vyssi hodnotu. Sbira ho kral.
- Mapa kralovstvi vyplnuje obrazovku bez praveho panelu. Kral, farmy, mesto i
  zbrojnice jsou na jedne mape; kazda budova ma pudorys 3 x 4 pole.
- Pokus krale vstoupit do pudorysu budovy rovnou otevre celou obrazovku obchodu;
  kral zustane stat pred budovou. Farmu lze koupit rovnou kliknutim.
- Prvni nakup za 250 minci odemkne farmarsky sektor a zalozi prvni farmu.
  Mesto lze koupit az po trech farmach; zbrojnice az po meste a trech vojaccich.
- Kazda farma prubezne generuje 3 mince za sekundu realneho casu.
  Hrac i bot si tak vydelavaji soucasne.
- Figuru lze vybrat kliknutim, pretahnout mysi nebo posouvat kralem pomoci WASD.
  Mesto najima pouze pesaky za 800 minci, bez dalsiho potvrzeni.
  Tahem prazdneho mista se posouva cela mapa; koleckem mysi se meni zoom.
- Mesto stoji 900 minci po splneni podminky tri farem a odemyka primy najem
  pesaku za 800 minci. Vylepseni musi jit po rade pesec, kun, strelec, vez, dama.
  Armada ma limit 16 jednotek; pesce lze vylepsit na silnejsi figuru.
- Zbrojnice stoji 3 000 minci. V ni se vybere velikost oddilu (1-8); do bitvy
  se berou nejsilnejsi dostupne jednotky. Padem armady souper prijde o jednotky,
  prezivsi se vraci a vitez ziska 250 minci navic.
- Hrac i bot rozvijeji kralovstvi soucasne. Bot postupne kupuje farmy, odemyka
  mesto, buduje a vylepsuje armadu a stavi zbrojnici; utoci vlastnim kralem na
  poklady. Obtiznost ridi i hloubku jeho sachovych tahu.
- Ekonomicke tahy nelze vratit.

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
  lehka (~100 Elo), stredni (~200 Elo) a tezka (~400 Elo). Jde o herni
  odhad, ne o oficialni ekvivalenci chess.com ratingu; tezka obtiznost
  prohledava tahy do vetsi hloubky. Pred tahem premysli nahodne 1 az 3
  sekundy; behem cekani se zobrazuje stav premysleni a hra zustava ovladatelna.
- Maximalni HP a odmena za vyrazeni: pesec 50, kun/strelec 150,
  vez 250, kral 600, dama 450.
- Bezny utok dava polovinu hodnoty utocici figury: pesec 25, kun/strelec
  75, vez 125, dama 200, kral 300 poskozeni. Dama porazi krale na tri zasahy.
  Hra konci ihned po porazce krale, neni nutne dobirat zbytek armady.
  Pri vyrazeni figury klesne
  tymove zdravi o jeji zbyvajici HP a utocnik ziska coiny podle jeji hodnoty.
- Upgrady muze kupovat a pouzivat pouze bily hrac. Kupuje se pro vybranou
  figuru a aktivuje se pri jejim kazdem tahu. Mina dava 200 HP poskozeni, odrazeny strelec
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
  nad zasazenym polem.

Vlastni efekt lze dodat rendereru pres rozhrani `Effects`:

```python
from Game.app import ChessApp

app = ChessApp(effects=MyEffects())
app.run()
```

`MyEffects` ma implementovat metodu `draw(surface, rect, *, selected, checked, time_seconds)`.
Pro GPU shadery bude potreba nahradit nebo rozsirit renderer; aktualni vykreslovani
je zamerne zalozene na Pygame 2D kresleni.
