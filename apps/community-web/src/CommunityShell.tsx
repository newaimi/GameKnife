import React from "react";
import { NavLink, useLocation } from "react-router-dom";
import { HelpCircle, Home, ListChecks, Menu, Moon, Settings, Sun, X } from "lucide-react";
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
  const location = useLocation();
  const toolActive = location.pathname === "/" || location.pathname.startsWith("/tools/") || location.pathname === "/manual-edit";
  const themeToggleLabel = theme === "light" ? "切换到暗色模式" : "切换到亮色模式";
  const themeToggleTooltip = `${themeToggleLabel} T`;

  return (
    <div className="app-shell">
      <header className="top-nav">
        <NavLink className="brand" to="/" onClick={onMobileMenuClose}>
          <img className="brand-mark" src="/gameknife-logo.png" alt="" aria-hidden="true" />
          <span>游戏刀工坊</span>
        </NavLink>
        <nav aria-label="主菜单">
          <NavButton active={toolActive} to="/" icon={<Home size={17} strokeWidth={2.4} />} label="首页" />
          <NavButton to="/jobs" icon={<ListChecks size={17} strokeWidth={2.4} />} label="任务" />
          <NavButton to="/settings" icon={<Settings size={17} strokeWidth={2.4} />} label="设置" />
          <NavButton to="/help" icon={<HelpCircle size={17} strokeWidth={2.4} />} label="帮助" />
        </nav>
        <div className="top-actions">
          <button
            className="theme-toggle desktop-action"
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
            aria-label={mobileMenuOpen ? "关闭菜单" : "打开菜单"}
            aria-expanded={mobileMenuOpen}
            aria-controls="mobile-header-menu"
            onClick={onMobileMenuToggle}
          >
            {mobileMenuOpen ? <X size={21} strokeWidth={2.5} /> : <Menu size={21} strokeWidth={2.5} />}
          </button>
          <div id="mobile-header-menu" className={`mobile-menu-popover ${mobileMenuOpen ? "open" : ""}`} role="menu">
            <MobileMenuItem active={toolActive} to="/" icon={<Home size={18} strokeWidth={2.4} />} label="首页" onClick={onMobileMenuClose} />
            <MobileMenuItem to="/jobs" icon={<ListChecks size={18} strokeWidth={2.4} />} label="任务" onClick={onMobileMenuClose} />
            <MobileMenuItem to="/settings" icon={<Settings size={18} strokeWidth={2.4} />} label="设置" onClick={onMobileMenuClose} />
            <MobileMenuItem to="/help" icon={<HelpCircle size={18} strokeWidth={2.4} />} label="帮助" onClick={onMobileMenuClose} />
            <div className="mobile-menu-divider" />
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
