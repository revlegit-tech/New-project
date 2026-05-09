const { test, expect } = require('@playwright/test');

const statusPayload = {
  status: 'ok',
  productState: 'research_mode',
  productStateDetail: { label: 'Research Mode' },
  latestBoardDate: '2026-05-08',
  dataConfidence: 'Good',
  productionEligibleMarkets: ['batter_hits', 'pitcher_strikeouts'],
  playerboard: { latestAvailableDate: '2026-05-08', schemaVersion: 'playerboard.v3', dataConfidence: 'Good' },
  grading: { state: 'partial' },
};

const rows = [
  {
    id: 'row-judge-hits',
    date: '2026-05-08',
    player: 'Aaron Judge',
    team: 'NYY',
    opponent: 'BAL',
    market: 'batter_hits',
    marketDisplay: 'Batter Hits',
    rawLabel: 'Over',
    line: 0.5,
    americanOdds: -135,
    modelProbability: 0.68,
    impliedProbability: 0.57,
    finalEdgePercent: 11.2,
    readinessLabel: 'Production ready',
  },
  {
    id: 'row-ohtani-ks',
    date: '2026-05-08',
    player: 'Shohei Ohtani',
    team: 'LAD',
    opponent: 'SF',
    market: 'pitcher_strikeouts',
    marketDisplay: 'Pitcher Strikeouts',
    rawLabel: 'Over',
    line: 5.5,
    americanOdds: 105,
    modelProbability: 0.54,
    impliedProbability: 0.49,
    finalEdgePercent: 5.1,
    readinessLabel: 'Research only',
  },
];

async function mockApis(page, overrides = {}) {
  let exposure = { activePickCount: 0, totalStakeUnits: 0, warnings: [] };
  await page.route('**/api/app/status', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(overrides.status || statusPayload) }));
  await page.route('**/api/edge-board**', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ status: 'ok', rows, source: { label: 'mock EdgeBoard' }, filters: {}, summary: {} }) }));
  await page.route('**/api/exposure/summary', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ status: 'ok', exposure }) }));
  await page.route('**/api/my-picks', async (route) => {
    if (route.request().method() === 'POST') {
      const body = route.request().postDataJSON();
      exposure = { activePickCount: 1, totalStakeUnits: 0, warnings: [] };
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ status: 'ok', pick: { ...body, stakeUnits: 0 }, exposure }) });
    } else {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ status: 'ok', picks: [], exposure }) });
    }
  });
}

test('Outlier board loads, filters rows, and opens detail rail', async ({ page }) => {
  await mockApis(page);
  await page.goto('/');
  await expect(page.locator('#outlierApp')).toBeVisible();
  await expect(page.locator('#boardHost')).toContainText('Aaron Judge');
  await expect(page.locator('#boardHost')).toContainText('Shohei Ohtani');

  await page.locator('#playerFilter').fill('Judge');
  await expect(page.locator('#boardHost')).toContainText('Aaron Judge');
  await expect(page.locator('#boardHost')).not.toContainText('Shohei Ohtani');

  await page.getByText('Aaron Judge').click();
  await expect(page.locator('#detailRail')).toContainText('Batter Hits');
  await expect(page.locator('#detailRail')).toContainText('Add research pick');
});

test('research-only pick save defaults to 0 units and refreshes exposure copy', async ({ page }) => {
  await mockApis(page);
  await page.goto('/');
  await page.getByText('Aaron Judge').click();
  await page.getByRole('button', { name: 'Add research pick' }).click();
  await expect(page.locator('#savePickStatus')).toContainText('0u research pick');
  await expect(page.locator('#exposureSummary')).toContainText('0.00u active exposure');
  await expect(page.locator('.ob-toast')).toContainText('Pick saved');
});

test('stale data warning is visible in the trust surface', async ({ page }) => {
  await mockApis(page, { status: { ...statusPayload, dataConfidence: 'Stale', staleDataSeverity: 'stale', playerboard: { ...statusPayload.playerboard, dataConfidence: 'Stale' } } });
  await page.goto('/');
  await expect(page.locator('#freshnessSurface')).toContainText('Stale');
  await expect(page.locator('#freshnessSurface')).toContainText('Do not trust for live betting');
});
