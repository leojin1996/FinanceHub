import type { ChangeEvent } from "react";

import { type Locale, useAppState } from "../state/app-state";
import { getMessages } from "../../i18n/messages";

export function LanguageSwitcher() {
  const { locale, setLocale } = useAppState();
  const messages = getMessages(locale);

  function handleLocaleChange(event: ChangeEvent<HTMLSelectElement>) {
    setLocale(event.target.value as Locale);
  }

  return (
    <label className="language-switcher">
      <span className="sr-only">{messages.languageLabel}</span>
      <select
        aria-label={messages.languageLabel}
        className="language-switcher__select"
        onChange={handleLocaleChange}
        value={locale}
      >
        <option value="zh-CN">简体中文</option>
        <option value="en-US">English (US)</option>
      </select>
    </label>
  );
}
