const { test, expect } = require('@playwright/test');

test('homepage serves the Outlier production shell and legacy tools are isolated', async ({ page, request }) => {
  const status = await request.get('/api/app/status');
  expect(status.ok()).toBeTruthy();
  const body = await status.json();
  expect(body.status).toBe('ok');
  expect(body.productState).toBe('research_mode');

  await page.goto('/');
  await expect(page.locator('#outlierApp')).toBeVisible();
  await expect(page.getByRole('heading', { name: /MLB betting research board/i })).toBeVisible();
  await expect(page.locator('#freshnessSurface')).toBeVisible();
  await expect(page.locator('body')).not.toContainText('Data manager');

  await page.goto('/legacy.html');
  await expect(page.locator('#trustSurfaceBanner')).toBeVisible();
  await expect(page.locator('#playerControl')).toBeVisible();
});

test('unknown API routes return safe JSON 404', async ({ request }) => {
  const response = await request.get('/api/does-not-exist');
  expect(response.status()).toBe(404);
  await expect(response).toHaveHeader(/content-type/i, /application\/json/);
  const body = await response.json();
  expect(body.code).toBe('not_found');
});


test('edge-board API returns bettor-facing rows contract', async ({ request }) => {
  const response = await request.get('/api/edge-board?season=2026&limit=5');
  expect(response.ok()).toBeTruthy();
  const body = await response.json();
  expect(body.status).toBe('ok');
  expect(Array.isArray(body.rows)).toBeTruthy();
  expect(body.summary).toBeDefined();
  expect(body.filters).toBeDefined();
});


test('my-picks API enforces action header and returns exposure contract', async ({ request }) => {
  const listResponse = await request.get('/api/my-picks');
  expect(listResponse.ok()).toBeTruthy();
  const listBody = await listResponse.json();
  expect(listBody.policy.separateFromModelBacktests).toBeTruthy();
  expect(listBody.exposure).toBeDefined();

  const denied = await request.post('/api/my-picks', {
    data: { player: 'No Header', team: 'NYY', opponent: 'BAL', market: 'batter_hits' },
  });
  expect(denied.status()).toBe(403);

  const saved = await request.post('/api/my-picks', {
    headers: { 'X-Baseball-Prop-Action': '1' },
    data: {
      date: '2026-05-07',
      player: 'Aaron Judge',
      team: 'NYY',
      opponent: 'BAL',
      market: 'batter_hits',
      decisionLabel: 'Watchlist',
      readinessLabel: 'Research only',
      suggestedStake: 'Research only',
      stakeUnits: 1,
    },
  });
  expect(saved.ok()).toBeTruthy();
  const savedBody = await saved.json();
  expect(savedBody.pick.stakeUnits).toBe(0);
});


test('prop-detail API returns drilldown contract', async ({ request }) => {
  const response = await request.get('/api/prop-detail?market=batter_hits&player=Smoke%20Player&team=NYY&opponent=BAL&line=0.5&americanOdds=-110');
  expect(response.ok()).toBeTruthy();
  const body = await response.json();
  expect(body.status).toBe('ok');
  expect(body.detail.overview.player).toBe('Smoke Player');
  expect(body.detail.priceComparison).toBeDefined();
  expect(body.detail.modelExplanation).toBeDefined();
  expect(body.detail.riskContext).toBeDefined();
  expect(body.detail.tracking.separateFromModelBacktests).toBeTruthy();
});


test('legacy data health dashboard shell is available', async ({ page }) => {
  await page.goto('/legacy.html');
  await page.getByRole('link', { name: 'Data Health' }).click();
  await expect(page.getByText('Data Confidence Dashboard')).toBeVisible();
  await expect(page.getByText('Daily workflow state machine')).toBeVisible();
});
