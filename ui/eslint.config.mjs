import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  {
    rules: {
      // Правило React Compiler из eslint-plugin-react-hooks 6.x запрещает
      // синхронный setState внутри эффекта. В приложении так устроена
      // гидратация состояния из localStorage при монтировании
      // (SettingsProvider, chats, SettingsDialog). Переписывание этих
      // компонентов выходит за рамки текущей задачи, поэтому правило
      // отключено осознанно, а не весь набор react-hooks.
      "react-hooks/set-state-in-effect": "off",
      // Подчёркивание — осознанная пометка «переменная нужна только для
      // исключения из объекта или является неиспользуемым аргументом».
      "@typescript-eslint/no-unused-vars": [
        "warn",
        {
          argsIgnorePattern: "^_",
          varsIgnorePattern: "^_",
          caughtErrorsIgnorePattern: "^_",
          ignoreRestSiblings: true,
        },
      ],
    },
  },
  {
    // Страница ошибки должна перезагружать приложение целиком, поэтому
    // здесь осознанно используется обычный <a>, а не клиентский <Link>.
    files: ["app/error.tsx"],
    rules: {
      "@next/next/no-html-link-for-pages": "off",
    },
  },
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
    "node_modules/**",
  ]),
]);

export default eslintConfig;
