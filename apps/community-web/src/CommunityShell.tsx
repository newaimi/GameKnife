import React from "react";
import { NavLink, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { HelpCircle, Home, Languages, ListChecks, Menu, Moon, Settings, Sun, X } from "lucide-react";
import { normalizeLanguage, type SupportedLanguage } from "@gameknife/i18n";
import type { ThemeMode } from "./theme";

export function CommunityShell({
  theme,
  mobileMenuOpen,
  children,
  onMobileMenuToggle,
  onMobileMenuClose,
  onThemeToggle,
}: {
  theme: ThemeMode;
  mobileMenuOpen: boolean;
  children: React.ReactNode;
  onMobileMenuToggle: () => void;
  onMobileMenuClose: () => void;
  onThemeToggle: () => void;
}) {
  const { t, i18n } = useTranslation("common");
  const location = useLocation();
  const toolActive = location.pathname === "/" || location.pathname.startsWith("/tools/") || location.pathname === "/manual-edit";
  const language = normalizeLanguage(i18n.resolvedLanguage ?? i18n.language);
  const alternateLanguage = language === "en" ? "zh-CN" : "en";
  const themeToggleLabel = theme === "light" ? t("theme.switchToDark") : t("theme.switchToLight");
  const themeToggleTooltip = `${themeToggleLabel} T`;
  const changeLanguage = (nextLanguage: SupportedLanguage) => void i18n.changeLanguage(nextLanguage);

  return (
    <div className={`app-shell ${toolActive ? "editor-shell" : ""}`}>
      <header className="top-nav">
        <NavLink className="brand" to="/" onClick={onMobileMenuClose}>
          <img className="brand-mark" src="/gameknife-logo.png" alt="" aria-hidden="true" />
          <span>{t("brand")}</span>
        </NavLink>
        <nav aria-label={t("navigation.mainMenu")}>
          <NavButton active={toolActive} to="/" icon={<Home size={17} strokeWidth={2.4} />} label={t("navigation.home")} />
          <NavButton to="/jobs" icon={<ListChecks size={17} strokeWidth={2.4} />} label={t("navigation.jobs")} />
          <NavButton to="/settings" icon={<Settings size={17} strokeWidth={2.4} />} label={t("navigation.settings")} />
          <NavButton to="/help" icon={<HelpCircle size={17} strokeWidth={2.4} />} label={t("navigation.help")} />
        </nav>
        <div className="top-actions">
          <div className="header-control language-toggle desktop-action" role="group" aria-label={t("language.switcherLabel")}>
            <LanguageOption active={language === "en"} label="EN" title={t("language.english")} onClick={() => changeLanguage("en")} />
            <LanguageOption active={language === "zh-CN"} label="CN" title={t("language.simplifiedChinese")} onClick={() => changeLanguage("zh-CN")} />
          </div>
          <button
            className="header-control theme-toggle desktop-action"
            aria-label={themeToggleLabel}
            aria-keyshortcuts="T"
            data-tooltip={themeToggleTooltip}
            title={themeToggleTooltip}
            onClick={onThemeToggle}
            type="button"
          >
            {theme === "light" ? <Moon size={19} strokeWidth={2.3} /> : <Sun size={19} strokeWidth={2.3} />}
          </button>
          <button
            className="mobile-menu-trigger"
            type="button"
            aria-label={mobileMenuOpen ? t("navigation.closeMenu") : t("navigation.openMenu")}
            aria-expanded={mobileMenuOpen}
            aria-controls="mobile-header-menu"
            onClick={onMobileMenuToggle}
          >
            {mobileMenuOpen ? <X size={21} strokeWidth={2.5} /> : <Menu size={21} strokeWidth={2.5} />}
          </button>
          <div id="mobile-header-menu" className={`mobile-menu-popover ${mobileMenuOpen ? "open" : ""}`} role="menu">
            <MobileMenuItem active={toolActive} to="/" icon={<Home size={18} strokeWidth={2.4} />} label={t("navigation.home")} onClick={onMobileMenuClose} />
            <MobileMenuItem to="/jobs" icon={<ListChecks size={18} strokeWidth={2.4} />} label={t("navigation.jobs")} onClick={onMobileMenuClose} />
            <MobileMenuItem to="/settings" icon={<Settings size={18} strokeWidth={2.4} />} label={t("navigation.settings")} onClick={onMobileMenuClose} />
            <MobileMenuItem to="/help" icon={<HelpCircle size={18} strokeWidth={2.4} />} label={t("navigation.help")} onClick={onMobileMenuClose} />
            <div className="mobile-menu-divider" />
            <MobileMenuItem
              icon={<Languages size={18} strokeWidth={2.4} />}
              label={alternateLanguage === "en" ? t("language.switchToEnglish") : t("language.switchToSimplifiedChinese")}
              onClick={() => changeLanguage(alternateLanguage)}
            />
            <MobileMenuItem
              icon={theme === "light" ? <Moon size={18} strokeWidth={2.4} /> : <Sun size={18} strokeWidth={2.4} />}
              label={themeToggleLabel}
              onClick={onThemeToggle}
            />
          </div>
        </div>
      </header>
      {children}
    </div>
  );
}

function LanguageOption({ active, label, title, onClick }: { active: boolean; label: string; title: string; onClick: () => void }) {
  return (
    <button className={`language-option ${active ? "active" : ""}`} type="button" aria-label={title} aria-pressed={active} title={title} onClick={onClick}>
      {label}
    </button>
  );
}

function NavButton({ active, icon, label, to }: { active?: boolean; icon: React.ReactNode; label: string; to: string }) {
  return (
    <NavLink className={({ isActive }) => (active ?? isActive ? "active" : "")} to={to}>
      <span className="nav-icon">{icon}</span>
      <span>{label}</span>
    </NavLink>
  );
}

function MobileMenuItem({
  active,
  icon,
  label,
  to,
  onClick,
}: {
  active?: boolean;
  icon: React.ReactNode;
  label: string;
  to?: string;
  onClick: () => void;
}) {
  if (to) {
    return (
      <NavLink className={({ isActive }) => `mobile-menu-item ${active ?? isActive ? "active" : ""}`} to={to} role="menuitem" onClick={onClick}>
        <span>{icon}</span>
        <strong>{label}</strong>
      </NavLink>
    );
  }

  return (
    <button className={`mobile-menu-item ${active ? "active" : ""}`} type="button" role="menuitem" onClick={onClick}>
      <span>{icon}</span>
      <strong>{label}</strong>
    </button>
  );
}
