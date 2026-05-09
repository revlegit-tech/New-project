const { test, expect } = require('@playwright/test');

test('trust surface rejects unsafe API message without executing HTML', async ({ page }) => {
  let dialogFired = false;
  page.on('dialog', async (dialog) => {
    dialogFired = true;
    await dialog.dismiss();
  });

  await page.route('**/api/app/status**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        status: 'ok',
        productState: 'research_mode',
        productStateDetail: {
          state: 'research_mode',
          label: 'Research <Only>',
          message: '<script>alert(1)</script>',
        },
        latestBoardDate: '2026-05-07',
        dataConfidence: 'Missing',
        productionEligibleMarkets: [],
        grading: { state: 'not_started' },
        warnings: ['<img src=x onerror=alert(1)>'],
      }),
    });
  });

  await page.goto('/legacy.html');

  await expect(page.locator('#trustSurfaceBanner')).toContainText('Malformed status payload');
  await expect(page.locator('img[src="x"]')).toHaveCount(0);
  expect(dialogFired).toBeFalsy();
});
