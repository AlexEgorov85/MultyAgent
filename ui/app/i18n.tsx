"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import {
  LANGUAGES,
  readLanguage,
  writeLanguage,
  type Lang,
} from "./preferences";

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
  aboutStudio: string;
  stackLabel: string;
  versionLabel: string;
  versionValue: string;
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
      "Ассистент отвечает по данным аудиторской базы: проверки, акты, находки и отклонения.",
    aboutStudio:
      "LangGraph Studio (smith.langchain.com) — служебный англоязычный инструмент LangChain. Он не входит в интерфейс ассистента.",
    stackLabel: "Стек",
    versionLabel: "Версия",
    versionValue: "0.1.0",
    preferencesSaved: "Изменения сохраняются автоматически",
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
    thinking: "Ассистент готовит ответ…",
    disclaimer:
      "Ответы основаны только на данных аудиторской базы. Проверяйте критичные выводы по первоисточникам.",
    errorTitle: "Не удалось получить ответ",
    errorHint: "Проверьте, что LangGraph API запущен, и повторите запрос.",
    assistantInitial: "А",
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
      "The assistant answers from the audit database: audits, acts, findings and deviations.",
    aboutStudio:
      "LangGraph Studio (smith.langchain.com) is a service-level English-only LangChain tool. It is not part of the assistant interface.",
    stackLabel: "Stack",
    versionLabel: "Version",
    versionValue: "0.1.0",
    preferencesSaved: "Changes are saved automatically",
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
    thinking: "The assistant is preparing an answer…",
    disclaimer:
      "Answers are based only on the audit database. Verify critical conclusions against the source documents.",
    errorTitle: "Could not get an answer",
    errorHint: "Make sure the LangGraph API is running and try again.",
    assistantInitial: "A",
  },
};

type LanguageContextValue = {
  lang: Lang;
  setLang: (lang: Lang) => void;
  t: Dictionary;
};

const LanguageContext = createContext<LanguageContextValue | null>(null);

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>("ru");

  useEffect(() => {
    setLangState(readLanguage());
  }, []);

  const setLang = useCallback((next: Lang) => {
    setLangState(next);
    writeLanguage(next);
  }, []);

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
