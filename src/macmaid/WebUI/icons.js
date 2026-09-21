/* =========================================================
   MacMaid Pro — Shared SF-style icon catalog and renderer
   ========================================================= */

// System glyphs used by the Web UI, named after the SF Symbols they mirror.
// SF Symbols itself cannot ship inside a web surface, so each entry is a
// hand-drawn monochrome SVG approximation of the system symbol — filled
// silhouettes for object icons, hairline strokes for instrument glyphs —
// keeping one shared catalog instead of mixing emoji and icon packs.
const SF_SYMBOLS = {
  'app': ['fill', '<rect x="4" y="4" width="16" height="16" rx="4.4"/>'],
  'archivebox': ['fill', '<path fill-rule="evenodd" d="M3 3.5h18a1 1 0 0 1 1 1v3a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1v-3a1 1 0 0 1 1-1zM4 10h16l-.8 9.6a2 2 0 0 1-2 1.9H6.8a2 2 0 0 1-2-1.9L4 10zm5.5 2.2a1 1 0 0 0 0 2h5a1 1 0 0 0 0-2h-5z"/>'],
  'arrow.clockwise': ['stroke', '<path d="M20 12a8 8 0 1 1-2.3-5.6"/><path d="M20 3.6v4h-4"/>'],
  'arrow.down': ['stroke', '<path d="M12 4v16"/><path d="M5.5 13.5 12 20l6.5-6.5"/>'],
  'arrow.down.circle': ['fill', '<path fill-rule="evenodd" d="M12 2.5a9.5 9.5 0 1 0 0 19 9.5 9.5 0 0 0 0-19zM8.2 11.7l1.2-1.2 1.8 1.8V6.8h1.6v5.5l1.8-1.8 1.2 1.2-3.8 3.8-3.8-3.8z"/>'],
  'arrow.up': ['stroke', '<path d="M12 20V4"/><path d="M5.5 10.5 12 4l6.5 6.5"/>'],
  'arrow.up.arrow.down': ['stroke', '<path d="M8 4v16"/><path d="M4.5 7.5 8 4l3.5 3.5"/><path d="M16 20V4"/><path d="M12.5 16.5 16 20l3.5-3.5"/>'],
  'bolt': ['fill', '<path d="M13.1 2 4.6 13.6h5.3L8.8 22l8.7-11.6h-5.3L13.1 2z"/>'],
  'chart.line.uptrend.xyaxis': ['stroke', '<path d="M4 4v15a1 1 0 0 0 1 1h15"/><path d="M7.5 14.5l3.5-3.5 2.5 2.5 5-5"/><path d="M15.6 8.5h3v3"/>'],
  'checkmark': ['stroke', '<path d="M5 12.5l4.5 4.5L19 7.5"/>'],
  'checkmark.circle': ['fill', '<path fill-rule="evenodd" d="M12 2.5a9.5 9.5 0 1 0 0 19 9.5 9.5 0 0 0 0-19zm4.8 6.7-6.2 6.2-3.4-3.4 1.2-1.2 2.2 2.2 5-5 1.2 1.2z"/>'],
  'checkmark.shield': ['fill', '<path fill-rule="evenodd" d="M12 2.3l7.5 2.8v6.4c0 4.9-3.2 8-7.5 9.7-4.3-1.7-7.5-4.8-7.5-9.7V5.1L12 2.3zm4.6 7.2-5.6 5.6-2.7-2.7 1.1-1.1 1.6 1.6 4.5-4.5 1.1 1.1z"/>'],
  'circle.circle': ['fill', '<path fill-rule="evenodd" d="M12 2.5a9.5 9.5 0 1 0 0 19 9.5 9.5 0 0 0 0-19zM12 3.7a8.3 8.3 0 1 1 0 16.6 8.3 8.3 0 0 1 0-16.6zM12 6.6a5.4 5.4 0 1 0 0 10.8 5.4 5.4 0 0 0 0-10.8zm0 1.8a3.6 3.6 0 1 1 0 7.2 3.6 3.6 0 0 1 0-7.2z"/>'],
  'clock': ['stroke', '<circle cx="12" cy="12" r="8.5"/><path d="M12 7v5.2l3.4 2"/>'],
  'clock.arrow.circlepath': ['stroke', '<path d="M20.5 12a8.5 8.5 0 1 1-2.6-6.1"/><path d="M20.5 3.5v4h-4"/><path d="M12 7.5v4.7l3.2 1.9"/>'],
  'cpu': ['fill', '<path fill-rule="evenodd" d="M8 4h8a4 4 0 0 1 4 4v8a4 4 0 0 1-4 4H8a4 4 0 0 1-4-4V8a4 4 0 0 1 4-4zM9.5 9.5h5v5h-5z"/><path d="M9.2 1.5h1.6v2.4H9.2V1.5zm4 0h1.6v2.4h-1.6V1.5zM9.2 20.1h1.6v2.4H9.2v-2.4zm4 0h1.6v2.4h-1.6v-2.4zM1.5 9.2h2.4v1.6H1.5V9.2zm0 4h2.4v1.6H1.5v-1.6zM20.1 9.2h2.4v1.6h-2.4V9.2zm0 4h2.4v1.6h-2.4v-1.6z"/><rect x="10" y="10" width="4" height="4" rx="0.6"/>'],
  'curlybraces': ['fill', '<path d="M8.6 3.5c-1.8 0-2.9 1.1-2.9 2.9v3c0 1-.6 1.7-1.8 1.7v1.8c1.2 0 1.8.7 1.8 1.7v3c0 1.8 1.1 2.9 2.9 2.9h.8v-1.8h-.5c-.8 0-1.1-.4-1.1-1.2v-3.3c0-.9-.5-1.7-1.4-2.2.9-.5 1.4-1.3 1.4-2.2V6.4c0-.8.3-1.2 1.1-1.2h.5V3.5h-.8zm6.8 0c1.8 0 2.9 1.1 2.9 2.9v3c0 1 .6 1.7 1.8 1.7v1.8c-1.2 0-1.8.7-1.8 1.7v3c0 1.8-1.1 2.9-2.9 2.9h-.8v-1.8h.5c.8 0 1.1-.4 1.1-1.2v-3.3c0-.9.5-1.7 1.4-2.2-.9-.5-1.4-1.3-1.4-2.2V6.4c0-.8-.3-1.2-1.1-1.2h-.5V3.5h.8z"/>'],
  'cylinder': ['fill', '<ellipse cx="12" cy="5.8" rx="8.5" ry="2.8"/><path d="M3.5 5.8v11.7c0 1.9 3.8 3.5 8.5 3.5s8.5-1.6 8.5-3.5V5.8c0 1.9-3.8 3.5-8.5 3.5s-8.5-1.6-8.5-3.5z"/>'],
  'doc': ['stroke', '<path d="M6.5 3.5h6.8l5.2 5.2V19a2 2 0 0 1-2 2H6.5a2 2 0 0 1-2-2V5.5a2 2 0 0 1 2-2z"/><path d="M13 3.5V9h5.5"/>'],
  'doc.on.doc': ['fill', '<path d="M9.5 2.5H16a2.5 2.5 0 0 1 2.5 2.5v9a2.5 2.5 0 0 1-2.5 2.5H9.5A2.5 2.5 0 0 1 7 14V5a2.5 2.5 0 0 1 2.5-2.5z"/><path d="M5.5 6.5v10A4 4 0 0 0 9.5 20.5H17a2.5 2.5 0 0 1-1.8 2H5.7A3.7 3.7 0 0 1 2 18.8v-8.6a3.5 3.5 0 0 1 3.5-3.7z"/>'],
  'doc.text.magnifyingglass': ['fill', '<path fill-rule="evenodd" d="M6.5 2.5h6.3l5.7 5.7v2.1a5.2 5.2 0 0 0-7.9 10.2H6.5a2 2 0 0 1-2-2V4.5a2 2 0 0 1 2-2zm5.8 1.7V8h3.8l-3.8-3.8zM8 9.2h4.8v1.5H8V9.2zm0 2.8h3.4v1.5H8V12z"/><path fill-rule="evenodd" d="M15.2 13a3.6 3.6 0 1 0 0 7.2 3.6 3.6 0 0 0 0-7.2zm0 1.5a2.1 2.1 0 1 1 0 4.2 2.1 2.1 0 0 1 0-4.2zm-3.1 4.3 2.6 2.6a.9.9 0 0 0 1.3-1.3l-2.3-2.3c-.5.4-1 .7-1.6 1z"/>'],
  'ellipsis.circle': ['fill', '<path fill-rule="evenodd" d="M12 2.5a9.5 9.5 0 1 0 0 19 9.5 9.5 0 0 0 0-19zM6.8 10.6a1.4 1.4 0 1 1 0 2.8 1.4 1.4 0 0 1 0-2.8zm5.2 0a1.4 1.4 0 1 1 0 2.8 1.4 1.4 0 0 1 0-2.8zm5.2 0a1.4 1.4 0 1 1 0 2.8 1.4 1.4 0 0 1 0-2.8z"/>'],
  'exclamationmark.circle': ['fill', '<path fill-rule="evenodd" d="M12 2.5a9.5 9.5 0 1 0 0 19 9.5 9.5 0 0 0 0-19zM10.9 6.5h2.2l-.3 7h-1.6l-.3-7zM12 15a1.3 1.3 0 1 1 0 2.6 1.3 1.3 0 0 1 0-2.6z"/>'],
  'exclamationmark.triangle': ['fill', '<path fill-rule="evenodd" d="M12.9 3.8 21.9 19a1.5 1.5 0 0 1-1.3 2.2H3.4A1.5 1.5 0 0 1 2.1 19L11.1 3.8a1.5 1.5 0 0 1 1.8 0zM11 9.2l.2 4.8h1.6l.2-4.8H11zm1 6.4a1.35 1.35 0 1 0 0 2.7 1.35 1.35 0 0 0 0-2.7z"/>'],
  'folder': ['fill', '<path d="M4.5 3.5h4.6c.6 0 1.1.2 1.5.7l1 1.3c.2.3.6.5 1 .5h7c1.4 0 2.4 1 2.4 2.4v9.2c0 1.4-1 2.4-2.4 2.4h-15C3.1 20 2 19 2 17.6V5.9C2 4.5 3.1 3.5 4.5 3.5z"/>'],
  'folder.badge.gearshape': ['fill', '<path fill-rule="evenodd" d="M4.5 3.5h4.6c.6 0 1.1.2 1.5.7l1 1.3c.2.3.6.5 1 .5h7c1.4 0 2.4 1 2.4 2.4v9.2c0 1.4-1 2.4-2.4 2.4h-15C3.1 20 2 19 2 17.6V5.9C2 4.5 3.1 3.5 4.5 3.5zM16.8 10.6a4.9 4.9 0 1 0 0 9.8 4.9 4.9 0 0 0 0-9.8z"/><path fill-rule="evenodd" d="M16.3 12.4h1l.3 1.2 1 .4 1-.7.7.7-.7 1 .4 1 1.2.3v1l-1.2.3-.4 1 .7 1-.7.7-1-.7-1 .4-.3 1.2h-1l-.3-1.2-1-.4-1 .7-.7-.7.7-1-.4-1-1.2-.3v-1l1.2-.3.4-1-.7-1 .7-.7 1 .7 1-.4.3-1.2zm.5 2.5a1.6 1.6 0 1 0 0 3.2 1.6 1.6 0 0 0 0-3.2z"/>'],
  'gearshape': ['fill', '<path fill-rule="evenodd" d="M10.8 2.2h2.4l.5 2.5 1.9.8 2.1-1.4 1.7 1.7-1.4 2.1.8 1.9 2.5.5v2.4l-2.5.5-.8 1.9 1.4 2.1-1.7 1.7-2.1-1.4-1.9.8-.5 2.5h-2.4l-.5-2.5-1.9-.8-2.1 1.4-1.7-1.7 1.4-2.1-.8-1.9-2.5-.5v-2.4l2.5-.5.8-1.9-1.4-2.1 1.7-1.7 2.1 1.4 1.9-.8.5-2.5zM12 8.4a3.6 3.6 0 1 0 0 7.2 3.6 3.6 0 0 0 0-7.2z"/>'],
  'globe': ['stroke', '<circle cx="12" cy="12" r="8.5"/><path d="M3.5 12h17"/><path d="M12 3.5c2.8 2.3 4.2 5.2 4.2 8.5s-1.4 6.2-4.2 8.5c-2.8-2.3-4.2-5.2-4.2-8.5s1.4-6.2 4.2-8.5z"/>'],
  'hammer': ['fill', '<path d="M13.7 3.3l7 7-2 2-2.2-2.2-8.1 8.1a2.3 2.3 0 0 1-3.2-3.2l8.1-8.1-2.2-2.2 2.6-1.4z"/>'],
  'info.circle': ['fill', '<path fill-rule="evenodd" d="M12 2.5a9.5 9.5 0 1 0 0 19 9.5 9.5 0 0 0 0-19zM12 6.6a1.4 1.4 0 1 1 0 2.8 1.4 1.4 0 0 1 0-2.8zM10.9 11h2.2v6.5h-2.2V11z"/>'],
  'internaldrive': ['fill', '<path fill-rule="evenodd" d="M4.5 3.5h15a2.5 2.5 0 0 1 2.5 2.5v12a2.5 2.5 0 0 1-2.5 2.5h-15A2.5 2.5 0 0 1 2 18V6a2.5 2.5 0 0 1 2.5-2.5zM12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8zm0 2.6a1.4 1.4 0 1 1 0 2.8 1.4 1.4 0 0 1 0-2.8zM5.6 5.4h1.8v1.6H5.6V5.4z"/>'],
  'list.bullet': ['fill', '<path d="M4 5.5a1.4 1.4 0 1 0 0 2.8 1.4 1.4 0 0 0 0-2.8zm0 5.1a1.4 1.4 0 1 0 0 2.8 1.4 1.4 0 0 0 0-2.8zm0 5.1a1.4 1.4 0 1 0 0 2.8 1.4 1.4 0 0 0 0-2.8zM8.5 5.6h12v2.4h-12V5.6zm0 5.1h12v2.4h-12v-2.4zm0 5.1h12v2.4h-12v-2.4z"/>'],
  'magnifyingglass': ['stroke', '<circle cx="10.5" cy="10.5" r="6.5"/><path d="M15.3 15.3 21 21"/>'],
  'memorychip': ['fill', '<path fill-rule="evenodd" d="M7 5h10a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2zM9.4 9.4h5.2v5.2H9.4z"/><path d="M9 2.8h1.6v2.1H9V2.8zm3.2 0h1.6v2.1h-1.6V2.8zm3.2 0H17v2.1h-1.6V2.8zM9 19.1h1.6v2.1H9v-2.1zm3.2 0h1.6v2.1h-1.6v-2.1zm3.2 0H17v2.1h-1.6v-2.1zM2.8 9h2.1v1.6H2.8V9zm0 3.2h2.1v1.6H2.8v-1.6zm0 3.2h2.1V17H2.8v-1.6zM19.1 9h2.1v1.6h-2.1V9zm0 3.2h2.1v1.6h-2.1v-1.6zm0 3.2h2.1V17h-2.1v-1.6z"/>'],
  'shield': ['fill', '<path d="M12 2.3l7.5 2.8v6.4c0 4.9-3.2 8-7.5 9.7-4.3-1.7-7.5-4.8-7.5-9.7V5.1L12 2.3z"/>'],
  'slider.horizontal.3': ['stroke', '<path d="M4 6.5h16M4 12h16M4 17.5h16"/><circle cx="9" cy="6.5" r="2.1" fill="currentColor" stroke="none"/><circle cx="15" cy="12" r="2.1" fill="currentColor" stroke="none"/><circle cx="7" cy="17.5" r="2.1" fill="currentColor" stroke="none"/>'],
  'sparkles': ['fill', '<path d="M12.6 3l1.8 5.6 5.6 1.8-5.6 1.8-1.8 5.6-1.8-5.6L5 10.4l5.6-1.8z"/><path d="M18.6 14.8l.9 2.7 2.7.9-2.7.9-.9 2.7-.9-2.7-2.7-.9 2.7-.9z"/><path d="M5.4 3.4l.7 2 2 .7-2 .7-.7 2-.7-2-2-.7 2-.7z"/>'],
  'square.and.arrow.down': ['stroke', '<path d="M12 3v9"/><path d="M8.5 8.5 12 12l3.5-3.5"/><path d="M4.5 12.5v6a2 2 0 0 0 2 2h11a2 2 0 0 0 2-2v-6"/>'],
  'square.grid.2x2': ['fill', '<path d="M4.5 4h6a1 1 0 0 1 1 1v5.5a1 1 0 0 1-1 1h-6a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1zm9 0h6a1 1 0 0 1 1 1v5.5a1 1 0 0 1-1 1h-6a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1zM4.5 12.5h6a1 1 0 0 1 1 1V19a1 1 0 0 1-1 1h-6a1 1 0 0 1-1-1v-5.5a1 1 0 0 1 1-1zm9 0h6a1 1 0 0 1 1 1V19a1 1 0 0 1-1 1h-6a1 1 0 0 1-1-1v-5.5a1 1 0 0 1 1-1z"/>'],
  'square.stack.3d.up': ['fill', '<path d="M12 3l8.8 4.4L12 11.8 3.2 7.4 12 3z"/><path d="M4.6 10.6l7.4 3.7 7.4-3.7 1.4 1.4-8.8 4.4-8.8-4.4 1.4-1.4z"/><path d="M4.6 15.1l7.4 3.7 7.4-3.7 1.4 1.4-8.8 4.4-8.8-4.4 1.4-1.4z"/>'],
  'stethoscope': ['stroke', '<path d="M5.5 3.5H4M5.5 3.5h1.5M7 3.5v5a5 5 0 0 0 10 0v-5h-1.5M17 3.5h-1.5"/><path d="M12 13.5v2.5a4.5 4.5 0 0 0 9 0v-3"/><circle cx="21" cy="10.5" r="1.8"/>'],
  'sun.max': ['fill', '<path d="M12 7a5 5 0 1 0 0 10 5 5 0 0 0 0-10zM11.1 1.8h1.8v2.6h-1.8V1.8zm0 17.6h1.8V22h-1.8v-2.6zM3.6 5.1l2 1.2-1 1.7-2-1.2 1-1.7zm14.8 13.1 2 1.2-1 1.7-2-1.2 1-1.7zM1.8 11.1h2.6v1.8H1.8v-1.8zm17.6 0H22v1.8h-2.6v-1.8zM3.6 18.9l1-1.7 2 1.2-1 1.7-2-1.2zm14.8-13.8 2-1.2 1 1.7-2 1.2-1-1.7z"/>'],
  'speaker.slash': ['fill', '<path d="M11 3.5 6.8 7.5H3.5v9h3.3L11 20.5v-17z"/><path d="M15.6 9.9l1.4-1.4 2 2 2-2 1.4 1.4-2 2 2 2-1.4 1.4-2-2-2 2-1.4-1.4 2-2-2-2z"/>'],
  'speaker.wave.2': ['fill', '<path d="M11 3.5 6.8 7.5H3.5v9h3.3L11 20.5v-17z"/><path d="M14.6 8.2a5 5 0 0 1 0 7.6l-1.2-1.2a3.3 3.3 0 0 0 0-5.2l1.2-1.2z"/><path d="M16.9 5.4a9 9 0 0 1 0 13.2l-1.2-1.2a7.2 7.2 0 0 0 0-10.8l1.2-1.2z"/>'],
  'terminal': ['fill', '<path fill-rule="evenodd" d="M3.5 4h17a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-17a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2zm2.8 4.3a.9.9 0 0 0 0 1.3l2.6 2.6-2.6 2.6a.9.9 0 1 0 1.3 1.3l3.3-3.3a.9.9 0 0 0 0-1.3L7.6 8.3a.9.9 0 0 0-1.3 0zm5.6 7h6v1.6h-6v-1.6z"/>'],
  'trash': ['fill', '<path fill-rule="evenodd" d="M9.2 2.5h5.6l1 2h4.4v2H3.8v-2h4.4l1-2zM5.6 8.5h12.8l-1.1 12a2.2 2.2 0 0 1-2.2 2H8.9a2.2 2.2 0 0 1-2.2-2l-1.1-12zm3.7 2.8.4 8.2h1.4l-.4-8.2H9.3zm4 0h1.4l.4 8.2h-1.4l-.4-8.2z"/>'],
  'tray.full': ['fill', '<path fill-rule="evenodd" d="M4 10.5h3.6l1.4 2.2c.3.5.8.8 1.4.8h3.2c.6 0 1.1-.3 1.4-.8l1.4-2.2H20a1.5 1.5 0 0 1 1.5 1.5v6.5a1.5 1.5 0 0 1-1.5 1.5H4a1.5 1.5 0 0 1-1.5-1.5V12A1.5 1.5 0 0 1 4 10.5zM7 3.5h10v1.8H7V3.5zm1.5 3h7v1.8h-7V6.5z"/>'],
  'waveform.path.ecg': ['stroke', '<path d="M2.5 12h4l2-7 4 14 3-9.5 1.5 2.5h4.5"/>'],
  'xmark': ['fill', '<path d="M5.6 4.2 12 10.6l6.4-6.4a1 1 0 0 1 1.4 1.4L13.4 12l6.4 6.4a1 1 0 0 1-1.4 1.4L12 13.4l-6.4 6.4a1 1 0 0 1-1.4-1.4L10.6 12 4.2 5.6a1 1 0 0 1 1.4-1.4z"/>'],
};

function sfSymbol(name, className = '') {
  const entry = SF_SYMBOLS[name] || SF_SYMBOLS['info.circle'];
  const slug = name.replace(/[^a-z0-9]+/gi, '-');
  const classes = ['sf', `sf-${slug}`, className].filter(Boolean).join(' ');
  const paint = entry[0] === 'fill'
    ? 'fill="currentColor" stroke="none"'
    : 'fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"';
  return `<svg class="${classes}" xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" ${paint} aria-hidden="true">${entry[1]}</svg>`;
}

function renderIcons(root = document) {
  root.querySelectorAll('[data-icon]').forEach(el => {
    el.innerHTML = sfSymbol(el.dataset.icon);
    el.setAttribute('aria-hidden', 'true');
  });
}
