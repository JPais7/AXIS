import { test, expect } from '@playwright/test';

const project = '/projects/AXIS-DD-ERAP1-CURATED-001';
for (const width of [1440, 1024]) {
  test(`computational campaign workspace ${width}`, async ({ page }) => {
    await page.setViewportSize({ width, height: 1000 });
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    const shot = async name => page.screenshot({ path: `test-results/campaign-${width}-${name}.png`, fullPage: true });
    await page.goto(`${project}/campaigns`);
    await expect(page.getByRole('heading', { name: 'Computational Campaigns', level: 1 })).toBeVisible();
    const main = page.locator('main, #main').first();
    await expect(main).toContainText('Computational prioritization for experimental validation');
    await expect(main).toContainText('Campaign question');
    await expect(main).toContainText('Structural context');
    await expect(main).toContainText('Known experimental chemistry');
    await expect(main).toContainText('Why this molecule?');
    await expect(main).toContainText('there is no total');
    await expect(main).toContainText('no predicted pose');
    await expect(main).toContainText('requires experimental validation');
    await shot('1-erap1-campaign');
    await expect(page.locator('.badge.proposal').first()).toContainText('PREDICTED');
    expect(errors).toEqual([]);
  });
}
