import type { Metadata } from "next";
import "./globals.css";
import { LanguageProvider } from "./i18n";
import { MyRuntimeProvider } from "./MyRuntimeProvider";
import { SettingsProvider } from "./SettingsProvider";

export const metadata: Metadata = {
  title: "Ассистент внутреннего аудитора · Internal Audit Assistant",
  description:
    "Мультиагентная аналитика на LangGraph · Multi-agent analytics on LangGraph",
};

const themeScript = `(function(){try{var p=JSON.parse(localStorage.getItem("audit-ui-preferences")||"{}");var d=document.documentElement;var t=p.theme||"light";var dark=t==="dark"||(t==="system"&&window.matchMedia("(prefers-color-scheme: dark)").matches);d.dataset.theme=dark?"dark":"light";d.dataset.themeMode=t;if(p.accent)d.dataset.accent=p.accent;if(p.density)d.dataset.density=p.density;if(p.radius)d.dataset.radius=p.radius;if(p.width)d.dataset.width=p.width;d.dataset.animations=p.animations===false?"off":"on";d.dataset.glass=p.glass===false?"off":"on";if(p.fontFamily)d.dataset.font=p.fontFamily;if(p.background)d.dataset.background=p.background;if(typeof p.fontScale==="number")d.style.setProperty("--ui-scale",String(p.fontScale));if(typeof p.chatFontScale==="number")d.style.setProperty("--chat-scale",String(p.chatFontScale));d.style.colorScheme=dark?"dark":"light";d.lang=p.language||"ru";}catch(e){}})();`;

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ru" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body>
        <SettingsProvider>
          <LanguageProvider>
            <MyRuntimeProvider>{children}</MyRuntimeProvider>
          </LanguageProvider>
        </SettingsProvider>
      </body>
    </html>
  );
}
