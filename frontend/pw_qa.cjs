// QA walkthrough — node pw_qa.cjs
// Requires Vite dev server on http://localhost:3000
'use strict';
const { chromium } = require('playwright');
const { execSync }  = require('child_process');
const fs            = require('fs');

const OUT = 'C:/qa_shots';
execSync(`mkdir "${OUT}" 2>nul || true`, { shell: 'cmd.exe' });

const MOCKS = {
  ADMIN:   { id:'u1', email:'admin@s.edu',  role:'ADMIN',   full_name:'Admin User',   schema_name:'t_smoke', first_login:false },
  DEAN:    { id:'u2', email:'dean@s.edu',   role:'DEAN',    full_name:'Prof. Dean',   schema_name:'t_smoke', first_login:false },
  FACULTY: { id:'u3', email:'fac@s.edu',    role:'FACULTY', full_name:'Dr. Smith',    schema_name:'t_smoke', first_login:false },
  STUDENT: { id:'u4', email:'stu@s.edu',    role:'STUDENT', full_name:'Alice J',      schema_name:'t_smoke', first_login:false },
  BOARD:   { id:'u5', email:'board@s.edu',  role:'BOARD',   full_name:'Board Member', schema_name:'t_smoke', first_login:false },
  GUIDE:   { id:'u6', email:'guide@s.edu',  role:'GUIDE',   full_name:'Dr. Guide',    schema_name:'t_smoke', first_login:false },
};

// ── helpers ──────────────────────────────────────────────────────────────────

async function openPage(role, vp = { width: 1280, height: 800 }, extra = []) {
  const browser = await chromium.launch();
  const ctx     = await browser.newContext();
  const page    = await ctx.newPage();
  await page.setViewportSize(vp);

  await page.route('http://localhost:3000/api/auth/me', r =>
    r.fulfill({ status:200, contentType:'application/json', body: JSON.stringify(MOCKS[role]) }));
  await page.route(/localhost:3000\/api\/notifications/, r =>
    r.fulfill({ status:200, contentType:'application/json',
      body: JSON.stringify({ items:[], total:0, unread_count:0 }) }));

  for (const { pat, body } of extra) {
    await page.route(pat, r =>
      r.fulfill({ status:200, contentType:'application/json', body: JSON.stringify(body) }));
  }

  await ctx.addInitScript(r => {
    localStorage.setItem('vidya_token', 'mocked-token');
    localStorage.setItem('vidya_tenant_slug', 'smoke');
    localStorage.setItem('vidya_role', r);
  }, role);

  return { browser, page };
}

async function snap(page, url, file, ms = 800) {
  await page.goto('http://localhost:3000' + url, { waitUntil:'networkidle' });
  await page.waitForTimeout(ms);
  await page.screenshot({ path: `${OUT}/${file}` });
  console.log('  ✓', url, '->', file);
}

// ── 1. RBAC dashboards ───────────────────────────────────────────────────────

async function rbacDashboards() {
  console.log('\n=== 1. RBAC dashboards ===');
  for (const role of ['ADMIN','DEAN','FACULTY','STUDENT','BOARD','GUIDE']) {
    const { browser, page } = await openPage(role);
    await snap(page, '/dashboard', `rbac_${role.toLowerCase()}.png`);
    await browser.close();
  }
}

// ── 2. RBAC blocked routes ───────────────────────────────────────────────────

async function rbacBlocked() {
  console.log('\n=== 2. RBAC blocked routes ===');
  // FACULTY → /users  (ADMIN only)
  { const { browser, page } = await openPage('FACULTY');
    await snap(page, '/users', 'rbac_blocked_faculty_users.png');
    await browser.close(); }

  // STUDENT → /programs  (ADMIN/DEAN/FACULTY only)
  { const { browser, page } = await openPage('STUDENT');
    await snap(page, '/programs', 'rbac_blocked_student_programs.png');
    await browser.close(); }

  // BOARD → /labs  (FACULTY/ADMIN only)
  { const { browser, page } = await openPage('BOARD');
    await snap(page, '/labs', 'rbac_blocked_board_labs.png');
    await browser.close(); }
}

// ── 3. Mobile ────────────────────────────────────────────────────────────────

async function mobile() {
  console.log('\n=== 3. Mobile (375×812) ===');
  const vp = { width:375, height:812 };

  { const { browser, page } = await openPage('ADMIN', vp);
    await snap(page, '/dashboard', 'mobile_dashboard.png');
    // open sidebar via hamburger
    await page.click('[aria-label="Open navigation"]');
    await page.waitForTimeout(400);
    await page.screenshot({ path: `${OUT}/mobile_sidebar_open.png` });
    console.log('  ✓ mobile sidebar open');
    await browser.close(); }

  // login page at mobile
  { const browser = await chromium.launch();
    const page    = await browser.newPage();
    await page.setViewportSize(vp);
    await page.goto('http://localhost:3000/login', { waitUntil:'networkidle' });
    await page.waitForTimeout(400);
    await page.screenshot({ path: `${OUT}/mobile_login.png` });
    console.log('  ✓ mobile_login.png');
    await browser.close(); }

  // forgot-password at mobile
  { const browser = await chromium.launch();
    const page    = await browser.newPage();
    await page.setViewportSize(vp);
    await page.goto('http://localhost:3000/forgot-password', { waitUntil:'networkidle' });
    await page.waitForTimeout(400);
    await page.screenshot({ path: `${OUT}/mobile_forgot.png` });
    console.log('  ✓ mobile_forgot.png');
    await browser.close(); }
}

// ── 4. Async AI generating banner ────────────────────────────────────────────

async function asyncBanner() {
  console.log('\n=== 4. Async generating banner ===');
  // AIGeneratingBanner lives in SyllabusDetailPage (API base is /syllabi, not /syllabuses)
  const syl = { id:'s1', course_id:'c1', version:1, status:'AI_GENERATING',
    change_note:'', created_at: new Date().toISOString() };

  const { browser, page } = await openPage('FACULTY', { width:1280, height:800 }, [
    { pat: /localhost:3000\/api\/syllabi\/s1$/, body: syl },
    { pat: /localhost:3000\/api\/syllabi\/s1\/outcomes/, body: [] },
    { pat: /localhost:3000\/api\/syllabi\/s1\/units/, body: [] },
    { pat: /localhost:3000\/api\/syllabi\/s1\/references/, body: [] },
  ]);
  await snap(page, '/syllabuses/s1', 'async_generating_banner.png', 1500);
  await browser.close();
}

// ── 5. AI failure state ──────────────────────────────────────────────────────

async function aiFailure() {
  console.log('\n=== 5. AI failure (DRAFT after failed generation) ===');
  // SyllabusDetailPage shows AIGeneratingBanner with failed=true when
  // status transitions from AI_GENERATING → DRAFT with no outcomes/units.
  // We show the DRAFT empty state; generationFailed requires wasGenerating=true
  // in session state which can't be set from a fresh page load mock.
  const syl = {
    id:'s1', course_id:'c1', version:1, status:'DRAFT',
    change_note:'', created_at: new Date().toISOString(),
  };

  const { browser, page } = await openPage('FACULTY', { width:1280, height:800 }, [
    { pat: /localhost:3000\/api\/syllabi\/s1$/, body: syl },
    { pat: /localhost:3000\/api\/syllabi\/s1\/outcomes/, body: [] },
    { pat: /localhost:3000\/api\/syllabi\/s1\/units/, body: [] },
    { pat: /localhost:3000\/api\/syllabi\/s1\/references/, body: [] },
  ]);
  await snap(page, '/syllabuses/s1', 'ai_syllabus_draft.png', 1200);
  await browser.close();
}

// ── 6. Onboarding first-login redirect ──────────────────────────────────────

async function onboarding() {
  console.log('\n=== 6. Onboarding — first_login=true redirect ===');
  const browser = await chromium.launch();
  const ctx     = await browser.newContext();
  const page    = await ctx.newPage();
  await page.setViewportSize({ width:1280, height:800 });

  await page.route('http://localhost:3000/api/auth/me', r =>
    r.fulfill({ status:200, contentType:'application/json', body: JSON.stringify(
      { id:'u1', email:'newadmin@s.edu', role:'ADMIN', full_name:'New Admin',
        schema_name:'t_smoke', first_login:true }
    )}));
  await page.route(/localhost:3000\/api\/notifications/, r =>
    r.fulfill({ status:200, contentType:'application/json',
      body: JSON.stringify({ items:[], total:0, unread_count:0 }) }));
  await ctx.addInitScript(() => {
    localStorage.setItem('vidya_token','mocked-token');
    localStorage.setItem('vidya_tenant_slug','smoke');
    localStorage.setItem('vidya_role','ADMIN');
  });

  await page.goto('http://localhost:3000/dashboard', { waitUntil:'networkidle' });
  await page.waitForTimeout(800);
  await page.screenshot({ path: `${OUT}/onboarding_first_login_redirect.png` });
  console.log('  ✓ first-login redirect, url =', page.url());
  await browser.close();
}

// ── 7. Notifications drawer ──────────────────────────────────────────────────

async function notifications() {
  console.log('\n=== 7. Notifications drawer ===');
  const items = [
    { id:'n1', title:'Program ready', body:'B.E. CS generated.', is_read:false, created_at: new Date(Date.now()-60000).toISOString() },
    { id:'n2', title:'Syllabus approved', body:'CO-PO locked MAT101.', is_read:false, created_at: new Date(Date.now()-3600000).toISOString() },
    { id:'n3', title:'Lab submitted', body:'Alice submitted Lab 2.', is_read:true, created_at: new Date(Date.now()-86400000).toISOString() },
  ];

  const browser = await chromium.launch();
  const ctx     = await browser.newContext();
  const page    = await ctx.newPage();
  await page.setViewportSize({ width:1280, height:800 });

  await page.route('http://localhost:3000/api/auth/me', r =>
    r.fulfill({ status:200, contentType:'application/json', body: JSON.stringify(MOCKS['ADMIN']) }));
  await page.route(/localhost:3000\/api\/notifications/, r =>
    r.fulfill({ status:200, contentType:'application/json',
      body: JSON.stringify({ items, total:3, unread_count:2 }) }));
  await ctx.addInitScript(() => {
    localStorage.setItem('vidya_token','mocked-token');
    localStorage.setItem('vidya_tenant_slug','smoke');
    localStorage.setItem('vidya_role','ADMIN');
  });

  await page.goto('http://localhost:3000/dashboard', { waitUntil:'networkidle' });
  await page.waitForTimeout(800);
  await page.screenshot({ path: `${OUT}/notif_badge.png` });
  console.log('  ✓ notif_badge.png');

  await page.click('[aria-label="Notifications"]');
  await page.waitForTimeout(500);
  await page.screenshot({ path: `${OUT}/notif_drawer.png` });
  console.log('  ✓ notif_drawer.png');

  await browser.close();
}

// ── main ─────────────────────────────────────────────────────────────────────

(async () => {
  await rbacDashboards();
  await rbacBlocked();
  await mobile();
  await asyncBanner();
  await aiFailure();
  await onboarding();
  await notifications();
  console.log('\nAll QA shots complete. Output:', OUT);
})().catch(err => { console.error(err); process.exit(1); });
