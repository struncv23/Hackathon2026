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
- `constants.py` — ceny vylepseni a hodnoty figurek.

Po spusteni se zobrazi hlavni menu. Z nej lze spustit/pokracovat ve hre,
zacit novou hru nebo aplikaci ukoncit. Behem partie vede tlacitko **Menu**
nebo klavesa **Esc** zpet do menu; pokud je vybrana figurka, prvni Esc vyber
jen zrusi.

## Kampan

- Hra zacina levelem 1 na standardni sachovnici 8 x 8 se zakladnimi 16
  figurkami na kazde strane. Nahodne armady a RPG nabor jsou vypnute.
- Vyhra v prvnim levelu nastane, kdyz souper prijde alespon o polovinu sveho
  pocatecniho tymoveho zdravi (HP). Pri standardni sestave je cil 2050 HP.
  Po vyhre se odemkne level 2; odemceni zustane ulozene i po restartu hry.
- Level 2 je RPG mapa 25 x 25. Kazde strane se nahodne prida dalsich 20
  figurek (bez dalsiho krale), po cele mape na volna pole. Vyhra nastane,
  kdyz souper ztrati vsechny figurky.
- Koleckem mysi lze priblizovat a oddalovat zobrazeni; deska se sama
  neposouva.
- V levelu 2 muze bily hrac naverbovat pesaka, kone, strelce, vez nebo damu.
  Cena je dvojnasobek hodnoty figurky; nova jednotka se objevi na volnem poli
  pobliz bile zakladny. Nakup spotrebuje tah a cerny bot nakupovat nemuze.
- Maximalni tymove HP se pri zahajeni vypocita z nasazene armady a pri nakupu
  se zvysi o maximalni HP nove jednotky.

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
- Bezny utok dava polovinu hodnoty utocici figury: pesec 50, kun/strelec
  150, vez 250, dama 450, kral 100 poskozeni. Dama porazi na jeden zasah
  pesce, kone a strelce, ale ne vez ani damu. Pri vyrazeni figury klesne
  tymove zdravi o jeji zbyvajici HP a utocnik ziska coiny podle jeji hodnoty.
- Maximalni HP a odmena za vyrazeni: pesec 100, kun/strelec 300,
  vez 500, kral 200, dama 900.
- Upgrady muze kupovat a pouzivat pouze bily hrac. Kupuje se pro vybranou
  figuru a aktivuje se pri jejim kazdem tahu. Mina dava 200 HP poskozeni, odrazeny strelec
  ubere prvni dalsi figure na diagonale 99 HP a rentgen veze ubere vsem
  figuram v rade/sloupci 199 HP. Schopnosti poskozuji i vlastni figury.
- Upgradovana dama doplni vlastnimu kralovi HP na maximum pri utoku na
  souperova krale. Upgradovany kral vytvori pesce na volnem poli pred sebou.
- Vybrana bila dama muze byt obetovana; jeji zbyvajici HP se prida do
  tymoveho zdravi bileho hrace. Bot nepouziva upgrady ani schopnosti.
- V levelu 1 rozhoduje ztrata alespon poloviny pocatecniho tymoveho HP; v
  levelu 2 je potreba odstranit vsechny souperovy figurky. Sach a pat se
  nepouzivaji.
- `Ctrl+Z` nebo tlacitko **Vratit tah** vrati posledni tah nebo nakup
  upgradu/naboru vcetne HP, min, penez a figurek.
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
