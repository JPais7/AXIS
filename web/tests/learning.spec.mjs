import { test, expect } from '@playwright/test';

const project = '/projects/AXIS-DD-ERAP1-CURATED-001';
for (const width of [1440, 1024]) {
  test(`chemical learning workspace ${width}`, async ({ page }) => {
    await page.setViewportSize({ width, height: 1000 });
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.goto(`${project}/learning`);
    await expect(page.getByRole('heading', { name: 'Chemical Learning', level: 1 })).toBeVisible();
    const main = page.locator('main, #main').first();
    await expect(main).toContainText('What has been measured?');
    await expect(main).toContainText('What is directly comparable?');
    await expect(main).toContainText('OBSERVED SAR');
    await expect(main).toContainText('MODEL NOT BUILT');
    await expect(main).toContainText('Insufficient data for a defensible predictive model');
    await expect(main).toContainText('SAR ONLY');
    await page.screenshot({ path: `test-results/learning-${width}-erap1.png`, fullPage: true });
    expect(errors).toEqual([]);
  });
}

test('synthetic full loop is labelled and shows model, prediction boundaries and next compounds', async ({ page }) => {
  test.skip(process.env.AXIS_LEARNING_DEMO !== 'synthetic', 'needs the separate synthetic demo database');
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto(`${project}/learning`);
  await page.getByRole('link', { name: /SYN-SUBSTRATE-1/ }).last().click();
  const main = page.locator('main, #main').first();
  await expect(main).toContainText('SYNTHETIC / TEST ONLY / NOT SCIENTIFIC EVIDENCE');
  await expect(main).toContainText('INFERRED — not an observation');
  await expect(main).toContainText('there is no model score');
  await expect(main).toContainText('Which compound should we test next, and why?');
  await expect(main).toContainText('availability was not assessed');
  await page.screenshot({ path: 'test-results/learning-1440-synthetic.png', fullPage: true });
});
