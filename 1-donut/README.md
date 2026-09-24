# 1 – Donut, šálek a podšálek

![Náhled](donut-preview.png)

Scéna podle tutoriálu **Blender Guru**:

- [Blender Donut Tutorial Part 1 (2026)](https://www.youtube.com/watch?v=-tbSCMbJA6o)
- [Part 2, Level 3: Complete Modelling](https://www.youtube.com/watch?v=SBtDix7xGOg&list=PLjEaoINr3zgEt_DatH4t_A3u1PpLkK4Lm)

## Soubory

| Soubor | Popis |
| --- | --- |
| `donut.blend` | Blender soubor se scénou (Blender 5.0+) |
| `donut-preview.png` | Render scény (Cycles, 1600 × 1000) |
| `build_donut.py` | Skript, který scénu vygeneruje znovu |

## Postup modelování (principy z videa)

**Donut**
1. Torus (48 × 24 segmentů) + modifikátor *Subdivision Surface*.
2. Nepravidelný tvar: body posunuté „proportional editingem“ (šum podél normál), donut je lehce zploštělý.
3. Materiál těsta: tmavší nahoře a dole, světlejší proužek uprostřed.

**Poleva (Icing)**
1. Duplikát horní poloviny donutu (*Shift+D*, *P → Selection*).
2. Stékající kapky: vybrané body okraje stažené dolů.
3. Modifikátory: *Subdivision Surface → Shrinkwrap* (na donut) *→ Solidify* (tloušťka ~3 mm).

**Posypka (Sprinkles)**
1. Kolekce `Sprinkles` s 6 barevnými posypkami (válec se zaoblenými konci). Kolekce je skrytá.
2. *Geometry Nodes* na polevě: *Distribute Points on Faces* (Poisson) jen na plochách, které míří nahoru,
   *Instance on Points* s *Pick Instance*, náhodná rotace kolem normály a náhodná velikost.

**Šálek**
1. Profil válce: vytlačení (*extrude*), zúžení, okraj a vnitřní stěna. Tloušťka stěny je modelovaná.
2. Ucho: dvě plochy na boku se vytlačí ven, smažou a spojí přes *Bridge Edge Loops*
   (14 řezů, smoothness).
3. *Subdivision Surface*, *Shade Smooth*, bílý keramický materiál. Uvnitř je káva.

**Podšálek**
1. Profil válce s prohlubní pro šálek, zvednutým okrajem a spodní nožkou.
2. *Subdivision Surface* a stejný keramický materiál.

**Scéna:** dřevěný stůl (procedurální textura), 3 plošná světla (key, fill, rim), kamera 55 mm s hloubkou ostrosti, render v Cycles.

## Jak vygenerovat znovu

```bash
# s nainstalovaným Blenderem 5.x
blender -b -P build_donut.py

# nebo s Python modulem bpy (Python 3.11)
pip install bpy==5.0.1
python build_donut.py              # uloží donut.blend a vyrenderuje donut-preview.png
python build_donut.py --no-render  # jen donut.blend
```
