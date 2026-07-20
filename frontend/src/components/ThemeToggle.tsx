import React from 'react';
import { useAppStore } from '../stores/appStore';

export const ThemeToggle: React.FC = () => {
  const theme = useAppStore((s) => s.theme);
  const toggleTheme = useAppStore((s) => s.toggleTheme);

  return (
    <button
      type="button"
      className="theme-toggle"
      aria-label="切换浅色或深色主题"
      aria-pressed={theme === 'dark'}
      onClick={toggleTheme}
    >
      <span>{theme === 'dark' ? '深色' : '浅色'}</span>
      <span>{theme === 'dark' ? '浅色' : '深色'}</span>
    </button>
  );
};
