import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // Убираем англоязычный индикатор Next.js DevTools внизу слева.
  // Свои настройки интерфейса находятся в кнопке-шестерёнке приложения.
  devIndicators: false,
};

export default nextConfig;
