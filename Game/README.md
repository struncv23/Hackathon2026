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

Po spusteni se zobrazi hlavni menu. Z nej lze spustit/pokracovat ve hre,
zacit novou hru nebo aplikaci ukoncit. Behem partie vede tlacitko **Menu**
nebo klavesa **Esc** zpet do menu; pokud je vybrana figurka, prvni Esc vyber
jen zrusi.

Vlastni efekt lze dodat rendereru pres rozhrani `Effects`:

```python
from Game.app import ChessApp

app = ChessApp(effects=MyEffects())
app.run()
```

`MyEffects` ma implementovat metodu `draw(surface, rect, *, selected, checked, time_seconds)`.
Pro GPU shadery bude potreba nahradit nebo rozsirit renderer; aktualni vykreslovani
je zamerne zalozene na Pygame 2D kresleni.
