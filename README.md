# Samira, Yone и Miss Fortune в Isaac

Локальная тестовая сборка **0.5.47** включает Samira, Yone и Miss Fortune. [Воспроизводимая сборка Windows ZIP и проверка](docs/PORTABLE-BUILD.md). Проверку в игре выполняет тестер; сборщик игру не запускает.

[Скачать тестовую Windows-сборку с МФ 0.5.47](https://github.com/AverDroz/Soul-Fighter-Samira/releases/tag/mf-v0.5.47) · [Исправления и игровой прогон](docs/MISS-FORTUNE-0.5.47.md) · [Установка и запуск](docs/INSTALL.md)

Личный мод для The Binding of Isaac: Repentance+ с REPENTOGON. **Samira выбирается в меню персонажей** и начинает с трёх красных сердец и базовыми характеристиками Isaac. Мод добавляет управление мышью и QWER, ранги стиля, 73 предмета LoL, магазин компонентов и рюкзак на шесть слотов. [Запуск и управление](src/samira-testroom/README.md)

**Ёнэ** доступен в том же меню как отдельный персонаж с ближним боем, QWER и эмоциями на Ctrl+1–4. Ctrl+6 показывает значок мастерства со звуком и работает независимо от боя. [Управление и установка Ёнэ](docs/YONE.md)

**В 0.3.1** нативные залпы поворачиваются к цели с сохранением разброса и свойств оружия. Ранг стиля виден рядом с QWER, готовность R подсвечивает края экрана. Сложность растёт со стороны противников в забегах за персонажа Samira. [Механика боёв](docs/DESIGN.md)

Механики работают внутри игры. Внешний рендер показывает модель Soul Fighter, полный набор анимаций, эффекты и звук. Без него для Самиры доступны встроенные спрайты ходьбы и стойки. [Импорт модели](docs/SOUL-FIGHTER.md) · [Аудио](docs/SOUL-FIGHTER-AUDIO.md)

| Путь | Содержимое |
| --- | --- |
| `src/samira-testroom/mod/` | Актуальный мод и его игровые ресурсы |
| `src/samira/external/` | Модули внешнего рендера, звука и связи с игрой |
| `assets/samira-soul-fighter/` | Материалы Soul Fighter, модель с 89 анимациями и атрибуция |
| `docs/DESIGN.md`, `docs/BACKLOG.md` | Текущая механика и план работ |
| `docs/` | Срез каталога Riot, правила адаптации, источники рецептов и иконок |
| `src/samira/`, `vendor/` | Исторический каркас TFOS4 Isaac-LoL-HeroStudio и исходные пакеты |
| `tools/`, `work/` | Проверки и генераторы, локальные зависимости, логи и превью |

## Проверка 0.3.1

Игрок тестировал 0.3.0 в Repentance+ с REPENTOGON. Для 0.3.1 используются симуляции Lua и проверки внешнего рендера. После установки сборки и перезапуска игры и рендера предстоит перепроверить диагональное прицеливание, HUD и сложность боёв.

Из корня проекта:

```text
python tools/check_samira_combat.py
python tools/check_samira_weapons.py
python tools/check_samira_style.py
python tools/check_samira_style_hud.py
python tools/check_samira_kills.py
python tools/check_samira_items.py
python tools/check_samira_items_room.py
python tools/check_samira_inventory.py
python tools/check_samira_inventory_hud.py
```

Проверки Lua используют Lupa из `work/python-deps`. Для раннего каркаса сохранились отдельный `tools/audit_project.py` и [исторический аудит](docs/REUSE-AUDIT.md).

Исходные модель, звуки и прочие материалы LoL принадлежат Riot Games. Указания авторов и лицензии зависимостей сохранены.
