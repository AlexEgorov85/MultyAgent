import type { Metadata } from "next";
import "./globals.css";
import { LanguageProvider } from "./i18n";
import { MyRuntimeProvider } from "./MyRuntimeProvider";

export const metadata: Metadata = {
  title: "Ассистент внутреннего аудитора · Internal Audit Assistant",
  description:
    "Мультиагентная аналитика на LangGraph · Multi-agent analytics on LangGraph",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ru">
      <body>
        <LanguageProvider>
          <MyRuntimeProvider>{children}</MyRuntimeProvider>
        </LanguageProvider>
      </body>
    </html>
  );
}
