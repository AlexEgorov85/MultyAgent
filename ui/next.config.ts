import path from "node:path";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // Держим корень Turbopack внутри ui/. Иначе Next ищет lock-файлы выше по
  // дереву и предупреждает про package-lock.json из домашнего каталога,
  // который лежит вне git-репозитория.
  turbopack: {
    root: path.join(__dirname),
  },
  // В dev-режиме Next блокирует чужие hostname. Эти записи нужны, чтобы
  // открывать `npm run dev` через туннель (см. docs/share_ui.md).
  allowedDevOrigins: [
    "*.trycloudflare.com",
    "*.serveousercontent.com",
    "*.ngrok-free.app",
    "*.loca.lt",
    "*.localhost.run",
  ],
  // Убираем англоязычный индикатор Next.js DevTools внизу слева.
  // Свои настройки интерфейса находятся в кнопке-шестерёнке приложения.
  devIndicators: false,
};

export default nextConfig;
