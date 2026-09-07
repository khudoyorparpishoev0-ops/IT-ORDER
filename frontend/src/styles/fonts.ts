/**
 * Шрифты ставятся из npm и хостятся самим приложением: панель должна работать
 * в LAN без интернета, CDN брендбук запрещает. Подключаем только нужные
 * подмножества: latin, latin-ext, cyrillic, cyrillic-ext.
 * cyrillic-ext даёт таджикские ғ ӣ қ ӯ ҳ ҷ. Курсива нет — брендбук запрещает наклон.
 */

// Manrope — основная гарнитура: 300 / 400 / 600 / 700 / 800
import '@fontsource/manrope/latin-300.css';
import '@fontsource/manrope/latin-ext-300.css';
import '@fontsource/manrope/cyrillic-300.css';
import '@fontsource/manrope/cyrillic-ext-300.css';
import '@fontsource/manrope/latin-400.css';
import '@fontsource/manrope/latin-ext-400.css';
import '@fontsource/manrope/cyrillic-400.css';
import '@fontsource/manrope/cyrillic-ext-400.css';
import '@fontsource/manrope/latin-600.css';
import '@fontsource/manrope/latin-ext-600.css';
import '@fontsource/manrope/cyrillic-600.css';
import '@fontsource/manrope/cyrillic-ext-600.css';
import '@fontsource/manrope/latin-700.css';
import '@fontsource/manrope/latin-ext-700.css';
import '@fontsource/manrope/cyrillic-700.css';
import '@fontsource/manrope/cyrillic-ext-700.css';
import '@fontsource/manrope/latin-800.css';
import '@fontsource/manrope/latin-ext-800.css';
import '@fontsource/manrope/cyrillic-800.css';
import '@fontsource/manrope/cyrillic-ext-800.css';

// JetBrains Mono — служебный слой: рубрики, номера, даты, суммы, коды
import '@fontsource/jetbrains-mono/latin-400.css';
import '@fontsource/jetbrains-mono/latin-ext-400.css';
import '@fontsource/jetbrains-mono/cyrillic-400.css';
import '@fontsource/jetbrains-mono/cyrillic-ext-400.css';
import '@fontsource/jetbrains-mono/latin-600.css';
import '@fontsource/jetbrains-mono/latin-ext-600.css';
import '@fontsource/jetbrains-mono/cyrillic-600.css';
import '@fontsource/jetbrains-mono/cyrillic-ext-600.css';

// Noto Sans — обязательная пара для таджикского
import '@fontsource/noto-sans/latin-400.css';
import '@fontsource/noto-sans/latin-ext-400.css';
import '@fontsource/noto-sans/cyrillic-400.css';
import '@fontsource/noto-sans/cyrillic-ext-400.css';
import '@fontsource/noto-sans/latin-600.css';
import '@fontsource/noto-sans/latin-ext-600.css';
import '@fontsource/noto-sans/cyrillic-600.css';
import '@fontsource/noto-sans/cyrillic-ext-600.css';
