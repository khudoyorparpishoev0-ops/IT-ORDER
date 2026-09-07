# Шрифты для PDF

Файлы в этой папке собираются скриптом `backend/scripts/build_pdf_fonts.py`
из пакетов npm `@fontsource/manrope`, `@fontsource/jetbrains-mono` и
`@fontsource/noto-sans`. Они лежат в репозитории намеренно: на сервере
`node_modules` нет, а образ должен собираться без обращения в интернет.

Состав каждого файла — подмножества latin, latin-ext, cyrillic и
cyrillic-ext, плюс таджикские буквы `ғ ӣ қ ӯ ҳ ҷ` из Noto Sans: в Manrope
их нет, поэтому брендбук IT-HONA и требует пару с Noto Sans.

## Лицензии

- **Manrope** — SIL Open Font License 1.1, © Mikhail Sharanda, Michael Vodolazkiy.
- **JetBrains Mono** — SIL Open Font License 1.1, © JetBrains s.r.o.
- **Noto Sans** — SIL Open Font License 1.1, © Google LLC.

SIL OFL разрешает распространение шрифтов, в том числе в составе
программного обеспечения, при сохранении уведомления об авторских правах
и лицензии. Продажа шрифтов отдельно запрещена. Полный текст лицензии:
https://openfontlicense.org
