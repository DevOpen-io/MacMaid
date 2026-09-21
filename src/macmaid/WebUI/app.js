/* =========================================================
   MacMaid Pro — Modern Web Dashboard Controller
   With Real-time Continuous Live Feedback Engine & Full Tool Suite
   ========================================================= */

if (typeof navigator !== 'undefined' && navigator.userAgent && navigator.userAgent.includes('MacMaidApp')) {
  document.documentElement.classList.add('is-native-app');
  if (document.body) {
    document.body.classList.add('is-native-app');
  } else {
    document.addEventListener('DOMContentLoaded', () => {
      if (document.body) document.body.classList.add('is-native-app');
    });
  }
}

// State Management
const state = {
  activeTab: 'cleaner',
  refreshInterval: 3000,
  refreshTimer: null,
  progressTimer: null,
  isOperationRunning: false,
  operationObservedActive: false,
  operationStartedAt: 0,
  soundEnabled: localStorage.getItem('macmaid_sound') !== 'off',
  currentScan: null,
  selectedCleanItems: new Set(),
  apps: [],
  selectedApp: null,
  appLeftovers: [],
  purgeArtifacts: [],
  selectedPurgeArtifacts: new Set(),
  installers: [],
  selectedInstallers: new Set(),
  leftovers: [],
  selectedLeftovers: new Set(),
  devCaches: [],
  selectedDevCaches: new Set(),
  currentAnalyzePath: '~',
  analyzerViews: new Map(),
  analyzerRequestId: Date.now(),
  analyzerPollTimer: null,
  theme: ['dark', 'midnight', 'cyber', 'light'].includes(localStorage.getItem('macmaid_theme'))
    ? localStorage.getItem('macmaid_theme')
    : 'dark',
  lang: ['en', 'tr'].includes(localStorage.getItem('macmaid_lang'))
    ? localStorage.getItem('macmaid_lang')
    : 'en',
  modalReturnFocus: null,
  permissionReport: null,
};

// =========================================================
// DOM Ready & Event Setup
// =========================================================

document.addEventListener('DOMContentLoaded', () => {
  document.documentElement.setAttribute('data-theme', state.theme);
  const themeSelect = document.getElementById('theme-selector-setting');
  if (themeSelect) themeSelect.value = state.theme;
  const soundSetting = document.getElementById('chk-sound-setting');
  if (soundSetting) soundSetting.checked = state.soundEnabled;


  function activateTopLevelTab(tab, navItem = document.querySelector(`.nav-item[data-tab="${tab}"]`)) {
    document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
    document.querySelectorAll('.nav-item').forEach(n => n.removeAttribute('aria-current'));
    document.querySelectorAll('.nav-item.has-submenu').forEach(n => { if (n !== navItem) n.classList.remove('expanded'); });
    document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));

    const settingsBtn = document.getElementById('settings-btn');
    if (tab === 'settings') {
      settingsBtn?.classList.add('active');
    } else {
      settingsBtn?.classList.remove('active');
    }

    if (navItem) {
      navItem.classList.add('active');
      navItem.setAttribute('aria-current', 'page');
      if (navItem.classList.contains('has-submenu')) navItem.classList.add('expanded');
    }
    const targetPane = document.getElementById(`pane-${tab}`);
    if (targetPane) targetPane.classList.add('active');
    state.activeTab = tab;
    syncStatusPolling();
  }

  function setActiveSidebarSubmenu(selector) {
    document.querySelectorAll('.nav-submenu-item').forEach(n => n.classList.remove('active'));
    document.querySelector(selector)?.classList.add('active');
  }

  function activateDeveloperSubtab(devtab) {
    activateTopLevelTab('developer');
    document.querySelectorAll('#pane-developer .sub-pane').forEach(pane => pane.classList.remove('active'));
    document.getElementById(`subpane-dev-${devtab}`)?.classList.add('active');
    setActiveSidebarSubmenu(`.nav-submenu-item[data-devsubtab="${devtab}"]`);
    // Navigation only reveals the pane; scans start from explicit Scan buttons.
  }


  function activateMoreSubtab(moretab) {
    activateTopLevelTab('more');
    document.querySelectorAll('#pane-more .sub-pane').forEach(pane => pane.classList.remove('active'));
    document.getElementById(`subpane-more-${moretab}`)?.classList.add('active');
    setActiveSidebarSubmenu(`.nav-submenu-item[data-subtab="${moretab}"]`);

    if (moretab !== 'treemap') treemapRequestId += 1;
    if (moretab === 'treemap') reconnectTreemap();
    // Heavy scans (treemap, browser storage, downloads, duplicates, large files)
    // are explicit-button only; cached DOM/state persists across pane switches.
    if (moretab === 'history' && (!state.history || state.history.length === 0)) fetchHistory();
    if (moretab === 'whitelist' && (!state.whitelist || state.whitelist.length === 0)) fetchWhitelist();
  }

  // Sidebar navigation
  document.querySelectorAll('.nav-item').forEach(item => {
    item.addEventListener('click', () => {
      SoundEffects.playClick();
      const tab = item.dataset.tab;
      activateTopLevelTab(tab, item);

      if (item.classList.contains('has-submenu')) return;

      // Only lazy load static settings / metadata; DO NOT auto-run scans without user action
      if (tab === 'optimize' && (!state.optimizeTasks || state.optimizeTasks.length === 0)) fetchOptimizationTasks();
    });
  });

  // Submenu navigation is now only in the left sidebar; legacy in-page pill markup is hidden.
  document.querySelectorAll('.nav-submenu-item[data-subtab]').forEach(subItem => {
    subItem.addEventListener('click', () => {
      SoundEffects.playClick();
      activateMoreSubtab(subItem.dataset.subtab);
    });
  });

  document.querySelectorAll('.nav-submenu-item[data-devsubtab]').forEach(subItem => {
    subItem.addEventListener('click', () => {
      SoundEffects.playClick();
      activateDeveloperSubtab(subItem.dataset.devsubtab);
    });
  });


  // Sound toggle button in header
  const soundBtn = document.getElementById('sound-toggle');
  soundBtn?.addEventListener('click', () => {
    state.soundEnabled = !state.soundEnabled;
    localStorage.setItem('macmaid_sound', state.soundEnabled ? 'on' : 'off');
    soundBtn.querySelector('.icon-sound-on').classList.toggle('hidden', !state.soundEnabled);
    soundBtn.querySelector('.icon-sound-off').classList.toggle('hidden', state.soundEnabled);
    const soundChk = document.getElementById('chk-sound-setting');
    if (soundChk) soundChk.checked = state.soundEnabled;
    const mainSoundChk = document.getElementById('chk-main-sound-setting');
    if (mainSoundChk) mainSoundChk.checked = state.soundEnabled;
    SoundEffects.playClick();
    const msg = state.soundEnabled
      ? (state.lang === 'tr' ? I18N.tr['toast.sound_on'] : I18N.en['toast.sound_on'])
      : (state.lang === 'tr' ? I18N.tr['toast.sound_off'] : I18N.en['toast.sound_off']);
    showToast(msg, 'info');
  });

  soundSetting?.addEventListener('change', event => {
    state.soundEnabled = event.target.checked;
    localStorage.setItem('macmaid_sound', state.soundEnabled ? 'on' : 'off');
    soundBtn?.querySelector('.icon-sound-on')?.classList.toggle('hidden', !state.soundEnabled);
    soundBtn?.querySelector('.icon-sound-off')?.classList.toggle('hidden', state.soundEnabled);
    const mainSoundChk = document.getElementById('chk-main-sound-setting');
    if (mainSoundChk) mainSoundChk.checked = state.soundEnabled;
  });

  // Theme toggle button in header
  document.getElementById('theme-btn')?.addEventListener('click', () => {
    const themes = ['dark', 'midnight', 'cyber', 'light'];
    let nextIdx = (themes.indexOf(state.theme) + 1) % themes.length;
    state.theme = themes[nextIdx];
    document.documentElement.setAttribute('data-theme', state.theme);
    localStorage.setItem('macmaid_theme', state.theme);
    if (themeSelect) themeSelect.value = state.theme;
    const mainTheme = document.getElementById('main-theme-selector');
    if (mainTheme) mainTheme.value = state.theme;
    SoundEffects.playClick();
  });

  // Settings button in sidebar footer
  document.getElementById('settings-btn')?.addEventListener('click', () => {
    SoundEffects.playClick();
    activateTopLevelTab('settings');
    document.querySelectorAll('.nav-submenu-item').forEach(n => n.classList.remove('active'));
    document.getElementById('main-content')?.scrollTo({ top: 0, behavior: 'smooth' });
    // Cheap access probe; cache it and refresh only via the explicit button.
    if (!state.permissionReport) fetchPermissionReport();
  });

  if (themeSelect) {
    themeSelect.addEventListener('change', (e) => {
      state.theme = e.target.value;
      document.documentElement.setAttribute('data-theme', state.theme);
      localStorage.setItem('macmaid_theme', state.theme);
      const mainTheme = document.getElementById('main-theme-selector');
      if (mainTheme) mainTheme.value = state.theme;
    });
  }

  // Language selector in Settings page
  const langSelect = document.getElementById('setting-lang-select');
  if (langSelect) {
    langSelect.value = state.lang;
    langSelect.addEventListener('change', (e) => {
      const newLang = e.target.value;
      state.lang = newLang;
      localStorage.setItem('macmaid_lang', newLang);
      applyLanguage(newLang);
      SoundEffects.playClick();
      const msg = newLang === 'en' ? I18N.en['toast.lang_en'] : I18N.tr['toast.lang_tr'];
      showToast(msg, 'info');
    });
  }

  // Main settings theme selector
  const mainThemeSelect = document.getElementById('main-theme-selector');
  if (mainThemeSelect) {
    mainThemeSelect.value = state.theme;
    mainThemeSelect.addEventListener('change', (e) => {
      state.theme = e.target.value;
      document.documentElement.setAttribute('data-theme', state.theme);
      localStorage.setItem('macmaid_theme', state.theme);
      if (themeSelect) themeSelect.value = state.theme;
      SoundEffects.playClick();
    });
  }

  // Main settings sound toggle
  const mainSoundSetting = document.getElementById('chk-main-sound-setting');
  if (mainSoundSetting) {
    mainSoundSetting.checked = state.soundEnabled;
    mainSoundSetting.addEventListener('change', (e) => {
      state.soundEnabled = e.target.checked;
      localStorage.setItem('macmaid_sound', state.soundEnabled ? 'on' : 'off');
      if (soundSetting) soundSetting.checked = state.soundEnabled;
      soundBtn?.querySelector('.icon-sound-on')?.classList.toggle('hidden', !state.soundEnabled);
      soundBtn?.querySelector('.icon-sound-off')?.classList.toggle('hidden', state.soundEnabled);
      SoundEffects.playClick();
    });
  }

  // Save main settings button
  document.getElementById('btn-save-main-settings')?.addEventListener('click', () => {
    SoundEffects.playSuccess();
    const msg = state.lang === 'tr' ? I18N.tr['toast.settings_saved'] : I18N.en['toast.settings_saved'];
    showToast(msg, 'success');
  });

  // Apply language on initial load
  applyLanguage(state.lang);
  renderIcons();

  document.querySelector('.nav-item.active')?.setAttribute('aria-current', 'page');

  // Initialize sidebar submenu state from the active sub-pane; in-page subnav was removed.
  const activeMoreTab = document.querySelector('#pane-more .sub-pane.active')?.id?.replace('subpane-more-', '') || 'leftovers';
  document.querySelector(`.nav-submenu-item[data-subtab="${activeMoreTab}"]`)?.classList.add('active');

  const activeDevTab = document.querySelector('#pane-developer .sub-pane.active')?.id?.replace('subpane-dev-', '') || 'storage';
  document.querySelector(`.nav-submenu-item[data-devsubtab="${activeDevTab}"]`)?.classList.add('active');

  // Expand submenus if they are the active tab
  if (state.activeTab === 'more') {
    document.querySelector('.nav-item[data-tab="more"]')?.classList.add('expanded');
  }
  if (state.activeTab === 'developer') {
    document.querySelector('.nav-item[data-tab="developer"]')?.classList.add('expanded');
  }

  // Initial polling: a single progress probe; status polling starts only when
  // the dashboard tab becomes visible (syncStatusPolling in activateTopLevelTab).
  pollLiveProgress();
});
