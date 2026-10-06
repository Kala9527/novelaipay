import { Languages, SunMoon } from 'lucide-react'
import { PageHeader } from '../components/UI'
import { usePreferences, type LanguagePreference, type ThemePreference } from '../lib/preferences'

export function PreferencesPage() {
  const { theme, setTheme, language, setLanguage, t } = usePreferences()
  return <div className="page preferences-page"><PageHeader title={t('preferences')} subtitle={t('preferencesSubtitle')} />
    <section className="preference-section"><div className="preference-intro"><SunMoon size={19} /><div><h2>{t('appearance')}</h2><p>{t('themeHint')}</p></div></div><div className="preference-options" role="group" aria-label={t('theme')}>{(['system', 'light', 'dark'] as const).map(value => <button key={value} type="button" aria-pressed={theme === value} className={theme === value ? 'selected' : ''} onClick={() => setTheme(value as ThemePreference)}>{t(value)}</button>)}</div></section>
    <section className="preference-section"><div className="preference-intro"><Languages size={19} /><div><h2>{t('languageSettings')}</h2><p>{t('languageHint')}</p></div></div><div className="preference-options" role="group" aria-label={t('language')}>{(['auto', 'zh', 'en', 'ja'] as const).map(value => <button key={value} type="button" aria-pressed={language === value} className={language === value ? 'selected' : ''} onClick={() => setLanguage(value as LanguagePreference)}>{t(value === 'zh' ? 'chinese' : value === 'en' ? 'english' : value === 'ja' ? 'japanese' : 'auto')}</button>)}</div></section>
  </div>
}
