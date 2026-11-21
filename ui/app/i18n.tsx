"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  type ReactNode,
} from "react";
import { useSettings } from "./SettingsProvider";
import { LANGUAGES, type Lang } from "./preferences";

type Suggestion = {
  title: string;
  text: string;
};

export type Dictionary = {
  appTitle: string;
  appShort: string;
  tagline: string;
  online: string;
  menu: string;
  menuHint: string;
  settings: string;
  settingsHint: string;
  newChat: string;
  about: string;
  close: string;
  interfaceLanguage: string;
  interfaceLanguageHint: string;
  auditor: string;
  auditorHint: string;
  aboutTitle: string;
  aboutDescription: string;
  systemLabel: string;
  agentVersionLabel: string;
  agentVersionValue: string;
  interfaceVersionLabel: string;
  interfaceVersionValue: string;
  modelLabel: string;
  modelValue: string;
  stackLabel: string;
  stackValue: string;
  dataAccessLabel: string;
  dataAccessValue: string;
  aboutCapabilities: string;
  aboutCapabilitiesList: string[];
  aboutNote: string;
  preferencesSaved: string;
  emptyTitle: string;
  emptyDescription: string;
  suggestions: Suggestion[];
  placeholder: string;
  send: string;
  thinking: string;
  disclaimer: string;
  errorTitle: string;
  errorHint: string;
  assistantInitial: string;
  agentPath: string;
  agentPathShowSql: string;
  agentPathHideSql: string;
  agentPathSeconds: string;
  agentPathWarnings: string;
  chats: string;
  chatsHint: string;
  openChats: string;
  closeChats: string;
  noChats: string;
  loadingChats: string;
  deleteChat: string;
  deleteChatConfirm: string;
  chatsStoredLocally: string;
  appearanceTab: string;
  behaviorTab: string;
  dataTab: string;
  aboutTab: string;
  theme: string;
  themeHint: string;
  themeLight: string;
  themeDark: string;
  themeSystem: string;
  accent: string;
  accentHint: string;
  accentIndigo: string;
  accentViolet: string;
  accentEmerald: string;
  accentAmber: string;
  accentRose: string;
  accentSky: string;
  fontSize: string;
  fontSizeHint: string;
  chatFontSize: string;
  chatFontSizeHint: string;
  density: string;
  densityHint: string;
  densityCompact: string;
  densityCozy: string;
  densityComfortable: string;
  corners: string;
  cornersHint: string;
  cornersSharp: string;
  cornersSoft: string;
  cornersRound: string;
  contentWidth: string;
  contentWidthHint: string;
  widthNarrow: string;
  widthNormal: string;
  widthWide: string;
  animations: string;
  animationsHint: string;
  animationsOn: string;
  animationsOff: string;
  glass: string;
  glassHint: string;
  glassOn: string;
  glassOff: string;
  fontFamily: string;
  fontFamilyHint: string;
  fontSystem: string;
  fontSerif: string;
  fontMono: string;
  background: string;
  backgroundHint: string;
  backgroundGradient: string;
  backgroundPlain: string;
  timeFormat: string;
  timeFormatHint: string;
  time24: string;
  time12: string;
  showAvatars: string;
  showAvatarsHint: string;
  showSuggestions: string;
  showSuggestionsHint: string;
  showOnline: string;
  showOnlineHint: string;
  showAgentTrace: string;
  showAgentTraceHint: string;
  enterToSend: string;
  enterToSendHint: string;
  showTimestamps: string;
  showTimestampsHint: string;
  dataHint: string;
  resetSettings: string;
  resetSettingsHint: string;
  resetConfirm: string;
};

const DICTIONARIES: Record<Lang, Dictionary> = {
  ru: {
    appTitle: "Ассистент внутреннего аудитора",
    appShort: "Ассистент аудитора",
    tagline: "LangGraph · PostgreSQL · FIPA-ACL",
    online: "онлайн",
    menu: "Меню",
    menuHint: "Открыть меню",
    settings: "Настройки",
    settingsHint: "Открыть настройки",
    newChat: "Новый диалог",
    about: "О системе",
    close: "Закрыть",
    interfaceLanguage: "Язык интерфейса",
    interfaceLanguageHint:
      "Меню, подсказки и кнопки переключаются сразу. Ответы ассистента формируются на языке вопроса.",
    auditor: "Идентификатор аудитора",
    auditorHint: "Профиль и память загружаются по этому идентификатору.",
    aboutTitle: "О системе",
    aboutDescription:
      "Мультиагентная система для внутреннего аудита. Отвечает на вопросы по проверкам, актам и находкам, строит безопасные SQL-запросы и готовит проекты разделов акта.",
    systemLabel: "Система",
    agentVersionLabel: "Версия агента",
    agentVersionValue: "0.1.0",
    interfaceVersionLabel: "Версия интерфейса",
    interfaceVersionValue: "0.1.0",
    modelLabel: "Модель",
    modelValue: "qwen3.6-35b-a3b-noreason",
    stackLabel: "Стек",
    stackValue: "LangGraph · PostgreSQL · FIPA-ACL",
    dataAccessLabel: "Доступ к данным",
    dataAccessValue: "Только чтение",
    aboutCapabilities: "Возможности",
    aboutCapabilitiesList: [
      "Аналитика по проверкам, актам и находкам",
      "Поиск подтверждений в актах и методических документах",
      "Подготовка проекта раздела акта со ссылками на источники",
      "Расследование отклонений по нескольким источникам",
    ],
    aboutNote: "Учебный проект. Все данные синтетические.",
    preferencesSaved: "Изменения сохраняются сразу",
    emptyTitle: "Ассистент внутреннего аудитора",
    emptyDescription:
      "Задайте вопрос по карманам, проверкам и находкам. Ассистент построит безопасный SQL, найдёт подтверждения в актах и подготовит проект раздела.",
    suggestions: [
      {
        title: "Сколько проверок завершено?",
        text: "Сколько завершённых проверок по ипотеке в 2026 году?",
      },
      {
        title: "Найти похожие находки",
        text: "Найди отклонения про просроченную актуализацию оценки залога.",
      },
      {
        title: "Сформировать акт",
        text: "Сформируй раздел акта по AUD-2026-MORTGAGE-03.",
      },
      {
        title: "Почему выросла доля?",
        text: "Почему в ипотеке в 2026 году выросла доля просроченных пунктов?",
      },
    ],
    placeholder: "Спросите про проверки, отклонения или акт…",
    send: "Отправить",
    thinking: "Ассистент готовит ответ",
    disclaimer:
      "Ответы основаны только на данных аудиторской базы. Проверяйте критичные выводы по первоисточникам.",
    errorTitle: "Не удалось получить ответ",
    errorHint: "Проверьте, что LangGraph API запущен, и повторите запрос.",
    assistantInitial: "А",
    agentPath: "Как получен ответ",
    agentPathShowSql: "Показать SQL",
    agentPathHideSql: "Скрыть SQL",
    agentPathSeconds: "{seconds} с",
    agentPathWarnings: "Замечаний: {count}",
    chats: "Чаты",
    chatsHint: "История диалогов",
    openChats: "Открыть список чатов",
    closeChats: "Закрыть список чатов",
    noChats: "Пока нет диалогов",
    loadingChats: "Загрузка…",
    deleteChat: "Удалить диалог",
    deleteChatConfirm: "Удалить этот диалог?",
    chatsStoredLocally: "История хранится в браузере",
    appearanceTab: "Интерфейс",
    behaviorTab: "Поведение",
    dataTab: "Данные",
    aboutTab: "О системе",
    theme: "Тема",
    themeHint: "Светлая, тёмная или как в системе.",
    themeLight: "Светлая",
    themeDark: "Тёмная",
    themeSystem: "Системная",
    accent: "Акцентный цвет",
    accentHint: "Цвет кнопок, ссылок и активных элементов.",
    accentIndigo: "Индиго",
    accentViolet: "Фиолетовый",
    accentEmerald: "Изумрудный",
    accentAmber: "Янтарный",
    accentRose: "Розовый",
    accentSky: "Небесный",
    fontSize: "Размер интерфейса",
    fontSizeHint: "Масштаб меню, кнопок и отступов.",
    chatFontSize: "Размер текста чата",
    chatFontSizeHint: "Только сообщения ассистента и пользователя.",
    density: "Плотность",
    densityHint: "Насколько просторно располагать сообщения.",
    densityCompact: "Компактная",
    densityCozy: "Обычная",
    densityComfortable: "Просторная",
    corners: "Скругление углов",
    cornersHint: "Форма карточек, полей и кнопок.",
    cornersSharp: "Острые",
    cornersSoft: "Мягкие",
    cornersRound: "Круглые",
    contentWidth: "Ширина диалога",
    contentWidthHint: "Максимальная ширина ленты сообщений.",
    widthNarrow: "Узкая",
    widthNormal: "Обычная",
    widthWide: "Широкая",
    animations: "Анимации",
    animationsHint: "Плавные переходы и подсветка.",
    animationsOn: "Включены",
    animationsOff: "Выключены",
    glass: "Стеклянный эффект",
    glassHint: "Полупрозрачные шапка и панель ввода.",
    glassOn: "Включён",
    glassOff: "Выключен",
    fontFamily: "Шрифт",
    fontFamilyHint: "Основной шрифт интерфейса.",
    fontSystem: "Системный",
    fontSerif: "С засечками",
    fontMono: "Моноширинный",
    background: "Фон чата",
    backgroundHint: "Градиентная подложка или ровный фон.",
    backgroundGradient: "Градиент",
    backgroundPlain: "Ровный",
    timeFormat: "Формат времени",
    timeFormatHint: "Как показывать время сообщений.",
    time24: "24 часа",
    time12: "12 часов",
    showAvatars: "Аватар ассистента",
    showAvatarsHint: "Показывать значок рядом с ответами.",
    showSuggestions: "Подсказки на старте",
    showSuggestionsHint: "Показывать карточки с примерами вопросов.",
    showOnline: "Статус «онлайн»",
    showOnlineHint: "Индикатор доступности в шапке.",
    showAgentTrace: "Как получен ответ",
    showAgentTraceHint: "Показывать раскрываемую цепочку шагов под ответом.",
    enterToSend: "Enter отправляет сообщение",
    enterToSendHint:
      "Если выключено, Enter переносит строку, а отправка — Ctrl+Enter.",
    showTimestamps: "Время сообщений",
    showTimestampsHint: "Показывать время рядом с каждым сообщением.",
    dataHint: "Профиль аудитора, новый диалог и сброс настроек.",
    resetSettings: "Сбросить настройки",
    resetSettingsHint: "Вернуть тему, цвета, размеры и поведение по умолчанию.",
    resetConfirm: "Сбросить все настройки интерфейса?",
  },
  en: {
    appTitle: "Internal Audit Assistant",
    appShort: "Audit Assistant",
    tagline: "LangGraph · PostgreSQL · FIPA-ACL",
    online: "online",
    menu: "Menu",
    menuHint: "Open menu",
    settings: "Settings",
    settingsHint: "Open settings",
    newChat: "New chat",
    about: "About",
    close: "Close",
    interfaceLanguage: "Interface language",
    interfaceLanguageHint:
      "Menus, suggestions and buttons switch instantly. Assistant answers follow the language of your question.",
    auditor: "Auditor ID",
    auditorHint: "The profile and memory are loaded by this identifier.",
    aboutTitle: "About",
    aboutDescription:
      "A multi-agent internal audit system. It answers questions about audits, acts and findings, builds safe SQL queries and drafts act sections.",
    systemLabel: "System",
    agentVersionLabel: "Agent version",
    agentVersionValue: "0.1.0",
    interfaceVersionLabel: "Interface version",
    interfaceVersionValue: "0.1.0",
    modelLabel: "Model",
    modelValue: "qwen3.6-35b-a3b-noreason",
    stackLabel: "Stack",
    stackValue: "LangGraph · PostgreSQL · FIPA-ACL",
    dataAccessLabel: "Data access",
    dataAccessValue: "Read-only",
    aboutCapabilities: "Capabilities",
    aboutCapabilitiesList: [
      "Analytics across audits, acts and findings",
      "Evidence search in acts and methodology documents",
      "Drafting act sections with source citations",
      "Investigation of deviations across multiple sources",
    ],
    aboutNote: "Training project. All data is synthetic.",
    preferencesSaved: "Changes are saved instantly",
    emptyTitle: "Internal Audit Assistant",
    emptyDescription:
      "Ask about audit pockets, audits and findings. The assistant builds safe SQL, finds evidence in acts and drafts a report section.",
    suggestions: [
      {
        title: "How many audits were completed?",
        text: "How many mortgage audits were completed in 2026?",
      },
      {
        title: "Find similar findings",
        text: "Find deviations about the overdue collateral valuation.",
      },
      {
        title: "Draft an act section",
        text: "Draft the act section for AUD-2026-MORTGAGE-03.",
      },
      {
        title: "Why did the share grow?",
        text: "Why did the share of overdue items grow in mortgage in 2026?",
      },
    ],
    placeholder: "Ask about audits, deviations or an act…",
    send: "Send",
    thinking: "The assistant is preparing an answer",
    disclaimer:
      "Answers are based only on the audit database. Verify critical conclusions against the source documents.",
    errorTitle: "Could not get an answer",
    errorHint: "Make sure the LangGraph API is running and try again.",
    assistantInitial: "A",
    agentPath: "How the answer was built",
    agentPathShowSql: "Show SQL",
    agentPathHideSql: "Hide SQL",
    agentPathSeconds: "{seconds} s",
    agentPathWarnings: "Warnings: {count}",
    chats: "Chats",
    chatsHint: "Conversation history",
    openChats: "Open chat list",
    closeChats: "Close chat list",
    noChats: "No conversations yet",
    loadingChats: "Loading…",
    deleteChat: "Delete conversation",
    deleteChatConfirm: "Delete this conversation?",
    chatsStoredLocally: "History is stored in the browser",
    appearanceTab: "Appearance",
    behaviorTab: "Behavior",
    dataTab: "Data",
    aboutTab: "About",
    theme: "Theme",
    themeHint: "Light, dark or follow the system.",
    themeLight: "Light",
    themeDark: "Dark",
    themeSystem: "System",
    accent: "Accent color",
    accentHint: "Color of buttons, links and active elements.",
    accentIndigo: "Indigo",
    accentViolet: "Violet",
    accentEmerald: "Emerald",
    accentAmber: "Amber",
    accentRose: "Rose",
    accentSky: "Sky",
    fontSize: "Interface size",
    fontSizeHint: "Scale of menus, buttons and spacing.",
    chatFontSize: "Chat text size",
    chatFontSizeHint: "Only user and assistant message text.",
    density: "Density",
    densityHint: "How spacious the message list is.",
    densityCompact: "Compact",
    densityCozy: "Cozy",
    densityComfortable: "Comfortable",
    corners: "Corner radius",
    cornersHint: "Shape of cards, inputs and buttons.",
    cornersSharp: "Sharp",
    cornersSoft: "Soft",
    cornersRound: "Round",
    contentWidth: "Content width",
    contentWidthHint: "Maximum width of the message list.",
    widthNarrow: "Narrow",
    widthNormal: "Normal",
    widthWide: "Wide",
    animations: "Animations",
    animationsHint: "Smooth transitions and highlights.",
    animationsOn: "On",
    animationsOff: "Off",
    glass: "Glass effect",
    glassHint: "Translucent header and composer.",
    glassOn: "On",
    glassOff: "Off",
    fontFamily: "Font",
    fontFamilyHint: "Main interface font.",
    fontSystem: "System",
    fontSerif: "Serif",
    fontMono: "Monospace",
    background: "Chat background",
    backgroundHint: "Gradient backdrop or a flat color.",
    backgroundGradient: "Gradient",
    backgroundPlain: "Flat",
    timeFormat: "Time format",
    timeFormatHint: "How message time is displayed.",
    time24: "24-hour",
    time12: "12-hour",
    showAvatars: "Assistant avatar",
    showAvatarsHint: "Show the icon next to answers.",
    showSuggestions: "Starter suggestions",
    showSuggestionsHint: "Show example question cards on the empty screen.",
    showOnline: "Online status",
    showOnlineHint: "Availability indicator in the header.",
    showAgentTrace: "How the answer was built",
    showAgentTraceHint: "Show a collapsible chain of steps under the answer.",
    enterToSend: "Enter sends the message",
    enterToSendHint:
      "When off, Enter inserts a newline and Ctrl+Enter sends.",
    showTimestamps: "Message time",
    showTimestampsHint: "Show the time next to each message.",
    dataHint: "Auditor profile, new chat and settings reset.",
    resetSettings: "Reset settings",
    resetSettingsHint: "Restore the default theme, colors, sizes and behavior.",
    resetConfirm: "Reset all interface settings?",
  },
};

type LanguageContextValue = {
  lang: Lang;
  setLang: (lang: Lang) => void;
  t: Dictionary;
};

const LanguageContext = createContext<LanguageContextValue | null>(null);

export function LanguageProvider({ children }: { children: ReactNode }) {
  const { settings, setSetting } = useSettings();
  const lang = settings.language;

  const setLang = useCallback(
    (next: Lang) => {
      setSetting("language", next);
    },
    [setSetting],
  );

  useEffect(() => {
    const desired = DICTIONARIES[lang].appTitle;
    document.documentElement.lang = lang;
    document.title = desired;

    // Next.js обновляет <title> после гидратации; удерживаем язык вкладки.
    const observer = new MutationObserver(() => {
      if (document.title !== desired) document.title = desired;
    });
    observer.observe(document.head, {
      childList: true,
      subtree: true,
      characterData: true,
    });
    return () => observer.disconnect();
  }, [lang]);

  const value = useMemo(
    () => ({ lang, setLang, t: DICTIONARIES[lang] }),
    [lang, setLang],
  );

  return (
    <LanguageContext.Provider value={value}>
      {children}
    </LanguageContext.Provider>
  );
}

export function useI18n(): LanguageContextValue {
  const context = useContext(LanguageContext);
  if (!context) {
    throw new Error("useI18n must be used inside LanguageProvider");
  }
  return context;
}

export { LANGUAGES };
export type { Lang };
