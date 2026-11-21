import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // В dev-режиме Next блокирует чужие hostname. Эти записи нужны, чтобы
  // открывать `npm run dev` через туннель (см. docs/share_ui.md).
  allowedDevOrigins: [
    "*.trycloudflare.com",
    "*.ngrok-free.app",
    "*.loca.lt",
    "*.localhost.run",
  ],
  // Убираем англоязычный индикатор Next.js DevTools внизу слева.
  // Свои настройки интерфейса находятся в кнопке-шестерёнке приложения.
  devIndicators: false,
};

export default nextConfig;
