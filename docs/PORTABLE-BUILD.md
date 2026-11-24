# Локальная переносимая Windows-сборка 0.5.47

Тестовую сборку собирают из текущего checkout. Игра и REPENTOGON в архив не входят. Скрипт ничего не устанавливает и не запускает игру/рендер.

Из корня проекта в PowerShell:

```powershell
python tools/export_samira.py --output ../../outputs --staging-area ../mf-package-final-0547 --include-local-mf --include-local-yone --python-runtime 'C:/Users/Mortem ad Deos/samira айзек/work/export-runtime/python' --dependency-archive ../nikromant-v27-release/Soul-Fighter-Samira-Yone-v27-Windows.zip
python tools/verify_portable.py ../../outputs/Soul-Fighter-Miss-Fortune-0.5.47-Windows-Test.zip --package-root ../mf-package-final-0547/Soul-Fighter-Samira
```

`--staging-area` должен указывать на новую папку. Для повторной сборки выбери другое имя. Версия берётся из `src/samira-testroom/mod/metadata.xml`; `--version` позволяет явно задать версию, но проверка архива требует её совпадения с metadata.xml.

`--python-runtime` — подготовленный переносимый Python x64 с NumPy, Pillow, ModernGL и GLFW. Его лицензии/уведомления сохраняются. `--dependency-archive` — предыдущая переносимая сборка: из неё берутся только модель, rig/actions и звуки Ёнэ из `companion/assets/yone-local/`. Старый код, настройки, Lua и остальные ресурсы из неё не переносятся. Локальный `--yone-assets` может дополнять/заменять эти материалы. MF и Samira берутся из текущего checkout.

В архиве находятся три персонажа: Samira, Yone и Miss Fortune. Нативный мод расположен в `samira_testroom/`, переносимый Python и внешний рендер — в `companion/`. MF-эффекты дополнительно доступны по пути Companion `src/samira-testroom/mod/resources/gfx/mf/`. Пакет сохраняет исходные идентификаторы `Soul-Fighter-Samira` и `samira_testroom`, чтобы запускатель обновлял тот же мод.

`BUILD.json` записывает версию, SHA-256 исходного архива зависимостей и python.exe. `SHA256SUMS.json` покрывает все остальные файлы; рядом с ZIP создаётся его SHA-256. Порядок файлов, ZIP-время и права фиксированы: одинаковые входные файлы дают одинаковый ZIP.

Проверка проверяет CRC, каждый SHA-256, полноту манифеста, версии, ростер, наличие всех ANM2-спрайтлистов и GLB. При `--package-root` она также импортирует модули встроенным Python и вызывает `--help` рендера. Окна/игра не запускаются; это не игровая проверка.

У v27 отсутствуют дополнительные текстуры `assets/yone-local/vfx/*.png`. Рендер Ёнэ продолжает использовать существующую геометрию и процедурные линии; дополнительные исходные текстуры не появятся в этой сборке. Модель и звуки Ёнэ включены. Это ограничение материалов, а не подтверждение проверки в игре.

Установка для тестера описана в `INSTALL.txt` внутри ZIP: распаковать целиком, закрыть Isaac, запустить `launch.cmd`, выбрать корень игры с `isaac-ng.exe`, затем запустить игру через REPENTOGON и включить мод. Запускатель копирует `samira_testroom` в `<игра>/mods`, использует `<игра>/data/samira_testroom_link` для связи и сохраняет пути в `companion/work/portable-launcher.json`. Он может перезаписать ручные изменения установленного мода. `stop.cmd` останавливает только рендер из этой папки. После обновления нужен полный перезапуск игры и Companion.
