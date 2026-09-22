"""Centralised LinkedIn selectors.

LinkedIn changes its UI regularly. Every entry is a list of fallbacks tried in
order; prefer accessible roles / visible text over deep CSS. When something
breaks, this is the only file that should need updating.
"""

# ---------- global page state ----------
LOGIN_URL_MARKERS = ["/login", "/authwall", "/uas/login", "/checkpoint/lg/login", "/signup"]
VERIFICATION_URL_MARKERS = ["/checkpoint/challenge", "/checkpoint/rp", "/checkpoint/lg/", "/captcha"]
VERIFICATION_TEXT_MARKERS = [
    "security verification",
    "quick security check",
    "let's do a quick verification",
    "verify your identity",
    "verification code",
    "enter the code",
    "we've detected unusual activity",
    "unusual activity",
    "prove you're human",
    "are you a robot",
    "captcha",
]
VERIFICATION_IFRAMES = [
    "iframe[src*='captcha']",
    "iframe[title*='captcha' i]",
    "iframe[src*='arkoselabs']",
    "iframe[src*='recaptcha']",
    "iframe[src*='hcaptcha']",
]
LOGGED_IN_MARKERS = [
    "a[href*='/mynetwork/']",
    "img.global-nav__me-photo",
    "button.global-nav__primary-link-me-menu-trigger",
    "nav.global-nav",
]

# ---------- job page ----------
JOB_PAGE_URL_MARKERS = ["/jobs/view/", "/jobs/collections/", "/jobs/search/"]
# The 2026 job page has no <h1> and obfuscated class names; the title comes
# from document.title ("<Job> | <Company> | LinkedIn"), these are fallbacks.
JOB_TITLE = [
    "h1.t-24",
    ".job-details-jobs-unified-top-card__job-title h1",
    "main h1",
]
JOB_COMPANY_NAME = [
    ".job-details-jobs-unified-top-card__company-name a",
    "main a[href*='/company/']",
]
EASY_APPLY_BUTTON = [
    "button[aria-label*='Easy Apply']",
    "button.jobs-apply-button:has-text('Easy Apply')",
    "button:has-text('Easy Apply')",
]
EXTERNAL_APPLY_BUTTON = [
    "button[aria-label^='Apply to']",
    "button.jobs-apply-button:has-text('Apply')",
    "a.jobs-apply-button",
    "main button:has-text('Apply'):not(:has-text('Easy'))",
]
ALREADY_APPLIED_MARKERS = [
    ".artdeco-inline-feedback:has-text('Applied')",
    ".jobs-s-apply__application-link",
    ".post-apply-timeline",
    "main :text-matches('^Applied( |$)', 'i')",
    "main :text-matches('^Application submitted', 'i')",
    "main :text-matches('See application', 'i')",
]
JOB_CLOSED_MARKERS = [
    "main :text-matches('No longer accepting applications', 'i')",
    "main :text-matches('Not currently accepting applications', 'i')",
    "main :text-matches('This job is no longer available', 'i')",
    "main :text-matches('job is closed', 'i')",
    ".jobs-details-top-card__apply-error",
]

# ---------- Easy Apply modal ----------
# APPLY_MODAL is located from the page; everything marked "(modal-scoped)" is
# looked up *inside* that modal locator, so those selectors carry no prefix.
# 2026 UI: a native <dialog> holding the whole form on one screen
# (contact info + resume radiogroup + "Submit application"). Older UI: a
# div[role=dialog] with Next / Review steps. Both are handled.
APPLY_MODAL = [
    "dialog:has-text('Apply')",
    "div.jobs-easy-apply-modal",
    "div[role='dialog']:has(button[aria-label='Dismiss'])",
    "div[role='dialog']",
]
APPLY_MODAL_HEADING = ["h3", "h2"]  # (modal-scoped)
APPLY_NEXT = [  # (modal-scoped)
    "button[aria-label='Continue to next step']",
    "button:has-text('Next')",
]
APPLY_REVIEW = [  # (modal-scoped)
    "button[aria-label='Review your application']",
    "button:has-text('Review')",
]
APPLY_SUBMIT = [  # (modal-scoped)
    "button[aria-label='Submit application']",
    "button:has-text('Submit application')",
]
APPLY_DISMISS = [
    "dialog button[aria-label='Dismiss']",
    "div[role='dialog'] button[aria-label='Dismiss']",
    "div[role='dialog'] button.artdeco-modal__dismiss",
]
APPLY_DISCARD = [
    "button[data-control-name='discard_application_confirm_btn']",
    "div[role='alertdialog'] button:has-text('Discard')",
    "button:has-text('Discard')",
]
APPLY_ERROR = [  # (modal-scoped)
    ".artdeco-inline-feedback--error",
    "[role='alert']",
    ".fb-form-element__error-text",
    "[aria-invalid='true']",
    "[class*='error']",
]
APPLY_SUCCESS = [
    "text=/Your application was sent/i",
    "text=/Application sent/i",
    "text=/application was submitted/i",
    "text=/Application submitted/i",
    "h2:has-text('application was sent')",
]
# resume step (modal-scoped)
RESUME_CARDS = [
    ".jobs-document-upload-redesign-card__container",
    ".jobs-document-upload__container",
    ".jobs-resume-picker__resume",
    "[class*='document-upload'] [class*='card']",
]
# Generic fallback: any radio control in the modal; the card is its nearest
# ancestor whose text contains a document file extension.
# 2026 UI: div[role=radio][aria-label="<file name>"] with aria-checked.
RESUME_RADIO_LABELLED = ["[role='radio'][aria-label]"]
RESUME_RADIOS = ["input[type='radio']", "[role='radio']"]
RESUME_CARD_FROM_RADIO_XPATH = (
    "xpath=ancestor::*[contains(., '.pdf') or contains(., '.PDF') or contains(., '.doc') or contains(., '.DOC')][1]"
)
RESUME_CARD_NAME = [  # (card-scoped)
    ".jobs-document-upload-redesign-card__file-name",
    ".jobs-document-upload__file-name",
    "h3",
    "[class*='file-name']",
]
RESUME_CARD_SELECT_BUTTON = [  # (card-scoped)
    "button:has-text('Select')",
    "input[type='radio']",
    "[role='radio']",
    "label",
]
RESUME_SHOW_MORE = [  # (modal-scoped)
    "button:has-text('Show more resumes')",
    "button[aria-label*='more resumes']",
]
RESUME_STEP_MARKERS = ["resume", "upload"]

# form fields inside the modal (modal-scoped, structure-based). The JS tags
# each field with data-agent-idx so Python can locate it afterwards.
FORM_FIELDS_JS = r"""(dlg) => {
  const vis = e => e.getClientRects().length > 0;
  const clean = t => (t || '').replace(/\s+/g, ' ').trim();
  const fileRe = /\.(pdf|docx?|txt)(?![a-z])/i;
  dlg.querySelectorAll('[data-agent-idx]').forEach(e => e.removeAttribute('data-agent-idx'));
  const out = [];
  let idx = 0;
  const labelFor = el => {
    if (el.id) { const l = dlg.querySelector('label[for="' + CSS.escape(el.id) + '"]'); if (l) return clean(l.innerText); }
    const lb = el.getAttribute('aria-labelledby');
    if (lb) { const t = lb.split(/\s+/).map(i => document.getElementById(i)).filter(Boolean).map(e => clean(e.innerText)).join(' '); if (t) return t; }
    if (el.getAttribute('aria-label')) return clean(el.getAttribute('aria-label'));
    const wrap = el.closest('label'); if (wrap) return clean(wrap.innerText.replace(el.value || '', ''));
    let c = el;
    for (let i = 0; i < 4 && c.parentElement; i++) {
      c = c.parentElement;
      const lines = (c.innerText || '').split('\n').map(clean).filter(Boolean);
      if (lines.length) return lines[0];
    }
    return '';
  };
  // text / number / textarea / select
  for (const el of dlg.querySelectorAll('input, textarea, select')) {
    if (!vis(el)) continue;
    const type = (el.getAttribute('type') || el.tagName.toLowerCase()).toLowerCase();
    if (['hidden', 'radio', 'checkbox', 'file', 'submit', 'button'].includes(type)) continue;
    el.setAttribute('data-agent-idx', String(idx));
    let kind = 'text', options = [], value = el.value || '';
    if (el.tagName === 'SELECT') { kind = 'select'; options = [...el.options].map(o => clean(o.text)); value = el.selectedIndex >= 0 ? clean(el.options[el.selectedIndex].text) : ''; }
    else if (type === 'number' || (el.getAttribute('inputmode') || '').match(/numeric|decimal/)) kind = 'number';
    out.push({idx, kind, label: labelFor(el), value: clean(value), options, required: el.required || (el.getAttribute('aria-required') === 'true'), maxlen: el.maxLength > 0 ? el.maxLength : 0});
    idx++;
  }
  // radio groups
  const groups = new Set();
  for (const r of dlg.querySelectorAll('[role=radio], input[type=radio]')) {
    const g = r.closest('[role=radiogroup], fieldset') || r.parentElement.parentElement;
    if (g) groups.add(g);
  }
  for (const g of groups) {
    const radios = [...g.querySelectorAll('[role=radio], input[type=radio]')];
    const opts = [], checkedOpts = [];
    for (const r of radios) {
      let t = r.getAttribute('aria-label') || '';
      if (!t && r.id) { const l = g.querySelector('label[for="' + CSS.escape(r.id) + '"]'); if (l) t = l.innerText; }
      if (!t) { const l = r.closest('label'); if (l) t = l.innerText; }
      t = clean(t);
      if (!t || opts.includes(t)) continue;
      opts.push(t);
      const checked = r.checked || r.getAttribute('aria-checked') === 'true';
      if (checked) checkedOpts.push(t);
    }
    if (!opts.length || opts.some(o => fileRe.test(o))) continue;  // resume picker handled elsewhere
    g.setAttribute('data-agent-idx', String(idx));
    const legend = g.querySelector('legend');
    let label = legend ? clean(legend.innerText) : '';
    if (!label) { const lines = (g.innerText || '').split('\n').map(clean).filter(x => x && !opts.includes(x)); label = lines[0] || ''; }
    out.push({idx, kind: 'radio', label, value: checkedOpts[0] || '', options: opts, required: g.getAttribute('aria-required') === 'true'});
    idx++;
  }
  return out;
}"""
FORM_FIELD_BY_IDX = "[data-agent-idx='{idx}']"
# Visible validation messages inside the modal, mapped to the nearest tagged
# field (run FORM_FIELDS_JS first so fields carry data-agent-idx).
FORM_ERRORS_JS = r"""(dlg) => {
  const vis = e => e.getClientRects().length > 0;
  const clean = t => (t || '').replace(/\s+/g, ' ').trim();
  const errRe = /^(invalid|please (enter|select|provide|choose)|required|this field|must be|enter a valid|value must|should be|cannot|can't|too long|maximum|minimum|select an option|choose an option|not valid|valid (number|input|value|email|phone))/i;
  const out = [];
  const leaves = [...dlg.querySelectorAll('span, p, div, small, label')].filter(e => vis(e) && e.children.length === 0);
  for (const e of leaves) {
    const t = clean(e.innerText);
    if (!t || t.length > 120) continue;
    const isAlert = e.getAttribute('role') === 'alert' || e.getAttribute('aria-live') || /error|invalid/i.test(e.className || '');
    if (!isAlert && !errRe.test(t)) continue;
    let c = e, idx = null;
    for (let i = 0; i < 6 && c; i++) {
      c = c.parentElement; if (!c) break;
      const f = c.querySelector('[data-agent-idx]');
      if (f) { idx = f.getAttribute('data-agent-idx'); break; }
    }
    out.push({idx: idx === null ? null : parseInt(idx, 10), text: t});
  }
  return out;
}"""

# ---------- company / people ----------
# 2026 UI: the company page redirects to /posts/, has no <h1>, and exposes the
# numeric company id in an "N employees" link (currentCompany=["<id>"]). People
# are then found through LinkedIn's people search with that id + keywords.
COMPANY_PAGE_MARKERS = [
    "main a[href*='/people/']",
    "a[href*='currentCompany']",
    "h1.org-top-card-summary__title",
    "main h1",
]
COMPANY_NAME = [
    "h1.org-top-card-summary__title",
    "main h1",
]
COMPANY_ID_LINK = ["a[href*='currentCompany=']"]
COMPANY_NOT_FOUND = [
    "text=/Page not found/i",
    "text=/This page doesn't exist/i",
]
PEOPLE_SEARCH_URL = "https://www.linkedin.com/search/results/people/?currentCompany=%5B%22{company_id}%22%5D&keywords={keywords}&origin=FACETED_SEARCH"
PEOPLE_RESULT_LINKS = ["main a[href*='/in/']"]
PEOPLE_NEXT_PAGE = ["button[aria-label='Next']", "main button:has-text('Next')"]
PEOPLE_SHOW_MORE = [
    "button.scaffold-finite-scroll__load-button",
    "button:has-text('Show more results')",
]
PEOPLE_NO_RESULTS = [
    "main :text-matches('No results found', 'i')",
    "main :text-matches('no employees', 'i')",
]
# JS: extract people cards from the current page (search results or company
# People tab). Each visible profile link -> nearest ancestor with >= 3 lines.
PEOPLE_CARDS_JS = r"""() => {
  const vis = e => e.getClientRects().length > 0;
  const degree = /^[^A-Za-z0-9]*(1st|2nd|3rd)\+?$/;
  const seen = new Set(); const out = [];
  for (const a of document.querySelectorAll('main a[href*="/in/"]')) {
    if (!vis(a)) continue;
    const href = (a.getAttribute('href') || '').split('?')[0];
    if (!/\/in\/[^/]+/.test(href) || seen.has(href)) continue;
    let card = a, lines = [];
    for (let i = 0; i < 8 && card.parentElement; i++) {
      card = card.parentElement;
      lines = (card.innerText || '').split('\n').map(x => x.trim()).filter(Boolean);
      if (lines.length >= 3) break;
    }
    if (lines.length < 2) continue;
    seen.add(href);
    const name = lines[0].replace(/[^A-Za-z0-9)]*\s*(1st|2nd|3rd)\+?\s*$/, '').replace(/[^A-Za-z0-9).]+$/, '').trim();
    let headline = '';
    for (let i = 1; i < lines.length; i++) {
      if (degree.test(lines[i]) || lines[i] === name) continue;
      headline = lines[i]; break;
    }
    const deg = (lines.find(l => degree.test(l)) || '').replace(/^[^A-Za-z0-9]*/, '');
    out.push({href, name, headline, degree: deg});
  }
  return out;
}"""

# ---------- profile page ----------
# 2026 UI: no <h1>; name from document.title; degree shown as "\u00b7 3rd" text.
PROFILE_READY = [
    "main button:has(span:text-is('More'))",
    "main button[aria-label^='Invite']",
    "main button[aria-label^='Follow']",
    "main button[aria-label^='Message']",
    "main a:has-text('Message')",
    "main h1",
]
PROFILE_NAME = ["main h1", ".pv-top-card h1"]
PROFILE_TOPCARD_JS = r"""() => {
  const vis = e => e.getClientRects().length > 0;
  const main = document.querySelector('main') || document.body;
  const degree = /^[^A-Za-z0-9]*(1st|2nd|3rd)\+?$/;
  let deg = '';
  for (const e of main.querySelectorAll('p, span, div')) {
    if (e.children.length === 0 && vis(e) && degree.test((e.innerText || '').trim())) { deg = e.innerText.trim().replace(/^[^A-Za-z0-9]*/, ''); break; }
  }
  const lines = (main.innerText || '').split('\n').map(x => x.trim()).filter(Boolean).slice(0, 12);
  return {degree: deg, lines};
}"""
PROFILE_CONNECT_BUTTON = [
    "main button[aria-label^='Invite'][aria-label*='connect' i]",
    "main .pv-top-card-v2-ctas button:has(span:text-is('Connect'))",
]
PROFILE_PENDING_BUTTON = [
    "main button[aria-label*='Pending']",
    "main button:has-text('Pending')",
]
PROFILE_MORE_BUTTON = [
    "main button[aria-label='More actions']",
    "main button:has(span:text-is('More'))",
    "main button:has-text('More')",
]
PROFILE_MORE_CONNECT_ITEM = [
    "[role='menuitem']:has-text('Connect')",
    "[role='menu'] a:has-text('Connect')",
    ".artdeco-dropdown__content div[aria-label^='Invite'][aria-label*='connect' i]",
    "div[role='dialog'] div[role='button']:has-text('Connect')",
]
PROFILE_MORE_MENU = ["[role='menu']", ".artdeco-dropdown__content"]

# connect dialog
# 2026 UI: rendered inside a shadow root as div[role=dialog]; Playwright's CSS
# engine pierces shadow DOM so these page-level selectors still work.
CONNECT_DIALOG = [
    "[role='dialog']:has(button[aria-label='Send without a note'])",
    "[role='dialog']:has(button[aria-label='Add a note'])",
    "[role='dialog']:has(button[aria-label='Send invitation'])",
    "[role='dialog']:has(textarea#custom-message)",
    "[role='dialog']:has(button[aria-label='Send now'])",
    "div.send-invite",
]
CONNECT_ADD_NOTE = [
    "button[aria-label='Add a note']",
    "div[role='dialog'] button:has(span:text-is('Add a note'))",
]
CONNECT_NOTE_TEXTAREA = [
    "textarea#custom-message",
    "textarea[name='message']",
    "div[role='dialog'] textarea",
]
CONNECT_SEND = [
    "button[aria-label='Send invitation']",
    "button[aria-label='Send now']",
    "div[role='dialog'] button:has(span:text-is('Send'))",
    "div[role='dialog'] button.artdeco-button--primary:has-text('Send')",
]
CONNECT_SEND_WITHOUT_NOTE = [
    "button[aria-label='Send without a note']",
    "div[role='dialog'] button:has(span:text-is('Send without a note'))",
]
CONNECT_EMAIL_REQUIRED = [
    "div[role='dialog'] input[type='email']",
    "div[role='dialog'] label:has-text('email')",
]
CONNECT_NOTE_LIMIT_MARKERS = [
    "text=/No free personalized invitations left/i",
    "text=/you've reached the limit/i",
    "text=/limit of personalized invitations/i",
    "text=/Premium/i",
]
CONNECT_DIALOG_DISMISS = [
    "[role='dialog'] button[aria-label='Dismiss']",
    "[role='dialog'] button.artdeco-modal__dismiss",
]
INVITATION_SENT_TOAST = [
    ".artdeco-toast-item:has-text('Invitation sent')",
    "text=/Invitation sent/i",
    "text=/invitation has been sent/i",
    "main button:has-text('Pending')",
]
INVITATION_LIMIT_MARKERS = [
    "text=/You've reached the weekly invitation limit/i",
    "text=/weekly invitation limit/i",
    "text=/reached the weekly limit/i",
]
